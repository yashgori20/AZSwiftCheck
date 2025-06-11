from enum import Enum
from datetime import datetime, timedelta
from cosmos_db_utils import enhanced_cosmos_db
from event_grid_handler import event_grid_handler
import uuid
import json

class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class WorkflowStage(Enum):
    DRAFT = "draft"
    QC_REVIEW = "qc_review"
    MANAGER_APPROVAL = "manager_approval"
    FINAL_APPROVAL = "final_approval"
    PUBLISHED = "published"

class WorkflowEngine:
    def __init__(self):
        self.container = enhanced_cosmos_db.database.get_container_client("workflow_approvals")
        
    def create_approval_workflow(self, request_id, template_data, tenant_id="default"):
        """Create approval workflow for QC template"""
        workflow_id = str(uuid.uuid4())
        
        workflow_doc = {
            "id": workflow_id,
            "request_id": request_id,
            "tenant_id": tenant_id,
            "current_stage": WorkflowStage.QC_REVIEW.value,
            "status": ApprovalStatus.PENDING.value,
            "template_data": template_data,
            "approval_chain": [
                {
                    "stage": WorkflowStage.QC_REVIEW.value,
                    "approver_role": "QC Supervisor",
                    "approver_id": None,
                    "status": ApprovalStatus.PENDING.value,
                    "required": True,
                    "due_date": (datetime.now() + timedelta(hours=24)).isoformat()
                },
                {
                    "stage": WorkflowStage.MANAGER_APPROVAL.value,
                    "approver_role": "QC Manager", 
                    "approver_id": None,
                    "status": ApprovalStatus.PENDING.value,
                    "required": True,
                    "due_date": (datetime.now() + timedelta(hours=48)).isoformat()
                },
                {
                    "stage": WorkflowStage.FINAL_APPROVAL.value,
                    "approver_role": "Department Head",
                    "approver_id": None,
                    "status": ApprovalStatus.PENDING.value,
                    "required": False,
                    "due_date": (datetime.now() + timedelta(hours=72)).isoformat()
                }
            ],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        try:
            self.container.create_item(workflow_doc)
            
            # Send workflow started event
            event_grid_handler.send_workflow_event(
                "WorkflowStarted", workflow_id, request_id, 
                WorkflowStage.QC_REVIEW.value, tenant_id
            )
            
            print(f"✅ Created approval workflow: {workflow_id}")
            return workflow_id
            
        except Exception as e:
            print(f"❌ Error creating workflow: {e}")
            raise
    
    def submit_approval(self, workflow_id, approver_id, approver_role, decision, comments=""):
        """Submit approval decision"""
        try:
            # Get workflow
            workflow = self.container.read_item(item=workflow_id, partition_key=workflow_id)
            
            # Find current stage
            current_stage = workflow["current_stage"]
            approval_chain = workflow["approval_chain"]
            
            # Update current stage
            for stage in approval_chain:
                if stage["stage"] == current_stage:
                    stage["approver_id"] = approver_id
                    stage["status"] = decision
                    stage["comments"] = comments
                    stage["approved_at"] = datetime.now().isoformat()
                    break
            
            # Determine next stage
            if decision == ApprovalStatus.APPROVED.value:
                next_stage = self.get_next_stage(current_stage, approval_chain)
                if next_stage:
                    workflow["current_stage"] = next_stage
                else:
                    # All approvals complete
                    workflow["status"] = ApprovalStatus.APPROVED.value
                    workflow["current_stage"] = WorkflowStage.PUBLISHED.value
                    
                    # Publish the template
                    self.publish_template(workflow["request_id"], workflow["template_data"])
            
            elif decision == ApprovalStatus.REJECTED.value:
                workflow["status"] = ApprovalStatus.REJECTED.value
                workflow["rejected_by"] = approver_id
                workflow["rejection_reason"] = comments
            
            workflow["updated_at"] = datetime.now().isoformat()
            
            # Update in Cosmos DB
            self.container.replace_item(item=workflow_id, body=workflow)
            
            # Send event
            event_grid_handler.send_workflow_event(
                "ApprovalSubmitted", workflow_id, workflow["request_id"],
                workflow["current_stage"], workflow["tenant_id"],
                {"decision": decision, "approver": approver_role}
            )
            
            print(f"✅ Approval submitted: {workflow_id} - {decision}")
            return workflow
            
        except Exception as e:
            print(f"❌ Error submitting approval: {e}")
            raise
    
    def get_next_stage(self, current_stage, approval_chain):
        """Get next required stage in approval chain"""
        stage_order = [stage["stage"] for stage in approval_chain]
        
        try:
            current_index = stage_order.index(current_stage)
            
            # Find next required stage
            for i in range(current_index + 1, len(approval_chain)):
                if approval_chain[i]["required"]:
                    return approval_chain[i]["stage"]
            
            return None  # No more required stages
            
        except ValueError:
            return None
    
    def publish_template(self, request_id, template_data):
        """Publish approved template"""
        try:
            # Create published template record
            published_doc = {
                "id": f"published_{request_id}",
                "request_id": request_id,
                "template_data": template_data,
                "status": "published",
                "published_at": datetime.now().isoformat(),
                "version": "1.0"
            }
            
            published_container = enhanced_cosmos_db.database.get_container_client("published_templates")
            published_container.create_item(published_doc)
            
            print(f"✅ Template published: {request_id}")
            
        except Exception as e:
            print(f"❌ Error publishing template: {e}")
    
    def get_pending_approvals(self, approver_role, tenant_id="default"):
        """Get pending approvals for a role"""
        try:
            query = """
                SELECT * FROM c 
                WHERE c.tenant_id = @tenant_id 
                AND c.status = @status
                AND EXISTS(
                    SELECT VALUE stage FROM stage IN c.approval_chain 
                    WHERE stage.approver_role = @approver_role 
                    AND stage.status = @pending_status
                    AND stage.stage = c.current_stage
                )
            """
            
            items = list(self.container.query_items(
                query=query,
                parameters=[
                    {"name": "@tenant_id", "value": tenant_id},
                    {"name": "@status", "value": ApprovalStatus.PENDING.value},
                    {"name": "@approver_role", "value": approver_role},
                    {"name": "@pending_status", "value": ApprovalStatus.PENDING.value}
                ]
            ))
            
            return items
            
        except Exception as e:
            print(f"❌ Error getting pending approvals: {e}")
            return []

# Global instance
workflow_engine = WorkflowEngine()