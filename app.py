import json
import re
import random
from datetime import datetime
import string
import os
import tempfile
from PIL import Image
import pytesseract
import fitz  
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, redirect, url_for, render_template_string, Response
from pathlib import Path
import requests
from cosmos_db_utils import enhanced_cosmos_db as cosmos_db
from azure_search_utils import get_comprehensive_context, format_context_for_prompt
from azure_cache_utils import azure_cache
import os
from datetime import datetime
from azure_monitoring import azure_monitoring
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta
import uuid
from azure_secrets import get_blob_connection
from pathlib import Path
from rate_limiter import rate_limit, rate_limiter
from performance_monitor import performance_monitor
from flask import g
from workflow_engine import workflow_engine, ApprovalStatus
from tenant_manager import tenant_manager
from analytics_engine import analytics_engine
from audit_logger import audit_log

app = Flask(__name__)
azure_monitoring.init_app(app)
global_parameters = []
global_json_template = {}

# system prompt with comprehensive QC requirements
SYSTEM_PROMPT = """
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

# PARAMETER TYPES AND INTELLIGENT SELECTION:

## Image Upload - USE FOR:
- Visual inspections (appearance, defects, packaging condition)
- Evidence documentation (defects, foreign objects)
- Label verification and batch code photos
- Before/after cooking comparisons

## Toggle - USE FOR:
- Pass/fail decisions (acceptable/not acceptable)
- Present/absent checks (clustering, defects)
- Compliance status (passed/failed)
- Binary quality assessments

## Checklist - USE FOR:
- Foreign objects (comprehensive list of all possible contaminants)
- Allergens (all 14 major allergens)
- Packaging defects (multiple possible issues)
- Compliance requirements (multiple standards)
- Multi-item verification lists

## Numeric Input - USE FOR:
- Measurements WITH specifications and units
- Weight: "25±2g", "165±5g"
- Dimensions: "60±5mm length", "7-8 inch diameter"
- Temperature: "-18°C ±2°C", "180°C ±10°C"
- Microbiological limits: "<10^4 CFU/g", "<10^2"
- Chemical limits: "<0.1ppm", "<0.10ppm"
- Time measurements: "2-3 minutes", "30±5 seconds"

## Text Input - USE FOR:
- Alphanumeric data entry
- Batch numbers, lot codes
- Production dates, expiry dates
- Supplier codes, product codes
- Equipment serial numbers

## Remarks - USE FOR:
- Detailed observations requiring explanation
- Corrective actions taken
- Special conditions noted
- Inspector additional comments
- Non-conformance descriptions

# REGULATORY COMPLIANCE:
- Include specific clause references for each parameter when available
- Reference Dubai Municipality guidelines, HACCP principles, ISO standards
- Ensure traceability requirements are met
- Include metal detection and allergen management as per UAE regulations

# OUTPUT FORMAT:
Provide comprehensive, actionable parameters with:
- Minimum 15+ parameters covering all categories above
- Appropriate types based on intelligent selection rules
- Realistic specifications with proper units and tolerances
- Comprehensive options for dropdowns/checklists
- Clause references where applicable (e.g., "Dubai Municipality Section 4.2.1")
- Professional formatting matching Al Kabeer Group standards

Remember: Generate PROFESSIONAL, COMPREHENSIVE checklists that match Al Kabeer Group's quality standards with full regulatory compliance and intelligent parameter type selection.
"""

# default refine prompt
DEFAULT_REFINE_PROMPT = """
Create a comprehensive professional food quality control checklist for the specified product following Al Kabeer Group standards. Include a MINIMUM of 15+ parameters that cover:

1. PHYSICAL ATTRIBUTES: Appearance (with photo), texture, dimensions, weight with precise tolerance limits
2. SENSORY EVALUATION: Flavor, aroma, taste, mouthfeel characteristics with detailed assessment
3. SAFETY PARAMETERS: Comprehensive foreign objects checklist, microbiological specifications, chemical contaminants, allergen verification
4. PRODUCT-SPECIFIC CHECKS: Based on processing method (frozen, fried, baked, filled, etc.) with specialized parameters
5. PACKAGING INTEGRITY: Visual inspection with photos, seal quality, labeling accuracy, weight verification
6. PROCESS CONTROL: Temperature monitoring, time parameters, equipment calibration status
7. COMPLIANCE VERIFICATION: HACCP principles, Dubai Municipality requirements, ISO standards, traceability
8. DOCUMENTATION: Batch codes, production dates, certificates, inspector assessment

Use intelligent parameter type selection:
- Image Upload for visual inspections and evidence documentation
- Toggle for pass/fail and binary assessments
- Checklist for foreign objects, allergens, and multi-item verifications
- Numeric Input for all measurements with proper specifications and units
- Text Input for codes, dates, and identifiers
- Remarks for detailed observations and corrective actions

Include specific regulatory clause references where applicable and ensure professional formatting that matches Al Kabeer Group's quality standards.
"""

# digitization system prompt
DIGITIZE_SYSTEM_PROMPT = """
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

# TABLE STRUCTURE RECOGNITION:
- Preserve section headings like "ORGANOLEPTIC EVALUATION", "COOKING DETAILS", "PACKAGING & FREEZING"
- Maintain parameter groupings and logical flow
- Keep tolerance limits and specifications with their parameters
- Preserve professional formatting structure

# OUTPUT FORMAT:
Provide a comprehensive JSON array with intelligent parameter type selection:
[
  {
    "Parameter": "Actual Parameter Name from Document",
    "Type": "Intelligently Selected Type",
    "Spec": "Extracted specifications with units",
    "DropdownOptions": "Specific options from document",
    "ChecklistOptions": "Comprehensive list items",
    "IncludeRemarks": "Yes/No based on parameter complexity",
    "Section": "Document section/category",
    "ClauseReference": "Regulatory reference if identified"
  }
]

Focus on creating comprehensive, professional parameters that maintain the structure and intelligence of the original document while using appropriate modern input types.
"""



def extract_top_level_json_array(text):
    """
    function to extract JSON array from text, handling both raw JSON and code blocks
    """
    # First try to find JSON in code blocks (```json ... ```)
    import re
    
    # Look for JSON code blocks
    json_block_pattern = r'```json\s*(.*?)\s*```'
    json_block_match = re.search(json_block_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if json_block_match:
        json_content = json_block_match.group(1).strip()
        # Validate that it starts with [ and ends with ]
        if json_content.startswith('[') and json_content.endswith(']'):
            return json_content
    
    # Fallback to original method for raw JSON arrays
    start = text.find('[')
    if start == -1:
        return ""
    
    balance = 0
    end = start
    for i in range(start, len(text)):
        char = text[i]
        if char == '[':
            balance += 1
        elif char == ']':
            balance -= 1
            if balance == 0:
                end = i
                break
    
    return text[start:end+1]

# Replace the existing function in app.py with this version

def call_groq_llm(user_message, doc_type, product_name, supplier_name, existing_parameters=None, is_digitization=False):
    """Wrapper function - now uses Azure OpenAI instead of Groq"""
    from azure_openai_utils import azure_openai
    return azure_openai.call_openai_llm(user_message, doc_type, product_name, supplier_name, existing_parameters, is_digitization)


def parse_llm_changes(llm_text):
    """Parse LLM response into summary and changes"""
    json_array_text = extract_top_level_json_array(llm_text)
    changes = []
    if json_array_text:
        try:
            changes = json.loads(json_array_text)
        except Exception as e:
            print("JSON parse error:", e)
    summary_text = llm_text.replace(json_array_text, "").strip() if json_array_text else llm_text.strip()
    return summary_text, changes

def apply_changes_to_params(parameters, changes):
    """Apply changes to parameters with parameter handling"""
    valid_types = ["Checklist", "Dropdown", "Image Upload", "Remarks", "Text Input", "Numeric Input", "Toggle"]

    for change in changes:
        if not isinstance(change, dict):
            print(f"Skipping non-dict change: {change}")
            continue
            
        action = change.get("action", "").lower()
        p_name = change.get("Parameter", "Unnamed")
        options = change.get("DropdownOptions", "")
        checklist_options = change.get("ChecklistOptions", "")
        
        # Handle both DropdownOptions and ChecklistOptions
        if not options and checklist_options:
            options = checklist_options
        if isinstance(options, list):
            options = ", ".join(options)

        if action == "add":
            new_type = change.get("Type", "Text Input")
            if new_type not in valid_types:
                new_type = "Text Input"
                
            new_param = {
                "Parameter": p_name,
                "Type": new_type,
                "Spec": change.get("Spec", ""),
                "DropdownOptions": options, 
                "IncludeRemarks": change.get("IncludeRemarks", "No"),
                "Section": change.get("Section", "General"),
                "ClauseReference": change.get("ClauseReference", "")
            }
            parameters.append(new_param)
            
        elif action == "remove":
            parameters[:] = [p for p in parameters if p["Parameter"].lower() != p_name.lower()]
            
        elif action == "update":
            for p in parameters:
                if p["Parameter"].lower() == p_name.lower():
                    new_type = change.get("Type", "Text Input")
                    if new_type not in valid_types:
                        new_type = "Text Input"
                    p["Type"] = new_type
                    p["Spec"] = change.get("Spec", "")
                    p["DropdownOptions"] = options  
                    p["IncludeRemarks"] = change.get("IncludeRemarks", "No")
                    p["Section"] = change.get("Section", "General")
                    p["ClauseReference"] = change.get("ClauseReference", "")
                    break

    return parameters

def generate_json_template(doc_type, product_name, supplier_name, parameters):
    """
    JSON template generation with intelligent parameter type handling.
    """
    header_text = f"{product_name} {doc_type}"
    template = {
        "templateId": "neY5j",
        "isDrafted": False,
        "pageStyle": {
            "margin": {
                "top": 10,
                "bottom": 10,
                "left": 10,
                "right": 10
            },
            "showPageNumber": False,
            "headerImgUrl": "",
            "fotterImgUrl": ""
        },
        "pageToolsDataList": [],
        "workflowInfo": {
            "currentState": "Draft",
            "approvalStates": ["Draft", "Under Review", "Approved", "Rejected"],
            "currentApprover": {
                "userId": "user123",
                "name": "Ashish Kumar",
                "role": "QC Manager"
            },
            "previousApprovers": [
                {
                    "userId": "user456",
                    "name": "Raj Singh",
                    "role": "QC Supervisor",
                    "approvalDate": "2025-05-01T10:30:00Z",
                    "status": "Approved",
                    "comments": "Looks good to me."
                }
            ],
            "nextApprovers": [
                {
                    "userId": "user789",
                    "name": "Priya Patel",
                    "role": "CEO"
                }
            ]
        }
    }
    
    def generate_tool_id():
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
    
    # Add main header
    title_text = header_text
    heading_tool = {
        "toolId": generate_tool_id(),
        "toolType": "HEADING",
        "textData": {
            "text": title_text,
            "isBold": True,
            "isItalic": False,
            "isUnderlined": False,
            "textAliend": "LEFT",
            "color": 4294967295,  # White
            "fontSize": 14
        },
        "boxData": {
            "fillColor": 4288111521,  # Blue background
            "borderEnable": False,
            "borderColor": 4294967295,
            "borderWidth": 0.8,
            "boxAlignment": "CENTER_LEFT",
            "cornerRadius": {
                "topLeft": 0,
                "topRight": 0,
                "bottomLeft": 0,
                "bottomRight": 0
            },
            "padding": {
                "top": 4,
                "bottom": 4,
                "left": 9,
                "right": 4
            },
            "margin": {
                "top": 0,
                "bottom": 0,
                "left": 0,
                "right": 0
            }
        },
        "toolWidth": 1.7976931348623157e+308
    }
    template["pageToolsDataList"].append(heading_tool)
    
    # Add supplier information
    supplier_text = {
        "toolId": generate_tool_id(),
        "toolType": "TEXT",
        "textData": {
            "text": f"Supplier Name: {supplier_name}",
            "isBold": True,
            "isItalic": False,
            "isUnderlined": False,
            "textAliend": "LEFT",
            "color": 4278190080,  # Black
            "fontSize": 12
        },
        "toolHeight": 30,
        "toolWidth": 1.7976931348623157e+308
    }
    template["pageToolsDataList"].append(supplier_text)
    
    # Group parameters by section for better organization
    sections = {}
    for param in parameters:
        section = param.get("Section", "General Parameters")
        if section not in sections:
            sections[section] = []
        sections[section].append(param)
    
    # Add parameters organized by sections
    for section_name, section_params in sections.items():
        # Add section header
        if section_name != "General Parameters":
            section_header = {
                "toolId": generate_tool_id(),
                "toolType": "TEXT",
                "textData": {
                    "text": section_name.upper(),
                    "isBold": True,
                    "isItalic": False,
                    "isUnderlined": True,
                    "textAliend": "LEFT",
                    "color": 4283215696,  # Green
                    "fontSize": 13
                },
                "toolHeight": 35,
                "toolWidth": 1.7976931348623157e+308
            }
            template["pageToolsDataList"].append(section_header)
        
        # Add parameters in this section
        for param in section_params:
            param_name = param.get("Parameter", "")
            param_type = param.get("Type", "Text Input")
            spec = param.get("Spec", "")
            options = param.get("DropdownOptions", "")
            include_remarks = param.get("IncludeRemarks", "No")
            clause_ref = param.get("ClauseReference", "")
            
            # Create display name with clause reference
            display_name = param_name
            if clause_ref:
                display_name += f" ({clause_ref})"
            
            # Split options into a list if it's a string
            option_list = []
            if isinstance(options, str) and options.strip():
                option_list = [opt.strip() for opt in options.split(",") if opt.strip()]
            
            # PARAMETER TYPE HANDLING
            if param_type == "Image Upload":
                # Create image upload tool with toggle
                image_tool = {
                    "toolId": generate_tool_id(),
                    "toolType": "IMAGE",
                    "imageLableData": {
                        "text": display_name + ":",
                        "isBold": True,
                        "isItalic": False,
                        "isUnderlined": False,
                        "textAliend": "LEFT",
                        "fontSize": 14,
                        "lablePositioned": "LEFT",
                        "spacing": 10,
                        "txtColor": 4278190080,  # Black
                        "showLable": True
                    },
                    "imageData": {
                        "showImageUploadArea": True,
                        "width": 200,
                        "height": 150
                    },
                    "iconData": 57344,
                    "showIcon": False,
                    "iconCodePoint": 59729,
                    "iconSize": 30,
                    "iconColor": 4278190080,  # Black
                    "toolHeight": 160,
                    "toolWidth": 1.7976931348623157e+308,
                    "showToggle": True,
                    "imageToggleData": {
                        "label": "Assessment",
                        "isBold": True,
                        "isItalic": False,
                        "isUnderlined": False,
                        "fontSize": 14,
                        "showLabel": True,
                        "enabledText": "Acceptable",
                        "disabledText": "Not Acceptable",
                        "enabledColor": 4283215696,  # Green
                        "disabledColor": 4294198070,  # Red
                        "isSelected": True
                    }
                }
                template["pageToolsDataList"].append(image_tool)
                
            elif param_type == "Toggle":
                # Create toggle tool
                toggle_tool = {
                    "toolId": generate_tool_id(),
                    "toolType": "TOGGLE",
                    "toggleData": {
                        "disabledColor": 4294198070,  # Red
                        "disabledText": "Not Acceptable" if not option_list else option_list[1] if len(option_list) > 1 else "No",
                        "enabledColor": 4283215696,  # Green
                        "enabledText": "Acceptable" if not option_list else option_list[0] if option_list else "Yes",
                        "showLabel": True,
                        "label": display_name,
                        "labelFontSize": 14,
                        "labelTextColor": 4278190080,  # Black
                        "isBold": True,
                        "isItalic": False,
                        "isSelected": True,
                        "toggleTextFontSize": 12,
                        "toggleTextIsBold": False
                    },
                    "toolWidth": 1.7976931348623157e+308,
                    "toolHeight": 80
                }
                template["pageToolsDataList"].append(toggle_tool)
                
            elif param_type == "Dropdown":
                # Create dropdown tool
                dropdown_tool = {
                    "toolId": generate_tool_id(),
                    "toolType": "DROPDOWN",
                    "dropdownData": {
                        "hintText": f"Select {param_name.lower()}",
                        "hintTextColor": 4288585374,  # Gray
                        "hintFontSize": 14,
                        "dropdownWidth": 350,
                        "spacingBetweeenLableAndDropdownWidth": 10,
                        "showLable": True,
                        "labelText": display_name,
                        "isBold": True,
                        "isItalic": False,
                        "isUnderlined": False,
                        "textAliend": "LEFT",
                        "lablePositioned": "TOP",
                        "labelFontSize": 14,
                        "lableTextColor": 4278190080,  # Black
                        "numberOfOptions": len(option_list) if option_list else 3,
                        "optionFontSize": 14,
                        "optionTextColor": 4278190080,  # Black
                        "optionLst": option_list if option_list else ["Acceptable", "Marginal", "Not Acceptable"],
                        "selectedOptionIndex": -1
                    },
                    "toolHeight": 90,
                    "toolWidth": 1.7976931348623157e+308
                }
                template["pageToolsDataList"].append(dropdown_tool)
                
            elif param_type == "Checklist":
                # Create checkbox tool for checklists
                if not option_list:
                    option_list = ["Item 1", "Item 2", "Item 3"]
                    
                checkbox_tool = {
                    "toolId": generate_tool_id(),
                    "toolType": "CHECKBOX",
                    "checkboxData": {
                        "numberOfCheckboxes": len(option_list),
                        "checkboxBgColor": 4294967295,  # White
                        "spacing": 8,
                        "runSpacing": 8,
                        "checkboxTileWidth": 140,
                        "checkBoxAlignmentEnum": "HORIZONTAL",
                        "checkBoxButtonStyleEnum": "CHECKBOX",
                        "checkBoxPositionedEnum": "START",
                        "checkBoxSelectionModeEnum": "MULTIPLE",
                        "isBold": False,
                        "isItalic": False,
                        "isUnderlined": False,
                        "textAliend": "LEFT",
                        "fontSize": 13,
                        "lablePositioned": "LEFT",
                        "txtColor": 4278190080,  # Black
                        "labelLst": option_list,
                        "showLable": True,
                        "selectedIndexLstForMultiSelect": [],
                        "selectedIndexForSingleSelect": 0
                    },
                    "toolWidth": 1.7976931348623157e+308,
                    "toolHeight": max(100, len(option_list) * 15 + 40)  # Dynamic height based on items
                }
                
                # Add section label for checklist
                checklist_label = {
                    "toolId": generate_tool_id(),
                    "toolType": "TEXT",
                    "textData": {
                        "text": display_name + ":",
                        "isBold": True,
                        "isItalic": False,
                        "isUnderlined": False,
                        "textAliend": "LEFT",
                        "color": 4278190080,  # Black
                        "fontSize": 14
                    },
                    "toolHeight": 25,
                    "toolWidth": 1.7976931348623157e+308
                }
                template["pageToolsDataList"].append(checklist_label)
                template["pageToolsDataList"].append(checkbox_tool)
                
            elif param_type == "Numeric Input":
                # Create numeric input with specification
                label_text = display_name
                if spec:
                    label_text += f" (Spec: {spec})"
                    
                numeric_tool = {
                    "toolId": generate_tool_id(),
                    "toolType": "TEXTAREA",
                    "lableData": {
                        "text": label_text + ":",
                        "isBold": True,
                        "isItalic": False,
                        "isUnderlined": False,
                        "textAliend": "LEFT",
                        "fontSize": 14,
                        "lablePositioned": "TOP_LEFT",
                        "spacing": 5,
                        "txtColor": 4278190080,  # Black
                        "showLable": True
                    },
                    "textAreaData": {
                        "isFilled": True,
                        "fillColor": 4292927712,  # Light gray
                        "borderType": "UNDERLINED",
                        "storkStyle": "LINE",
                        "dummyTxt": "Enter numeric value" + (f" ({spec})" if spec else ""),
                        "borderColor": 4278190080,  # Black
                        "isBold": False,
                        "isItalic": False,
                        "isUnderlined": False,
                        "fontSize": 12,
                        "txtColor": 4288585374  # Gray
                    },
                    "toolHeight": 75,
                    "toolWidth": 1.7976931348623157e+308,
                    "toggleData": {
                        "label": "Status",
                        "isBold": True,
                        "isItalic": False,
                        "isUnderlined": False,
                        "fontSize": 12,
                        "showLabel": True,
                        "enabledText": "Within Spec",
                        "disabledText": "Out of Spec",
                        "enabledColor": 4283215696,  # Green
                        "disabledColor": 4294198070,  # Red
                        "isSelected": True
                    },
                    "showToggle": True  # Show toggle for spec compliance
                }
                template["pageToolsDataList"].append(numeric_tool)
                
            elif param_type == "Text Input":
                # Create text input
                text_tool = {
                    "toolId": generate_tool_id(),
                    "toolType": "TEXTAREA",
                    "lableData": {
                        "text": display_name + ":",
                        "isBold": True,
                        "isItalic": False,
                        "isUnderlined": False,
                        "textAliend": "LEFT",
                        "fontSize": 14,
                        "lablePositioned": "TOP_LEFT",
                        "spacing": 5,
                        "txtColor": 4278190080,  # Black
                        "showLable": True
                    },
                    "textAreaData": {
                        "isFilled": True,
                        "fillColor": 4292927712,  # Light gray
                        "borderType": "UNDERLINED",
                        "storkStyle": "LINE",
                        "dummyTxt": "Enter " + param_name.lower(),
                        "borderColor": 4278190080,  # Black
                        "isBold": False,
                        "isItalic": False,
                        "isUnderlined": False,
                        "fontSize": 12,
                        "txtColor": 4288585374  # Gray
                    },
                    "toolHeight": 65,
                    "toolWidth": 1.7976931348623157e+308,
                    "showToggle": False
                }
                template["pageToolsDataList"].append(text_tool)
                
            elif param_type == "Remarks":
                # Create remarks/textarea
                remarks_tool = {
                    "toolId": generate_tool_id(),
                    "toolType": "TEXTAREA",
                    "lableData": {
                        "text": display_name + ":",
                        "isBold": True,
                        "isItalic": False,
                        "isUnderlined": False,
                        "textAliend": "LEFT",
                        "fontSize": 14,
                        "lablePositioned": "TOP_LEFT",
                        "spacing": 5,
                        "txtColor": 4278190080,  # Black
                        "showLable": True
                    },
                    "textAreaData": {
                        "isFilled": True,
                        "fillColor": 4292927712,  # Light gray
                        "borderType": "UNDERLINED",
                        "storkStyle": "LINE",
                        "dummyTxt": "Enter detailed observations and remarks",
                        "borderColor": 4278190080,  # Black
                        "isBold": False,
                        "isItalic": False,
                        "isUnderlined": False,
                        "fontSize": 12,
                        "txtColor": 4288585374  # Gray
                    },
                    "toolHeight": 100,  # Larger height for remarks
                    "toolWidth": 1.7976931348623157e+308,
                    "showToggle": False
                }
                template["pageToolsDataList"].append(remarks_tool)
            
            # Add additional remarks field if requested and not already a remarks parameter
            if include_remarks == "Yes" and param_type != "Remarks":
                additional_remarks = {
                    "toolId": generate_tool_id(),
                    "toolType": "TEXTAREA",
                    "lableData": {
                        "text": f"{param_name} - Additional Remarks:",
                        "isBold": False,
                        "isItalic": True,
                        "isUnderlined": False,
                        "textAliend": "LEFT",
                        "fontSize": 12,
                        "lablePositioned": "TOP_LEFT",
                        "spacing": 5,
                        "txtColor": 4278190080,  # Black
                        "showLable": True
                    },
                    "textAreaData": {
                        "isFilled": True,
                        "fillColor": 4292927712,  # Light gray
                        "borderType": "UNDERLINED",
                        "storkStyle": "LINE",
                        "dummyTxt": "Additional observations or corrective actions",
                        "borderColor": 4278190080,  # Black
                        "isBold": False,
                        "isItalic": False,
                        "isUnderlined": False,
                        "fontSize": 11,
                        "txtColor": 4288585374  # Gray
                    },
                    "toolHeight": 60,
                    "toolWidth": 1.7976931348623157e+308,
                    "showToggle": False
                }
                template["pageToolsDataList"].append(additional_remarks)
    
    # Add final overall assessment section
    final_assessment_header = {
        "toolId": generate_tool_id(),
        "toolType": "TEXT",
        "textData": {
            "text": "FINAL ASSESSMENT",
            "isBold": True,
            "isItalic": False,
            "isUnderlined": True,
            "textAliend": "CENTER",
            "color": 4283215696,  # Green
            "fontSize": 14
        },
        "toolHeight": 35,
        "toolWidth": 1.7976931348623157e+308
    }
    template["pageToolsDataList"].append(final_assessment_header)
    
    # Overall quality assessment toggle
    overall_toggle = {
        "toolId": generate_tool_id(),
        "toolType": "TOGGLE",
        "toggleData": {
            "disabledColor": 4294198070,  # Red
            "disabledText": "REJECTED",
            "enabledColor": 4283215696,  # Green
            "enabledText": "APPROVED",
            "showLabel": True,
            "label": "Overall Quality Assessment",
            "labelFontSize": 15,
            "labelTextColor": 4278190080,  # Black
            "isBold": True,
            "isItalic": False,
            "isSelected": True,
            "toggleTextFontSize": 14,
            "toggleTextIsBold": True
        },
        "toolWidth": 1.7976931348623157e+308,
        "toolHeight": 100
    }
    template["pageToolsDataList"].append(overall_toggle)
    
    # Inspector signature and date
    inspector_info = {
        "toolId": generate_tool_id(),
        "toolType": "TEXTAREA",
        "lableData": {
            "text": "Inspector Name & Signature:",
            "isBold": True,
            "isItalic": False,
            "isUnderlined": False,
            "textAliend": "LEFT",
            "fontSize": 14,
            "lablePositioned": "TOP_LEFT",
            "spacing": 5,
            "txtColor": 4278190080,  # Black
            "showLable": True
        },
        "textAreaData": {
            "isFilled": True,
            "fillColor": 4292927712,  # Light gray
            "borderType": "UNDERLINED",
            "storkStyle": "LINE",
            "dummyTxt": "Inspector name and signature",
            "borderColor": 4278190080,  # Black
            "isBold": False,
            "isItalic": False,
            "isUnderlined": False,
            "fontSize": 12,
            "txtColor": 4288585374  # Gray
        },
        "toolHeight": 80,
        "toolWidth": 1.7976931348623157e+308,
        "showToggle": False
    }
    template["pageToolsDataList"].append(inspector_info)
    
    # Final comprehensive remarks
    final_remarks = {
        "toolId": generate_tool_id(),
        "toolType": "TEXTAREA",
        "lableData": {
            "text": "Final Comprehensive Remarks:",
            "isBold": True,
            "isItalic": False,
            "isUnderlined": False,
            "textAliend": "LEFT",
            "fontSize": 14,
            "lablePositioned": "TOP_LEFT",
            "spacing": 5,
            "txtColor": 4278190080,  # Black
            "showLable": True
        },
        "textAreaData": {
            "isFilled": True,
            "fillColor": 4292927712,  # Light gray
            "borderType": "UNDERLINED",
            "storkStyle": "LINE",
            "dummyTxt": "Overall assessment, corrective actions, and additional observations",
            "borderColor": 4278190080,  # Black
            "isBold": False,
            "isItalic": False,
            "isUnderlined": False,
            "fontSize": 12,
            "txtColor": 4288585374  # Gray
        },
        "toolHeight": 120,
        "toolWidth": 1.7976931348623157e+308,
        "showToggle": False
    }
    template["pageToolsDataList"].append(final_remarks)
    
    return template

# OCR and text extraction functions
def extract_text_from_document(filepath, file_ext):
    """Enhanced text extraction using Azure Document Intelligence"""
    try:
        from azure_document_intelligence import azure_doc_intelligence
        
        # Use Azure Document Intelligence for better OCR
        extracted_data = azure_doc_intelligence.analyze_document(filepath)
        
        # Enhanced text with structure preservation
        enhanced_text = extracted_data["text"]
        
        # Add table information
        if extracted_data["tables"]:
            enhanced_text += "\n\n=== EXTRACTED TABLES ===\n"
            for i, table in enumerate(extracted_data["tables"]):
                enhanced_text += f"\nTable {i+1} ({table['rows']}x{table['columns']}):\n"
                for row in table["content"]:
                    enhanced_text += " | ".join(row) + "\n"
        
        # Add section information
        if extracted_data["sections"]:
            enhanced_text += "\n\n=== DETECTED SECTIONS ===\n"
            for section in extracted_data["sections"]:
                enhanced_text += f"- {section['title']}\n"
        
        print(f"✅ Enhanced OCR: {len(enhanced_text)} chars, {len(extracted_data['tables'])} tables, {len(extracted_data['sections'])} sections")
        return enhanced_text
        
    except Exception as e:
        print(f"❌ Azure Document Intelligence failed, falling back to basic OCR: {e}")
        
        # Fallback to basic OCR
        try:
            import fitz
            import pytesseract
            from PIL import Image
            import pdf2image
            
            if file_ext == 'pdf':
                pdf_document = fitz.open(filepath)
                extracted_text = ""
                
                for page_num in range(pdf_document.page_count):
                    page = pdf_document[page_num]
                    text = page.get_text()
                    
                    if len(text.strip()) < 100:
                        # Use OCR for scanned pages
                        mat = fitz.Matrix(3, 3)
                        pix = page.get_pixmap(matrix=mat)
                        img_data = pix.pil_tobytes(format="PNG")
                        
                        from io import BytesIO
                        image = Image.open(BytesIO(img_data))
                        text = pytesseract.image_to_string(image)
                    
                    extracted_text += f"\n=== PAGE {page_num + 1} ===\n{text}\n"
                
                pdf_document.close()
                return extracted_text
            
            else:  # Image files
                image = Image.open(filepath)
                text = pytesseract.image_to_string(image)
                return text
                
        except Exception as fallback_error:
            print(f"❌ Fallback OCR also failed: {fallback_error}")
            return None
def enhance_table_structure(text):
    """Enhance text to better preserve table structures and headings"""
    if not text:
        return text
    
    # Preserve important section headings
    section_patterns = [
        (r'(ORGANOLEPTIC\s+EVALUATION)', r'\n## \1\n'),
        (r'(COOKING\s+DETAILS)', r'\n## \1\n'),
        (r'(PACKAGING\s*&\s*FREEZING)', r'\n## \1\n'),
        (r'(FREEZING\s+DETAILS)', r'\n## \1\n'),
        (r'(METAL\s+SCREENING)', r'\n## \1\n'),
        (r'(SIZE\s+VARIATIONS)', r'\n## \1\n'),
        (r'(COLOUR\s+VARIATIONS)', r'\n## \1\n'),
        (r'(EVALUATION\s+OF\s+PASTRY)', r'\n## \1\n'),
        (r'(FINAL\s+ASSESSMENT)', r'\n## \1\n'),
    ]
    
    processed_text = text
    for pattern, replacement in section_patterns:
        processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
    
    # Preserve parameter-value pairs
    param_patterns = [
        (r'([A-Za-z\s]+):\s*(Acceptable|Non-acceptable|Present|Absent|To be mentioned)', r'**\1**: \2'),
        (r'([A-Za-z\s]+)\s+(Sam\s+\d+)', r'**\1** - \2'),
        (r'(Temperature|Weight|Time|Dimension[s]?)[:\s]+([0-9\-\+\±°C\s\w]+)', r'**\1**: \2'),
    ]
    
    for pattern, replacement in param_patterns:
        processed_text = re.sub(pattern, replacement, processed_text, flags=re.IGNORECASE)
    
    # Clean up excessive whitespace while preserving structure
    processed_text = re.sub(r'\n\s*\n\s*\n', '\n\n', processed_text)
    processed_text = re.sub(r'[ \t]+', ' ', processed_text)
    
    return processed_text

def extract_metadata_from_ocr(ocr_text, filename=""):
    """Enhanced metadata extraction"""
    try:
        from azure_document_intelligence import azure_doc_intelligence
        return azure_doc_intelligence.extract_enhanced_metadata(ocr_text, filename)
    except:
        # Fallback to basic extraction
        return {
            "document_type": "QC Checklist",
            "product_name": "Food Product", 
            "supplier_name": "Al Kabeer"
        }
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def fetch_json_from_firebase(firebase_json_url):
    """Fetch JSON template from Firebase Storage URL"""
    try:
        response = requests.get(firebase_json_url)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"Error fetching JSON from Firebase: {str(e)}")
        return None

# API Routes
@app.route("/")
def index():
    return """
    <html>
    <head>
        <title>Swift Check API</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f8f9fa; }
            .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .endpoint { margin: 25px 0; border: 1px solid #ddd; padding: 20px; border-radius: 8px; background: #fafafa; }
            .new { border-left: 4px solid #28a745; background: #f8fff9; }
            .{ border-left: 4px solid #007bff; background: #f8fcff; }
            code { background-color: #e9ecef; padding: 3px 6px; font-family: 'Courier New', monospace; border-radius: 3px; }
            pre { background-color: #e9ecef; padding: 15px; border-radius: 5px; overflow: auto; }
            h1 { color: #333; text-align: center; margin-bottom: 30px; }
            h2 { color: #4CAF50; }
            h3 { color: #333; }
            .method { font-weight: bold; color: #e74c3c; }
            .optional { color: #3498db; }
            .badge { background: #28a745; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin-left: 10px; }
            .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }
            .feature { padding: 15px; background: #e8f5e8; border-radius: 8px; border-left: 4px solid #28a745; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Swift Check API </h1>
            
  
            <h2>API Endpoints:</h2>
            
            <div class="endpoint ">
                <h3><span class="method">POST</span> <code>/refine</code> - Create QC Template</h3>
                <p>Creates comprehensive quality control templates with 15+ parameters, regulatory compliance, and intelligent type selection.</p>
                <h4>Parameters:</h4>
                <ul>
                    <li><code>doc_type</code> <strong>(required)</strong> - Document type</li>
                    <li><code>product_name</code> <strong>(required)</strong> - Product name</li>
                    <li><code>supplier_name</code> <strong>(required)</strong> - Supplier name</li>
                    <li><code>user_message</code> <span class="optional">(optional)</span> - Additional instructions</li>
                    <li><code>context_file</code> <span class="optional">(optional)</span> - Reference document</li>
                </ul>
            </div>
            
            <div class="endpoint ">
                <h3><span class="method">POST</span> <code>/edit</code> - Edit existing template</h3>
                <p>Modifies existing templates using comprehensive context and intelligent parameter optimization.</p>
            </div>   

            
            <div class="endpoint new">
                <h3><span class="method">POST</span> <code>/digitize</code> - Document Digitization</h3>
                <p>OCR processing with table structure recognition and intelligent parameter extraction.</p>
                
                <h4>Parameters (multipart/form-data):</h4>
                <ul>
                    <li><code>checklist_file</code> <strong>(required)</strong> - Scanned document</li>
                    <li><code>doc_type</code> <span class="optional">(optional)</span> - Document type</li>
                    <li><code>product_name</code> <span class="optional">(optional)</span> - Product name</li>
                    <li><code>supplier_name</code> <span class="optional">(optional)</span> - Supplier name</li>
                </ul>
            </div>
            
            <div class="endpoint">
                <h3><span class="method">GET</span> <code>/template/{request_id}</code> - Get Template JSON</h3>
                <p>Returns professionally formatted JSON templates with intelligent parameter types.</p>
            </div>
            
            <div class="endpoint">
                <h3><span class="method">GET</span> <code>/history</code> - View Request History</h3>
                <p>Browse all QC requests with preview and download options.</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/refine", methods=["POST"])
@rate_limit("/refine")
@audit_log("CREATE", "TEMPLATE", lambda result, *args, **kwargs: result.json.get('request_id') if hasattr(result, 'json') else 'unknown')
def refine_parameters():
    """refine endpoint with comprehensive RAG and intelligent parameter generation"""
    global global_parameters
    global global_json_template

    print(">> /refine route called <<")

    # Handle both form data and JSON
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        data = {
            "doc_type": request.form.get("doc_type", ""),
            "product_name": request.form.get("product_name", ""),
            "supplier_name": request.form.get("supplier_name", ""),
            "user_message": request.form.get("user_message", "")
        }
            
        # Handle file upload with OCR
        uploaded_file = request.files.get('context_file')
        file_context = ""
        
        if uploaded_file and allowed_file(uploaded_file.filename):
            filename = secure_filename(uploaded_file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower()
            
            temp_dir = tempfile.mkdtemp()
            filepath = os.path.join(temp_dir, filename)
            uploaded_file.save(filepath)
            
            # text extraction
            extracted_text = extract_text_from_document(filepath, file_ext)
            
            os.unlink(filepath)
            os.rmdir(temp_dir)
            
            if extracted_text:
                file_context = f"\n\nReference document content ({filename}):\n{extracted_text}"
                print(f"✅ OCR extracted {len(extracted_text)} characters from {filename}")
            else:
                file_context = f"\n\n[Failed to extract text from {filename}]"
                
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload found"}), 400
        file_context = ""

    # Validate required fields
    doc_type = data.get("doc_type", "")
    product_name = data.get("product_name", "")
    supplier_name = data.get("supplier_name", "")
    
    if not doc_type:
        return jsonify({"error": "doc_type is required"}), 400
    if not product_name:
        return jsonify({"error": "product_name is required"}), 400
    if not supplier_name:
        return jsonify({"error": "supplier_name is required"}), 400
    
    # Use default prompt if none provided
    user_message = data.get("user_message", "")
    if not user_message:
        user_message = DEFAULT_REFINE_PROMPT
    else:
        user_message = DEFAULT_REFINE_PROMPT + "\n\nAdditional instructions: " + user_message

    # Add file context to user message if available
    if file_context:
        user_message += file_context

    try:
        request_id = cosmos_db.create_qc_request(doc_type, product_name, supplier_name, user_message)
        print(f"✅ Created request with ID: {request_id}")
        
        # Call LLM with comprehensive RAG
        llm_response = call_groq_llm(
            user_message=user_message,
            doc_type=doc_type,
            product_name=product_name,
            supplier_name=supplier_name,
            is_digitization=False
        )

        print("\n🎯 LLM RESPONSE:")
        print("=" * 50)
        print(llm_response[:500] + "..." if len(llm_response) > 500 else llm_response)
        print("=" * 50)

        # Parse response with handling
        summary_text, changes_list = parse_llm_changes(llm_response)
        
        # Store LLM response
        cosmos_db.save_llm_response(request_id, llm_response, summary_text)
        
        # Apply changes with parameter handling
        updated_params = apply_changes_to_params([], changes_list)
        global_parameters = updated_params
        
        print(f"✅ Generated {len(updated_params)} parameters")
        
        cosmos_db.save_parameters(request_id, updated_params)
        
        # Generate JSON template
        json_template = generate_json_template(
            doc_type=doc_type,
            product_name=product_name,
            supplier_name=supplier_name,
            parameters=updated_params
        )
        global_json_template = json_template
        
        # Store JSON template
        cosmos_db.save_json_template(request_id, json_template)
        
        response_data = {
            "success": True, 
            "request_id": request_id,
            "message": f"QC template created with {len(updated_params)} comprehensive parameters", 
            "summary": summary_text,
            "parameters_count": len(updated_params),
            "enhancements": {
                "comprehensive_rag": True,
                "regulatory_compliance": True,
                "intelligent_types": True,
                "minimum_15_params": len(updated_params) >= 15
            }
        }
        
        if file_context:
            response_data["file_info"] = f"OCR processed {filename}" if 'filename' in locals() else "File processed with OCR"
            
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in /refine: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@app.route("/edit", methods=["POST"])
@rate_limit("/edit")
@audit_log("UPDATE", "TEMPLATE", lambda result, *args, **kwargs: result.json.get('request_id') if hasattr(result, 'json') else 'unknown')
def edit_parameters():
    """edit endpoint with comprehensive context and intelligent optimization - NOW ACCEPTS JSON FILE"""
    global global_parameters
    global global_json_template

    print(">> /edit route called <<")

    # Handle both form data and JSON
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        data = {
            "request_id": request.form.get("request_id"),
            "user_message": request.form.get("user_message", "")
        }
            
        # Handle context file upload with OCR
        uploaded_file = request.files.get('context_file')
        file_context = ""
        
        if uploaded_file and allowed_file(uploaded_file.filename):
            filename = secure_filename(uploaded_file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower()
            
            temp_dir = tempfile.mkdtemp()
            filepath = os.path.join(temp_dir, filename)
            uploaded_file.save(filepath)
            
            extracted_text = extract_text_from_document(filepath, file_ext)
            
            os.unlink(filepath)
            os.rmdir(temp_dir)
            
            if extracted_text:
                file_context = f"\n\nReference document content ({filename}):\n{extracted_text}"
                print(f"✅ OCR extracted {len(extracted_text)} characters from {filename}")
            else:
                file_context = f"\n\n[Failed to extract text from {filename}]"

        # Handle JSON template file upload
        json_template_file = request.files.get('json_template_file')
        json_template_data = None
        
        if json_template_file and json_template_file.filename.endswith('.json'):
            try:
                json_content = json_template_file.read().decode('utf-8')
                json_template_data = json.loads(json_content)
                print(f"✅ JSON template file loaded: {json_template_file.filename}")
            except Exception as e:
                print(f"❌ Error loading JSON file: {str(e)}")
                return jsonify({"error": f"Invalid JSON file: {str(e)}"}), 400
                
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload found"}), 400
        file_context = ""
        json_template_data = data.get("json_template_data")  # For direct JSON payload

    # Validate required fields
    user_message = data.get("user_message", "")
    if not user_message:
        return jsonify({"error": "user_message is required for editing"}), 400
    
    request_id = data.get("request_id")
    
    if not request_id and not json_template_data:
        return jsonify({"error": "Either request_id or json_template_file is required"}), 400
    
    # Add file context to user message if available
    if file_context:
        user_message += file_context

    try:
        existing_parameters = []
        doc_type = ""
        product_name = ""
        supplier_name = ""
        
        if request_id:
            # Get original request data from Cosmos DB
            query = "SELECT * FROM c WHERE c.id = @request_id"
            items = list(cosmos_db.qc_requests.query_items(
                query=query,
                parameters=[{"name": "@request_id", "value": request_id}]
            ))
            
            if not items:
                return jsonify({"error": f"Request ID {request_id} not found"}), 404
            
            original_data = items[0]
            doc_type = original_data["doc_type"]
            product_name = original_data["product_name"] 
            supplier_name = original_data["supplier_name"]
            
            # Get existing parameters from Cosmos DB
            param_query = "SELECT * FROM c WHERE c.request_id = @request_id"
            param_items = list(cosmos_db.parameters.query_items(
                query=param_query,
                parameters=[{"name": "@request_id", "value": request_id}]
            ))
            
            existing_parameters = [
                {
                    "Parameter": item["parameter_name"], 
                    "Type": item["type"], 
                    "Spec": item["spec"], 
                    "DropdownOptions": item["dropdown_options"], 
                    "IncludeRemarks": item["include_remarks"],
                    "Section": item["section"],
                    "ClauseReference": item["clause_reference"]
                } 
                for item in param_items
            ]
            
        elif json_template_data:
            # JSON template processing
            template_data = json_template_data
            
            # parameter extraction from JSON template
            existing_parameters = []
            
            for tool in template_data.get("pageToolsDataList", []):
                tool_type = tool.get("toolType", "")
                
                if tool_type == "DROPDOWN":
                    dropdown_data = tool.get("dropdownData", {})
                    existing_parameters.append({
                        "Parameter": dropdown_data.get("labelText", "Dropdown Field"),
                        "Type": "Dropdown",
                        "Spec": "",
                        "DropdownOptions": ", ".join(dropdown_data.get("optionLst", [])),
                        "IncludeRemarks": "No",
                        "Section": "General",
                        "ClauseReference": ""
                    })
                elif tool_type == "CHECKBOX":
                    checkbox_data = tool.get("checkboxData", {})
                    existing_parameters.append({
                        "Parameter": "Checklist Group",
                        "Type": "Checklist",
                        "Spec": "",
                        "DropdownOptions": ", ".join(checkbox_data.get("labelLst", [])),
                        "IncludeRemarks": "No",
                        "Section": "General",
                        "ClauseReference": ""
                    })
                elif tool_type == "IMAGE":
                    image_data = tool.get("imageLableData", {})
                    existing_parameters.append({
                        "Parameter": image_data.get("text", "Image Upload").replace(":", ""),
                        "Type": "Image Upload",
                        "Spec": "Visual inspection with photo evidence",
                        "DropdownOptions": "",
                        "IncludeRemarks": "Yes",
                        "Section": "Visual Inspection",
                        "ClauseReference": ""
                    })
                elif tool_type == "TOGGLE":
                    toggle_data = tool.get("toggleData", {})
                    existing_parameters.append({
                        "Parameter": toggle_data.get("label", "Toggle Assessment"),
                        "Type": "Toggle",
                        "Spec": "",
                        "DropdownOptions": f"{toggle_data.get('enabledText', 'Yes')}, {toggle_data.get('disabledText', 'No')}",
                        "IncludeRemarks": "No",
                        "Section": "Assessment",
                        "ClauseReference": ""
                    })
                elif tool_type == "TEXTAREA":
                    label_data = tool.get("lableData", {})
                    text_area_data = tool.get("textAreaData", {})
                    label_text = label_data.get("text", "").replace(":", "")
                    
                    if "Remarks" in label_text or "remarks" in text_area_data.get("dummyTxt", ""):
                        param_type = "Remarks"
                    elif "numeric" in text_area_data.get("dummyTxt", "").lower():
                        param_type = "Numeric Input"
                    else:
                        param_type = "Text Input"
                        
                    existing_parameters.append({
                        "Parameter": label_text,
                        "Type": param_type,
                        "Spec": "",
                        "DropdownOptions": "",
                        "IncludeRemarks": "No",
                        "Section": "General",
                        "ClauseReference": ""
                    })
                    
            # Extract basic info from template
            for tool in template_data.get("pageToolsDataList", []):
                if tool.get("toolType") == "HEADING":
                    title_text = tool.get("textData", {}).get("text", "")
                    parts = title_text.split(" ", 1)
                    if len(parts) >= 2:
                        product_name = parts[0]
                        doc_type = parts[1]
                    else:
                        product_name = title_text
                        doc_type = "Inspection Document"
                    break
                    
            if not product_name:
                product_name = "Product"
            if not doc_type:
                doc_type = "Inspection Document"
                
            # Find supplier info
            for tool in template_data.get("pageToolsDataList", []):
                if tool.get("toolType") == "TEXT":
                    text = tool.get("textData", {}).get("text", "")
                    if "Supplier" in text:
                        supplier_name = text.replace("Supplier Name:", "").strip()
                        break
                        
            if not supplier_name:
                supplier_name = "Unknown Supplier"
        
        # Create new version in Cosmos DB
        created_id = cosmos_db.create_qc_request(doc_type, product_name, supplier_name, user_message)
        print(f"✅ Created edit version with ID: {created_id}")
        
        # Call LLM with comprehensive context
        message = f"EDIT REQUEST: {user_message}\n\nExisting parameters for optimization and enhancement: {len(existing_parameters)} parameters"
        llm_response = call_groq_llm(
            user_message=message,
            doc_type=doc_type,
            product_name=product_name,
            supplier_name=supplier_name,
            existing_parameters=existing_parameters,
            is_digitization=False
        )

        print(f"\n🎯 EDIT LLM RESPONSE:")
        print("=" * 50)
        print(llm_response[:500] + "..." if len(llm_response) > 500 else llm_response)
        print("=" * 50)

        # Parse and apply changes with handling
        summary_text, changes_list = parse_llm_changes(llm_response)
        
        # Store LLM response in Cosmos DB
        cosmos_db.save_llm_response(created_id, llm_response, summary_text)
        
        updated_params = apply_changes_to_params(existing_parameters, changes_list)
        global_parameters = updated_params
        
        print(f"✅ edit generated {len(updated_params)} optimized parameters")
        
        # Store parameters in Cosmos DB
        cosmos_db.save_parameters(created_id, updated_params)
        
        # Generate JSON template  
        json_template = generate_json_template(
            doc_type=doc_type,
            product_name=product_name,
            supplier_name=supplier_name,
            parameters=updated_params
        )
        global_json_template = json_template
        
        # Store JSON template in Cosmos DB
        cosmos_db.save_json_template(created_id, json_template)
        
        response_data = {
            "success": True, 
            "request_id": created_id,
            "message": f"template edited with {len(updated_params)} optimized parameters", 
            "summary": summary_text,
            "parameters_count": len(updated_params),
            "enhancements": {
                "context_aware_editing": True,
                "intelligent_optimization": True,
                "regulatory_compliance": True,''
                "comprehensive_coverage": len(updated_params) >= 15
            }
        }
        
        if request_id:
            response_data["original_request_id"] = request_id
        if json_template_data:
            response_data["json_template_processed"] = True
        if file_context:
            response_data["file_info"] = f"OCR processed {filename}" if 'filename' in locals() else "File processed with OCR"
            
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in /edit: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/digitize", methods=["POST"])
@rate_limit("/digitize")
@audit_log("CREATE", "TEMPLATE", lambda result, *args, **kwargs: result.json.get('request_id') if hasattr(result, 'json') else 'unknown')
def digitize_checklist():
    """digitization with advanced OCR and intelligent parameter extraction"""
    print(">> /digitize route called <<")
    
    if 'checklist_file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['checklist_file']
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Allowed: PDF, PNG, JPG, JPEG"}), 400
    
    # Get optional parameters
    doc_type = request.form.get("doc_type", "")
    product_name = request.form.get("product_name", "")
    supplier_name = request.form.get("supplier_name", "")
    
    try:
        filename = secure_filename(file.filename)
        temp_dir = tempfile.mkdtemp()
        filepath = os.path.join(temp_dir, filename)
        file.save(filepath)

        # text extraction with table structure preservation
        file_ext = filename.rsplit('.', 1)[1].lower()
        extracted_text = extract_text_from_document(filepath, file_ext)

        os.unlink(filepath)
        os.rmdir(temp_dir)

        if not extracted_text:
            return jsonify({"error": "Failed to extract text from file"}), 500

        print(f"✅ OCR extracted {len(extracted_text)} characters from {filename}")
        print(f"📄 Preview: {extracted_text[:300]}...")

        # metadata extraction
        if not doc_type or not product_name or not supplier_name:
            metadata = extract_metadata_from_ocr(extracted_text, filename)
            detected_doc_type = metadata["document_type"]
            detected_product = metadata["product_name"] 
            detected_supplier = metadata["supplier_name"]

        # LLM processing for digitization
        llm_prompt = f"""
I've extracted text from a scanned QC checklist using OCR with table structure preservation. 

DOCUMENT ANALYSIS:
- File: {filename}
- Detected Document Type: {doc_type}
- Detected Product: {product_name}
- Detected Supplier: {supplier_name}

EXTRACTED TEXT WITH STRUCTURE:
{extracted_text}

Please perform COMPREHENSIVE DIGITIZATION with:

1. **TABLE STRUCTURE PRESERVATION**: Maintain section headings and organization
2. **INTELLIGENT PARAMETER EXTRACTION**: Convert each item to appropriate parameter type
3. **SPECIFICATION EXTRACTION**: Capture tolerance limits, measurement units, acceptable ranges
4. **REGULATORY COMPLIANCE**: Include any regulatory references or compliance requirements
5. **COMPREHENSIVE COVERAGE**: Ensure minimum 15+ parameters for professional QC checklist

Focus on creating a PROFESSIONAL, COMPREHENSIVE parameter set that maintains the structure and intelligence of the original document while using modern parameter types and ensuring regulatory compliance.
"""
        
        
        # Call LLM for digitization
        llm_response = call_groq_llm(
            user_message=llm_prompt,
            doc_type=doc_type,
            product_name=product_name,
            supplier_name=supplier_name,
            is_digitization=True
        )
        
        print(f"\n🎯 DIGITIZATION LLM RESPONSE:")
        print("=" * 50)
        print(llm_response[:500] + "..." if len(llm_response) > 500 else llm_response)
        print("=" * 50)
        
        # Parse parameters with handling
        json_array_text = extract_top_level_json_array(llm_response)
        parameters = []
        
        if json_array_text:
            try:
                parameters = json.loads(json_array_text)
                # parameter processing
                processed_params = []
                for param in parameters:
                    if isinstance(param, dict) and param.get("Parameter", "").strip():
                        # Ensure parameter has meaningful content
                        param_name = param.get("Parameter", "").strip()
                        if param_name and param_name.lower() not in ["unknown", "parameter", "option", "item"]:
                            processed_params.append(param)
                parameters = processed_params
            except Exception as e:
                print(f"❌ JSON parse error: {e}")
                return jsonify({"error": f"Failed to parse LLM response: {str(e)}"}), 500
        
        if not parameters:
            return jsonify({"error": "No meaningful parameters extracted from document"}), 500
        
        # Save to Cosmos DB
        request_id = cosmos_db.create_qc_request(doc_type, product_name, supplier_name)
        
        # Store LLM response
        cosmos_db.save_llm_response(request_id, llm_response, f"digitization: {len(parameters)} comprehensive parameters extracted from {filename}")
        
        # Store parameters
        cosmos_db.save_parameters(request_id, parameters)
        
        # Generate JSON template
        json_template = generate_json_template(
            doc_type=doc_type,
            product_name=product_name,
            supplier_name=supplier_name,
            parameters=parameters
        )
        
        # Store JSON template
        cosmos_db.save_json_template(request_id, json_template)
        
        # response data
        response_data = {
            "success": True,
            "request_id": request_id,
            "message": f"digitization: {len(parameters)} comprehensive parameters extracted from {filename}",
            "parameters_count": len(parameters),
            "extracted_parameters": [p.get("Parameter", "") for p in parameters],
            "doc_type": doc_type,
            "product_name": product_name,
            "supplier_name": supplier_name,
            "enhancements": {
                "table_structure_preserved": True,
                "intelligent_type_detection": True,
                "comprehensive_extraction": len(parameters) >= 10,
                "specification_extraction": any(p.get("Spec") for p in parameters),
                "section_organization": any(p.get("Section") != "General" for p in parameters)
            },
            "file_processing": {
                "filename": filename,
                "text_extracted": len(extracted_text),
                "ocr_": True
            }
        }
            
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in /digitize: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# Existing routes with features
@app.route("/history", methods=["GET"])
def view_history():
    """history view with additional metadata"""
    if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
        try:
            # Get all requests from Cosmos DB
            requests = cosmos_db.get_all_requests()
            
            result = []
            for req in requests:
                # Count parameters for each request
                param_query = "SELECT * FROM c WHERE c.request_id = @request_id"
                param_items = list(cosmos_db.parameters.query_items(
                    query=param_query,
                    parameters=[{"name": "@request_id", "value": req["id"]}]
                ))
                
                result.append({
                    "id": req["id"],
                    "doc_type": req["doc_type"],
                    "product_name": req["product_name"],
                    "supplier_name": req["supplier_name"],
                    "created_at": req["created_at"],
                    "parameter_count": len(param_items)
                })
            
            # Sort by created_at descending
            result.sort(key=lambda x: x["created_at"], reverse=True)
            return jsonify(result)
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    # HTML view
    try:
        # Get all requests from Cosmos DB
        requests = cosmos_db.get_all_requests()
        
        rows = []
        for req in requests:
            # Count parameters for each request
            param_query = "SELECT * FROM c WHERE c.request_id = @request_id"
            param_items = list(cosmos_db.parameters.query_items(
                query=param_query,
                parameters=[{"name": "@request_id", "value": req["id"]}]
            ))
            
            rows.append((
                req["id"],
                req["doc_type"],
                req["product_name"],
                req["supplier_name"],
                req["created_at"],
                len(param_items)
            ))
        
        # Sort by created_at descending
        rows.sort(key=lambda x: x[4], reverse=True)
        
        html = """
        <html>
        <head>
            <title>QC Request History</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background-color: #f8f9fa; }
                .container { max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                table { border-collapse: collapse; width: 100%; margin-top: 20px; }
                th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
                th { background-color: #4CAF50; color: white; font-weight: bold; }
                tr:nth-child(even) { background-color: #f2f2f2; }
                tr:hover { background-color: #e8f5e8; }
                a { color: #4CAF50; text-decoration: none; margin: 0 5px; padding: 4px 8px; border-radius: 3px; }
                a:hover { background-color: #4CAF50; color: white; }
                .badge { background: #28a745; color: white; padding: 2px 6px; border-radius: 10px; font-size: 11px; }
                .param-count { font-weight: bold; color: #007bff; }
                h1 { color: #333; text-align: center; margin-bottom: 30px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>QC Request History </h1>
                <table>
                    <tr>
                        <th>ID</th>
                        <th>Product</th>
                        <th>Doc Type</th>
                        <th>Supplier</th>
                        <th>Parameters</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
        """
        
        for row in rows:
            param_badge = "🎯" if row[5] >= 15 else "⚠️" if row[5] >= 10 else "❌"
            html += f"""
                <tr>
                    <td>{row[0]}</td>
                    <td><strong>{row[2]}</strong></td>
                    <td>{row[1]}</td>
                    <td>{row[3]}</td>
                    <td class="param-count">{param_badge} {row[5]} params</td>
                    <td>{row[4]}</td>
                    <td>
                        <a href="/preview/{row[0]}">Preview</a>
                        <a href="/template/{row[0]}">JSON</a>
                    </td>
                </tr>
            """
        
        html += """
                </table>
                <div style="margin-top: 20px; padding: 15px; background: #e8f5e8; border-radius: 5px;">
                    <strong>Legend:</strong> 
                    🎯 15+ params (Professional) | 
                    ⚠️ 10-14 params (Good) | 
                    ❌ <10 params (Basic)
                </div>
            </div>
        </body>
        </html>
        """
        return html
        
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>", 500
@app.route("/debug/audit", methods=["POST"])
def debug_audit():
    """Debug audit logging"""
    try:
        from audit_logger import audit_logger
        
        # Manual audit log test
        audit_logger.log_event(
            event_type="DEBUG_TEST",
            entity_type="TEMPLATE", 
            entity_id="debug-test-123",
            details={"test": "manual audit log"},
            tenant_id="default"
        )
        
        return jsonify({
            "success": True,
            "message": "Debug audit log created"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/cache/stats", methods=["GET"])
def cache_stats():
    """Get cache statistics"""
    try:
        stats = azure_cache.get_cache_stats()
        return jsonify({
            "success": True,
            "cache_stats": stats
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cache/clear", methods=["POST"])
def clear_cache():
    """Clear cache entries"""
    try:
        azure_cache.clear_cache()
        return jsonify({
            "success": True,
            "message": "Cache cleared successfully"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/template/<request_id>", methods=["GET"])
def get_template_json(request_id):
    """Get template JSON by request ID"""
    try:
        template_data = cosmos_db.get_template_by_request_id(str(request_id))
        
        if template_data:
            return jsonify(template_data)
        else:
            return jsonify({"error": f"template not found for request ID {request_id}"}), 404
            
    except Exception as e:
        print(f"❌ Error in /template/{request_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/preview/<request_id>", methods=["GET"])
def preview_page(request_id):
    """preview with better formatting and metadata"""
    try:
        # Get template JSON from Cosmos DB
        template_data = cosmos_db.get_template_by_request_id(str(request_id))
        
        # Get parameters from Cosmos DB
        param_query = "SELECT * FROM c WHERE c.request_id = @request_id"
        param_items = list(cosmos_db.parameters.query_items(
            query=param_query,
            parameters=[{"name": "@request_id", "value": str(request_id)}]
        ))
        
        # Convert to tuple format for existing code
        parameters = [
            (
                item["parameter_name"],
                item["type"],
                item["spec"],
                item["dropdown_options"],
                item["include_remarks"],
                item["section"],
                item["clause_reference"]
            ) for item in param_items
        ]
        
        # Get request details from Cosmos DB
        req_query = "SELECT * FROM c WHERE c.id = @request_id"
        req_items = list(cosmos_db.qc_requests.query_items(
            query=req_query,
            parameters=[{"name": "@request_id", "value": str(request_id)}]
        ))
        
        if req_items:
            req = req_items[0]
            request_details = (req["doc_type"], req["product_name"], req["supplier_name"])
        else:
            request_details = None
        
        if not template_data:
            return f"""
            <html>
            <head><title>Not Found</title></head>
            <body>
                <h1>Template not found</h1>
                <p>No template exists for request ID {request_id}</p>
                <a href="/history">View History</a>
            </body>
            </html>
            """, 404
            
        json_template = template_data
        
        # Generate ASCII preview with sections
        ascii_preview = "╔══════════════════════════════════════════════════════════════════════╗\n"
        
        if request_details:
            header = f"{request_details[1]} {request_details[0]}"
        else:
            header = "QC Template"
        
        header_padding = (70 - len(header)) // 2
        ascii_preview += f"║{' ' * header_padding}{header}{' ' * (70 - header_padding - len(header))}║\n"
        
        if request_details and request_details[2]:
            supplier = f"Supplier: {request_details[2]}"
            supplier_padding = (70 - len(supplier)) // 2
            ascii_preview += f"║{' ' * supplier_padding}{supplier}{' ' * (70 - supplier_padding - len(supplier))}║\n"
            
        ascii_preview += "╚══════════════════════════════════════════════════════════════════════╝\n\n"
        
        # Group parameters by section
        sections = {}
        for param in parameters:
            param_name, param_type, spec, options, include_remarks, section, clause_ref = param
            section = section or "General Parameters"
            if section not in sections:
                sections[section] = []
            sections[section].append(param)
        
        # Add parameters organized by sections
        for section_name, section_params in sections.items():
            ascii_preview += f"\n🔹 {section_name.upper()}\n"
            ascii_preview += "─" * 60 + "\n"
            
            for param in section_params:
                param_name, param_type, spec, options, include_remarks, section, clause_ref = param
                
                # Add clause reference if available
                display_name = param_name
                if clause_ref:
                    display_name += f" ({clause_ref})"
                
                if param_type == "Image Upload":
                    ascii_preview += f"[📷] {display_name}: [ Upload Photo ] + Toggle Assessment\n"
                elif param_type == "Toggle":
                    ascii_preview += f"[◐] {display_name}: ● Acceptable ○ Not Acceptable\n"
                elif param_type == "Dropdown":
                    ascii_preview += f"[▼] {display_name}: _________________ "
                    if options:
                        option_list = [opt.strip() for opt in options.split(",")[:3]]
                        ascii_preview += f"({', '.join(option_list)}{'...' if len(options.split(',')) > 3 else ''})\n"
                    else:
                        ascii_preview += "\n"
                elif param_type == "Checklist":
                    ascii_preview += f"    {display_name}:\n"
                    if options:
                        option_list = [opt.strip() for opt in options.split(",")]
                        for opt in option_list[:5]:
                            ascii_preview += f"    ☐ {opt}\n"
                        if len(option_list) > 5:
                            ascii_preview += f"    ... and {len(option_list) - 5} more items\n"
                    else:
                        ascii_preview += "    ☐ Item 1\n"
                elif param_type == "Numeric Input":
                    ascii_preview += f"[#️⃣] {display_name}: _____________"
                    if spec:
                        ascii_preview += f" (Spec: {spec})\n"
                    else:
                        ascii_preview += "\n"
                elif param_type == "Text Input":
                    ascii_preview += f"[✏️] {display_name}: _____________________________\n"
                elif param_type == "Remarks":
                    ascii_preview += f"[📝] {display_name}:\n"
                    ascii_preview += "    ┌─────────────────────────────────────┐\n"
                    ascii_preview += "    │                                     │\n"
                    ascii_preview += "    │                                     │\n"
                    ascii_preview += "    └─────────────────────────────────────┘\n"
                
                if include_remarks == "Yes" and param_type != "Remarks":
                    ascii_preview += f"    └─ Additional Remarks: _______________________\n"
                
                ascii_preview += "\n"
        
        # Add final assessment
        ascii_preview += "═" * 70 + "\n"
        ascii_preview += "🎯 FINAL ASSESSMENT\n"
        ascii_preview += "═" * 70 + "\n"
        ascii_preview += "[✅] Overall Quality Assessment: ● APPROVED ○ REJECTED\n\n"
        ascii_preview += "[👤] Inspector Name & Signature: _________________________________\n\n"
        ascii_preview += "[📝] Final Comprehensive Remarks:\n"
        ascii_preview += "    ┌─────────────────────────────────────────────────────────────┐\n"
        ascii_preview += "    │ Overall assessment, corrective actions, and observations    │\n"
        ascii_preview += "    │                                                             │\n"
        ascii_preview += "    │                                                             │\n"
        ascii_preview += "    └─────────────────────────────────────────────────────────────┘\n"
        
        # statistics
        total_params = len(parameters)
        param_types = {}
        sections_count = len(sections)
        regulatory_refs = sum(1 for param in parameters if param[6])  # clause references
        
        for param in parameters:
            param_type = param[1]
            param_types[param_type] = param_types.get(param_type, 0) + 1
        
        html = f"""
        <html>
        <head>
            <title> QC Template Preview - Request #{request_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f8f9fa; }}
                .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .preview-section {{ margin: 25px 0; }}
                .ascii-preview {{ 
                    background-color: #1a1a1a; 
                    color: #00ff41; 
                    padding: 25px; 
                    border-radius: 8px; 
                    overflow: auto; 
                    font-family: 'Courier New', monospace;
                    font-size: 13px;
                    line-height: 1.4;
                    white-space: pre;
                    border: 2px solid #00ff41;
                }}
                .json-section {{ 
                    background-color: #f8f9fa; 
                    padding: 20px; 
                    border-radius: 8px; 
                    overflow: auto; 
                    max-height: 500px;
                    border: 1px solid #dee2e6;
                }}
                .stats-section {{
                    background: linear-gradient(135deg, #e8f5e8, #f0f8f0);
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #28a745;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                    gap: 15px;
                    margin: 15px 0;
                }}
                .stat-item {{
                    text-align: center;
                    padding: 15px;
                    background: white;
                    border-radius: 8px;
                    border: 1px solid #28a745;
                    font-size: 14px;
                }}
                h1, h2, h3 {{ color: #333; }}
                h1 {{ text-align: center; margin-bottom: 30px; }}
                button {{ 
                    background: linear-gradient(135deg, #28a745, #20c997);
                    color: white; 
                    padding: 12px 20px; 
                    border: none; 
                    border-radius: 6px; 
                    cursor: pointer; 
                    margin: 10px 5px;
                    font-weight: bold;
                    transition: all 0.3s ease;
                }}
                button:hover {{ 
                    transform: translateY(-2px);
                    box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3);
                }}
                .button-group {{ margin: 25px 0; text-align: center; }}
                .badge {{ background: #28a745; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px; }}
                .quality-badge {{ 
                    background: {'#28a745' if total_params >= 15 else '#ffc107' if total_params >= 10 else '#dc3545'};
                    color: white;
                    padding: 6px 12px;
                    border-radius: 15px;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>  QC Template Preview - Request #{request_id} 
                </h1>
                
                
                <div class="preview-section">
                    <h2>🖥️ ASCII Preview</h2>
                    <div class="ascii-preview">{ascii_preview}</div>
                </div>
                
                <div class="preview-section">
                    <h2>📋 JSON Template</h2>
                    <div class="button-group">
                        <button onclick="copyToClipboard()">📋 Copy JSON to Clipboard</button>
                        <button onclick="toggleJsonVisibility()">👁️ Toggle JSON View</button>
                        <button onclick="downloadJson()">💾 Download JSON</button>
                    </div>
                    <div id="jsonSection" class="json-section" style="display: none;">
                        <pre id="jsonContent">{json.dumps(json_template, indent=2)}</pre>
                    </div>
                </div>
                
                <div class="button-group">
                    <button onclick="window.location.href='/history'">⬅️ Back to History</button>
                    <button onclick="window.location.href='/template/{request_id}'">🔗 Direct JSON API</button>
                </div>
            </div>
            
            <script>
                function copyToClipboard() {{
                    const jsonContent = document.getElementById('jsonContent').textContent;
                    navigator.clipboard.writeText(jsonContent)
                        .then(() => alert('✅ JSON copied to clipboard!'))
                        .catch(err => console.error('❌ Failed to copy: ', err));
                }}
                
                function toggleJsonVisibility() {{
                    const jsonSection = document.getElementById('jsonSection');
                    jsonSection.style.display = jsonSection.style.display === 'none' ? 'block' : 'none';
                }}
                
                function downloadJson() {{
                    const jsonContent = document.getElementById('jsonContent').textContent;
                    const blob = new Blob([jsonContent], {{type: 'application/json'}});
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'qc_template_{request_id}.json';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                    URL.revokeObjectURL(url);
                }}
            </script>
        </body>
        </html>
        """
        return html
        
    except Exception as e:
        print(f"❌ Error in /preview/{request_id}: {str(e)}")
        return f"<h1>Error</h1><p>{str(e)}</p>", 500
    
@app.route("/upload/async", methods=["POST"])
@rate_limit("/upload/async")
def async_file_upload():
    """Async file upload with background processing"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # Get optional parameters
        doc_type = request.form.get("doc_type", "QC Document")
        product_name = request.form.get("product_name", "Unknown Product")
        supplier_name = request.form.get("supplier_name", "Unknown Supplier")
        
        # Create QC request
        request_id = cosmos_db.create_qc_request(doc_type, product_name, supplier_name)
        
        # Upload to blob storage
        blob_connection = get_blob_connection()
        blob_client = BlobServiceClient.from_connection_string(blob_connection)
        
        # Generate unique blob name
        file_ext = Path(file.filename).suffix
        blob_name = f"{request_id}_{uuid.uuid4()}{file_ext}"
        
        # Upload file
        blob_client_instance = blob_client.get_blob_client(
            container="uploads", 
            blob=blob_name
        )
        
        file.seek(0)
        blob_client_instance.upload_blob(file.read(), overwrite=True)
        blob_url = blob_client_instance.url
        
        # Trigger background processing
        success = trigger_background_processing(blob_url, "uploads", blob_name, request_id)
        
        if success:
            return jsonify({
                "success": True,
                "request_id": request_id,
                "message": "File uploaded successfully. Processing started in background.",
                "blob_url": blob_url,
                "status": "processing",
                "estimated_completion": "2-5 minutes"
            })
        else:
            return jsonify({
                "success": True,
                "request_id": request_id,
                "message": "File uploaded successfully. Processing will start shortly.",
                "blob_url": blob_url,
                "status": "queued"
            })
        
    except Exception as e:
        print(f"❌ Error in async upload: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/upload/status/<request_id>", methods=["GET"])
def check_upload_status(request_id):
    """Check status of async file processing"""
    try:
        # Get request from Cosmos DB
        query = "SELECT * FROM c WHERE c.id = @request_id"
        items = list(cosmos_db.qc_requests.query_items(
            query=query,
            parameters=[{"name": "@request_id", "value": request_id}]
        ))
        
        if not items:
            return jsonify({"error": "Request not found"}), 404
        
        request_doc = items[0]
        
        # Check processing status
        processing_status = request_doc.get("processing_status", "queued")
        processing_metadata = request_doc.get("processing_metadata", {})
        
        response = {
            "request_id": request_id,
            "status": processing_status,
            "created_at": request_doc["created_at"],
            "updated_at": request_doc.get("updated_at", request_doc["created_at"]),
            "doc_type": request_doc["doc_type"],
            "product_name": request_doc["product_name"],
            "supplier_name": request_doc["supplier_name"]
        }
        
        if processing_status == "processed":
            response["processing_metadata"] = processing_metadata
            response["message"] = "Document processed successfully"
            
            # Check if parameters were generated
            param_count = len(cosmos_db.get_parameters_by_request_id(request_id))
            response["parameters_generated"] = param_count
            
        elif processing_status == "error":
            response["error"] = processing_metadata.get("error", "Unknown error")
            response["message"] = "Document processing failed"
            
        else:
            response["message"] = "Document processing in progress"
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def trigger_background_processing(blob_url, container_name, blob_name, request_id):
    """Trigger background processing job"""
    try:
        # For now, we'll simulate triggering a Container Apps Job
        # In actual deployment, this would trigger via Event Grid or HTTP call
        
        print(f"🔄 Would trigger background job for: {blob_name}")
        print(f"   - Blob URL: {blob_url}")
        print(f"   - Request ID: {request_id}")
        
        # Update request status to indicate processing started
        query = "SELECT * FROM c WHERE c.id = @request_id"
        items = list(cosmos_db.qc_requests.query_items(
            query=query,
            parameters=[{"name": "@request_id", "value": request_id}]
        ))
        
        if items:
            request_doc = items[0]
            request_doc["processing_status"] = "processing"
            request_doc["blob_url"] = blob_url
            request_doc["blob_name"] = blob_name
            request_doc["updated_at"] = datetime.now().isoformat()
            
            cosmos_db.qc_requests.replace_item(
                item=request_doc["id"], 
                body=request_doc
            )
        
        return True
        
    except Exception as e:
        print(f"❌ Error triggering background processing: {e}")
        return False
@app.route("/audit/trail", methods=["GET"])
def get_audit_trail():
    """Get audit trail"""
    try:
        from audit_logger import audit_logger
        
        entity_type = request.args.get("entity_type")
        entity_id = request.args.get("entity_id")
        tenant_id = request.args.get("tenant_id", "default")
        limit = int(request.args.get("limit", 100))
        
        trail = audit_logger.get_audit_trail(entity_type, entity_id, tenant_id, limit)
        
        return jsonify({
            "success": True,
            "audit_trail": trail,
            "count": len(trail)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/audit/user/<user_id>", methods=["GET"])
def get_user_audit(user_id):
    """Get user audit activity"""
    try:
        from audit_logger import audit_logger
        
        tenant_id = request.args.get("tenant_id", "default")
        days = int(request.args.get("days", 30))
        
        activity = audit_logger.get_user_activity(user_id, tenant_id, days)
        
        return jsonify({
            "success": True,
            "user_id": user_id,
            "activity_summary": activity,
            "period_days": days
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/jobs/trigger", methods=["POST"])
def trigger_manual_job():
    """Manually trigger background processing job (for testing)"""
    try:
        data = request.get_json()
        blob_url = data.get("blob_url")
        container_name = data.get("container_name", "uploads")
        blob_name = data.get("blob_name")
        request_id = data.get("request_id")
        
        if not blob_url or not blob_name:
            return jsonify({"error": "Missing blob_url or blob_name"}), 400
        
        # In actual deployment, this would call Container Apps Job
        # For now, simulate the processing
        success = trigger_background_processing(blob_url, container_name, blob_name, request_id)
        
        return jsonify({
            "success": success,
            "message": "Background processing triggered" if success else "Failed to trigger processing",
            "job_parameters": {
                "blob_url": blob_url,
                "container_name": container_name,
                "blob_name": blob_name,
                "request_id": request_id
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Container Apps"""
    try:
        # Test key services
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "environment": os.getenv("AZURE_ENVIRONMENT", "development"),
            "services": {}
        }
        
        # Test Azure services
        try:
            # Test Cosmos DB
            from cosmos_db_utils import enhanced_cosmos_db
            test_requests = enhanced_cosmos_db.get_all_requests()
            health_status["services"]["cosmos_db"] = "healthy"
        except Exception as e:
            health_status["services"]["cosmos_db"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"
        
        try:
            # Test Redis Cache
            from azure_cache_utils import azure_cache
            azure_cache.redis_client.ping()
            health_status["services"]["redis_cache"] = "healthy"
        except Exception as e:
            health_status["services"]["redis_cache"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"
        
        try:
            # Test Key Vault
            from azure_secrets import azure_secrets
            test_secret = azure_secrets.get_secret("openai-key")
            if test_secret:
                health_status["services"]["key_vault"] = "healthy"
            else:
                health_status["services"]["key_vault"] = "unhealthy: no secrets"
                health_status["status"] = "degraded"
        except Exception as e:
            health_status["services"]["key_vault"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"
        
        # Return appropriate HTTP status
        if health_status["status"] == "healthy":
            return jsonify(health_status), 200
        else:
            return jsonify(health_status), 503
            
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503

# Add startup info endpoint
@app.route("/info", methods=["GET"])
def app_info():
    """Application information endpoint"""
    return jsonify({
        "app_name": "Swift Check AI",
        "version": "2.0.0",
        "environment": os.getenv("AZURE_ENVIRONMENT", "development"),
        "azure_services": {
            "cosmos_db": "enabled",
            "openai": "enabled", 
            "ai_search": "enabled",
            "redis_cache": "enabled",
            "key_vault": "enabled",
            "document_intelligence": "enabled"
        },
        "endpoints": [
            "/health",
            "/info", 
            "/refine",
            "/edit",
            "/digitize",
            "/template/<request_id>",
            "/history",
            "/cache/stats",
            "/cache/clear"
        ]
    })
@app.before_request
def before_request():
    """Track request start and rate limiting"""
    g.request_id = performance_monitor.track_request_start(
        request.endpoint or request.path,
        request.method
    )
    azure_monitoring.track_request(
        endpoint=request.endpoint or request.path,
        method=request.method,
        status_code=0  # Will be updated in after_request
    )
@app.route("/workflow/create", methods=["POST"])
def create_workflow():
    """Create approval workflow"""
    try:
        data = request.get_json()
        request_id = data.get("request_id")
        template_data = data.get("template_data")
        tenant_id = data.get("tenant_id", "default")
        
        if not request_id or not template_data:
            return jsonify({"error": "Missing request_id or template_data"}), 400
        
        workflow_id = workflow_engine.create_approval_workflow(
            request_id, template_data, tenant_id
        )
        
        return jsonify({
            "success": True,
            "workflow_id": workflow_id,
            "message": "Approval workflow created"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/workflow/approve", methods=["POST"])
def submit_approval():
    """Submit approval decision"""
    try:
        data = request.get_json()
        workflow_id = data.get("workflow_id")
        approver_id = data.get("approver_id")
        approver_role = data.get("approver_role")
        decision = data.get("decision")  # "approved" or "rejected"
        comments = data.get("comments", "")
        
        if not all([workflow_id, approver_id, approver_role, decision]):
            return jsonify({"error": "Missing required fields"}), 400
        
        if decision not in ["approved", "rejected"]:
            return jsonify({"error": "Decision must be 'approved' or 'rejected'"}), 400
        
        workflow = workflow_engine.submit_approval(
            workflow_id, approver_id, approver_role, decision, comments
        )
        
        return jsonify({
            "success": True,
            "workflow": workflow,
            "message": f"Approval {decision} successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/workflow/pending/<approver_role>", methods=["GET"])
def get_pending_approvals(approver_role):
    """Get pending approvals for role"""
    try:
        tenant_id = request.args.get("tenant_id", "default")
        
        pending = workflow_engine.get_pending_approvals(approver_role, tenant_id)
        
        return jsonify({
            "success": True,
            "pending_approvals": pending,
            "count": len(pending)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Multi-tenant endpoints
@app.route("/tenant/create", methods=["POST"])
def create_tenant():
    """Create new tenant"""
    try:
        data = request.get_json()
        company_name = data.get("company_name")
        contact_email = data.get("contact_email")
        subscription_plan = data.get("subscription_plan", "basic")
        
        if not company_name or not contact_email:
            return jsonify({"error": "Missing company_name or contact_email"}), 400
        
        tenant_id = tenant_manager.create_tenant(
            company_name, contact_email, subscription_plan
        )
        
        return jsonify({
            "success": True,
            "tenant_id": tenant_id,
            "message": "Tenant created successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/tenant/<tenant_id>/analytics", methods=["GET"])
def get_tenant_analytics(tenant_id):
    """Get tenant analytics"""
    try:
        days = int(request.args.get("days", 30))
        
        analytics = analytics_engine.get_dashboard_data(tenant_id, days)
        
        return jsonify({
            "success": True,
            "analytics": analytics
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/analytics/dashboard", methods=["GET"])
def analytics_dashboard():
    """Analytics dashboard endpoint"""
    tenant_id = request.args.get("tenant_id", "default")
    
    try:
        # Get dashboard data
        dashboard_data = analytics_engine.get_dashboard_data(tenant_id)
        performance_metrics = analytics_engine.get_performance_metrics(tenant_id)
        
        return jsonify({
            "success": True,
            "dashboard": dashboard_data,
            "performance": performance_metrics,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.after_request
def after_request(response):
    """Track request completion and add security headers"""
    # Performance tracking
    if hasattr(g, 'request_id'):
        performance_monitor.track_request_end(
            g.request_id,
            response.status_code,
            len(response.get_data())
        )
    
    # Add security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Add rate limit headers
    rate_limit_headers = rate_limiter.get_rate_limit_headers()
    for key, value in rate_limit_headers.items():
        response.headers[key] = value
    from flask import request
    azure_monitoring.track_request(
        endpoint=request.endpoint or request.path,
        method=request.method, 
        status_code=response.status_code
    )
    return response
@app.route("/admin/performance", methods=["GET"])
def performance_dashboard():
    """Performance monitoring dashboard"""
    try:
        stats = performance_monitor.get_performance_stats()
        return jsonify({
            "success": True,
            "performance_stats": stats,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin/rate-limits", methods=["GET"])
def rate_limits_info():
    """Rate limiting information"""
    return jsonify({
        "rate_limits": rate_limiter.default_limits,
        "client_id": rate_limiter.get_client_id(),
        "redis_connected": azure_cache.redis_client.ping()
    })

@app.route("/pdf/template/<request_id>", methods=["GET"])
def generate_template_pdf(request_id):
    """Generate PDF report for QC template"""
    try:
        from pdf_generator import pdf_generator
        
        pdf_bytes = pdf_generator.generate_qc_template_report(request_id)
        
        if pdf_bytes:
            return Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename=qc_template_{request_id}.pdf'
                }
            )
        else:
            return jsonify({"error": "Template not found or PDF generation failed"}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/pdf/analytics", methods=["GET"])
def generate_analytics_pdf():
    """Generate analytics PDF report"""
    try:
        from pdf_generator import pdf_generator
        
        tenant_id = request.args.get("tenant_id", "default")
        days = int(request.args.get("days", 30))
        
        pdf_bytes = pdf_generator.generate_analytics_report(tenant_id, days)
        
        if pdf_bytes:
            return Response(
                pdf_bytes,
                mimetype='application/pdf',
                headers={
                    'Content-Disposition': f'attachment; filename=analytics_report_{tenant_id}.pdf'
                }
            )
        else:
            return jsonify({"error": "Analytics data not found"}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/admin/setup-containers", methods=["POST"])
def setup_containers():
    """Setup missing containers"""
    try:
        # Import here to avoid circular imports
        from cosmos_db_utils import enhanced_cosmos_db
        
        database = enhanced_cosmos_db.database
        
        containers_to_create = [
            "workflow_approvals",
            "tenants", 
            "analytics_events",
            "published_templates"
        ]
        
        created = []
        for container_name in containers_to_create:
            try:
                database.create_container(
                    id=container_name,
                    partition_key={"paths": ["/id"], "kind": "Hash"}
                )
                created.append(container_name)
                print(f"✅ Created container: {container_name}")
            except Exception as e:
                if "already exists" not in str(e).lower():
                    print(f"⚠️ Error creating {container_name}: {e}")
                else:
                    print(f"ℹ️ Container {container_name} already exists")
        
        return jsonify({
            "success": True,
            "containers_created": created,
            "message": f"Setup complete. Created {len(created)} new containers"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("🚀 Starting Swift Check API v2.0...")
    app.run(host="127.0.0.1", port=5000, debug=True)