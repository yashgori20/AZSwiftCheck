from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
import sys
sys.path.append('/app')
from azure_secrets import get_search_config
from sentence_transformers import SentenceTransformer
import uuid

class SimpleSearchIndexer:
    def __init__(self):
        config = get_search_config()
        self.search_client = SearchClient(
            endpoint=config["endpoint"],
            index_name="qc-knowledge-index",
            credential=AzureKeyCredential(config["admin_key"])
        )
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    def upload_documents(self, documents):
        """Upload documents to search index"""
        try:
            result = self.search_client.upload_documents(documents)
            success_count = sum(1 for r in result if r.succeeded)
            print(f"✅ Successfully uploaded {success_count}/{len(documents)} documents")
        except Exception as e:
            print(f"❌ Error uploading documents: {e}")
            raise