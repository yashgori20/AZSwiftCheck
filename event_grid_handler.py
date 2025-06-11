from azure.eventgrid import EventGridPublisherClient, EventGridEvent
from azure.core.credentials import AzureKeyCredential
from azure_secrets import azure_secrets
from datetime import datetime
import json

class EventGridHandler:

    def send_workflow_event(self, event_type, workflow_id, request_id, stage, tenant_id, additional_data=None):
        """Send workflow event"""
        if not self.client:
            print(f"📝 WORKFLOW EVENT (would send): {event_type} - Workflow: {workflow_id}, Stage: {stage}")
            return True
        
        try:
            from azure.eventgrid import EventGridEvent
            
            event_data = {
                "workflow_id": workflow_id,
                "request_id": request_id,
                "stage": stage,
                "tenant_id": tenant_id,
                "timestamp": datetime.now().isoformat()
            }
            
            if additional_data:
                event_data.update(additional_data)
            
            event = EventGridEvent(
                event_type=f"SwiftCheck.{event_type}",
                subject=f"workflows/{workflow_id}",
                data=event_data,
                data_version="1.0"
            )
            
            self.client.send([event])
            print(f"✅ Sent workflow event: {event_type} for {workflow_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending workflow event: {e}")
            return False    
    def __init__(self):
        try:
            endpoint = azure_secrets.get_secret("event-grid-endpoint")
            key = azure_secrets.get_secret("event-grid-key")
            
            if endpoint and key:
                self.client = EventGridPublisherClient(
                    endpoint,
                    AzureKeyCredential(key)
                )
                print("✅ Event Grid client initialized")
            else:
                self.client = None
                print("⚠️ Event Grid credentials not found")
                
        except Exception as e:
            self.client = None
            print(f"⚠️ Event Grid initialization failed: {e}")
    
    def send_document_uploaded_event(self, blob_name, request_id, metadata):
        """Send document uploaded event"""
        if not self.client:
            return False
        
        try:
            event = EventGridEvent(
                event_type="SwiftCheck.DocumentUploaded",
                subject=f"documents/{blob_name}",
                data={
                    "blob_name": blob_name,
                    "request_id": request_id,
                    "uploaded_at": datetime.now().isoformat(),
                    "metadata": metadata
                },
                data_version="1.0"
            )
            
            self.client.send([event])
            print(f"✅ Sent document uploaded event for {blob_name}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending upload event: {e}")
            return False
    
    def send_qc_template_generated_event(self, request_id, parameters_count, product_name):
        """Send QC template generated event"""
        if not self.client:
            return False
        
        try:
            event = EventGridEvent(
                event_type="SwiftCheck.QCTemplateGenerated",
                subject=f"templates/{request_id}",
                data={
                    "request_id": request_id,
                    "product_name": product_name,
                    "parameters_count": parameters_count,
                    "generated_at": datetime.now().isoformat()
                },
                data_version="1.0"
            )
            
            self.client.send([event])
            print(f"✅ Sent QC template generated event for {request_id}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending template event: {e}")
            return False

# Global instance
event_grid_handler = EventGridHandler()