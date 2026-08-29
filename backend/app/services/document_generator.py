import io
import re
import json
import zlib
import base64
import urllib.request
import docx
from datetime import datetime
from PIL import Image as PILImage
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from docx import Document
from docx.shared import Inches

def render_mermaid_to_png_bytes(mermaid_code: str) -> bytes | None:
    if not mermaid_code or not isinstance(mermaid_code, str) or not mermaid_code.strip():
        return None
    try:
        url = "https://kroki.io/mermaid/png"
        req = urllib.request.Request(
            url,
            data=mermaid_code.strip().encode("utf-8"),
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-SDLC-Studio/2.0"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            png_bytes = resp.read()
            if png_bytes and png_bytes.startswith(b'\x89PNG'):
                return png_bytes
    except Exception as e:
        print(f"[Warning] Kroki API diagram rendering failed: {e}")
    return None

def get_kroki_mermaid_png_url(mermaid_code: str) -> str:
    if not mermaid_code or not isinstance(mermaid_code, str) or not mermaid_code.strip():
        return ""
    try:
        compressed = zlib.compress(mermaid_code.strip().encode('utf-8'), 9)
        b64 = base64.urlsafe_b64encode(compressed).decode('utf-8')
        return f"https://kroki.io/mermaid/png/{b64}"
    except Exception:
        return ""

# Dynamic Page Numbering helper that skips headers/footers on the cover page (Page 1)
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            super().showPage()
        super().save()

    def draw_page_number(self, page_count):
        if self._pageNumber == 1:
            # Skip running header/footer on cover page
            return
            
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#64748b"))
        
        # Header
        self.drawString(54, 750, "AI SDLC Studio - Enterprise E2E Documentation")
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(54, 742, 558, 742)
        
        # Footer
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 40, page_text)
        self.drawString(54, 40, f"Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        self.line(54, 52, 558, 52)
        
        self.restoreState()


def render_markdown_bold_html(text: str) -> str:
    """Helper to convert **bold** markdown to ReportLab <b>bold</b> tags."""
    return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)


def generate_srs_pdf(project_name: str, srs_data: dict, version: int, approval_status: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        leftMargin=54, 
        rightMargin=54, 
        topMargin=72, 
        bottomMargin=72
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=30,
        textColor=colors.HexColor("#1e3a8a"),
        spaceAfter=15,
        alignment=1 # Center
    )
    
    subtitle_style = ParagraphStyle(
        'CoverSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#475569"),
        spaceAfter=25,
        alignment=1 # Center
    )
    
    h1_style = ParagraphStyle(
        'DocH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'DocBullet',
        parent=body_style,
        leftIndent=15,
        spaceAfter=4
    )

    story = []
    
    # 1. COVER PAGE
    story.append(Spacer(1, 80))
    story.append(Paragraph("SOFTWARE REQUIREMENTS SPECIFICATION (SRS)", title_style))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f"Project: <b>{project_name}</b>", subtitle_style))
    story.append(Spacer(1, 80))
    
    meta_table_data = [
        [Paragraph("<b>Document Version:</b>", body_style), Paragraph(f"v{version}.0", body_style)],
        [Paragraph("<b>Approval Status:</b>", body_style), Paragraph(f"<b>{approval_status}</b>", body_style)],
        [Paragraph("<b>Author System:</b>", body_style), Paragraph("AI SDLC Studio Autonomous Requirements Engine", body_style)],
        [Paragraph("<b>Specification Standard:</b>", body_style), Paragraph("IEEE-830 Software Requirements Standard", body_style)],
        [Paragraph("<b>Classification Level:</b>", body_style), Paragraph("Enterprise Confidential", body_style)],
        [Paragraph("<b>Generation Date:</b>", body_style), Paragraph(datetime.now().strftime('%Y-%m-%d %H:%M'), body_style)],
    ]
    t_meta = Table(meta_table_data, colWidths=[150, 250])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
        ('PADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(t_meta)
    story.append(PageBreak())
    
    # 2. TABLE OF CONTENTS PAGE
    story.append(Paragraph("TABLE OF CONTENTS", h1_style))
    story.append(Spacer(1, 8))
    
    toc_data = [
        [Paragraph("<b>Section Title</b>", body_style), Paragraph("<b>Page Reference</b>", body_style)],
        [Paragraph("1. Document Information", body_style), Paragraph("Page 3", body_style)],
        [Paragraph("2. Revision History", body_style), Paragraph("Page 3", body_style)],
        [Paragraph("3. Approval History", body_style), Paragraph("Page 3", body_style)],
        [Paragraph("4. Executive Summary", body_style), Paragraph("Page 4", body_style)],
        [Paragraph("5. Problem Statement & Current State", body_style), Paragraph("Page 4", body_style)],
        [Paragraph("6. Business Objectives & Strategic KPIs", body_style), Paragraph("Page 5", body_style)],
        [Paragraph("7. Stakeholders & Responsibilities", body_style), Paragraph("Page 5", body_style)],
        [Paragraph("8. User Personas & Detailed Profiles", body_style), Paragraph("Page 6", body_style)],
        [Paragraph("9. System Actors & Access Rights", body_style), Paragraph("Page 6", body_style)],
        [Paragraph("10. In-Scope Functional Boundaries", body_style), Paragraph("Page 7", body_style)],
        [Paragraph("11. Out-of-Scope & Future Phases", body_style), Paragraph("Page 7", body_style)],
        [Paragraph("12. Business Requirements", body_style), Paragraph("Page 8", body_style)],
        [Paragraph("13. Detailed Functional Requirements", body_style), Paragraph("Page 8", body_style)],
        [Paragraph("14. Non-Functional & Quality Attributes", body_style), Paragraph("Page 10", body_style)],
        [Paragraph("15. Business Rules & Logic Constraints", body_style), Paragraph("Page 11", body_style)],
        [Paragraph("16. User Stories & Epics", body_style), Paragraph("Page 11", body_style)],
        [Paragraph("17. Primary & Secondary Use Cases", body_style), Paragraph("Page 12", body_style)],
        [Paragraph("18. Acceptance Criteria (Given-When-Then)", body_style), Paragraph("Page 13", body_style)],
        [Paragraph("19. UI/UX & Layout Guidelines", body_style), Paragraph("Page 14", body_style)],
        [Paragraph("20. Navigation & Information Architecture", body_style), Paragraph("Page 14", body_style)],
        [Paragraph("21. Data Architecture & Schema Specs", body_style), Paragraph("Page 15", body_style)],
        [Paragraph("22. Security, Auth & Encryption Policies", body_style), Paragraph("Page 15", body_style)],
        [Paragraph("23. API & External Integration Contracts", body_style), Paragraph("Page 16", body_style)],
        [Paragraph("24. Performance & Scalability Specs", body_style), Paragraph("Page 16", body_style)],
        [Paragraph("25. Compliance & Regulatory Auditing", body_style), Paragraph("Page 17", body_style)],
        [Paragraph("26. Architectural Constraints", body_style), Paragraph("Page 17", body_style)],
        [Paragraph("27. Operational Assumptions", body_style), Paragraph("Page 18", body_style)],
        [Paragraph("28. Risk Assessment & Mitigation Plan", body_style), Paragraph("Page 18", body_style)],
        [Paragraph("29. System Dependencies & SDKs", body_style), Paragraph("Page 19", body_style)],
        [Paragraph("30. Requirement Traceability Matrix (RTM)", body_style), Paragraph("Page 19", body_style)],
    ]
    t_toc = Table(toc_data, colWidths=[330, 90])
    t_toc.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_toc)
    story.append(PageBreak())
    
    # 3. 30 SECTIONS CONTENT
    sections = [
        ("1. Document Information", "document_information"),
        ("2. Revision History", "revision_history"),
        ("3. Approval History", "approval_history"),
        ("4. Executive Summary", "executive_summary"),
        ("5. Problem Statement & Current State", "problem_statement"),
        ("6. Business Objectives & Strategic KPIs", "business_objectives"),
        ("7. Stakeholders & Responsibilities", "stakeholders"),
        ("8. User Personas & Profiles", "user_personas"),
        ("9. System Actors & Access Rights", "actors"),
        ("10. In-Scope Functional Boundaries", "scope"),
        ("11. Out-of-Scope & Future Phases", "out_of_scope"),
        ("12. Business Requirements", "business_requirements"),
        ("13. Detailed Functional Requirements", "functional_requirements"),
        ("14. Non-Functional & Quality Attributes", "non_functional_requirements"),
        ("15. Business Rules & Logic Constraints", "business_rules"),
        ("16. User Stories & Epics", "user_stories"),
        ("17. Primary & Secondary Use Cases", "use_cases"),
        ("18. Acceptance Criteria (Given-When-Then)", "acceptance_criteria"),
        ("19. UI/UX & Layout Guidelines", "ui_requirements"),
        ("20. Navigation & Information Architecture", "navigation_flow"),
        ("21. Data Architecture & Schema Specs", "data_requirements"),
        ("22. Security, Auth & Encryption Policies", "security_requirements"),
        ("23. API & External Integration Contracts", "integration_requirements"),
        ("24. Performance & Scalability Specs", "performance_requirements"),
        ("25. Compliance & Regulatory Auditing", "compliance_requirements"),
        ("26. Architectural Constraints", "constraints"),
        ("27. Operational Assumptions", "assumptions"),
        ("28. Risk Assessment & Mitigation Plan", "risks"),
        ("29. System Dependencies & SDKs", "dependencies"),
    ]
    
    for label, key in sections:
        val = srs_data.get(key)
        story.append(Paragraph(label, h1_style))
        if not val:
            story.append(Paragraph("Not specified.", body_style))
        elif isinstance(val, list):
            for item in val:
                item_str = render_markdown_bold_html(str(item))
                lines = item_str.split('\n')
                for line in lines:
                    if line.strip():
                        story.append(Paragraph(f"• {line.strip()}", bullet_style))
        else:
            val_str = render_markdown_bold_html(str(val))
            paragraphs = val_str.split('\n\n')
            for p_text in paragraphs:
                lines = p_text.split('\n')
                for line in lines:
                    if line.strip():
                        story.append(Paragraph(line.strip(), body_style))
        story.append(Spacer(1, 8))
        
    # 30. Traceability Matrix Table
    matrix = srs_data.get("requirement_traceability_matrix", [])
    if matrix:
        story.append(Paragraph("30. Requirement Traceability Matrix (RTM)", h1_style))
        table_data = [[
            Paragraph("<b>Req ID</b>", body_style), 
            Paragraph("<b>Title</b>", body_style), 
            Paragraph("<b>Detailed Description</b>", body_style), 
            Paragraph("<b>Category</b>", body_style)
        ]]
        for row in matrix:
            table_data.append([
                Paragraph(str(row.get("id", "")), body_style),
                Paragraph(render_markdown_bold_html(str(row.get("title", ""))), body_style),
                Paragraph(render_markdown_bold_html(str(row.get("description", ""))), body_style),
                Paragraph(str(row.get("category", "")), body_style)
            ])
            
        t = Table(table_data, colWidths=[65, 110, 225, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ('PADDING', (0,0), (-1,-1), 5),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(t)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


def generate_srs_docx(project_name: str, srs_data: dict, version: int, approval_status: str) -> bytes:
    doc = Document()
    
    title_p = doc.add_paragraph()
    run = title_p.add_run("SOFTWARE REQUIREMENTS SPECIFICATION")
    run.font.size = docx.shared.Pt(22) if hasattr(docx, 'shared') else None
    run.bold = True
    
    p_sub = doc.add_paragraph()
    p_sub.add_run("Project Name: ").bold = True
    p_sub.add_run(project_name + "\n")
    p_sub.add_run("Version: ").bold = True
    p_sub.add_run(f"v{version}.0\n")
    p_sub.add_run("Status: ").bold = True
    p_sub.add_run(approval_status + "\n")
    p_sub.add_run("Specification Standard: ").bold = True
    p_sub.add_run("IEEE-830 Software Requirements Standard\n")
    p_sub.add_run("Generation Date: ").bold = True
    p_sub.add_run(datetime.now().strftime('%Y-%m-%d %H:%M') + "\n")
    
    # Table of Contents
    doc.add_heading("TABLE OF CONTENTS", level=1)
    toc_fields = [
        "1. Document Information", "2. Revision History", "3. Approval History",
        "4. Executive Summary", "5. Problem Statement & Current State", "6. Business Objectives & Strategic KPIs",
        "7. Stakeholders & Responsibilities", "8. User Personas & Profiles", "9. System Actors & Access Rights",
        "10. In-Scope Functional Boundaries", "11. Out-of-Scope & Future Phases", "12. Business Requirements",
        "13. Detailed Functional Requirements", "14. Non-Functional & Quality Attributes", "15. Business Rules & Logic Constraints",
        "16. User Stories & Epics", "17. Primary & Secondary Use Cases", "18. Acceptance Criteria (Given-When-Then)",
        "19. UI/UX & Layout Guidelines", "20. Navigation & Information Architecture", "21. Data Architecture & Schema Specs",
        "22. Security, Auth & Encryption Policies", "23. API & External Integration Contracts", "24. Performance & Scalability Specs",
        "25. Compliance & Regulatory Auditing", "26. Architectural Constraints", "27. Operational Assumptions",
        "28. Risk Assessment & Mitigation Plan", "29. System Dependencies & SDKs", "30. Requirement Traceability Matrix (RTM)"
    ]
    for field in toc_fields:
        doc.add_paragraph(field, style='List Bullet')

    doc.add_page_break()
    
    sections = [
        ("1. Document Information", "document_information"),
        ("2. Revision History", "revision_history"),
        ("3. Approval History", "approval_history"),
        ("4. Executive Summary", "executive_summary"),
        ("5. Problem Statement & Current State", "problem_statement"),
        ("6. Business Objectives & Strategic KPIs", "business_objectives"),
        ("7. Stakeholders & Responsibilities", "stakeholders"),
        ("8. User Personas & Profiles", "user_personas"),
        ("9. System Actors & Access Rights", "actors"),
        ("10. In-Scope Functional Boundaries", "scope"),
        ("11. Out-of-Scope & Future Phases", "out_of_scope"),
        ("12. Business Requirements", "business_requirements"),
        ("13. Detailed Functional Requirements", "functional_requirements"),
        ("14. Non-Functional & Quality Attributes", "non_functional_requirements"),
        ("15. Business Rules & Logic Constraints", "business_rules"),
        ("16. User Stories & Epics", "user_stories"),
        ("17. Primary & Secondary Use Cases", "use_cases"),
        ("18. Acceptance Criteria (Given-When-Then)", "acceptance_criteria"),
        ("19. UI/UX & Layout Guidelines", "ui_requirements"),
        ("20. Navigation & Information Architecture", "navigation_flow"),
        ("21. Data Architecture & Schema Specs", "data_requirements"),
        ("22. Security, Auth & Encryption Policies", "security_requirements"),
        ("23. API & External Integration Contracts", "integration_requirements"),
        ("24. Performance & Scalability Specs", "performance_requirements"),
        ("25. Compliance & Regulatory Auditing", "compliance_requirements"),
        ("26. Architectural Constraints", "constraints"),
        ("27. Operational Assumptions", "assumptions"),
        ("28. Risk Assessment & Mitigation Plan", "risks"),
        ("29. System Dependencies & SDKs", "dependencies"),
    ]
    
    for label, key in sections:
        doc.add_heading(label, level=1)
        val = srs_data.get(key)
        if not val:
            doc.add_paragraph("Not specified.")
        elif isinstance(val, list):
            for item in val:
                lines = str(item).split('\n')
                for line in lines:
                    if line.strip():
                        doc.add_paragraph(line.strip(), style='List Bullet')
        else:
            paragraphs = str(val).split('\n\n')
            for p_text in paragraphs:
                lines = p_text.split('\n')
                for line in lines:
                    if line.strip():
                        doc.add_paragraph(line.strip())
            
    matrix = srs_data.get("requirement_traceability_matrix", [])
    if matrix:
        doc.add_heading("30. Requirement Traceability Matrix (RTM)", level=1)
        table = doc.add_table(rows=1, cols=4)
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = 'Req ID'
        hdr_cells[1].text = 'Title'
        hdr_cells[2].text = 'Detailed Description'
        hdr_cells[3].text = 'Category'
        for item in matrix:
            row_cells = table.add_row().cells
            row_cells[0].text = str(item.get("id", ""))
            row_cells[1].text = str(item.get("title", ""))
            row_cells[2].text = str(item.get("description", ""))
            row_cells[3].text = str(item.get("category", ""))
            
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def generate_srs_markdown(project_name: str, srs_data: dict, version: int, approval_status: str) -> str:
    md = []
    md.append(f"# Software Requirements Specification (SRS)")
    md.append(f"**Project**: {project_name}")
    md.append(f"**Version**: v{version}.0")
    md.append(f"**Approval Status**: {approval_status}")
    md.append(f"**Specification Standard**: IEEE-830 Software Requirements Standard")
    md.append(f"**Generated Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append("\n---\n")

    md.append("## TABLE OF CONTENTS")
    toc_fields = [
        "1. Document Information", "2. Revision History", "3. Approval History",
        "4. Executive Summary", "5. Problem Statement & Current State", "6. Business Objectives & Strategic KPIs",
        "7. Stakeholders & Responsibilities", "8. User Personas & Profiles", "9. System Actors & Access Rights",
        "10. In-Scope Functional Boundaries", "11. Out-of-Scope & Future Phases", "12. Business Requirements",
        "13. Detailed Functional Requirements", "14. Non-Functional & Quality Attributes", "15. Business Rules & Logic Constraints",
        "16. User Stories & Epics", "17. Primary & Secondary Use Cases", "18. Acceptance Criteria (Given-When-Then)",
        "19. UI/UX & Layout Guidelines", "20. Navigation & Information Architecture", "21. Data Architecture & Schema Specs",
        "22. Security, Auth & Encryption Policies", "23. API & External Integration Contracts", "24. Performance & Scalability Specs",
        "25. Compliance & Regulatory Auditing", "26. Architectural Constraints", "27. Operational Assumptions",
        "28. Risk Assessment & Mitigation Plan", "29. System Dependencies & SDKs", "30. Requirement Traceability Matrix (RTM)"
    ]
    for field in toc_fields:
        md.append(f"- [{field}](#{field.lower().replace(' ', '-').replace('&', '').replace('(', '').replace(')', '')})")
    md.append("\n---\n")

    sections = [
        ("1. Document Information", "document_information"),
        ("2. Revision History", "revision_history"),
        ("3. Approval History", "approval_history"),
        ("4. Executive Summary", "executive_summary"),
        ("5. Problem Statement & Current State", "problem_statement"),
        ("6. Business Objectives & Strategic KPIs", "business_objectives"),
        ("7. Stakeholders & Responsibilities", "stakeholders"),
        ("8. User Personas & Profiles", "user_personas"),
        ("9. System Actors & Access Rights", "actors"),
        ("10. In-Scope Functional Boundaries", "scope"),
        ("11. Out-of-Scope & Future Phases", "out_of_scope"),
        ("12. Business Requirements", "business_requirements"),
        ("13. Detailed Functional Requirements", "functional_requirements"),
        ("14. Non-Functional & Quality Attributes", "non_functional_requirements"),
        ("15. Business Rules & Logic Constraints", "business_rules"),
        ("16. User Stories & Epics", "user_stories"),
        ("17. Primary & Secondary Use Cases", "use_cases"),
        ("18. Acceptance Criteria (Given-When-Then)", "acceptance_criteria"),
        ("19. UI/UX & Layout Guidelines", "ui_requirements"),
        ("20. Navigation & Information Architecture", "navigation_flow"),
        ("21. Data Architecture & Schema Specs", "data_requirements"),
        ("22. Security, Auth & Encryption Policies", "security_requirements"),
        ("23. API & External Integration Contracts", "integration_requirements"),
        ("24. Performance & Scalability Specs", "performance_requirements"),
        ("25. Compliance & Regulatory Auditing", "compliance_requirements"),
        ("26. Architectural Constraints", "constraints"),
        ("27. Operational Assumptions", "assumptions"),
        ("28. Risk Assessment & Mitigation Plan", "risks"),
        ("29. System Dependencies & SDKs", "dependencies"),
    ]

    for label, key in sections:
        val = srs_data.get(key)
        md.append(f"## {label}")
        if not val:
            md.append("Not specified.\n")
        elif isinstance(val, list):
            for item in val:
                md.append(f"- {item}")
            md.append("")
        else:
            md.append(f"{val}\n")

    matrix = srs_data.get("requirement_traceability_matrix", [])
    if matrix:
        md.append("## 30. Requirement Traceability Matrix (RTM)")
        md.append("| Req ID | Title | Detailed Description | Category |")
        md.append("| --- | --- | --- | --- |")
        for item in matrix:
            title = str(item.get("title", "")).replace("\n", " ")
            desc = str(item.get("description", "")).replace("\n", " ")
            md.append(f"| {item.get('id', '')} | {title} | {desc} | {item.get('category', '')} |")
        md.append("")

    return "\n".join(md)


def generate_sdd_pdf(project_name: str, sdd_data: dict, version: int, approval_status: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter,
        leftMargin=54, 
        rightMargin=54, 
        topMargin=72, 
        bottomMargin=72
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=26,
        leading=32,
        textColor=colors.HexColor("#4f46e5"),
        spaceAfter=15,
        alignment=1
    )
    
    subtitle_style = ParagraphStyle(
        'CoverSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#475569"),
        spaceAfter=30,
        alignment=1
    )
    
    h1_style = ParagraphStyle(
        'DocH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6
    )

    story = []
    
    # 1. COVER PAGE
    story.append(Spacer(1, 100))
    story.append(Paragraph("SOFTWARE DESIGN DOCUMENT", title_style))
    story.append(Spacer(1, 15))
    story.append(Paragraph(f"Project: <b>{project_name}</b>", subtitle_style))
    story.append(Spacer(1, 120))
    
    meta_table_data = [
        [Paragraph("<b>Document Version:</b>", body_style), Paragraph(f"v{version}", body_style)],
        [Paragraph("<b>Approval Status:</b>", body_style), Paragraph(approval_status, body_style)],
        [Paragraph("<b>Author Role:</b>", body_style), Paragraph("Lead Systems Architect", body_style)],
        [Paragraph("<b>Organization:</b>", body_style), Paragraph("AI SDLC Studio Corp", body_style)],
        [Paragraph("<b>Generation Date:</b>", body_style), Paragraph(datetime.now().strftime('%Y-%m-%d %H:%M'), body_style)],
    ]
    t_meta = Table(meta_table_data, colWidths=[150, 250])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(t_meta)
    story.append(PageBreak())
    
    # 2. TABLE OF CONTENTS PAGE
    story.append(Paragraph("TABLE OF CONTENTS", h1_style))
    story.append(Spacer(1, 10))
    toc_fields = [
        "1. Cover Page Details", "2. Revision History", "3. Approval History",
        "4. Introduction", "5. Design Goals", "6. System Overview",
        "7. High-Level Architecture", "8. Low-Level Architecture", "9. Module Breakdown",
        "10. System Context Diagram (Mermaid)", "11. Use Case Diagram (Mermaid)", "12. Component Diagram (Mermaid)",
        "13. Class Diagram (Mermaid)", "14. Sequence Diagram (Mermaid)", "15. Activity Diagram (Mermaid)",
        "16. ER Diagram (Mermaid)", "17. Deployment Diagram (Mermaid)", "18. Database Design Overview",
        "19. Table Definitions", "20. Database Relationships & Constraints", "21. API Design Overview",
        "22. API Endpoints Map", "23. Authentication Flow", "24. Authorization Flow",
        "25. Security Design Policies", "26. Logging Strategy", "27. Exception Handling",
        "28. Configuration Management", "29. Technology Stack", "30. Folder Structure",
        "31. Coding Standards", "32. Performance Design", "33. Scalability Design",
        "34. Availability Design", "35. Monitoring Strategy", "36. Backup Strategy",
        "37. Disaster Recovery Runbook", "38. Risks & Mitigations", "39. Design Assumptions",
        "40. Future Enhancements & Traceability Matrix"
    ]
    for field in toc_fields:
        story.append(Paragraph(f"{field} .....................................................................................................................................", body_style))
    story.append(PageBreak())
    
    # 3. 40 SECTIONS CONTENT
    sections = [
        ("1. Cover Page Details", "cover_page"),
        ("2. Revision History", "revision_history"),
        ("3. Approval History", "approval_history"),
        ("4. Introduction", "introduction"),
        ("5. Design Goals", "design_goals"),
        ("6. System Overview", "system_overview"),
        ("7. High-Level Architecture", "high_level_architecture"),
        ("8. Low-Level Architecture", "low_level_architecture"),
        ("9. Module Breakdown", "module_breakdown"),
        
        # Diagrams specifications
        ("10. System Context Diagram (Mermaid)", "system_context_diagram_mermaid"),
        ("11. Use Case Diagram (Mermaid)", "use_case_diagram_mermaid"),
        ("12. Component Diagram (Mermaid)", "component_diagram_mermaid"),
        ("13. Class Diagram (Mermaid)", "class_diagram_mermaid"),
        ("14. Sequence Diagram (Mermaid)", "sequence_diagram_mermaid"),
        ("15. Activity Diagram (Mermaid)", "activity_diagram_mermaid"),
        ("16. ER Diagram (Mermaid)", "er_diagram_mermaid"),
        ("17. Deployment Diagram (Mermaid)", "deployment_diagram_mermaid"),
        ("18. Flow Diagram (Mermaid)", "flow_diagram_mermaid"),
        ("19. Database Relationship Diagram (Mermaid)", "db_relationship_diagram_mermaid"),
        
        ("20. Database Design Overview", "database_design_overview"),
    ]
    
    code_style = ParagraphStyle(
        'DocCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#6366f1"),
        spaceAfter=4
    )

    for label, key in sections:
        val = sdd_data.get(key)
        story.append(Paragraph(label, h1_style))
        if not val:
            story.append(Paragraph("Not specified.", body_style))
        elif key.endswith("_mermaid"):
            png_bytes = render_mermaid_to_png_bytes(str(val))
            if png_bytes:
                try:
                    im = PILImage.open(io.BytesIO(png_bytes))
                    img_w, img_h = im.size
                    max_w = 460.0
                    aspect = float(img_h) / float(img_w)
                    w = min(float(img_w), max_w)
                    h = w * aspect
                    story.append(RLImage(io.BytesIO(png_bytes), width=w, height=h))
                except Exception as ex:
                    print(f"[Warning] Error embedding PNG diagram image in PDF: {ex}")
                    clean_lines = [Paragraph(line.replace(' ', '&nbsp;'), code_style) for line in str(val).split('\n') if line.strip()]
                    diag_table = Table([[clean_lines]], colWidths=[400])
                    diag_table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0f172a")),
                        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#334155")),
                        ('PADDING', (0,0), (-1,-1), 8),
                    ]))
                    story.append(diag_table)
            else:
                clean_lines = [Paragraph(line.replace(' ', '&nbsp;'), code_style) for line in str(val).split('\n') if line.strip()]
                diag_table = Table([[clean_lines]], colWidths=[400])
                diag_table.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0f172a")),
                    ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#334155")),
                    ('PADDING', (0,0), (-1,-1), 8),
                ]))
                story.append(diag_table)
        else:
            story.append(Paragraph(str(val), body_style))
        story.append(Spacer(1, 10))
        
    # Database tables definitions
    tables = sdd_data.get("database_tables", [])
    story.append(Paragraph("21. Database Tables Definitions", h1_style))
    if not tables:
        story.append(Paragraph("No tables defined.", body_style))
    else:
        for tbl in tables:
            story.append(Paragraph(f"<b>Table: {tbl.get('name')}</b> (PK: {tbl.get('primary_key')})", body_style))
            cols = tbl.get("columns", [])
            for c in cols:
                req_str = "NOT NULL" if not c.get("nullable") else "NULL"
                desc = f" — {c.get('description')}" if c.get('description') else ""
                story.append(Paragraph(f"  - <i>{c.get('name')}</i>: {c.get('type')} ({req_str}){desc}", body_style))
                
            fks = tbl.get("foreign_keys", [])
            if fks:
                story.append(Paragraph("  <b>Foreign Keys:</b>", body_style))
                for fk in fks:
                    story.append(Paragraph(f"    - {fk.get('column')} references {fk.get('references_table')}.{fk.get('references_column')}", body_style))
            story.append(Spacer(1, 8))
            
    # Relationships & Constraints
    story.append(Paragraph("22. Database Relationships", h1_style))
    for r in sdd_data.get("database_relationships", []):
        story.append(Paragraph(f"• {r}", body_style))
    story.append(Paragraph("23. Database Constraints", h1_style))
    for c in sdd_data.get("database_constraints", []):
        story.append(Paragraph(f"• {c}", body_style))
    story.append(Spacer(1, 10))
        
    # API Design Overview
    story.append(Paragraph("24. API Design Overview", h1_style))
    story.append(Paragraph(str(sdd_data.get("api_design_overview", "Not specified.")), body_style))
    
    # API Endpoints
    story.append(Paragraph("25. API Endpoints Map", h1_style))
    apis = sdd_data.get("api_endpoints", [])
    if apis:
        api_data = [["Method", "Path", "Request Body", "Response Body", "Description"]]
        for a in apis:
            api_data.append([
                a.get("method", ""),
                a.get("path", ""),
                a.get("request_body") or "None",
                a.get("response_body", ""),
                a.get("description", "")
            ])
        t = Table(api_data, colWidths=[50, 110, 110, 110, 120])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#0f172a")),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 7),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No API routes defined.", body_style))
    story.append(Spacer(1, 10))
    
    # NFR and Administration fields
    more_sections = [
        ("26. Authentication Flow", "authentication_flow"),
        ("27. Authorization Flow", "authorization_flow"),
        ("28. Security Design Policies", "security_design_policies"),
        ("29. Logging Strategy", "logging_strategy"),
        ("30. Exception Handling", "exception_handling"),
        ("31. Configuration Management", "configuration_management"),
        ("32. Technology Stack", "technology_stack"),
        ("33. Folder Structure", "folder_structure"),
        ("34. Coding Standards", "coding_standards"),
        ("35. Performance Design", "performance_design"),
        ("36. Scalability Design", "scalability_design"),
        ("37. Availability Design", "availability_design"),
        ("38. Monitoring Strategy", "monitoring_strategy"),
        ("39. Backup Strategy", "backup_strategy"),
        ("40. Disaster Recovery Runbook", "disaster_recovery_runbook"),
        ("41. Architectural Risks & Mitigations", "architectural_risks"),
        ("42. Design Assumptions", "design_assumptions"),
        ("43. Future Enhancements", "future_enhancements"),
    ]
    
    for label, key in more_sections:
        val = sdd_data.get(key)
        story.append(Paragraph(label, h1_style))
        if not val:
            story.append(Paragraph("Not specified.", body_style))
        elif isinstance(val, list):
            for item in val:
                story.append(Paragraph(f"• {item}", body_style))
        else:
            story.append(Paragraph(str(val), body_style))
        story.append(Spacer(1, 10))
        
    # Requirement Traceability Matrix
    matrix = sdd_data.get("traceability_matrix", [])
    if matrix:
        story.append(Paragraph("Requirement Traceability Matrix", h1_style))
        table_data = [["Req ID", "Module Component", "API Route", "DB Table", "UI Interface"]]
        for row in matrix:
            table_data.append([
                row.get("requirement_id", ""),
                row.get("module", ""),
                row.get("api_endpoint", ""),
                row.get("db_table", ""),
                row.get("ui_screen", "")
            ])
            
        t = Table(table_data, colWidths=[70, 110, 110, 110, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#0f172a")),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#f8fafc")]),
        ]))
        story.append(t)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


def generate_sdd_docx(project_name: str, sdd_data: dict, version: int, approval_status: str) -> bytes:
    doc = Document()
    doc.add_heading("Software Design Document", 0)
    
    p = doc.add_paragraph()
    p.add_run("Project Name: ").bold = True
    p.add_run(project_name + "\n")
    p.add_run("Version: ").bold = True
    p.add_run(str(version) + "\n")
    p.add_run("Status: ").bold = True
    p.add_run(approval_status + "\n")
    p.add_run("Generated Date: ").bold = True
    p.add_run(datetime.now().strftime('%Y-%m-%d %H:%M') + "\n")
    
    sections = [
        ("1. Cover Page Details", "cover_page"),
        ("2. Revision History", "revision_history"),
        ("3. Approval History", "approval_history"),
        ("4. Introduction", "introduction"),
        ("5. Design Goals", "design_goals"),
        ("6. System Overview", "system_overview"),
        ("7. High-Level Architecture", "high_level_architecture"),
        ("8. Low-Level Architecture", "low_level_architecture"),
        ("9. Module Breakdown", "module_breakdown"),
        
        ("10. System Context Diagram (Mermaid)", "system_context_diagram_mermaid"),
        ("11. Use Case Diagram (Mermaid)", "use_case_diagram_mermaid"),
        ("12. Component Diagram (Mermaid)", "component_diagram_mermaid"),
        ("13. Class Diagram (Mermaid)", "class_diagram_mermaid"),
        ("14. Sequence Diagram (Mermaid)", "sequence_diagram_mermaid"),
        ("15. Activity Diagram (Mermaid)", "activity_diagram_mermaid"),
        ("16. ER Diagram (Mermaid)", "er_diagram_mermaid"),
        ("17. Deployment Diagram (Mermaid)", "deployment_diagram_mermaid"),
        ("18. Flow Diagram (Mermaid)", "flow_diagram_mermaid"),
        ("19. Database Relationship Diagram (Mermaid)", "db_relationship_diagram_mermaid"),
        
        ("20. Database Design Overview", "database_design_overview"),
    ]
    
    for label, key in sections:
        doc.add_heading(label, level=1)
        val = sdd_data.get(key)
        if not val:
            doc.add_paragraph("Not specified.")
        elif key.endswith("_mermaid"):
            png_bytes = render_mermaid_to_png_bytes(str(val))
            if png_bytes:
                try:
                    doc.add_picture(io.BytesIO(png_bytes), width=Inches(6.0))
                except Exception as ex:
                    print(f"[Warning] Failed inserting PNG diagram image in Word doc: {ex}")
                    doc.add_paragraph(str(val))
            else:
                doc.add_paragraph(str(val))
        else:
            doc.add_paragraph(str(val))
            
    doc.add_heading("21. Database Tables Definitions", level=1)
    for tbl in sdd_data.get("database_tables", []):
        p = doc.add_paragraph()
        p.add_run(f"Table: {tbl.get('name')} ").bold = True
        p.add_run(f"(Primary Key: {tbl.get('primary_key')})\n")
        for col in tbl.get("columns", []):
            req = "NOT NULL" if not col.get("nullable") else "NULL"
            doc.add_paragraph(f"{col.get('name')} ({col.get('type')}) - {req} - {col.get('description', '')}", style='List Bullet')
            
    doc.add_heading("22. Database Relationships", level=1)
    for rel in sdd_data.get("database_relationships", []):
        doc.add_paragraph(rel, style='List Bullet')
    doc.add_heading("23. Database Constraints", level=1)
    for const in sdd_data.get("database_constraints", []):
        doc.add_paragraph(const, style='List Bullet')
        
    doc.add_heading("24. API Design Overview", level=1)
    doc.add_paragraph(str(sdd_data.get("api_design_overview", "Not specified.")))
    
    doc.add_heading("25. API Endpoints Map", level=1)
    apis = sdd_data.get("api_endpoints", [])
    if apis:
        table = doc.add_table(rows=1, cols=5)
        hdr = table.rows[0].cells
        hdr[0].text = 'Method'
        hdr[1].text = 'Path'
        hdr[2].text = 'Request'
        hdr[3].text = 'Response'
        hdr[4].text = 'Description'
        for a in apis:
            cells = table.add_row().cells
            cells[0].text = a.get("method", "")
            cells[1].text = a.get("path", "")
            cells[2].text = a.get("request_body") or "None"
            cells[3].text = a.get("response_body", "")
            cells[4].text = a.get("description", "")
            
    more_sections = [
        ("26. Authentication Flow", "authentication_flow"),
        ("27. Authorization Flow", "authorization_flow"),
        ("28. Security Design Policies", "security_design_policies"),
        ("29. Logging Strategy", "logging_strategy"),
        ("30. Exception Handling", "exception_handling"),
        ("31. Configuration Management", "configuration_management"),
        ("32. Technology Stack", "technology_stack"),
        ("33. Folder Structure", "folder_structure"),
        ("34. Coding Standards", "coding_standards"),
        ("35. Performance Design", "performance_design"),
        ("36. Scalability Design", "scalability_design"),
        ("37. Availability Design", "availability_design"),
        ("38. Monitoring Strategy", "monitoring_strategy"),
        ("39. Backup Strategy", "backup_strategy"),
        ("40. Disaster Recovery Runbook", "disaster_recovery_runbook"),
        ("41. Architectural Risks & Mitigations", "architectural_risks"),
        ("42. Design Assumptions", "design_assumptions"),
        ("43. Future Enhancements", "future_enhancements"),
    ]
    
    for label, key in more_sections:
        doc.add_heading(label, level=1)
        val = sdd_data.get(key)
        if not val:
            doc.add_paragraph("Not specified.")
        elif isinstance(val, list):
            for item in val:
                doc.add_paragraph(item, style='List Bullet')
        else:
            doc.add_paragraph(str(val))
            
    matrix = sdd_data.get("traceability_matrix", [])
    if matrix:
        doc.add_heading("Requirement Traceability Matrix", level=1)
        table = doc.add_table(rows=1, cols=5)
        hdr = table.rows[0].cells
        hdr[0].text = 'Req ID'
        hdr[1].text = 'Module Component'
        hdr[2].text = 'API Route'
        hdr[3].text = 'DB Table'
        hdr[4].text = 'UI Interface'
        for item in matrix:
            cells = table.add_row().cells
            cells[0].text = item.get("requirement_id", "")
            cells[1].text = item.get("module", "")
            cells[2].text = item.get("api_endpoint", "")
            cells[3].text = item.get("db_table", "")
            cells[4].text = item.get("ui_screen", "")
            
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def generate_sdd_markdown(project_name: str, sdd_data: dict, version: int, approval_status: str) -> str:
    """Generates clean GitHub-Flavored Markdown for the System Design Specification."""
    md = []
    md.append(f"# System Design Specification (SDD)")
    md.append(f"**Project**: {project_name}")
    md.append(f"**Version**: {version}.0.0")
    md.append(f"**Approval Status**: {approval_status}")
    md.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    sections = [
        ("Executive Introduction", "introduction"),
        ("Design Goals & Priorities", "design_goals"),
        ("System Overview", "system_overview"),
        ("High-Level Architecture", "high_level_architecture"),
        ("Low-Level Architecture", "low_level_architecture"),
        ("Module & Package Breakdown", "module_breakdown"),
        ("Database Design Overview", "database_design_overview"),
        ("API Design Overview", "api_design_overview"),
        ("Authentication & Authorization Flow", "authentication_flow"),
        ("Security Design Policies", "security_design_policies"),
        ("Technology Stack", "technology_stack"),
        ("Performance Architecture", "performance_design"),
        ("Scalability Architecture", "scalability_design"),
        ("Availability & Reliability", "availability_design"),
        ("Monitoring & Observability", "monitoring_strategy"),
        ("Backup & Disaster Recovery", "backup_strategy")
    ]
    
    for label, key in sections:
        val = sdd_data.get(key)
        md.append(f"## {label}")
        if not val:
            md.append("Not specified.\n")
        elif isinstance(val, list):
            for item in val:
                md.append(f"- {item}")
            md.append("")
        else:
            md.append(f"{val}\n")

    # Visual Architecture & UML Diagrams Section
    md.append("## System Architecture & UML Diagrams")
    diagram_fields = [
        ("System Context Diagram", "system_context_diagram_mermaid"),
        ("Use Case Diagram", "use_case_diagram_mermaid"),
        ("Component Diagram", "component_diagram_mermaid"),
        ("Class Structure Diagram", "class_diagram_mermaid"),
        ("Sequence Flow Diagram", "sequence_diagram_mermaid"),
        ("Activity Diagram", "activity_diagram_mermaid"),
        ("Entity Relationship Diagram (ER)", "er_diagram_mermaid"),
        ("Deployment Nodes Diagram", "deployment_diagram_mermaid"),
        ("Process Flow Diagram", "flow_diagram_mermaid"),
        ("Database Relationship Diagram", "db_relationship_diagram_mermaid")
    ]
    for d_title, d_key in diagram_fields:
        chart = sdd_data.get(d_key)
        if chart:
            md.append(f"### {d_title}")
            img_url = get_kroki_mermaid_png_url(chart)
            if img_url:
                md.append(f"![{d_title}]({img_url})\n")
            md.append("```mermaid")
            md.append(chart.strip())
            md.append("```\n")
            
    # Architecture Decision Records (ADRs)
    adrs = sdd_data.get("adrs", [])
    if adrs:
        md.append("## Architecture Decision Records (ADRs)")
        for adr in adrs:
            md.append(f"### {adr.get('id', 'ADR')}: {adr.get('title', '')}")
            md.append(f"**Status**: {adr.get('status', 'Accepted')}")
            md.append(f"**Context**: {adr.get('context', '')}")
            md.append(f"**Decision**: {adr.get('decision', '')}")
            if adr.get('trade_offs'):
                md.append("**Trade-offs & Consequences**:")
                for t in adr.get('trade_offs', []):
                    md.append(f"- {t}")
            md.append("")
            
    # API Endpoints Table
    apis = sdd_data.get("api_endpoints", [])
    if apis:
        md.append("## API Endpoints Specification")
        md.append("| Method | Path | Request Schema | Response Schema | Description |")
        md.append("|---|---|---|---|---|")
        for a in apis:
            md.append(f"| `{a.get('method', 'GET')}` | `{a.get('path', '')}` | `{a.get('request_body', 'None')}` | `{a.get('response_body', '')}` | {a.get('description', '')} |")
        md.append("")
        
    # Database Tables
    tables = sdd_data.get("database_tables", [])
    if tables:
        md.append("## Database Schema Specification")
        for tbl in tables:
            md.append(f"### Table: `{tbl.get('name')}` (Primary Key: `{tbl.get('primary_key')}`)")
            md.append("| Column | Type | Nullable | Description |")
            md.append("|---|---|---|---|")
            for col in tbl.get("columns", []):
                req = "YES" if col.get("nullable") else "NO"
                md.append(f"| `{col.get('name')}` | `{col.get('type')}` | {req} | {col.get('description', '')} |")
            md.append("")
            
    # Traceability Matrix
    matrix = sdd_data.get("traceability_matrix", [])
    if matrix:
        md.append("## Requirement Traceability Matrix")
        md.append("| Requirement ID | Module Component | API Endpoint | DB Table | UI Interface | ADR |")
        md.append("|---|---|---|---|---|---|")
        for item in matrix:
            md.append(f"| `{item.get('requirement_id', '')}` | {item.get('module', '')} | `{item.get('api_endpoint', '')}` | `{item.get('db_table', '')}` | {item.get('ui_screen', '')} | `{item.get('adr_id', '')}` |")
        md.append("")
        
    return "\n".join(md)
