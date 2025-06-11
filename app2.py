import json
import re
import random
import string
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, g
from werkzeug.utils import secure_filename
from PIL import Image
import pytesseract
import fitz

# Azure Service Imports
from cosmos_db_utils import enhanced_cosmos_db as cosmos_db
from azure_search_utils import get_comprehensive_context, format_context_for_prompt
from azure_cache_utils import azure_cache
from azure_monitoring import azure_monitoring
from azure_openai_utils import azure_openai
from azure_document_intelligence import azure_doc_intelligence
from azure_secrets import get_blob_connection
from azure.storage.blob import BlobServiceClient

# Advanced Features
from rate_limiter import rate_limit
from performance_monitor import performance_monitor
from workflow_engine import workflow_engine
from tenant_manager import tenant_manager
from analytics_engine import analytics_engine
from event_grid_handler import event_grid_handler

# Initialize Flask Application
app = Flask(__name__)
azure_monitoring.init_app(app)

# Global Variables
global_parameters = []
global_json_template = {}

# Configuration
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

# ============================================================================
# CORE PROMPTS AND TEMPLATES
# ============================================================================

SYSTEM_PROMPT = """
You are the Swift Check AI assistant, specialized in creating comprehensive Quality Control (QC) checklists and inspection documents for food products with full regulatory compliance.

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
- Microbiological Specifications (Numeric Input): Total Plate Count, E.coli, Salmonella, etc. with limits
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
- Image Upload: Visual inspections, evidence documentation
- Toggle: Pass/fail decisions, binary assessments
- Checklist: Foreign objects, allergens, multi-item verifications
- Numeric Input: Measurements WITH specifications and units
- Text Input: Codes, dates, identifiers
- Remarks: Detailed observations, corrective actions

Remember: Generate PROFESSIONAL, COMPREHENSIVE checklists that match Al Kabeer Group's quality standards with full regulatory compliance and intelligent parameter type selection.
"""

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

Use intelligent parameter type selection and include specific regulatory clause references where applicable.
"""

DIGITIZE_SYSTEM_PROMPT = """
You are the Swift Check AI digitization assistant. Your job is to analyze OCR-extracted text from scanned QC checklists and convert them into structured parameters for comprehensive food safety and quality control checklists.

# INTELLIGENT PARAMETER TYPE DETECTION:
- Image Upload: Parameters mentioning "photo", "attach", "capture", "visual", "appearance"
- Toggle: Binary choices: "Acceptable/Non-acceptable", "Present/Absent", "Pass/Fail"
- Checklist: Lists of items to verify (foreign objects, allergens, defects)
- Numeric Input: Measurements with units and tolerances
- Text Input: Codes, dates, identifiers
- Remarks: "Remarks", "Comments", "Observations", requiring detailed explanations

Focus on creating comprehensive, professional parameters that maintain the structure and intelligence of the original document.
"""

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_top_level_json_array(text):
    """Extract JSON array from text, handling both raw JSON and code blocks"""
    # Look for JSON code blocks first
    json_block_pattern = r'```json\s*(.*?)\s*```'
    json_block_match = re.search(json_block_pattern, text, re.DOTALL | re.IGNORECASE)
    
    if json_block_match:
        json_content = json_block_match.group(1).strip()
        if json_content.startswith('[') and json_content.endswith(']'):
            return json_content
    
    # Fallback to raw JSON array detection
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

def parse_llm_changes(llm_text):
    """Parse LLM response into summary and changes"""
    json_array_text = extract_top_level_json_array(llm_text)
    changes = []
    
    if json_array_text:
        try:
            changes = json.loads(json_array_text)
        except Exception as e:
            print(f"❌ JSON parse error: {e}")
    
    summary_text = llm_text.replace(json_array_text, "").strip() if json_array_text else llm_text.strip()
    return summary_text, changes

def apply_changes_to_params(parameters, changes):
    """Apply changes to parameters with intelligent handling"""
    valid_types = ["Checklist", "Dropdown", "Image Upload", "Remarks", "Text Input", "Numeric Input", "Toggle"]

    for change in changes:
        if not isinstance(change, dict):
            continue
            
        action = change.get("action", "").lower()
        p_name = change.get("Parameter", "Unnamed")
        options = change.get("DropdownOptions", "") or change.get("ChecklistOptions", "")
        
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
                    p.update({
                        "Type": new_type,
                        "Spec": change.get("Spec", ""),
                        "DropdownOptions": options,
                        "IncludeRemarks": change.get("IncludeRemarks", "No"),
                        "Section": change.get("Section", "General"),
                        "ClauseReference": change.get("ClauseReference", "")
                    })
                    break

    return parameters

def call_llm_with_rag(user_message, doc_type, product_name, supplier_name, existing_parameters=None, is_digitization=False):
    """Call LLM with comprehensive RAG support"""
    return azure_openai.call_openai_llm(
        user_message, doc_type, product_name, supplier_name, existing_parameters, is_digitization
    )

def extract_text_from_document(filepath, file_ext):
    """Enhanced text extraction using Azure Document Intelligence with fallback"""
    try:
        # Try Azure Document Intelligence first
        extracted_data = azure_doc_intelligence.analyze_document(filepath)
        
        enhanced_text = extracted_data["text"]
        
        # Add table information
        if extracted_data.get("tables"):
            enhanced_text += "\n\n=== EXTRACTED TABLES ===\n"
            for i, table in enumerate(extracted_data["tables"]):
                enhanced_text += f"\nTable {i+1} ({table['rows']}x{table['columns']}):\n"
                for row in table["content"]:
                    enhanced_text += " | ".join(row) + "\n"
        
        print(f"✅ Enhanced OCR: {len(enhanced_text)} chars, {len(extracted_data.get('tables', []))} tables")
        return enhanced_text
        
    except Exception as e:
        print(f"⚠️ Azure Document Intelligence failed, using fallback OCR: {e}")
        
        # Fallback to basic OCR
        try:
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
            else:
                # Image files
                image = Image.open(filepath)
                return pytesseract.image_to_string(image)
                
        except Exception as fallback_error:
            print(f"❌ All OCR methods failed: {fallback_error}")
            return None

def extract_metadata_from_ocr(ocr_text, filename=""):
    """Extract metadata from OCR text with enhanced detection"""
    try:
        return azure_doc_intelligence.extract_enhanced_metadata(ocr_text, filename)
    except:
        # Fallback to basic extraction
        return {
            "document_type": "QC Checklist",
            "product_name": "Food Product", 
            "supplier_name": "Al Kabeer"
        }

def generate_json_template(doc_type, product_name, supplier_name, parameters):
    """Generate comprehensive JSON template with intelligent parameter handling"""
    def generate_tool_id():
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
    
    header_text = f"{product_name} {doc_type}"
    
    template = {
        "templateId": generate_tool_id(),
        "isDrafted": False,
        "pageStyle": {
            "margin": {"top": 10, "bottom": 10, "left": 10, "right": 10},
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
            "previousApprovers": [],
            "nextApprovers": []
        }
    }
    
    # Add main header
    template["pageToolsDataList"].append({
        "toolId": generate_tool_id(),
        "toolType": "HEADING",
        "textData": {
            "text": header_text,
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
            "cornerRadius": {"topLeft": 0, "topRight": 0, "bottomLeft": 0, "bottomRight": 0},
            "padding": {"top": 4, "bottom": 4, "left": 9, "right": 4},
            "margin": {"top": 0, "bottom": 0, "left": 0, "right": 0}
        },
        "toolWidth": 1.7976931348623157e+308
    })
    
    # Add supplier information
    template["pageToolsDataList"].append({
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
    })
    
    # Group parameters by section
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
            template["pageToolsDataList"].append({
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
            })
        
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
            
            # Add parameter tool based on type
            tool = create_parameter_tool(generate_tool_id, param_type, display_name, spec, option_list, param_name)
            if tool:
                template["pageToolsDataList"].append(tool)
                
                # Add additional remarks field if requested
                if include_remarks == "Yes" and param_type != "Remarks":
                    remarks_tool = create_remarks_tool(generate_tool_id, f"{param_name} - Additional Remarks")
                    template["pageToolsDataList"].append(remarks_tool)
    
    # Add final assessment section
    add_final_assessment_section(template, generate_tool_id)
    
    return template

def create_parameter_tool(generate_tool_id, param_type, display_name, spec, option_list, param_name):
    """Create parameter tool based on type"""
    if param_type == "Image Upload":
        return {
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
                "txtColor": 4278190080,
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
            "iconColor": 4278190080,
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
                "enabledColor": 4283215696,
                "disabledColor": 4294198070,
                "isSelected": True
            }
        }
    
    elif param_type == "Toggle":
        return {
            "toolId": generate_tool_id(),
            "toolType": "TOGGLE",
            "toggleData": {
                "disabledColor": 4294198070,
                "disabledText": "Not Acceptable" if not option_list else option_list[1] if len(option_list) > 1 else "No",
                "enabledColor": 4283215696,
                "enabledText": "Acceptable" if not option_list else option_list[0] if option_list else "Yes",
                "showLabel": True,
                "label": display_name,
                "labelFontSize": 14,
                "labelTextColor": 4278190080,
                "isBold": True,
                "isItalic": False,
                "isSelected": True,
                "toggleTextFontSize": 12,
                "toggleTextIsBold": False
            },
            "toolWidth": 1.7976931348623157e+308,
            "toolHeight": 80
        }
    
    elif param_type == "Dropdown":
        return {
            "toolId": generate_tool_id(),
            "toolType": "DROPDOWN",
            "dropdownData": {
                "hintText": f"Select {param_name.lower()}",
                "hintTextColor": 4288585374,
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
                "lableTextColor": 4278190080,
                "numberOfOptions": len(option_list) if option_list else 3,
                "optionFontSize": 14,
                "optionTextColor": 4278190080,
                "optionLst": option_list if option_list else ["Acceptable", "Marginal", "Not Acceptable"],
                "selectedOptionIndex": -1
            },
            "toolHeight": 90,
            "toolWidth": 1.7976931348623157e+308
        }
    
    elif param_type == "Checklist":
        if not option_list:
            option_list = ["Item 1", "Item 2", "Item 3"]
        
        return {
            "toolId": generate_tool_id(),
            "toolType": "CHECKBOX",
            "checkboxData": {
                "numberOfCheckboxes": len(option_list),
                "checkboxBgColor": 4294967295,
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
                "txtColor": 4278190080,
                "labelLst": option_list,
                "showLable": True,
                "selectedIndexLstForMultiSelect": [],
                "selectedIndexForSingleSelect": 0
            },
            "toolWidth": 1.7976931348623157e+308,
            "toolHeight": max(100, len(option_list) * 15 + 40)
        }
    
    elif param_type == "Numeric Input":
        label_text = display_name
        if spec:
            label_text += f" (Spec: {spec})"
        
        return {
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
                "txtColor": 4278190080,
                "showLable": True
            },
            "textAreaData": {
                "isFilled": True,
                "fillColor": 4292927712,
                "borderType": "UNDERLINED",
                "storkStyle": "LINE",
                "dummyTxt": "Enter numeric value" + (f" ({spec})" if spec else ""),
                "borderColor": 4278190080,
                "isBold": False,
                "isItalic": False,
                "isUnderlined": False,
                "fontSize": 12,
                "txtColor": 4288585374
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
                "enabledColor": 4283215696,
                "disabledColor": 4294198070,
                "isSelected": True
            },
            "showToggle": True
        }
    
    elif param_type == "Text Input":
        return {
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
                "txtColor": 4278190080,
                "showLable": True
            },
            "textAreaData": {
                "isFilled": True,
                "fillColor": 4292927712,
                "borderType": "UNDERLINED",
                "storkStyle": "LINE",
                "dummyTxt": "Enter " + param_name.lower(),
                "borderColor": 4278190080,
                "isBold": False,
                "isItalic": False,
                "isUnderlined": False,
                "fontSize": 12,
                "txtColor": 4288585374
            },
            "toolHeight": 65,
            "toolWidth": 1.7976931348623157e+308,
            "showToggle": False
        }
    
    elif param_type == "Remarks":
        return {
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
                "txtColor": 4278190080,
                "showLable": True
            },
            "textAreaData": {
                "isFilled": True,
                "fillColor": 4292927712,
                "borderType": "UNDERLINED",
                "storkStyle": "LINE",
                "dummyTxt": "Enter detailed observations and remarks",
                "borderColor": 4278190080,
                "isBold": False,
                "isItalic": False,
                "isUnderlined": False,
                "fontSize": 12,
                "txtColor": 4288585374
            },
            "toolHeight": 100,
            "toolWidth": 1.7976931348623157e+308,
            "showToggle": False
        }
    
    return None

def create_remarks_tool(generate_tool_id, label_text):
    """Create additional remarks tool"""
    return {
        "toolId": generate_tool_id(),
        "toolType": "TEXTAREA",
        "lableData": {
            "text": label_text + ":",
            "isBold": False,
            "isItalic": True,
            "isUnderlined": False,
            "textAliend": "LEFT",
            "fontSize": 12,
            "lablePositioned": "TOP_LEFT",
            "spacing": 5,
            "txtColor": 4278190080,
            "showLable": True
        },
        "textAreaData": {
            "isFilled": True,
            "fillColor": 4292927712,
            "borderType": "UNDERLINED",
            "storkStyle": "LINE",
            "dummyTxt": "Additional observations or corrective actions",
            "borderColor": 4278190080,
            "isBold": False,
            "isItalic": False,
            "isUnderlined": False,
            "fontSize": 11,
            "txtColor": 4288585374
        },
        "toolHeight": 60,
        "toolWidth": 1.7976931348623157e+308,
        "showToggle": False
    }

def add_final_assessment_section(template, generate_tool_id):
    """Add final assessment section to template"""
    # Final assessment header
    template["pageToolsDataList"].append({
        "toolId": generate_tool_id(),
        "toolType": "TEXT",
        "textData": {
            "text": "FINAL ASSESSMENT",
            "isBold": True,
            "isItalic": False,
            "isUnderlined": True,
            "textAliend": "CENTER",
            "color": 4283215696,
            "fontSize": 14
        },
        "toolHeight": 35,
        "toolWidth": 1.7976931348623157e+308
    })
    
    # Overall quality assessment toggle
    template["pageToolsDataList"].append({
        "toolId": generate_tool_id(),
        "toolType": "TOGGLE",
        "toggleData": {
            "disabledColor": 4294198070,
            "disabledText": "REJECTED",
            "enabledColor": 4283215696,
            "enabledText": "APPROVED",
            "showLabel": True,
            "label": "Overall Quality Assessment",
            "labelFontSize": 15,
            "labelTextColor": 4278190080,
            "isBold": True,
            "isItalic": False,
            "isSelected": True,
            "toggleTextFontSize": 14,
            "toggleTextIsBold": True
        },
        "toolWidth": 1.7976931348623157e+308,
        "toolHeight": 100
    })
    
    # Inspector signature and date
    template["pageToolsDataList"].append({
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
            "txtColor": 4278190080,
            "showLable": True
        },
        "textAreaData": {
            "isFilled": True,
            "fillColor": 4292927712,
            "borderType": "UNDERLINED",
            "storkStyle": "LINE",
            "dummyTxt": "Inspector name and signature",
            "borderColor": 4278190080,
            "isBold": False,
            "isItalic": False,
            "isUnderlined": False,
            "fontSize": 12,
            "txtColor": 4288585374
        },
        "toolHeight": 80,
        "toolWidth": 1.7976931348623157e+308,
        "showToggle": False
    })
    
    # Final comprehensive remarks
    template["pageToolsDataList"].append({
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
            "txtColor": 4278190080,
            "showLable": True
        },
        "textAreaData": {
            "isFilled": True,
            "fillColor": 4292927712,
            "borderType": "UNDERLINED",
            "storkStyle": "LINE",
            "dummyTxt": "Overall assessment, corrective actions, and additional observations",
            "borderColor": 4278190080,
            "isBold": False,
            "isItalic": False,
            "isUnderlined": False,
            "fontSize": 12,
            "txtColor": 4288585374
        },
        "toolHeight": 120,
        "toolWidth": 1.7976931348623157e+308,
        "showToggle": False
    })

# ============================================================================
# FLASK REQUEST HANDLERS
# ============================================================================

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
        status_code=0
    )

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
    from rate_limiter import rate_limiter
    rate_limit_headers = rate_limiter.get_rate_limit_headers()
    for key, value in rate_limit_headers.items():
        response.headers[key] = value
    
    azure_monitoring.track_request(
        endpoint=request.endpoint or request.path,
        method=request.method, 
        status_code=response.status_code
    )
    return response

# ============================================================================
# MAIN API ROUTES
# ============================================================================

@app.route("/")
def index():
    """API documentation and status"""
    return """
    <html>
    <head>
        <title>Swift Check AI - Enterprise QC Platform</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
            .container { max-width: 1200px; margin: 0 auto; background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); margin-top: 20px; margin-bottom: 20px; }
            .header { text-align: center; margin-bottom: 40px; }
            .header h1 { color: #333; font-size: 2.5em; margin: 0; }
            .header p { color: #666; font-size: 1.2em; margin: 10px 0; }
            .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 25px; margin: 30px 0; }
            .feature { padding: 25px; background: linear-gradient(135deg, #f8fff9, #e8f5e8); border-radius: 10px; border-left: 5px solid #28a745; }
            .feature h3 { color: #28a745; margin-top: 0; }
            .endpoints { margin: 30px 0; }
            .endpoint { margin: 20px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #007bff; }
            .method { font-weight: bold; color: #e74c3c; background: #fff; padding: 4px 8px; border-radius: 4px; }
            .status { text-align: center; margin: 30px 0; padding: 20px; background: linear-gradient(135deg, #d4edda, #c3e6cb); border-radius: 10px; }
            .badge { background: #28a745; color: white; padding: 4px 10px; border-radius: 15px; font-size: 12px; margin-left: 10px; }
            code { background: #e9ecef; padding: 4px 8px; border-radius: 4px; font-family: 'Courier New', monospace; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 Swift Check AI</h1>
                <p>Enterprise Quality Control Platform with AI-Powered Template Generation</p>
                <div class="status">
                    <strong>✅ System Status: OPERATIONAL</strong>
                    <span class="badge">Azure Native</span>
                    <span class="badge">Enterprise Ready</span>
                    <span class="badge">Multi-Tenant</span>
                </div>
            </div>
            
            <div class="features">
                <div class="feature">
                    <h3>🧠 AI-Powered Generation</h3>
                    <p>Intelligent QC template creation with 25+ parameters, regulatory compliance, and smart type selection using Azure OpenAI GPT-4o.</p>
                </div>
                <div class="feature">
                    <h3>📄 Document Intelligence</h3>
                    <p>Advanced OCR with Azure Document Intelligence for table detection, structure preservation, and metadata extraction.</p>
                </div>
                <div class="feature">
                    <h3>🏢 Enterprise Features</h3>
                    <p>Multi-tenant support, workflow approvals, analytics dashboards, and comprehensive monitoring.</p>
                </div>
                <div class="feature">
                    <h3>⚡ High Performance</h3>
                    <p>Redis caching, rate limiting, background processing, and sub-second response times.</p>
                </div>
            </div>
            
            <div class="endpoints">
                <h2>🔗 API Endpoints</h2>
                
                <div class="endpoint">
                    <h3><span class="method">POST</span> <code>/refine</code> - Create QC Template</h3>
                    <p>Generate comprehensive quality control templates with intelligent parameter selection and regulatory compliance.</p>
                    <strong>Parameters:</strong> doc_type, product_name, supplier_name, user_message (optional), context_file (optional)
                </div>
                
                <div class="endpoint">
                    <h3><span class="method">POST</span> <code>/edit</code> - Edit Template</h3>
                    <p>Modify existing templates using comprehensive context and intelligent optimization.</p>
                    <strong>Parameters:</strong> request_id OR json_template_file, user_message, context_file (optional)
                </div>
                
                <div class="endpoint">
                    <h3><span class="method">POST</span> <code>/digitize</code> - Document Digitization</h3>
                    <p>OCR processing with table structure recognition and intelligent parameter extraction.</p>
                    <strong>Parameters:</strong> checklist_file (required), doc_type, product_name, supplier_name (optional)
                </div>
                
                <div class="endpoint">
                    <h3><span class="method">POST</span> <code>/upload/async</code> - Async File Processing</h3>
                    <p>Background file processing with real-time status updates and event notifications.</p>
                </div>
                
                <div class="endpoint">
                    <h3><span class="method">GET</span> <code>/template/{request_id}</code> - Get Template JSON</h3>
                    <p>Retrieve professionally formatted JSON templates with intelligent parameter types.</p>
                </div>
                
                <div class="endpoint">
                    <h3><span class="method">GET</span> <code>/history</code> - Request History</h3>
                    <p>Browse all QC requests with preview and download options.</p>
                </div>
                
                <div class="endpoint">
                    <h3><span class="method">GET</span> <code>/health</code> - Health Check</h3>
                    <p>System health monitoring for Azure Container Apps deployment.</p>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 10px;">
                <p><strong>Swift Check AI v2.0</strong> - Enterprise Quality Control Platform</p>
                <p>Powered by Azure OpenAI, Document Intelligence, Cosmos DB, AI Search & Redis Cache</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route("/refine", methods=["POST"])
@rate_limit("/refine")
def refine_parameters():
    """Create comprehensive QC template with RAG support"""
    global global_parameters, global_json_template

    print("🎯 /refine endpoint called")

    # Handle both form data and JSON
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        data = {
            "doc_type": request.form.get("doc_type", ""),
            "product_name": request.form.get("product_name", ""),
            "supplier_name": request.form.get("supplier_name", ""),
            "user_message": request.form.get("user_message", "")
        }
        
        # Handle file upload with OCR
        file_context = ""
        uploaded_file = request.files.get('context_file')
        
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
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload found"}), 400
        file_context = ""

    # Validate required fields
    doc_type = data.get("doc_type", "")
    product_name = data.get("product_name", "")
    supplier_name = data.get("supplier_name", "")
    
    if not all([doc_type, product_name, supplier_name]):
        return jsonify({"error": "doc_type, product_name, and supplier_name are required"}), 400

    # Prepare user message
    user_message = data.get("user_message", "") or DEFAULT_REFINE_PROMPT
    if data.get("user_message"):
        user_message = DEFAULT_REFINE_PROMPT + "\n\nAdditional instructions: " + data.get("user_message")
    if file_context:
        user_message += file_context

    try:
        # Create QC request
        request_id = cosmos_db.create_qc_request(doc_type, product_name, supplier_name, user_message)
        print(f"✅ Created request: {request_id}")
        
        # Call LLM with comprehensive RAG
        llm_response = call_llm_with_rag(
            user_message, doc_type, product_name, supplier_name, is_digitization=False
        )

        print(f"🎯 LLM Response: {len(llm_response)} characters")

        # Parse and apply changes
        summary_text, changes_list = parse_llm_changes(llm_response)
        cosmos_db.save_llm_response(request_id, llm_response, summary_text)
        
        updated_params = apply_changes_to_params([], changes_list)
        global_parameters = updated_params
        
        print(f"✅ Generated {len(updated_params)} parameters")
        
        # Save to database
        cosmos_db.save_parameters(request_id, updated_params)
        
        # Generate JSON template
        json_template = generate_json_template(doc_type, product_name, supplier_name, updated_params)
        global_json_template = json_template
        cosmos_db.save_json_template(request_id, json_template)
        
        # Track analytics
        analytics_engine.track_event(
            tenant_id="default",
            event_type="template_created",
            event_data={
                "product_name": product_name,
                "doc_type": doc_type,
                "parameters_count": len(updated_params)
            }
        )
        
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
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/edit", methods=["POST"])
@rate_limit("/edit")
def edit_parameters():
    """Edit existing template with context-aware optimization"""
    global global_parameters, global_json_template

    print("🔧 /edit endpoint called")

    # Handle form data and JSON
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        data = {
            "request_id": request.form.get("request_id"),
            "user_message": request.form.get("user_message", "")
        }
        
        # Handle context file upload
        file_context = ""
        uploaded_file = request.files.get('context_file')
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

        # Handle JSON template file upload
        json_template_data = None
        json_template_file = request.files.get('json_template_file')
        if json_template_file and json_template_file.filename.endswith('.json'):
            try:
                json_content = json_template_file.read().decode('utf-8')
                json_template_data = json.loads(json_content)
                print(f"✅ JSON template file loaded: {json_template_file.filename}")
            except Exception as e:
                return jsonify({"error": f"Invalid JSON file: {str(e)}"}), 400
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON payload found"}), 400
        file_context = ""
        json_template_data = data.get("json_template_data")

    # Validate required fields
    user_message = data.get("user_message", "")
    if not user_message:
        return jsonify({"error": "user_message is required for editing"}), 400
    
    request_id = data.get("request_id")
    
    if not request_id and not json_template_data:
        return jsonify({"error": "Either request_id or json_template_file is required"}), 400

    if file_context:
        user_message += file_context

    try:
        existing_parameters = []
        doc_type = product_name = supplier_name = ""
        
        if request_id:
            # Get original request data
            query = "SELECT * FROM c WHERE c.id = @request_id"
            items = list(cosmos_db.qc_requests.query_items(
                query=query,
                parameters=[{"name": "@request_id", "value": request_id}],
                enable_cross_partition_query=True
            ))
            
            if not items:
                return jsonify({"error": f"Request ID {request_id} not found"}), 404
            
            original_data = items[0]
            doc_type = original_data["doc_type"]
            product_name = original_data["product_name"] 
            supplier_name = original_data["supplier_name"]
            
            # Get existing parameters
            existing_parameters = cosmos_db.get_parameters_by_request_id(request_id)
            existing_parameters = [
                {
                    "Parameter": item["parameter_name"], 
                    "Type": item["type"], 
                    "Spec": item["spec"], 
                    "DropdownOptions": item["dropdown_options"], 
                    "IncludeRemarks": item["include_remarks"],
                    "Section": item["section"],
                    "ClauseReference": item["clause_reference"]
                } for item in existing_parameters
            ]
            
        elif json_template_data:
            # Extract parameters from JSON template
            existing_parameters = extract_parameters_from_json_template(json_template_data)
            doc_type, product_name, supplier_name = extract_basic_info_from_template(json_template_data)
        
        # Create new version
        created_id = cosmos_db.create_qc_request(doc_type, product_name, supplier_name, user_message)
        print(f"✅ Created edit version: {created_id}")
        
        # Call LLM with context
        message = f"EDIT REQUEST: {user_message}\n\nExisting parameters for optimization: {len(existing_parameters)} parameters"
        llm_response = call_llm_with_rag(
            message, doc_type, product_name, supplier_name, existing_parameters, is_digitization=False
        )

        # Parse and apply changes
        summary_text, changes_list = parse_llm_changes(llm_response)
        cosmos_db.save_llm_response(created_id, llm_response, summary_text)
        
        updated_params = apply_changes_to_params(existing_parameters, changes_list)
        global_parameters = updated_params
        
        print(f"✅ Edit generated {len(updated_params)} optimized parameters")
        
        # Save results
        cosmos_db.save_parameters(created_id, updated_params)
        json_template = generate_json_template(doc_type, product_name, supplier_name, updated_params)
        global_json_template = json_template
        cosmos_db.save_json_template(created_id, json_template)
        
        response_data = {
            "success": True, 
            "request_id": created_id,
            "message": f"Template edited with {len(updated_params)} optimized parameters", 
            "summary": summary_text,
            "parameters_count": len(updated_params),
            "enhancements": {
                "context_aware_editing": True,
                "intelligent_optimization": True,
                "regulatory_compliance": True,
                "comprehensive_coverage": len(updated_params) >= 15
            }
        }
        
        if request_id:
            response_data["original_request_id"] = request_id
        if json_template_data:
            response_data["json_template_processed"] = True
        if file_context:
            response_data["file_info"] = f"OCR processed {filename}" if 'filename' in locals() else "File processed"
            
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in /edit: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/digitize", methods=["POST"])
@rate_limit("/digitize")
def digitize_checklist():
    """Digitize documents with advanced OCR and AI parameter extraction"""
    print("📄 /digitize endpoint called")
    
    if 'checklist_file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['checklist_file']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({"error": "Invalid file. Allowed: PDF, PNG, JPG, JPEG"}), 400
    
    # Get optional parameters
    doc_type = request.form.get("doc_type", "")
    product_name = request.form.get("product_name", "")
    supplier_name = request.form.get("supplier_name", "")
    
    try:
        filename = secure_filename(file.filename)
        temp_dir = tempfile.mkdtemp()
        filepath = os.path.join(temp_dir, filename)
        file.save(filepath)

        # Extract text with structure preservation
        file_ext = filename.rsplit('.', 1)[1].lower()
        extracted_text = extract_text_from_document(filepath, file_ext)

        os.unlink(filepath)
        os.rmdir(temp_dir)

        if not extracted_text:
            return jsonify({"error": "Failed to extract text from file"}), 500

        print(f"✅ OCR extracted {len(extracted_text)} characters from {filename}")

        # Enhanced metadata extraction
        if not all([doc_type, product_name, supplier_name]):
            metadata = extract_metadata_from_ocr(extracted_text, filename)
            doc_type = doc_type or metadata["document_type"]
            product_name = product_name or metadata["product_name"]
            supplier_name = supplier_name or metadata["supplier_name"]

        # LLM processing for digitization
        llm_prompt = f"""
I've extracted text from a scanned QC checklist: {filename}

Document Details:
- Type: {doc_type}
- Product: {product_name}
- Supplier: {supplier_name}

Extracted Content:
{extracted_text}

Please perform comprehensive digitization with:
1. Table structure preservation
2. Intelligent parameter type detection
3. Specification extraction with units
4. Professional organization
5. Minimum 15+ parameters

Create a professional parameter set maintaining original structure while using modern input types.
"""
        
        # Call LLM for digitization
        llm_response = call_llm_with_rag(
            llm_prompt, doc_type, product_name, supplier_name, is_digitization=True
        )
        
        # Parse parameters
        json_array_text = extract_top_level_json_array(llm_response)
        parameters = []
        
        if json_array_text:
            try:
                parameters = json.loads(json_array_text)
                # Filter meaningful parameters
                parameters = [
                    param for param in parameters 
                    if isinstance(param, dict) and 
                       param.get("Parameter", "").strip() and
                       param.get("Parameter", "").lower() not in ["unknown", "parameter", "option", "item"]
                ]
            except Exception as e:
                print(f"❌ JSON parse error: {e}")
                return jsonify({"error": f"Failed to parse LLM response: {str(e)}"}), 500
        
        if not parameters:
            return jsonify({"error": "No meaningful parameters extracted from document"}), 500
        
        # Save to database
        request_id = cosmos_db.create_qc_request(doc_type, product_name, supplier_name)
        cosmos_db.save_llm_response(request_id, llm_response, f"Digitization: {len(parameters)} parameters from {filename}")
        cosmos_db.save_parameters(request_id, parameters)
        
        # Generate JSON template
        json_template = generate_json_template(doc_type, product_name, supplier_name, parameters)
        cosmos_db.save_json_template(request_id, json_template)
        
        # Track analytics
        analytics_engine.track_event(
            tenant_id="default",
            event_type="file_processed",
            event_data={
                "filename": filename,
                "parameters_extracted": len(parameters),
                "product_name": product_name
            }
        )
        
        response_data = {
            "success": True,
            "request_id": request_id,
            "message": f"Digitization complete: {len(parameters)} parameters extracted from {filename}",
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
                "advanced_ocr": True
            }
        }
            
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in /digitize: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

def extract_parameters_from_json_template(template_data):
    """Extract parameters from JSON template data"""
    parameters = []
    
    for tool in template_data.get("pageToolsDataList", []):
        tool_type = tool.get("toolType", "")
        
        if tool_type == "DROPDOWN":
            dropdown_data = tool.get("dropdownData", {})
            parameters.append({
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
            parameters.append({
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
            parameters.append({
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
            parameters.append({
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
                
            parameters.append({
                "Parameter": label_text,
                "Type": param_type,
                "Spec": "",
                "DropdownOptions": "",
                "IncludeRemarks": "No",
                "Section": "General",
                "ClauseReference": ""
            })
    
    return parameters

def extract_basic_info_from_template(template_data):
    """Extract basic document info from JSON template"""
    doc_type = product_name = supplier_name = ""
    
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
    
    return doc_type, product_name, supplier_name

# ============================================================================
# TEMPLATE AND DATA ROUTES
# ============================================================================

@app.route("/template/<request_id>", methods=["GET"])
def get_template_json(request_id):
    """Get template JSON by request ID"""
    try:
        template_data = cosmos_db.get_template_by_request_id(request_id)
        
        if template_data:
            return jsonify(template_data)
        else:
            return jsonify({"error": f"Template not found for request ID {request_id}"}), 404
            
    except Exception as e:
        print(f"❌ Error in /template/{request_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/history", methods=["GET"])
def view_history():
    """Request history with enhanced metadata"""
    # JSON API response
    if request.headers.get('Accept') == 'application/json' or request.args.get('format') == 'json':
        try:
            requests = cosmos_db.get_all_requests()
            
            result = []
            for req in requests:
                param_items = cosmos_db.get_parameters_by_request_id(req["id"])
                result.append({
                    "id": req["id"],
                    "doc_type": req["doc_type"],
                    "product_name": req["product_name"],
                    "supplier_name": req["supplier_name"],
                    "created_at": req["created_at"],
                    "parameter_count": len(param_items),
                    "status": req.get("status", "completed")
                })
            
            result.sort(key=lambda x: x["created_at"], reverse=True)
            return jsonify(result)
            
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    # HTML view
    try:
        requests = cosmos_db.get_all_requests()
        
        rows = []
        for req in requests:
            param_items = cosmos_db.get_parameters_by_request_id(req["id"])
            rows.append((
                req["id"],
                req["doc_type"],
                req["product_name"],
                req["supplier_name"],
                req["created_at"],
                len(param_items)
            ))
        
        rows.sort(key=lambda x: x[4], reverse=True)
        
        html = """
        <html>
        <head>
            <title>Swift Check AI - Request History</title>
            <style>
                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
                .container { max-width: 1400px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
                .header { text-align: center; margin-bottom: 30px; }
                .header h1 { color: #333; margin: 0; }
                table { border-collapse: collapse; width: 100%; margin-top: 20px; border-radius: 10px; overflow: hidden; }
                th, td { border: 1px solid #ddd; padding: 15px; text-align: left; }
                th { background: linear-gradient(135deg, #28a745, #20c997); color: white; font-weight: bold; }
                tr:nth-child(even) { background-color: #f8f9fa; }
                tr:hover { background-color: #e8f5e8; transform: translateY(-1px); transition: all 0.3s ease; }
                a { color: #28a745; text-decoration: none; margin: 0 8px; padding: 6px 12px; border-radius: 5px; border: 1px solid #28a745; transition: all 0.3s ease; }
                a:hover { background-color: #28a745; color: white; }
                .param-count { font-weight: bold; color: #007bff; }
                .badge { padding: 4px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }
                .legend { margin-top: 20px; padding: 20px; background: linear-gradient(135deg, #e8f5e8, #f0f8f0); border-radius: 10px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 QC Request History</h1>
                    <p>Enterprise Quality Control Template Management</p>
                </div>
                <table>
                    <tr>
                        <th>Request ID</th>
                        <th>Product</th>
                        <th>Document Type</th>
                        <th>Supplier</th>
                        <th>Parameters</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
        """
        
        for row in rows:
            param_badge = "🎯" if row[5] >= 15 else "⚠️" if row[5] >= 10 else "❌"
            quality_class = "professional" if row[5] >= 15 else "good" if row[5] >= 10 else "basic"
            
            html += f"""
                <tr class="{quality_class}">
                    <td><code>{row[0][:8]}...</code></td>
                    <td><strong>{row[2]}</strong></td>
                    <td>{row[1]}</td>
                    <td>{row[3]}</td>
                    <td class="param-count">{param_badge} <span class="badge">{row[5]} params</span></td>
                    <td>{row[4][:16]}</td>
                    <td>
                        <a href="/preview/{row[0]}">👁️ Preview</a>
                        <a href="/template/{row[0]}">📋 JSON</a>
                    </td>
                </tr>
            """
        
        html += """
                </table>
                <div class="legend">
                    <strong>Quality Indicators:</strong> 
                    🎯 Professional (15+ params) | 
                    ⚠️ Good (10-14 params) | 
                    ❌ Basic (<10 params)
                </div>
            </div>
        </body>
        </html>
        """
        return html
        
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

@app.route("/preview/<request_id>", methods=["GET"])
def preview_page(request_id):
    """Enhanced template preview with ASCII visualization"""
    try:
        # Get template and parameters
        template_data = cosmos_db.get_template_by_request_id(request_id)
        param_items = cosmos_db.get_parameters_by_request_id(request_id)
        
        if not template_data:
            return f"""
            <html>
            <head><title>Template Not Found</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 100px;">
                <h1>❌ Template Not Found</h1>
                <p>No template exists for request ID: {request_id}</p>
                <a href="/history" style="color: #28a745;">← Back to History</a>
            </body>
            </html>
            """, 404
        
        # Get request details
        req_query = "SELECT * FROM c WHERE c.id = @request_id"
        req_items = list(cosmos_db.qc_requests.query_items(
            query=req_query,
            parameters=[{"name": "@request_id", "value": request_id}],
            enable_cross_partition_query=True
        ))
        
        request_details = None
        if req_items:
            req = req_items[0]
            request_details = (req["doc_type"], req["product_name"], req["supplier_name"])
        
        # Convert parameters to display format
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
        
        # Generate ASCII preview
        ascii_preview = generate_ascii_preview(parameters, request_details)
        
        # Statistics
        total_params = len(parameters)
        sections = {}
        for param in parameters:
            section = param[5] or "General Parameters"
            sections[section] = sections.get(section, 0) + 1
        
        regulatory_refs = sum(1 for param in parameters if param[6])
        
        html = f"""
        <html>
        <head>
            <title>Swift Check AI - Template Preview #{request_id}</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }}
                .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }}
                .header {{ text-align: center; margin-bottom: 40px; }}
                .header h1 {{ color: #333; margin: 0; }}
                .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }}
                .stat-card {{ padding: 20px; background: linear-gradient(135deg, #e8f5e8, #f0f8f0); border-radius: 10px; text-align: center; border-left: 4px solid #28a745; }}
                .stat-card h3 {{ margin: 0; color: #28a745; }}
                .ascii-preview {{ 
                    background: #1a1a1a; 
                    color: #00ff41; 
                    padding: 30px; 
                    border-radius: 10px; 
                    overflow: auto; 
                    font-family: 'Courier New', monospace;
                    font-size: 13px;
                    line-height: 1.4;
                    white-space: pre;
                    border: 2px solid #00ff41;
                    margin: 20px 0;
                }}
                .json-section {{ 
                    background: #f8f9fa; 
                    padding: 20px; 
                    border-radius: 10px; 
                    overflow: auto; 
                    max-height: 500px;
                    border: 1px solid #dee2e6;
                    margin: 20px 0;
                }}
                .button-group {{ text-align: center; margin: 30px 0; }}
                .btn {{ 
                    background: linear-gradient(135deg, #28a745, #20c997);
                    color: white; 
                    padding: 12px 24px; 
                    border: none; 
                    border-radius: 8px; 
                    cursor: pointer; 
                    margin: 0 10px;
                    font-weight: bold;
                    text-decoration: none;
                    display: inline-block;
                    transition: all 0.3s ease;
                }}
                .btn:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(40, 167, 69, 0.3); }}
                .quality-badge {{ 
                    background: {'#28a745' if total_params >= 15 else '#ffc107' if total_params >= 10 else '#dc3545'};
                    color: white;
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-weight: bold;
                    display: inline-block;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎯 QC Template Preview</h1>
                    <p>Request ID: <code>{request_id}</code></p>
                    <div class="quality-badge">
                        {total_params} Parameters - {'Professional' if total_params >= 15 else 'Good' if total_params >= 10 else 'Basic'}
                    </div>
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <h3>{total_params}</h3>
                        <p>Total Parameters</p>
                    </div>
                    <div class="stat-card">
                        <h3>{len(sections)}</h3>
                        <p>Organized Sections</p>
                    </div>
                    <div class="stat-card">
                        <h3>{regulatory_refs}</h3>
                        <p>Regulatory References</p>
                    </div>
                    <div class="stat-card">
                        <h3>{'✅ Yes' if total_params >= 15 else '⚠️ Partial'}</h3>
                        <p>Enterprise Ready</p>
                    </div>
                </div>
                
                <div>
                    <h2>🖥️ Template Structure</h2>
                    <div class="ascii-preview">{ascii_preview}</div>
                </div>
                
                <div>
                    <h2>📋 JSON Template</h2>
                    <div class="button-group">
                        <button class="btn" onclick="copyToClipboard()">📋 Copy JSON</button>
                        <button class="btn" onclick="toggleJsonVisibility()">👁️ Show/Hide JSON</button>
                        <button class="btn" onclick="downloadJson()">💾 Download JSON</button>
                    </div>
                    <div id="jsonSection" class="json-section" style="display: none;">
                        <pre id="jsonContent">{json.dumps(template_data, indent=2)}</pre>
                    </div>
                </div>
                
                <div class="button-group">
                    <a href="/history" class="btn">⬅️ Back to History</a>
                    <a href="/template/{request_id}" class="btn">🔗 JSON API</a>
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

def generate_ascii_preview(parameters, request_details):
    """Generate ASCII preview of the template"""
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
    ascii_preview += "    └─────────────────────────────────────────────────────────────┘\n"
    
    return ascii_preview

# ============================================================================
# ENTERPRISE FEATURES & SYSTEM ROUTES
# ============================================================================

@app.route("/upload/async", methods=["POST"])
@rate_limit("/upload/async")
def async_file_upload():
    """Async file upload with background processing"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400
        
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file type"}), 400
        
        # Get parameters
        doc_type = request.form.get("doc_type", "QC Document")
        product_name = request.form.get("product_name", "Unknown Product")
        supplier_name = request.form.get("supplier_name", "Unknown Supplier")
        
        # Create request
        request_id = cosmos_db.create_qc_request(doc_type, product_name, supplier_name)
        
        # Upload to blob storage
        blob_connection = get_blob_connection()
        blob_client = BlobServiceClient.from_connection_string(blob_connection)
        
        file_ext = Path(file.filename).suffix
        blob_name = f"{request_id}_{uuid.uuid4()}{file_ext}"
        
        blob_client_instance = blob_client.get_blob_client(container="uploads", blob=blob_name)
        file.seek(0)
        blob_client_instance.upload_blob(file.read(), overwrite=True)
        blob_url = blob_client_instance.url
        
        # Send event for background processing
        event_grid_handler.send_document_uploaded_event(blob_name, request_id, {
            "product_name": product_name,
            "doc_type": doc_type,
            "supplier_name": supplier_name
        })
        
        return jsonify({
            "success": True,
            "request_id": request_id,
            "message": "File uploaded successfully. Processing started in background.",
            "blob_url": blob_url,
            "status": "processing",
            "estimated_completion": "2-5 minutes"
        })
        
    except Exception as e:
        print(f"❌ Error in async upload: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/upload/status/<request_id>", methods=["GET"])
def check_upload_status(request_id):
    """Check status of async file processing"""
    try:
        query = "SELECT * FROM c WHERE c.id = @request_id"
        items = list(cosmos_db.qc_requests.query_items(
            query=query,
            parameters=[{"name": "@request_id", "value": request_id}],
            enable_cross_partition_query=True
        ))
        
        if not items:
            return jsonify({"error": "Request not found"}), 404
        
        request_doc = items[0]
        processing_status = request_doc.get("processing_status", "queued")
        
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
            param_count = len(cosmos_db.get_parameters_by_request_id(request_id))
            response["parameters_generated"] = param_count
            response["message"] = "Document processed successfully"
        elif processing_status == "error":
            response["error"] = request_doc.get("processing_metadata", {}).get("error", "Unknown error")
            response["message"] = "Document processing failed"
        else:
            response["message"] = "Document processing in progress"
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """Comprehensive health check for Container Apps"""
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "environment": os.getenv("AZURE_ENVIRONMENT", "development"),
            "version": "2.0.0",
            "services": {}
        }
        
        # Test Azure services
        try:
            cosmos_db.get_all_requests()
            health_status["services"]["cosmos_db"] = "healthy"
        except Exception as e:
            health_status["services"]["cosmos_db"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"
        
        try:
            azure_cache.redis_client.ping()
            health_status["services"]["redis_cache"] = "healthy"
        except Exception as e:
            health_status["services"]["redis_cache"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"
        
        try:
            from azure_secrets import azure_secrets
            test_secret = azure_secrets.get_secret("openai-key")
            health_status["services"]["key_vault"] = "healthy" if test_secret else "unhealthy"
        except Exception as e:
            health_status["services"]["key_vault"] = f"unhealthy: {str(e)}"
            health_status["status"] = "degraded"
        
        # Return appropriate status code
        status_code = 200 if health_status["status"] == "healthy" else 503
        return jsonify(health_status), status_code
            
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503

@app.route("/info", methods=["GET"])
def app_info():
    """Application information and capabilities"""
    return jsonify({
        "app_name": "Swift Check AI",
        "version": "2.0.0",
        "description": "Enterprise Quality Control Platform with AI-Powered Template Generation",
        "environment": os.getenv("AZURE_ENVIRONMENT", "development"),
        "azure_services": {
            "cosmos_db": "✅ Enabled",
            "azure_openai": "✅ Enabled", 
            "ai_search": "✅ Enabled",
            "redis_cache": "✅ Enabled",
            "key_vault": "✅ Enabled",
            "document_intelligence": "✅ Enabled",
            "blob_storage": "✅ Enabled",
            "event_grid": "✅ Enabled"
        },
        "features": {
            "ai_template_generation": "25+ intelligent parameters",
            "document_digitization": "Advanced OCR with table detection",
            "multi_tenant_support": "Enterprise isolation",
            "workflow_approvals": "Multi-stage approval chains",
            "analytics_dashboard": "Real-time insights",
            "background_processing": "Async file handling",
            "rate_limiting": "Tenant-based throttling",
            "caching_layer": "Redis performance optimization"
        },
        "api_endpoints": {
            "core": ["/refine", "/edit", "/digitize"],
            "data": ["/template/<id>", "/history", "/preview/<id>"],
            "enterprise": ["/upload/async", "/workflow/*", "/tenant/*"],
            "system": ["/health", "/info", "/cache/*"]
        },
        "capabilities": {
            "parameter_types": ["Image Upload", "Toggle", "Checklist", "Dropdown", "Numeric Input", "Text Input", "Remarks"],
            "supported_formats": ["PDF", "PNG", "JPG", "JPEG"],
            "regulatory_compliance": ["HACCP", "Dubai Municipality", "ISO Standards"],
            "intelligent_features": ["RAG Context", "Type Selection", "Specification Extraction", "Section Organization"]
        }
    })

@app.route("/cache/stats", methods=["GET"])
def cache_stats():
    """Redis cache statistics"""
    try:
        stats = azure_cache.get_cache_stats()
        return jsonify({
            "success": True,
            "cache_stats": stats,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/cache/clear", methods=["POST"])
def clear_cache():
    """Clear Redis cache entries"""
    try:
        azure_cache.clear_cache()
        return jsonify({
            "success": True,
            "message": "Cache cleared successfully",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    """Rate limiting information and status"""
    from rate_limiter import rate_limiter
    return jsonify({
        "rate_limits": rate_limiter.default_limits,
        "client_id": rate_limiter.get_client_id(),
        "redis_connected": azure_cache.redis_client.ping(),
        "timestamp": datetime.now().isoformat()
    })

# ============================================================================
# ENTERPRISE WORKFLOW ROUTES
# ============================================================================

@app.route("/workflow/create", methods=["POST"])
def create_workflow():
    """Create approval workflow for template"""
    try:
        data = request.get_json()
        request_id = data.get("request_id")
        template_data = data.get("template_data")
        tenant_id = data.get("tenant_id", "default")
        
        if not request_id or not template_data:
            return jsonify({"error": "Missing request_id or template_data"}), 400
        
        workflow_id = workflow_engine.create_approval_workflow(request_id, template_data, tenant_id)
        
        return jsonify({
            "success": True,
            "workflow_id": workflow_id,
            "message": "Approval workflow created successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/workflow/approve", methods=["POST"])
def submit_approval():
    """Submit approval decision for workflow"""
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
        
        workflow = workflow_engine.submit_approval(workflow_id, approver_id, approver_role, decision, comments)
        
        return jsonify({
            "success": True,
            "workflow": workflow,
            "message": f"Approval {decision} successfully"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/workflow/pending/<approver_role>", methods=["GET"])
def get_pending_approvals(approver_role):
    """Get pending approvals for specific role"""
    try:
        tenant_id = request.args.get("tenant_id", "default")
        pending = workflow_engine.get_pending_approvals(approver_role, tenant_id)
        
        return jsonify({
            "success": True,
            "pending_approvals": pending,
            "count": len(pending),
            "approver_role": approver_role
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# MULTI-TENANT ROUTES
# ============================================================================

@app.route("/tenant/create", methods=["POST"])
def create_tenant():
    """Create new enterprise tenant"""
    try:
        data = request.get_json()
        company_name = data.get("company_name")
        contact_email = data.get("contact_email")
        subscription_plan = data.get("subscription_plan", "basic")
        
        if not company_name or not contact_email:
            return jsonify({"error": "Missing company_name or contact_email"}), 400
        
        tenant_id = tenant_manager.create_tenant(company_name, contact_email, subscription_plan)
        
        return jsonify({
            "success": True,
            "tenant_id": tenant_id,
            "message": "Tenant created successfully",
            "subscription_plan": subscription_plan
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/tenant/<tenant_id>/analytics", methods=["GET"])
def get_tenant_analytics(tenant_id):
    """Get comprehensive analytics for tenant"""
    try:
        days = int(request.args.get("days", 30))
        analytics = analytics_engine.get_dashboard_data(tenant_id, days)
        
        return jsonify({
            "success": True,
            "tenant_id": tenant_id,
            "analytics": analytics,
            "period_days": days
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/analytics/dashboard", methods=["GET"])
def analytics_dashboard():
    """Comprehensive analytics dashboard"""
    tenant_id = request.args.get("tenant_id", "default")
    
    try:
        dashboard_data = analytics_engine.get_dashboard_data(tenant_id)
        performance_metrics = analytics_engine.get_performance_metrics(tenant_id)
        
        return jsonify({
            "success": True,
            "tenant_id": tenant_id,
            "dashboard": dashboard_data,
            "performance": performance_metrics,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        "error": "Not Found",
        "message": "The requested resource was not found",
        "status_code": 404
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        "error": "Internal Server Error",
        "message": "An unexpected error occurred",
        "status_code": 500
    }), 500

@app.errorhandler(429)
def rate_limit_exceeded(error):
    """Handle rate limit errors"""
    return jsonify({
        "error": "Rate Limit Exceeded",
        "message": "Too many requests. Please slow down.",
        "status_code": 429
    }), 429

# ============================================================================
# APPLICATION STARTUP
# ============================================================================

if __name__ == "__main__":
    print("🚀 Starting Swift Check AI v2.0 - Enterprise QC Platform")
    print("=" * 60)
    print("✅ Azure-Native Architecture Loaded")
    print("✅ Enterprise Features Enabled")
    print("✅ Multi-Tenant Support Ready")
    print("✅ AI-Powered Template Generation Active")
    print("=" * 60)
    
    # Development server
    app.run(
        host="127.0.0.1", 
        port=5000, 
        debug=os.getenv("FLASK_DEBUG", "False").lower() == "true"
    )