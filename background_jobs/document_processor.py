import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from azure.eventgrid import EventGridPublisherClient, EventGridEvent
from azure.core.credentials import AzureKeyCredential

# Add parent directory to path so we can import our modules
sys.path.append('/app')

from azure_secrets import get_blob_connection, azure_secrets
from azure_document_intelligence import azure_doc_intelligence
from simple_search_indexer import SimpleSearchIndexer

from cosmos_db_utils import enhanced_cosmos_db

class DocumentProcessorJob:
    def __init__(self):
        # Initialize services
        blob_connection = get_blob_connection()
        self.blob_client = BlobServiceClient.from_connection_string(blob_connection)
        
        # Event Grid for notifications
        try:
            event_grid_endpoint = azure_secrets.get_secret("event-grid-endpoint")
            event_grid_key = azure_secrets.get_secret("event-grid-key")
            self.event_client = EventGridPublisherClient(
                event_grid_endpoint,
                AzureKeyCredential(event_grid_key)
            )
        except Exception as e:
            print(f"⚠️ Event Grid not configured: {e}")
            self.event_client = None
        
        # Search indexer for adding to search
        self.search_indexer = SimpleSearchIndexer()
        
        print("✅ Document Processor Job initialized")
    
    async def process_document(self, blob_url, container_name, blob_name, request_id=None):
        """Process a single document through the pipeline"""
        print(f"🔄 Processing document: {blob_name}")
        
        try:
            # Step 1: Download blob to temp file
            temp_file = await self.download_blob(container_name, blob_name)
            
            # Step 2: Extract text using Document Intelligence
            extracted_data = azure_doc_intelligence.analyze_document(temp_file)
            
            # Step 3: Extract metadata
            metadata = azure_doc_intelligence.extract_enhanced_metadata(
                extracted_data["text"], 
                blob_name
            )
            
            # Step 4: Create search document
            search_doc = self.create_search_document(
                extracted_data, metadata, blob_url, blob_name
            )
            
            # Step 5: Upload to search index
            self.search_indexer.upload_documents([search_doc])
            
            # Step 6: Update request status if provided
            if request_id:
                await self.update_request_status(request_id, "processed", metadata)
            
            # Step 7: Send completion event
            await self.send_completion_event(blob_name, request_id, metadata)
            
            # Cleanup
            os.unlink(temp_file)
            
            print(f"✅ Successfully processed: {blob_name}")
            return {"status": "success", "metadata": metadata}
            
        except Exception as e:
            print(f"❌ Error processing {blob_name}: {e}")
            
            # Update request status with error
            if request_id:
                await self.update_request_status(request_id, "error", {"error": str(e)})
            
            # Send error event
            await self.send_error_event(blob_name, request_id, str(e))
            
            return {"status": "error", "error": str(e)}
    
    async def download_blob(self, container_name, blob_name):
        """Download blob to temporary file"""
        blob_client = self.blob_client.get_blob_client(
            container=container_name, 
            blob=blob_name
        )
        
        # Create temp file
        temp_dir = "/tmp"
        os.makedirs(temp_dir, exist_ok=True)
        temp_file = os.path.join(temp_dir, f"processing_{blob_name}")
        
        # Download
        with open(temp_file, "wb") as f:
            blob_data = blob_client.download_blob()
            f.write(blob_data.readall())
        
        return temp_file
    
    def create_search_document(self, extracted_data, metadata, blob_url, blob_name):
        """Create document for search index"""
        from sentence_transformers import SentenceTransformer
        import uuid
        
        embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Create content for embedding
        content = extracted_data["text"][:2000]  # Limit for embedding
        embedding = embedder.encode(content).tolist()
        
        # Determine source type based on metadata
        if "samosa" in metadata["product_name"].lower():
            source_type = "checklist"
        elif "specification" in metadata["document_type"].lower():
            source_type = "product_spec"
        else:
            source_type = "regulatory"
        
        return {
            "id": str(uuid.uuid4()),
            "content": extracted_data["text"],
            "contentVector": embedding,
            "source_type": source_type,
            "filename": blob_name,
            "blob_url": blob_url,
            "product_name": metadata["product_name"],
            "supplier": metadata["supplier_name"],
            "document_type": metadata["document_type"],
            "tables_count": len(extracted_data.get("tables", [])),
            "sections_count": len(extracted_data.get("sections", [])),
            "processed_at": datetime.now().isoformat()
        }
    
    async def update_request_status(self, request_id, status, metadata):
        """Update QC request status in Cosmos DB"""
        try:
            # Get existing request
            query = "SELECT * FROM c WHERE c.id = @request_id"
            items = list(enhanced_cosmos_db.qc_requests.query_items(
                query=query,
                parameters=[{"name": "@request_id", "value": request_id}]
            ))
            
            if items:
                request_doc = items[0]
                request_doc["processing_status"] = status
                request_doc["processing_metadata"] = metadata
                request_doc["updated_at"] = datetime.now().isoformat()
                
                enhanced_cosmos_db.qc_requests.replace_item(
                    item=request_doc["id"], 
                    body=request_doc
                )
                
                print(f"✅ Updated request {request_id} status: {status}")
            
        except Exception as e:
            print(f"❌ Error updating request status: {e}")
    
    async def send_completion_event(self, blob_name, request_id, metadata):
        """Send completion event via Event Grid"""
        if not self.event_client:
            return
        
        try:
            event = EventGridEvent(
                event_type="SwiftCheck.DocumentProcessed",
                subject=f"documents/{blob_name}",
                data={
                    "blob_name": blob_name,
                    "request_id": request_id,
                    "product_name": metadata["product_name"],
                    "document_type": metadata["document_type"],
                    "processed_at": datetime.now().isoformat(),
                    "status": "completed"
                },
                data_version="1.0"
            )
            
            self.event_client.send([event])
            print(f"✅ Sent completion event for {blob_name}")
            
        except Exception as e:
            print(f"❌ Error sending event: {e}")
    
    async def send_error_event(self, blob_name, request_id, error_message):
        """Send error event via Event Grid"""
        if not self.event_client:
            return
        
        try:
            event = EventGridEvent(
                event_type="SwiftCheck.DocumentProcessingError",
                subject=f"documents/{blob_name}",
                data={
                    "blob_name": blob_name,
                    "request_id": request_id,
                    "error": error_message,
                    "failed_at": datetime.now().isoformat(),
                    "status": "error"
                },
                data_version="1.0"
            )
            
            self.event_client.send([event])
            print(f"✅ Sent error event for {blob_name}")
            
        except Exception as e:
            print(f"❌ Error sending error event: {e}")

# Entry point for Container Apps Job
async def main():
    """Main entry point for background job"""
    print("🚀 Starting Document Processor Job")
    
    # Get job parameters from environment
    blob_url = os.getenv("BLOB_URL")
    container_name = os.getenv("CONTAINER_NAME", "uploads")
    blob_name = os.getenv("BLOB_NAME")
    request_id = os.getenv("REQUEST_ID")
    
    if not blob_url or not blob_name:
        print("❌ Missing required environment variables: BLOB_URL, BLOB_NAME")
        sys.exit(1)
    
    # Process the document
    processor = DocumentProcessorJob()
    result = await processor.process_document(blob_url, container_name, blob_name, request_id)
    
    if result["status"] == "success":
        print(f"✅ Job completed successfully")
        sys.exit(0)
    else:
        print(f"❌ Job failed: {result['error']}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())