from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from azure_secrets import get_search_config
from sentence_transformers import SentenceTransformer
from datetime import datetime
from typing import List, Dict, Optional
import json

class AzureSearchRAGUtils:
    def __init__(self):
        config = get_search_config()
        
        # Initialize Azure AI Search client
        credential = AzureKeyCredential(config["admin_key"])
        self.search_client = SearchClient(
            endpoint=config["endpoint"],
            index_name="qc-knowledge-index",  # We'll create this index
            credential=credential
        )
        
        # Initialize embedding model (same as before)
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        
        print("✅ Azure Search RAG Utils initialized")
    
    def retrieve_regulatory_requirements(self, product_name: str, domain: str = "Food Manufacturing", k: int = 3) -> List[Dict]:
        """Retrieve relevant regulatory requirements"""
        try:
            # Create targeted query
            query_text = f"{product_name} {domain} regulatory requirements compliance standards Dubai UAE HACCP"
            query_vector = self.embedder.encode(query_text).tolist()
            
            # Create vectorized query
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=k,
                fields="contentVector"
            )
            
            # Search with both text and vector
            results = self.search_client.search(
                search_text=query_text,
                vector_queries=[vector_query],
                select=["content", "regulatory_body", "standard_code", "clause_reference", "topics", "jurisdiction"],
                top=k
            )
            
            guidelines = []
            for result in results:
                guidelines.append({
                    "text": result.get("content", "")[:800],
                    "regulatory_body": result.get("regulatory_body", "Unknown"),
                    "standard_code": result.get("standard_code", ""),
                    "clause_reference": result.get("clause_reference", ""),
                    "topics": result.get("topics", ""),
                    "jurisdiction": result.get("jurisdiction", "UAE"),
                    "relevance_score": result.get("@search.score", 0.5),
                    "source_type": "regulatory"
                })
            
            return sorted(guidelines, key=lambda x: x['relevance_score'], reverse=True)
            
        except Exception as e:
            print(f"❌ Error retrieving regulatory requirements: {str(e)}")
            # Return fallback data
            return [{
                "text": f"Standard regulatory requirements for {product_name} in {domain}",
                "regulatory_body": "Dubai Municipality",
                "standard_code": "HACCP Guidelines",
                "clause_reference": "Section 7.8",
                "topics": "Food Safety, Quality Control",
                "jurisdiction": "UAE",
                "relevance_score": 0.8,
                "source_type": "regulatory"
            }]
    
    def retrieve_product_specifications(self, product_name: str, k: int = 3) -> List[Dict]:
        """Retrieve similar product specifications"""
        try:
            query_text = f"{product_name} product specification quality parameters tolerance limits"
            query_vector = self.embedder.encode(query_text).tolist()
            
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=k,
                fields="contentVector"
            )
            
            results = self.search_client.search(
                search_text=query_text,
                vector_queries=[vector_query],
                select=["content", "product_name", "supplier", "category", "specification_type", "parameters_count"],
                top=k
            )
            
            specifications = []
            for result in results:
                specifications.append({
                    "text": result.get("content", "")[:600],
                    "product_name": result.get("product_name", "Unknown"),
                    "supplier": result.get("supplier", "Unknown"),
                    "category": result.get("category", "Unknown"),
                    "specification_type": result.get("specification_type", "Unknown"),
                    "parameters_count": result.get("parameters_count", 0),
                    "detail_level": "standard",
                    "relevance_score": result.get("@search.score", 0.5),
                    "source_type": "product_spec"
                })
            
            return sorted(specifications, key=lambda x: x['relevance_score'], reverse=True)
            
        except Exception as e:
            print(f"❌ Error retrieving product specifications: {str(e)}")
            return [{
                "text": f"Standard product specifications for {product_name}",
                "product_name": product_name,
                "supplier": "Al Kabeer",
                "category": "Food Manufacturing",
                "specification_type": "Quality Control",
                "parameters_count": 15,
                "detail_level": "standard",
                "relevance_score": 0.8,
                "source_type": "product_spec"
            }]
    
    def retrieve_checklist_examples(self, product_name: str, k: int = 3) -> List[Dict]:
        """Retrieve similar checklist examples"""
        try:
            query_text = f"{product_name} quality control inspection checklist parameters"
            query_vector = self.embedder.encode(query_text).tolist()
            
            vector_query = VectorizedQuery(
                vector=query_vector,
                k_nearest_neighbors=k,
                fields="contentVector"
            )
            
            results = self.search_client.search(
                search_text=query_text,
                vector_queries=[vector_query],
                select=["content", "document_type", "product_name", "checklist_category", "total_parameters", "parameter_types", "input_methods"],
                top=k
            )
            
            examples = []
            for result in results:
                examples.append({
                    "text": result.get("content", "")[:500],
                    "document_type": result.get("document_type", "QC Checklist"),
                    "product_name": result.get("product_name", "Unknown"),
                    "checklist_category": result.get("checklist_category", "General"),
                    "total_parameters": result.get("total_parameters", 0),
                    "parameter_types": result.get("parameter_types", []),
                    "input_methods": result.get("input_methods", []),
                    "parameter_structure": [],
                    "relevance_score": result.get("@search.score", 0.5),
                    "source_type": "checklist_example"
                })
            
            return examples
            
        except Exception as e:
            print(f"❌ Error retrieving checklist examples: {str(e)}")
            return [{
                "text": f"Standard checklist example for {product_name}",
                "document_type": "QC Checklist",
                "product_name": product_name,
                "checklist_category": "General Inspection",
                "total_parameters": 15,
                "parameter_types": ["Physical", "Sensory", "Safety"],
                "input_methods": ["Image Upload", "Numeric Input", "Toggle"],
                "parameter_structure": [],
                "relevance_score": 0.8,
                "source_type": "checklist_example"
            }]
    
    def get_comprehensive_context(self, product_name: str, domain: str = "Food Manufacturing", 
                                 include_patterns: bool = True) -> Dict:
        """Get comprehensive context from Azure AI Search"""
        
        context = {
            "product_name": product_name,
            "domain": domain,
            "regulatory_requirements": [],
            "product_specifications": [],
            "checklist_examples": [],
            "parameter_patterns": [],
            "context_summary": {},
            "generated_at": datetime.now().isoformat()
        }
        
        print(f"🔍 Retrieving comprehensive context for: {product_name}")
        
        # Get regulatory requirements
        context["regulatory_requirements"] = self.retrieve_regulatory_requirements(product_name, domain, k=4)
        
        # Get product specifications
        context["product_specifications"] = self.retrieve_product_specifications(product_name, k=3)
        
        # Get checklist examples
        context["checklist_examples"] = self.retrieve_checklist_examples(product_name, k=4)
        
        # Get parameter patterns (simplified for now)
        if include_patterns:
            context["parameter_patterns"] = self._get_default_parameter_patterns()
        
        # Generate context summary
        context["context_summary"] = self._generate_context_summary(context)
        
        return context
    
    def format_context_for_prompt(self, context: Dict, max_length: int = 4000) -> str:
        """Format comprehensive context for AI prompt"""
        
        formatted_context = "\n# RETRIEVED CONTEXT FOR QC CHECKLIST GENERATION:\n"
        
        # Add regulatory compliance requirements
        if context["regulatory_requirements"]:
            formatted_context += "\n## 🏛️ REGULATORY COMPLIANCE REQUIREMENTS:\n"
            for i, req in enumerate(context["regulatory_requirements"][:2], 1):
                clause_ref = req.get('clause_reference', req.get('standard_code', ''))
                formatted_context += f"\n### {i}. {req['regulatory_body']} - {clause_ref}\n"
                
                if req.get('topics'):
                    formatted_context += f"**Key Topics**: {req['topics'][:100]}...\n"
                
                formatted_context += f"**Requirement**: {req['text'][:300]}...\n"
                
                if req.get('jurisdiction'):
                    formatted_context += f"**Jurisdiction**: {req['jurisdiction']}\n"
        
        # Add product specification depth reference
        if context["product_specifications"]:
            formatted_context += "\n## 📋 PRODUCT SPECIFICATION DEPTH REFERENCE:\n"
            for i, spec in enumerate(context["product_specifications"][:2], 1):
                formatted_context += f"\n### {i}. {spec['product_name']} ({spec['supplier']})\n"
                formatted_context += f"**Detail Level**: {spec['detail_level']} | **Parameters**: {spec['parameters_count']}\n"
                formatted_context += f"**Example Content**: {spec['text'][:250]}...\n"
        
        # Add checklist structure examples
        if context["checklist_examples"]:
            formatted_context += "\n## ✅ PROFESSIONAL CHECKLIST EXAMPLES:\n"
            for i, example in enumerate(context["checklist_examples"][:2], 1):
                formatted_context += f"\n### {i}. {example['document_type']} - {example['product_name']}\n"
                formatted_context += f"**Category**: {example['checklist_category']} | **Parameters**: {example['total_parameters']}\n"
                
                if example.get('input_methods'):
                    methods = ', '.join(example['input_methods'][:5]) if isinstance(example['input_methods'], list) else str(example['input_methods'])
                    formatted_context += f"**Input Methods Used**: {methods}\n"
        
        # Truncate if too long
        if len(formatted_context) > max_length:
            formatted_context = formatted_context[:max_length] + "\n\n[Context truncated for length...]"
        
        return formatted_context
    
    def _get_default_parameter_patterns(self):
        """Default parameter patterns when search is unavailable"""
        return [
            {"parameter_name": "Product Appearance", "parameter_type": "Quality Assessment", "input_method": "Image Upload", "usage_frequency": 10},
            {"parameter_name": "Net Weight", "parameter_type": "Measurement", "input_method": "Numeric Input", "usage_frequency": 8},
            {"parameter_name": "Foreign Objects", "parameter_type": "Safety Check", "input_method": "Checklist", "usage_frequency": 9},
            {"parameter_name": "Temperature", "parameter_type": "Process Control", "input_method": "Numeric Input", "usage_frequency": 7},
            {"parameter_name": "Overall Assessment", "parameter_type": "Quality Assessment", "input_method": "Toggle", "usage_frequency": 10}
        ]
    
    def _generate_context_summary(self, context: Dict) -> Dict:
        """Generate intelligent summary of retrieved context"""
        summary = {
            "regulatory_focus": "",
            "recommended_sections": [],
            "critical_parameters": [],
            "input_method_recommendations": {},
            "compliance_requirements": []
        }
        
        # Analyze regulatory requirements
        if context["regulatory_requirements"]:
            bodies = [req['regulatory_body'] for req in context["regulatory_requirements"]]
            if "Dubai Municipality" in bodies:
                summary["regulatory_focus"] = "Dubai Municipality HACCP Guidelines compliance required"
            elif "HACCP" in " ".join(bodies):
                summary["regulatory_focus"] = "HACCP principles implementation required"
        
        # Extract recommended sections
        sections = set()
        for example in context["checklist_examples"]:
            category = example.get('checklist_category', '')
            if category and category != 'General':
                sections.add(category)
        
        summary["recommended_sections"] = list(sections)[:5]
        
        # Generate input method recommendations
        summary["input_method_recommendations"] = {
            "Physical Parameters": "Numeric Input",
            "Safety Parameters": "Checklist",
            "Visual Inspection": "Image Upload",
            "Quality Assessment": "Toggle",
            "Documentation": "Text Input"
        }
        
        return summary

# Global instance
azure_search_rag = AzureSearchRAGUtils()
def retrieve_regulatory_requirements(self, product_name: str, domain: str = "Food Manufacturing", k: int = 3) -> List[Dict]:
    """Retrieve relevant regulatory requirements"""
    try:
        query_text = f"{product_name} {domain} regulatory requirements compliance standards Dubai UAE HACCP"
        
        # Simple search with only available fields
        results = self.search_client.search(
            search_text=query_text,
            select=["content", "source_type"],  # Only query available fields
            top=k
        )
        
        guidelines = []
        for result in results:
            guidelines.append({
                "text": result.get("content", "")[:800],
                "regulatory_body": "Dubai Municipality",  # Default values
                "standard_code": "HACCP Guidelines",
                "clause_reference": "Section 7.8",
                "topics": "Food Safety, Quality Control",
                "jurisdiction": "UAE",
                "relevance_score": result.get("@search.score", 0.5),
                "source_type": "regulatory"
            })
        
        return sorted(guidelines, key=lambda x: x['relevance_score'], reverse=True)
        
    except Exception as e:
        print(f"❌ Error retrieving regulatory requirements: {str(e)}")
        # Return fallback data
        return [{
            "text": f"Standard regulatory requirements for {product_name} in {domain}",
            "regulatory_body": "Dubai Municipality",
            "standard_code": "HACCP Guidelines",
            "clause_reference": "Section 7.8",
            "topics": "Food Safety, Quality Control",
            "jurisdiction": "UAE",
            "relevance_score": 0.8,
            "source_type": "regulatory"
        }]

def retrieve_product_specifications(self, product_name: str, k: int = 3) -> List[Dict]:
    """Retrieve similar product specifications"""
    try:
        query_text = f"{product_name} product specification quality parameters tolerance limits"
        
        results = self.search_client.search(
            search_text=query_text,
            select=["content", "source_type"],  # Only query available fields
            top=k
        )
        
        specifications = []
        for result in results:
            specifications.append({
                "text": result.get("content", "")[:600],
                "product_name": product_name,  # Use provided name
                "supplier": "Al Kabeer",
                "category": "Food Manufacturing",
                "specification_type": "Quality Control",
                "parameters_count": 15,
                "detail_level": "standard",
                "relevance_score": result.get("@search.score", 0.5),
                "source_type": "product_spec"
            })
        
        return sorted(specifications, key=lambda x: x['relevance_score'], reverse=True)
        
    except Exception as e:
        print(f"❌ Error retrieving product specifications: {str(e)}")
        return [{
            "text": f"Standard product specifications for {product_name}",
            "product_name": product_name,
            "supplier": "Al Kabeer",
            "category": "Food Manufacturing",
            "specification_type": "Quality Control",
            "parameters_count": 15,
            "detail_level": "standard",
            "relevance_score": 0.8,
            "source_type": "product_spec"
        }]

def retrieve_checklist_examples(self, product_name: str, k: int = 3) -> List[Dict]:
    """Retrieve similar checklist examples"""
    try:
        query_text = f"{product_name} quality control inspection checklist parameters"
        
        results = self.search_client.search(
            search_text=query_text,
            select=["content", "source_type"],  # Only query available fields
            top=k
        )
        
        examples = []
        for result in results:
            examples.append({
                "text": result.get("content", "")[:500],
                "document_type": "QC Checklist",
                "product_name": product_name,
                "checklist_category": "General Inspection",
                "total_parameters": 15,
                "parameter_types": ["Physical", "Sensory", "Safety"],
                "input_methods": ["Image Upload", "Numeric Input", "Toggle"],
                "parameter_structure": [],
                "relevance_score": result.get("@search.score", 0.5),
                "source_type": "checklist_example"
            })
        
        return examples
        
    except Exception as e:
        print(f"❌ Error retrieving checklist examples: {str(e)}")
        return [{
            "text": f"Standard checklist example for {product_name}",
            "document_type": "QC Checklist",
            "product_name": product_name,
            "checklist_category": "General Inspection",
            "total_parameters": 15,
            "parameter_types": ["Physical", "Sensory", "Safety"],
            "input_methods": ["Image Upload", "Numeric Input", "Toggle"],
            "parameter_structure": [],
            "relevance_score": 0.8,
            "source_type": "checklist_example"
        }]
# Export convenience functions (same names as before)
def get_comprehensive_context(product_name: str, domain: str = "Food Manufacturing") -> Dict:
    """Get comprehensive context from Azure AI Search"""
    return azure_search_rag.get_comprehensive_context(product_name, domain)

def format_context_for_prompt(context: Dict, max_length: int = 4000) -> str:
    """Format context for AI prompt"""
    return azure_search_rag.format_context_for_prompt(context, max_length)