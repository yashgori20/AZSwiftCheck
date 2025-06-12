from cosmos_db_utils import enhanced_cosmos_db
from datetime import datetime
import uuid
import json

class AuditLogger:
    def __init__(self):
        self.container = enhanced_cosmos_db.database.get_container_client("audit_logs")
    
    def log_action(self, tenant_id, user_id, action_type, resource_type, resource_id, 
                   details=None, ip_address=None, user_agent=None):
        """Log audit event"""
        
        audit_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action_type": action_type,  # CREATE, READ, UPDATE, DELETE, APPROVE, REJECT
            "resource_type": resource_type,  # TEMPLATE, WORKFLOW, TENANT, USER
            "resource_id": resource_id,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "details": details or {},
            "severity": self.get_action_severity(action_type)
        }
        
        try:
            self.container.create_item(audit_entry)
            print(f"📝 Audit log: {action_type} {resource_type} by {user_id}")
        except Exception as e:
            print(f"❌ Audit logging failed: {e}")
    
    def get_action_severity(self, action_type):
        """Get severity level for action"""
        high_severity = ["DELETE", "REJECT", "SECURITY_VIOLATION"]
        medium_severity = ["CREATE", "UPDATE", "APPROVE"]
        
        if action_type in high_severity:
            return "HIGH"
        elif action_type in medium_severity:
            return "MEDIUM"
        else:
            return "LOW"
    
    def get_audit_trail(self, tenant_id, resource_id=None, days=30):
        """Get audit trail for resource or tenant"""
        try:
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            
            if resource_id:
                query = """
                    SELECT * FROM c 
                    WHERE c.tenant_id = @tenant_id 
                    AND c.resource_id = @resource_id
                    AND c.date >= @start_date
                    ORDER BY c.timestamp DESC
                """
                parameters = [
                    {"name": "@tenant_id", "value": tenant_id},
                    {"name": "@resource_id", "value": resource_id},
                    {"name": "@start_date", "value": start_date}
                ]
            else:
                query = """
                    SELECT * FROM c 
                    WHERE c.tenant_id = @tenant_id 
                    AND c.date >= @start_date
                    ORDER BY c.timestamp DESC
                """
                parameters = [
                    {"name": "@tenant_id", "value": tenant_id},
                    {"name": "@start_date", "value": start_date}
                ]
            
            return list(self.container.query_items(query=query, parameters=parameters))
            
        except Exception as e:
            print(f"❌ Error getting audit trail: {e}")
            return []

# Global instance
audit_logger = AuditLogger()