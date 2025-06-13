from openai import AzureOpenAI
import json
from azure_secrets import get_openai_config
from azure_cache_utils import azure_cache
from datetime import datetime
import time  # Add this line at the top

class AzureOpenAIManager:
    def __init__(self):
        config = get_openai_config()
        
        # DEBUG: Print what we're actually using
        print(f"🔍 DEBUG: OpenAI Endpoint: {config['endpoint']}")
        print(f"🔍 DEBUG: OpenAI Key: {config['key'][:20]}...{config['key'][-10:] if config['key'] else 'None'}")
        
        # Configure Azure OpenAI with working API version
        self.client = AzureOpenAI(
            azure_endpoint=config["endpoint"],
            api_key=config["key"],
            api_version="2024-02-15-preview"
        )
        
        self.deployment_name = "gpt-4o"
        print(f"🔍 DEBUG: Using deployment: {self.deployment_name}")
        
    def call_openai_llm(self, user_message, doc_type, product_name, supplier_name, 
                    existing_parameters=None, is_digitization=False):
        """
        Azure OpenAI call with Redis caching support and enhanced Application Insights tracking.
        """
        import time
        
        start_time = time.time()
        cached_response = None
        
        # Check cache first
        cached_response = azure_cache.get_cached_response(
            user_message, doc_type, product_name, supplier_name
        )
        
        if cached_response:
            # Track cache hit
            duration_ms = (time.time() - start_time) * 1000
            azure_monitoring.track_llm_call(
                model=self.deployment_name,
                product_name=product_name,
                response_length=len(cached_response),
                duration_ms=duration_ms,
                cache_hit=True
            )
            return cached_response
            
        
        # Import here to avoid circular imports
        from azure_search_utils import get_comprehensive_context, format_context_for_prompt
        
        domain = "Food Manufacturing"

        # Get comprehensive context from Azure AI Search
        print(f"🔍 Retrieving comprehensive context for: {product_name}")
        try:
            comprehensive_context = get_comprehensive_context(product_name, domain)
            formatted_context = format_context_for_prompt(comprehensive_context, max_length=4500)
        except Exception as e:
            print(f"⚠️ RAG context error: {e}")
            formatted_context = f"Context retrieval temporarily unavailable. Generate comprehensive QC parameters for {product_name}."

        # Generate header and supplier info
        header_text = f"{product_name} {doc_type}"
        supplier_info = f"Supplier Name: {supplier_name}"
        
        # Check if user message contains reference document content
        has_reference = "Reference document content" in user_message
        
        # Select appropriate system prompt
        if is_digitization:
            system_instructions = self._get_digitize_system_prompt()
        else:
            system_instructions = self._get_system_prompt()

        # Build context
        context = formatted_context
        
        if has_reference:
            context += f"""

    **CRITICAL DIGITIZATION GUIDANCE**: The reference document content is provided to understand the STRUCTURE and PROFESSIONAL FORMAT of QC parameters. 

    Use the reference to identify:
    1. Section headings and table structures (preserve them)
    2. Parameter types and their appropriate input methods
    3. Tolerance specifications and measurement units
    4. Professional formatting and organization
    5. Regulatory compliance requirements

    Create parameters with values, specifications, and input types SPECIFIC to {product_name} while maintaining the professional structure and comprehensive coverage of the reference document.
            """
        else:
            context += f"""

    For {product_name}, ensure you include MINIMUM 15+ parameters covering these MANDATORY categories:

    1. **Physical Parameters** (4-5): Appearance (Image+Toggle), Texture (Dropdown+Remarks), Dimensions (Numeric), Weight (Numeric), Shape (Dropdown)
    2. **Sensory Parameters** (3-4): Flavor (Dropdown+Remarks), Aroma (Dropdown+Remarks), Mouthfeel (Dropdown), Overall Sensory (Toggle)
    3. **Safety Parameters** (4-5): Foreign Objects (Checklist+Image), Microbiological (Numeric), Chemical (Numeric), Allergens (Checklist), Metal Detection (Text+Toggle)
    4. **Product-Specific** (2-3): Based on product type (frozen, fried, baked, etc.)
    5. **Packaging** (3-4): Integrity (Image+Checklist), Weight Verification (Numeric), Date Verification (Text), Batch Traceability (Text)
    6. **Process Control** (2-3): Temperature (Numeric), Time (Numeric), Equipment (Toggle+Text)
    7. **Compliance** (2-3): Regulatory (Checklist), Documentation (Toggle), Inspector Assessment (Toggle+Remarks)

    **INTELLIGENT TYPE SELECTION RULES:**
    - Image Upload: Visual inspections, appearance, defects, evidence documentation
    - Toggle: Pass/fail, acceptable/not acceptable, present/absent, binary assessments
    - Checklist: Foreign objects (stones, glass, metals, plastic, wood, insects, hair, threads), allergens (all 14), packaging defects, compliance items
    - Numeric Input: ALL measurements with specifications and units (e.g., "Weight: 25±2g", "Temperature: -18°C ±2°C")
    - Text Input: Codes, dates, identifiers, batch numbers
    - Remarks: Detailed observations, corrective actions, complex assessments

    **PROFESSIONAL FORMATTING:**
    Match Al Kabeer Group's quality standards with proper section organization, comprehensive coverage, and intelligent parameter type selection.
            """

        # Construct the final system prompt
        final_system_prompt = f"""
    {system_instructions}

    User context:
    - Doc Type: {doc_type}
    - Product: {product_name}
    - Supplier: {supplier_name}
    - Generated Header: {header_text}
    - Supplier Info: {supplier_info}

    {context}

    **VALID PARAMETER TYPES:**
    Checklist, Dropdown, Image Upload, Remarks, Text Input, Numeric Input, Toggle

    **MANDATORY REQUIREMENTS:**
    1. MINIMUM 15+ parameters for comprehensive coverage
    2. Use intelligent type selection based on parameter purpose
    3. Include specifications with units for ALL Numeric Input parameters
    4. Provide comprehensive options for Checklist and Dropdown parameters
    5. Add clause references where regulatory compliance is required
    6. Include section organization for professional formatting
    7. Add "IncludeRemarks": "Yes" for complex parameters requiring detailed observations

    **OUTPUT INSTRUCTIONS:**
    1. Provide a brief summary describing the comprehensive QC parameters created.
    2. Then produce a bracketed JSON array with intelligent parameter selection.
    Example:
    [
        {{
        "action": "add",
        "Parameter": "Product Appearance",
        "Type": "Image Upload",
        "Spec": "Visual inspection with photo evidence",
        "DropdownOptions": "",
        "ChecklistOptions": "",
        "IncludeRemarks": "Yes",
        "Section": "Physical Parameters",
        "ClauseReference": "Dubai Municipality Section 4.1.2"
        }},
        {{
        "action": "add",
        "Parameter": "Foreign Objects Detection",
        "Type": "Checklist",
        "Spec": "Zero tolerance for all foreign materials",
        "ChecklistOptions": "Stones, Glass, Metals, Plastic, Wood, Insects/Pests, Hair, Threads, Paper, Bones, Feathers",
        "IncludeRemarks": "Yes",
        "Section": "Safety Parameters",
        "ClauseReference": "HACCP Principle 2"
        }},
        {{
        "action": "add",
        "Parameter": "Net Weight",
        "Type": "Numeric Input",
        "Spec": "25±2g per piece",
        "DropdownOptions": "",
        "IncludeRemarks": "No",
        "Section": "Physical Parameters"
        }}
    ]
    """

        messages = [
            {"role": "system", "content": final_system_prompt},
            {"role": "user", "content": user_message},
        ]

        try:
            print(f"🤖 Calling Azure OpenAI for {product_name}...")
            print(f"🔍 DEBUG: API call details:")
            print(f"   - Endpoint: {self.client._azure_endpoint}")
            print(f"   - Model: {self.deployment_name}")
            print(f"   - API Version: {self.client._api_version}")
            
            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=messages,
                temperature=0.2,
                max_tokens=4000
            )
            
            result = response.choices[0].message.content.strip()
            duration_ms = (time.time() - start_time) * 1000
            
            print(f"✅ Azure OpenAI response received ({len(result)} characters)")
            
            # Enhanced Application Insights tracking
            from azure_monitoring import azure_monitoring
            azure_monitoring.track_llm_call(
                model=self.deployment_name,
                product_name=product_name,
                response_length=len(result),
                duration_ms=duration_ms,
                cache_hit=False
            )
            
            # Track performance metric
            azure_monitoring.track_performance(
                operation="openai_generation",
                duration_ms=duration_ms,
                metadata={
                    "product_name": product_name,
                    "doc_type": doc_type,
                    "response_length": len(result),
                    "model": self.deployment_name
                }
            )
            
            # Cache the response
            azure_cache.cache_response(
                user_message, doc_type, product_name, supplier_name, result
            )
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            print(f"❌ Azure OpenAI call failed: {str(e)}")
            print(f"🔍 DEBUG: Exception type: {type(e)}")
            
            # Enhanced error tracking
            from azure_monitoring import azure_monitoring
            azure_monitoring.track_error(
                endpoint="openai_llm",
                error_type=type(e).__name__,
                error_message=str(e)
            )
            
            # Track failed performance
            azure_monitoring.track_performance(
                operation="openai_generation_failed",
                duration_ms=duration_ms,
                metadata={
                    "product_name": product_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:100]
                }
            )
            
            import traceback
            traceback.print_exc()
            return f"Azure OpenAI call failed: {str(e)}"
    
    def _get_system_prompt(self):
        """Your existing SYSTEM_PROMPT"""
        return """
You are the Swift Check AI assistant, specialized in creating comprehensive Quality Control (QC) checklists and inspection documents for food products with full regulatory compliance.

# CONTEXT:
You'll help users generate custom QC parameters for various food products following Al Kabeer Group's professional standards. The parameters will be used in quality inspection checklists that QC inspectors fill during product inspections, with full regulatory backing and clause references.

# COMPREHENSIVE QC CHECKLIST REQUIREMENTS:

## For Food Products, ALWAYS include these categories (MINIMUM 15+ PARAMETERS):

### 1. Physical Parameters (4-5 parameters)
- Appearance (Image Upload + Toggle): Color, visual defects, physical state with photo evidence
- Texture (Dropdown + Remarks): Firmness, consistency, crispness with detailed observations
- Size/Dimensions (Numeric Input): Length, width, diameter with tolerance specs (e.g., "60±5mm")
- Weight (Numeric Input): Individual/batch weight with tolerance (e.g., "25±2g")
- Shape (Dropdown): Uniformity, deformation assessment

### 2. Sensory Parameters (3-4 parameters)
- Flavor/Taste (Dropdown + Remarks): Characteristic flavors, off-tastes, intensity
- Aroma/Odor (Dropdown + Remarks): Normal smell, off-odors, freshness
- Mouthfeel (Dropdown): For applicable products (texture after cooking)
- Overall Sensory Assessment (Toggle): Acceptable/Not Acceptable

### 3. Safety Parameters (4-5 parameters)
- Foreign Objects (Checklist + Image Upload): MUST include comprehensive list: stones, glass, metals, plastic, wood, insects/pests, hair, threads, paper, bones, feathers
- Microbiological Specifications (Table/Numeric Input): Total Plate Count, E.coli, Salmonella, etc. with limits
- Chemical Contaminants (Numeric Input): Heavy metals, pesticides if applicable with ppm limits
- Allergen Declaration (Checklist): All 14 major allergens verification
- Metal Detection Results (Text Input + Toggle): Fe, Non-Fe, SS readings with pass/fail

### 4. Product-Specific Parameters (2-3 parameters)
- For filled products: Filling weight ratio, filling consistency
- For fried products: Oil absorption, crispness level
- For frozen products: Freezer burn check, ice crystals, clustering
- For baked products: Browning level, doneness, internal temperature

### 5. Packaging Parameters (3-4 parameters)
- Packaging Integrity (Image Upload + Checklist): Sealing, tears, punctures, label accuracy with photo
- Net Weight Verification (Numeric Input): Package weight vs declared weight with tolerance
- Date Verification (Text Input): Best before date, production date accuracy
- Batch/Lot Traceability (Text Input): Batch code, lot number verification

### 6. Process Control Parameters (2-3 parameters)
- Temperature Control (Numeric Input): Processing, storage, transport temperatures with specs
- Time Parameters (Numeric Input): Processing time, cooling time with specifications
- Equipment Calibration (Toggle + Text Input): Calibration status, last calibration date

### 7. Compliance & Documentation (2-3 parameters)
- Regulatory Compliance (Checklist): HACCP, Dubai Municipality, ISO requirements
- Documentation Complete (Toggle): All required certificates present
- Inspector Assessment (Toggle + Remarks): Overall quality assessment with detailed remarks

Remember: Generate PROFESSIONAL, COMPREHENSIVE checklists that match Al Kabeer Group's quality standards with full regulatory compliance and intelligent parameter type selection.
"""
    
    def _get_digitize_system_prompt(self):
        """Your existing DIGITIZE_SYSTEM_PROMPT"""
        return """
You are the Swift Check AI digitization assistant. Your job is to analyze OCR-extracted text from scanned QC checklists and convert them into structured parameters for comprehensive food safety and quality control checklists.

# YOUR TASKS:
1. Recognize and preserve table structures and section headings
2. Identify quality control parameters with their proper input types
3. Extract specifications, tolerance limits, and measurement units
4. Determine appropriate parameter types based on content analysis
5. Maintain professional formatting and organization

# INTELLIGENT PARAMETER TYPE DETECTION:

## Image Upload - DETECT FOR:
- Parameters mentioning "photo", "attach", "capture", "visual", "appearance"
- Instructions like "attach photos", "capture variations"
- Visual inspection requirements

## Toggle - DETECT FOR:
- Binary choices: "Acceptable/Non-acceptable", "Present/Absent", "Pass/Fail"
- "Yes/No" type assessments
- Simple pass/fail criteria

## Checklist - DETECT FOR:
- Lists of items to verify (foreign objects, allergens, defects)
- Multiple related items that can be selected simultaneously
- Categories with sub-items

## Numeric Input - DETECT FOR:
- Measurements with units and tolerances
- Temperature readings, weights, dimensions
- Time durations, counts, percentages
- Values with specifications like "±5g", "<10^4", "2-3 minutes"

## Text Input - DETECT FOR:
- Codes, dates, identifiers
- Batch numbers, lot codes
- Names, locations, serial numbers

## Remarks - DETECT FOR:
- "Remarks", "Comments", "Observations", "Notes"
- Areas requiring detailed explanations
- Corrective action descriptions

Focus on creating comprehensive, professional parameters that maintain the structure and intelligence of the original document while using appropriate modern input types.
"""

# Global instance
azure_openai = AzureOpenAIManager()