from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white, grey
from reportlab.lib import colors
from datetime import datetime
import io
import base64
from cosmos_db_utils import enhanced_cosmos_db

class PDFReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom styles for PDF"""
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            textColor=HexColor('#2E8B57'),
            alignment=1  # Center
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=10,
            textColor=HexColor('#4682B4'),
            leftIndent=20
        ))
    
    def generate_qc_template_report(self, request_id):
        """Generate PDF report for QC template"""
        try:
            # Get data from Cosmos DB
            template_data = enhanced_cosmos_db.get_template_by_request_id(request_id)
            if not template_data:
                return None
            
            # Get request details
            req_query = "SELECT * FROM c WHERE c.id = @request_id"
            req_items = list(enhanced_cosmos_db.qc_requests.query_items(
                query=req_query,
                parameters=[{"name": "@request_id", "value": request_id}]
            ))
            
            if not req_items:
                return None
            
            request_details = req_items[0]
            
            # Get parameters
            param_query = "SELECT * FROM c WHERE c.request_id = @request_id"
            param_items = list(enhanced_cosmos_db.parameters.query_items(
                query=param_query,
                parameters=[{"name": "@request_id", "value": request_id}]
            ))
            
            # Create PDF in memory
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
            
            # Build PDF content
            story = []
            
            # Title
            title = f"{request_details['product_name']} - {request_details['doc_type']}"
            story.append(Paragraph(title, self.styles['CustomTitle']))
            story.append(Spacer(1, 12))
            
            # Supplier info
            story.append(Paragraph(f"<b>Supplier:</b> {request_details['supplier_name']}", self.styles['Normal']))
            story.append(Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", self.styles['Normal']))
            story.append(Paragraph(f"<b>Request ID:</b> {request_id}", self.styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Parameters by section
            sections = {}
            for param in param_items:
                section = param.get("section", "General")
                if section not in sections:
                    sections[section] = []
                sections[section].append(param)
            
            for section_name, section_params in sections.items():
                # Section header
                story.append(Paragraph(section_name.upper(), self.styles['SectionHeader']))
                
                # Parameters table
                table_data = [['Parameter', 'Type', 'Specification', 'Options']]
                
                for param in section_params:
                    table_data.append([
                        param.get("parameter_name", ""),
                        param.get("type", ""),
                        param.get("spec", ""),
                        param.get("dropdown_options", "")[:30] + "..." if len(param.get("dropdown_options", "")) > 30 else param.get("dropdown_options", "")
                    ])
                
                table = Table(table_data, colWidths=[2*inch, 1.2*inch, 1.5*inch, 1.8*inch])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4682B4')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), white),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), HexColor('#F0F8FF')),
                    ('GRID', (0, 0), (-1, -1), 1, black),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#F0F8FF')])
                ]))
                
                story.append(table)
                story.append(Spacer(1, 20))
            
            # Summary
            story.append(Paragraph("SUMMARY", self.styles['SectionHeader']))
            story.append(Paragraph(f"Total Parameters: {len(param_items)}", self.styles['Normal']))
            story.append(Paragraph(f"Sections: {len(sections)}", self.styles['Normal']))
            
            # Parameter type breakdown
            type_counts = {}
            for param in param_items:
                param_type = param.get("type", "Unknown")
                type_counts[param_type] = type_counts.get(param_type, 0) + 1
            
            story.append(Spacer(1, 10))
            story.append(Paragraph("Parameter Type Breakdown:", self.styles['Normal']))
            for param_type, count in type_counts.items():
                story.append(Paragraph(f"• {param_type}: {count}", self.styles['Normal']))
            
            # Build PDF
            doc.build(story)
            
            # Get PDF bytes
            pdf_bytes = buffer.getvalue()
            buffer.close()
            
            return pdf_bytes
            
        except Exception as e:
            print(f"❌ PDF generation error: {e}")
            return None
    
    def generate_analytics_report(self, tenant_id, days=30):
        """Generate analytics PDF report"""
        try:
            from analytics_engine import analytics_engine
            
            # Get analytics data
            analytics = analytics_engine.get_dashboard_data(tenant_id, days)
            
            # Create PDF
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []
            
            # Title
            story.append(Paragraph(f"Swift Check Analytics Report", self.styles['CustomTitle']))
            story.append(Paragraph(f"Period: Last {days} days", self.styles['Normal']))
            story.append(Spacer(1, 20))
            
            # Key metrics
            story.append(Paragraph("KEY METRICS", self.styles['SectionHeader']))
            metrics_data = [
                ['Metric', 'Value'],
                ['Templates Created', str(analytics.get('templates_created', 0))],
                ['Templates Approved', str(analytics.get('templates_approved', 0))],
                ['Files Processed', str(analytics.get('files_processed', 0))],
                ['API Calls', str(analytics.get('api_calls', 0))],
                ['Error Rate', f"{analytics.get('error_rate', 0):.1f}%"]
            ]
            
            metrics_table = Table(metrics_data, colWidths=[3*inch, 2*inch])
            metrics_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4682B4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), white),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#F0F8FF')])
            ]))
            
            story.append(metrics_table)
            story.append(Spacer(1, 20))
            
            # Top products
            if analytics.get('top_products'):
                story.append(Paragraph("TOP PRODUCTS", self.styles['SectionHeader']))
                products_data = [['Product', 'Templates Created']]
                for product, count in list(analytics['top_products'].items())[:10]:
                    products_data.append([product, str(count)])
                
                products_table = Table(products_data, colWidths=[3*inch, 2*inch])
                products_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor('#2E8B57')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('GRID', (0, 0), (-1, -1), 1, black)
                ]))
                
                story.append(products_table)
            
            # Build PDF
            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            
            return pdf_bytes
            
        except Exception as e:
            print(f"❌ Analytics PDF error: {e}")
            return None

# Global instance
pdf_generator = PDFReportGenerator()