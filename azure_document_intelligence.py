from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure_secrets import get_form_recognizer_config
from azure.storage.blob import BlobServiceClient
from azure_secrets import get_blob_connection
import tempfile
import uuid
from pathlib import Path
import json

class AzureDocumentIntelligence:
    def __init__(self):
        # Initialize Document Intelligence client
        config = get_form_recognizer_config()
        self.doc_client = DocumentAnalysisClient(
            endpoint=config["endpoint"],
            credential=AzureKeyCredential(config["key"])
        )
        
        # Initialize Blob Storage client
        blob_connection = get_blob_connection()
        self.blob_client = BlobServiceClient.from_connection_string(blob_connection)
        
        print("✅ Azure Document Intelligence initialized")
    
    def upload_to_blob(self, file_path, container_name="uploads"):
       """Upload file to blob storage and return URL"""
       try:
           # Generate unique blob name
           file_name = Path(file_path).name
           blob_name = f"{uuid.uuid4()}_{file_name}"
           
           # Get blob client
           blob_client = self.blob_client.get_blob_client(
               container=container_name, 
               blob=blob_name
           )
           
           # Upload file
           with open(file_path, "rb") as data:
               blob_client.upload_blob(data, overwrite=True)
           
           # Return blob URL
           blob_url = blob_client.url
           print(f"✅ Uploaded {file_name} to blob storage")
           return blob_url
           
       except Exception as e:
           print(f"❌ Blob upload error: {e}")
           raise
   
def analyze_document(self, file_path):
       """Analyze document using Azure Document Intelligence"""
       try:
           # Upload to blob first (Document Intelligence works better with URLs)
           blob_url = self.upload_to_blob(file_path)
           
           print(f"🔍 Analyzing document with Azure Document Intelligence...")
           
           # Start analysis
           poller = self.doc_client.begin_analyze_document_from_url(
               "prebuilt-layout",  # Use layout model for table detection
               blob_url
           )
           
           # Wait for completion
           result = poller.result()
           
           # Extract structured data
           extracted_data = self.extract_structured_content(result)
           
           print(f"✅ Document analysis complete - {len(extracted_data['text'])} characters extracted")
           return extracted_data
           
       except Exception as e:
           print(f"❌ Document Intelligence error: {e}")
           raise
   
def extract_structured_content(self, result):
       """Extract structured content from Document Intelligence result"""
       extracted_data = {
           "text": "",
           "tables": [],
           "sections": [],
           "metadata": {
               "pages": len(result.pages),
               "tables_count": len(result.tables),
               "paragraphs_count": len(result.paragraphs)
           }
       }
       
       # Extract text with structure preservation
       full_text = ""
       
       # Process pages
       for page_idx, page in enumerate(result.pages):
           full_text += f"\n=== PAGE {page_idx + 1} ===\n"
           
           # Process lines with layout information
           for line in page.lines:
               full_text += line.content + "\n"
       
       # Process tables separately for better structure
       for table_idx, table in enumerate(result.tables):
           table_data = {
               "table_id": table_idx,
               "rows": table.row_count,
               "columns": table.column_count,
               "content": []
           }
           
           # Extract table content
           table_text = f"\n\n## TABLE {table_idx + 1} ##\n"
           
           # Group cells by row
           rows = {}
           for cell in table.cells:
               row_idx = cell.row_index
               if row_idx not in rows:
                   rows[row_idx] = {}
               rows[row_idx][cell.column_index] = cell.content
           
           # Format table as text
           for row_idx in sorted(rows.keys()):
               row_cells = []
               for col_idx in sorted(rows[row_idx].keys()):
                   row_cells.append(rows[row_idx][col_idx])
               table_text += " | ".join(row_cells) + "\n"
               table_data["content"].append(row_cells)
           
           extracted_data["tables"].append(table_data)
           full_text += table_text
       
       # Process paragraphs for section detection
       for para in result.paragraphs:
           # Detect section headers (usually bold, larger, or specific patterns)
           if self.is_section_header(para.content):
               extracted_data["sections"].append({
                   "title": para.content,
                   "bounding_regions": para.bounding_regions
               })
       
       extracted_data["text"] = full_text
       return extracted_data
   
def is_section_header(self, text):
       """Detect if text is likely a section header"""
       text = text.strip()
       
       # Common section header patterns
       header_patterns = [
           r"^[A-Z\s]+(?:EVALUATION|DETAILS|REQUIREMENTS|CONTROL|SCREENING)$",
           r"^[0-9]+\.\s*[A-Z][^.]+$",
           r"^\*\*[A-Z\s]+\*\*$",
           r"^[A-Z][A-Z\s&/()]{10,}$"  # All caps, long enough to be a header
       ]
       
       import re
       for pattern in header_patterns:
           if re.match(pattern, text):
               return True
       
       return False
   
def extract_enhanced_metadata(self, text_content, filename):
       """Enhanced metadata extraction using Document Intelligence results"""
       metadata = {
           "document_type": "QC Checklist",
           "product_name": "Unknown Product",
           "supplier_name": "Unknown Supplier",
           "filename": filename
       }
       
       text_lower = text_content.lower()
       
       # Enhanced product name detection
       product_patterns = [
           r"product\s*(?:name|description)?\s*[:\-]\s*([^\n]{1,50})",
           r"(malabar\s*paratha|green\s*peas|sweet\s*corn|vegetable\s*samosa|chicken\s*nuggets)",
           r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*[-–]\s*(?:inspection|checklist)",
       ]
       
       for pattern in product_patterns:
           import re
           match = re.search(pattern, text_content, re.IGNORECASE)
           if match:
               metadata["product_name"] = match.group(1).strip()
               break
       
       # Enhanced supplier detection
       supplier_patterns = [
           r"supplier\s*(?:name)?\s*[:\-]\s*([^\n]{1,40})",
           r"(al\s*kabeer|alkabeer|cascade\s*marine|sahar\s*food)",
           r"manufacturing\s*unit\s*[:\-]\s*([^\n]{1,40})"
       ]
       
       for pattern in supplier_patterns:
           import re
           match = re.search(pattern, text_content, re.IGNORECASE)
           if match:
               metadata["supplier_name"] = match.group(1).strip()
               break
       
       # Document type detection
       doc_type_patterns = {
           "Malabar Paratha Inspection": ["malabar", "paratha"],
           "Vegetable Samosa Inspection": ["vegetable", "samosa"],
           "Green Peas Inspection": ["green", "peas"],
           "Container Inspection Report": ["container", "inspection"],
           "Pre-Shipment Inspection": ["pre-shipment", "shipment"],
           "Temperature Log": ["temperature", "log", "chiller"],
           "HACCP Record": ["haccp", "critical control"]
       }
       
       for doc_type, keywords in doc_type_patterns.items():
           if all(keyword in text_lower for keyword in keywords):
               metadata["document_type"] = doc_type
               break
       
       return metadata

# Global instance
azure_doc_intelligence = AzureDocumentIntelligence()