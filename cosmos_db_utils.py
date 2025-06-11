from azure.cosmos import CosmosClient, exceptions
from azure_secrets import get_cosmos_connection
from datetime import datetime
import uuid
import json

class EnhancedCosmosDBManager:
    def __init__(self):
        connection_string = get_cosmos_connection()
        self.client = CosmosClient.from_connection_string(connection_string)
        self.database = self.client.get_database_client("swiftcheck")
        
        # Get containers
        self.qc_requests = self.database.get_container_client("qc_requests")
        self.parameters = self.database.get_container_client("parameters")
        self.templates = self.database.get_container_client("json_templates")
        self.responses = self.database.get_container_client("llm_responses")
    
    def create_qc_request(self, doc_type, product_name, supplier_name, user_message=None):
        """Create new QC request"""
        request_id = str(uuid.uuid4())
        
        doc = {
            "id": request_id,
            "doc_type": doc_type,
            "product_name": product_name,
            "supplier_name": supplier_name,
            "user_message": user_message,
            "status": "created",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        try:
            self.qc_requests.create_item(doc)
            print(f"✅ Created QC request: {request_id}")
            return request_id
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Error creating QC request: {e}")
            raise
    
    def save_llm_response(self, request_id, llm_response, summary_text):
        """Save LLM response"""
        doc = {
            "id": str(uuid.uuid4()),
            "request_id": request_id,
            "llm_response": llm_response,
            "summary_text": summary_text,
            "created_at": datetime.now().isoformat()
        }
        
        try:
            self.responses.create_item(doc)
            print(f"✅ Saved LLM response for request: {request_id}")
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Error saving LLM response: {e}")
            raise
    
    def save_parameters(self, request_id, parameters_list):
        """Save parameters for a request"""
        try:
            for i, param in enumerate(parameters_list):
                doc = {
                    "id": f"{request_id}-param-{i}",
                    "request_id": request_id,
                    "parameter_name": param.get("Parameter", ""),
                    "type": param.get("Type", ""),
                    "spec": param.get("Spec", ""),
                    "dropdown_options": param.get("DropdownOptions", ""),
                    "checklist_options": param.get("ChecklistOptions", ""),
                    "include_remarks": param.get("IncludeRemarks", "No"),
                    "section": param.get("Section", "General"),
                    "clause_reference": param.get("ClauseReference", ""),
                    "created_at": datetime.now().isoformat()
                }
                
                self.parameters.create_item(doc)
            
            print(f"✅ Saved {len(parameters_list)} parameters for request: {request_id}")
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Error saving parameters: {e}")
            raise
    
    def save_json_template(self, request_id, template_json):
        """Save JSON template"""
        doc = {
            "id": f"{request_id}-template",
            "request_id": request_id,
            "template_json": template_json,
            "created_at": datetime.now().isoformat()
        }
        
        try:
            self.templates.create_item(doc)
            print(f"✅ Saved JSON template for request: {request_id}")
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Error saving JSON template: {e}")
            raise
    
    def get_template_by_request_id(self, request_id):
        """Get template by request ID"""
        try:
            query = "SELECT * FROM c WHERE c.request_id = @request_id"
            items = list(self.templates.query_items(
                query=query,
                parameters=[{"name": "@request_id", "value": request_id}],
                enable_cross_partition_query=True
            ))
            
            if items:
                return items[0]["template_json"]
            return None
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Error getting template: {e}")
            return None
    
    def get_all_requests(self):
        """Get all QC requests with cross-partition enabled"""
        try:
            query = "SELECT * FROM c ORDER BY c.created_at DESC"
            return list(self.qc_requests.query_items(
                query=query,
                enable_cross_partition_query=True
            ))
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Error getting requests: {e}")
            return []
    
    def get_parameters_by_request_id(self, request_id):
        """Get parameters by request ID with cross-partition enabled"""
        try:
            query = "SELECT * FROM c WHERE c.request_id = @request_id"
            return list(self.parameters.query_items(
                query=query,
                parameters=[{"name": "@request_id", "value": request_id}],
                enable_cross_partition_query=True
            ))
        except exceptions.CosmosHttpResponseError as e:
            print(f"❌ Error getting parameters: {e}")
            return []

# Global instance
enhanced_cosmos_db = EnhancedCosmosDBManager()