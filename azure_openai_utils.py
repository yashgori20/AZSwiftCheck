from openai import AzureOpenAI
import time
from azure_secrets import get_openai_config
from azure_cache_utils import azure_cache

class AzureOpenAIManager:
    def __init__(self):
        config = get_openai_config()
        
        self.client = AzureOpenAI(
            azure_endpoint=config["endpoint"],
            api_key=config["key"],
            api_version="2024-02-15-preview"
        )
        
        self.deployment_name = "gpt-4o"
        print("? Azure OpenAI Manager initialized")
    
    def call_openai_llm(self, user_message, doc_type, product_name, supplier_name, 
                       existing_parameters=None, is_digitization=False):
        """Azure OpenAI call with monitoring"""
        
        start_time = time.time()
        
        # Check cache first
        cached_response = azure_cache.get_cached_response(
            user_message, doc_type, product_name, supplier_name
        )
        
        if cached_response:
            print(f"? Cache HIT for {product_name}")
            return cached_response
        
        # Import here to avoid circular imports
        from azure_search_utils import get_comprehensive_context, format_context_for_prompt
        
        domain = "Food Manufacturing"
        
        try:
            comprehensive_context = get_comprehensive_context(product_name, domain)
            formatted_context = format_context_for_prompt(comprehensive_context, max_length=4500)
        except Exception as e:
            print(f"?? RAG context error: {e}")
            formatted_context = f"Generate comprehensive QC parameters for {product_name}."
        
        # Build system prompt
        system_prompt = f'''
You are the Swift Check AI assistant. Create comprehensive QC parameters for {product_name}.

Context: {formatted_context}

Generate MINIMUM 15+ parameters covering:
1. Physical Parameters (appearance, weight, dimensions)
2. Safety Parameters (foreign objects, microbiological)
3. Sensory Parameters (taste, aroma, texture)
4. Packaging Parameters (integrity, labeling)
5. Process Control (temperature, time)
6. Compliance (regulatory requirements)

Output as JSON array with this format:
[
  {{
    "action": "add",
    "Parameter": "Product Appearance",
    "Type": "Image Upload",
    "Spec": "Visual inspection with photo",
    "DropdownOptions": "",
    "IncludeRemarks": "Yes",
    "Section": "Physical Parameters",
    "ClauseReference": "Dubai Municipality Section 4.1"
  }}
]

Valid Types: Image Upload, Toggle, Dropdown, Checklist, Numeric Input, Text Input, Remarks
'''
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        
        try:
            print(f"?? Calling Azure OpenAI for {product_name}...")
            
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=messages,
                temperature=0.2,
                max_tokens=4000
            )
            
            result = response.choices[0].message.content.strip()
            duration_ms = (time.time() - start_time) * 1000
            
            print(f"? Azure OpenAI response received ({len(result)} characters, {duration_ms:.2f}ms)")
            
            # Cache the response
            azure_cache.cache_response(
                user_message, doc_type, product_name, supplier_name, result
            )
            
            # Track monitoring
            try:
                from azure_monitoring import azure_monitoring
                azure_monitoring.track_llm_call(
                    model=self.deployment_name,
                    product_name=product_name,
                    response_length=len(result),
                    duration_ms=duration_ms,
                    cache_hit=False
                )
            except:
                pass  # Don't fail if monitoring fails
            
            return result
            
        except Exception as e:
            print(f"? Azure OpenAI call failed: {str(e)}")
            return f"Azure OpenAI call failed: {str(e)}"

# Global instance
azure_openai = AzureOpenAIManager()
