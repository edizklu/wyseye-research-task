from pathlib import Path
import fitz

from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table as RLTable, TableStyle,
    PageBreak, Image as RLImage, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

SAMPLES_DIR = Path(__file__).parent.parent / "samples"


def create_native_invoice() -> Path:
    output = SAMPLES_DIR / "native.pdf"
    doc = SimpleDocTemplate(str(output), pagesize=letter,
                           topMargin=0.5*inch, bottomMargin=0.5*inch,
                           leftMargin=0.75*inch, rightMargin=0.75*inch)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('InvoiceTitle', parent=styles['Title'],
                                  fontSize=24, textColor=colors.HexColor('#1a237e'),
                                  spaceAfter=6)
    header_style = ParagraphStyle('Header', parent=styles['Heading2'],
                                   fontSize=14, textColor=colors.HexColor('#283593'))
    normal = styles['Normal']
    right_style = ParagraphStyle('Right', parent=normal, alignment=TA_RIGHT)
    
    story = []
    
    story.append(Paragraph("ACME CORPORATION", title_style))
    story.append(Paragraph("123 Business Avenue, Suite 456", normal))
    story.append(Paragraph("New York, NY 10001 | Tel: (555) 123-4567", normal))
    story.append(Paragraph("Email: billing@acmecorp.com | Web: www.acmecorp.com", normal))
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#1a237e')))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("INVOICE", ParagraphStyle('InvLabel', parent=styles['Title'],
                                                       fontSize=20, alignment=TA_RIGHT,
                                                       textColor=colors.HexColor('#c62828'))))
    story.append(Spacer(1, 8))
    
    info_data = [
        ['Invoice Number:', 'INV-2025-00742'],
        ['Invoice Date:', 'January 15, 2025'],
        ['Due Date:', 'February 14, 2025'],
        ['Payment Terms:', 'Net 30'],
        ['Purchase Order:', 'PO-2025-1234'],
    ]
    info_table = RLTable(info_data, colWidths=[150, 200])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 16))
    
    story.append(Paragraph("Bill To:", header_style))
    story.append(Paragraph("Global Tech Solutions Ltd.", ParagraphStyle('Bold', parent=normal, fontName='Helvetica-Bold')))
    story.append(Paragraph("Attn: John Smith, Procurement Manager", normal))
    story.append(Paragraph("789 Enterprise Road, Building C", normal))
    story.append(Paragraph("San Francisco, CA 94102", normal))
    story.append(Paragraph("Tax ID: US-87-6543210", normal))
    story.append(Spacer(1, 16))
    
    story.append(Paragraph("Items & Services", header_style))
    story.append(Spacer(1, 6))
    
    items_data = [
        ['#', 'Description', 'Qty', 'Unit Price', 'Amount'],
        ['1', 'Cloud Infrastructure Setup\n(AWS/GCP configuration)', '1', '$4,500.00', '$4,500.00'],
        ['2', 'Custom API Development\n(REST + GraphQL endpoints)', '80 hrs', '$150.00/hr', '$12,000.00'],
        ['3', 'Database Migration Service\n(PostgreSQL to Cloud SQL)', '1', '$3,200.00', '$3,200.00'],
        ['4', 'Security Audit & Penetration\nTesting (OWASP Top 10)', '1', '$2,800.00', '$2,800.00'],
        ['5', 'Technical Documentation\n& Training (2 sessions)', '1', '$1,500.00', '$1,500.00'],
    ]
    
    items_table = RLTable(items_data, colWidths=[30, 220, 55, 85, 85])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (0, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),
        ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12))
    
    totals_data = [
        ['', '', 'Subtotal:', '$24,000.00'],
        ['', '', 'Tax (8.5%):', '$2,040.00'],
        ['', '', 'Discount (5%):', '-$1,200.00'],
        ['', '', 'Total Due:', '$24,840.00'],
    ]
    totals_table = RLTable(totals_data, colWidths=[220, 55, 100, 100])
    totals_table.setStyle(TableStyle([
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (2, -1), (-1, -1), 1.5, colors.HexColor('#1a237e')),
        ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (2, -1), (-1, -1), 12),
        ('TEXTCOLOR', (3, -1), (3, -1), colors.HexColor('#c62828')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 24))
    
    story.append(Paragraph("Payment Information", header_style))
    story.append(Paragraph("Bank: First National Bank of Commerce", normal))
    story.append(Paragraph("Account: 9876-5432-1098", normal))
    story.append(Paragraph("Routing: 021000021", normal))
    story.append(Paragraph("SWIFT: FNBCUS33", normal))
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<i>Thank you for your business! Please make payment by the due date. "
        "Late payments are subject to a 1.5% monthly interest charge. "
        "For questions, contact billing@acmecorp.com.</i>",
        ParagraphStyle('Note', parent=normal, fontSize=8, textColor=colors.grey)
    ))
    
    doc.build(story)
    return output


def rasterize_pdf(input_path: Path, output_path: Path, dpi: int = 200) -> Path:
    src = fitz.open(str(input_path))
    dst = fitz.open()
    
    for page in src:
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        img_page = dst.new_page(width=page.rect.width, height=page.rect.height)
        img_data = pix.tobytes("png")
        img_page.insert_image(img_page.rect, stream=img_data)
    
    dst.save(str(output_path))
    dst.close()
    src.close()
    return output_path


def create_mixed_document() -> Path:
    output = SAMPLES_DIR / "mixed.pdf"
    
    temp_path = SAMPLES_DIR / "_temp_mixed.pdf"
    doc = SimpleDocTemplate(str(temp_path), pagesize=letter,
                           topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title2', parent=styles['Title'],
                                  fontSize=22, textColor=colors.HexColor('#1b5e20'))
    header_style = ParagraphStyle('Header2', parent=styles['Heading2'],
                                   textColor=colors.HexColor('#2e7d32'))
    normal = styles['Normal']
    
    story = []
    
    story.append(Spacer(1, 100))
    story.append(Paragraph("QUARTERLY PERFORMANCE REPORT", title_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Prepared by: DataVision Analytics Inc.", 
                           ParagraphStyle('Sub', parent=normal, alignment=TA_CENTER, fontSize=14)))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Report Period: Q4 2024 (October – December)",
                           ParagraphStyle('Sub2', parent=normal, alignment=TA_CENTER, fontSize=12)))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Date: January 20, 2025",
                           ParagraphStyle('Sub3', parent=normal, alignment=TA_CENTER, fontSize=12)))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Reference: RPT-Q4-2024-0089",
                           ParagraphStyle('Sub4', parent=normal, alignment=TA_CENTER, fontSize=12)))
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="60%", thickness=2, color=colors.HexColor('#1b5e20')))
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Confidential — For internal use only. This report contains proprietary "
        "performance metrics and strategic recommendations for Q1 2025.",
        ParagraphStyle('Conf', parent=normal, alignment=TA_CENTER, 
                       fontSize=9, textColor=colors.grey)
    ))
    story.append(PageBreak())
    
    story.append(Paragraph("Revenue by Region — Q4 2024", header_style))
    story.append(Spacer(1, 12))
    
    revenue_data = [
        ['Region', 'Revenue', 'Growth', 'Target', 'Status'],
        ['North America', '$2,450,000', '+12.3%', '$2,200,000', 'Exceeded'],
        ['Europe (EMEA)', '$1,890,000', '+8.7%', '$1,950,000', 'Below Target'],
        ['Asia Pacific', '$1,120,000', '+22.1%', '$1,000,000', 'Exceeded'],
        ['Latin America', '$680,000', '+15.4%', '$600,000', 'Exceeded'],
        ['Middle East', '$340,000', '+5.2%', '$400,000', 'Below Target'],
        ['Total', '$6,480,000', '+13.1%', '$6,150,000', 'Exceeded'],
    ]
    
    rev_table = RLTable(revenue_data, colWidths=[100, 90, 65, 90, 85])
    rev_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1b5e20')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e8f5e9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f1f8e9')]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(rev_table)
    story.append(Spacer(1, 20))
    
    story.append(Paragraph("Key Performance Indicators", header_style))
    story.append(Spacer(1, 8))
    
    kpi_data = [
        ['KPI', 'Q3 2024', 'Q4 2024', 'Change'],
        ['Customer Acquisition Cost', '$142', '$128', '-9.9%'],
        ['Monthly Recurring Revenue', '$1.82M', '$2.16M', '+18.7%'],
        ['Churn Rate', '3.2%', '2.8%', '-12.5%'],
        ['Net Promoter Score', '67', '72', '+7.5%'],
        ['Employee Satisfaction', '4.1/5', '4.3/5', '+4.9%'],
    ]
    
    kpi_table = RLTable(kpi_data, colWidths=[150, 90, 90, 70])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e7d32')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(kpi_table)
    story.append(PageBreak())
    
    story.append(Paragraph("Executive Summary & Recommendations", header_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Q4 2024 demonstrated strong overall performance with total revenue of $6.48M, "
        "exceeding our target of $6.15M by 5.4%. The Asia Pacific region showed the "
        "strongest growth at 22.1%, driven primarily by expansion in the Southeast Asian markets. "
        "Customer acquisition costs decreased by 9.9%, reflecting improved marketing efficiency.",
        normal
    ))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Key Recommendations for Q1 2025:", 
                           ParagraphStyle('BoldNormal', parent=normal, fontName='Helvetica-Bold')))
    story.append(Spacer(1, 6))
    
    recommendations = [
        "Increase investment in Asia Pacific region by 15% to capitalize on growth momentum",
        "Launch targeted retention program for EMEA to address below-target performance",
        "Expand the partnership program that drove North American success",
        "Implement new pricing tier for mid-market segment based on Q4 feedback data",
        "Hire 3 additional sales representatives for Latin America",
    ]
    for i, rec in enumerate(recommendations, 1):
        story.append(Paragraph(f"{i}. {rec}", normal))
        story.append(Spacer(1, 4))
    
    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Prepared by:", ParagraphStyle('Sig', parent=normal, fontName='Helvetica-Bold')))
    story.append(Paragraph("Sarah Chen, Director of Analytics", normal))
    story.append(Paragraph("DataVision Analytics Inc.", normal))
    story.append(Paragraph("sarah.chen@datavision.com", normal))
    
    doc.build(story)
    
    src = fitz.open(str(temp_path))
    dst = fitz.open()
    
    for i, page in enumerate(src):
        if i == 1:
            zoom = 200 / 72.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, stream=pix.tobytes("png"))
        else:
            dst.insert_pdf(src, from_page=i, to_page=i)
    
    dst.save(str(output))
    dst.close()
    src.close()
    
    temp_path.unlink()
    
    return output


def main():
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    
    print("Generating sample PDFs...")
    print()
    
    native = create_native_invoice()
    print(f"  Created {native} (native text invoice)")
    
    scanned = rasterize_pdf(native, SAMPLES_DIR / "scanned.pdf", dpi=200)
    print(f"  Created {scanned} (scanned/rasterized invoice)")
    
    mixed = create_mixed_document()
    print(f"  Created {mixed} (mixed native + scanned)")
    
    print()
    print("Done! All samples in:", SAMPLES_DIR)


if __name__ == "__main__":
    main()
