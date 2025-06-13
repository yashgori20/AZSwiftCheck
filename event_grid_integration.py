from azure.eventgrid import EventGridPublisherClient, EventGridEvent
from azure.core.credentials import AzureKeyCredential
import os
from datetime import datetime
import json

class WorkingEventGridHandler:
    def __init__(self):
        # Use environment variables set by Container App
        self.endpoint = os.getenv("EVENT_GRID_ENDPOINT") or "https://swiftcheck-events.centralus-1.eventgrid.azure.net/api/events"
        self.key = os.getenv("EVENT_GRID_KEY") or "6QsTE1f2D3oANdwwMOgL57x7e9cxBEPMpuAbQOmpOQsAtiq8XGMgJQQJ99BFAC1i4TkXJ3w3AAABAZEGhQJS"
        
        try:
            self.client = EventGridPublisherClient(
                self.endpoint,
                AzureKeyCredential(self.key)
            )
            print("? Event Grid client initialized successfully")
        except Exception as e:
            print(f"? Event Grid initialization failed: {e}")
            self.client = None
    
    def send_template_generated_event(self, request_id, product_name, parameters_count):
        """Send QC template generated event"""
        if not self.client:
            print("?? Event Grid client not available")
            return False
        
        try:
            event = EventGridEvent(
                event_type="SwiftCheck.QCTemplateGenerated",
                subject=f"templates/{request_id}",
                data={
                    "request_id": request_id,
                    "product_name": product_name,
                    "parameters_count": parameters_count,
                    "generated_at": datetime.now().isoformat(),
                    "status": "completed"
                },
                data_version="1.0"
            )
            
            self.client.send([event])
            print(f"? Sent QC template event for {product_name} ({parameters_count} parameters)")
            return True
            
        except Exception as e:
            print(f"? Error sending template event: {e}")
            return False
    
    def send_file_upload_event(self, blob_name, request_id, metadata):
        """Send file upload event"""
        if not self.client:
            print("?? Event Grid client not available")
            return False
        
        try:
            event = EventGridEvent(
                event_type="SwiftCheck.DocumentUploaded",
                subject=f"documents/{blob_name}",
                data={
                    "blob_name": blob_name,
                    "request_id": request_id,
                    "uploaded_at": datetime.now().isoformat(),
                    "metadata": metadata,
                    "status": "uploaded"
                },
                data_version="1.0"
            )
            
            self.client.send([event])
            print(f"? Sent file upload event for {blob_name}")
            return True
            
        except Exception as e:
            print(f"? Error sending upload event: {e}")
            return False
    
    def send_workflow_event(self, event_type, workflow_id, stage, tenant_id="default"):
        """Send workflow approval event"""
        if not self.client:
            print("?? Event Grid client not available")
            return False
        
        try:
            event = EventGridEvent(
                event_type=f"SwiftCheck.{event_type}",
                subject=f"workflows/{workflow_id}",
                data={
                    "workflow_id": workflow_id,
                    "stage": stage,
                    "tenant_id": tenant_id,
                    "timestamp": datetime.now().isoformat()
                },
                data_version="1.0"
            )
            
            self.client.send([event])
            print(f"? Sent workflow event: {event_type} for {workflow_id}")
            return True
            
        except Exception as e:
            print(f"? Error sending workflow event: {e}")
            return False

# Global instance
working_event_handler = WorkingEventGridHandler()
