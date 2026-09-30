"""
Export service for generating PDF and DOCX from the literature review.
"""

import io
import re
import structlog
from typing import List, Dict, Any, Optional

logger = structlog.get_logger(__name__)


class ReviewExporter:
    """Exports literature reviews as PDF and DOCX documents."""

    def to_pdf(self, review_text: str, comparison_table: Optional[List[Dict]] = None,
               citations: Optional[List[Dict]] = None) -> bytes:
        """Convert the review to a styled PDF document."""
        from weasyprint import HTML
        from jinja2 import Template

        html_content = self._render_html(review_text, comparison_table, citations)

        html = HTML(string=html_content)
        pdf_bytes = html.write_pdf()

        logger.info("PDF exported", size=len(pdf_bytes))
        return pdf_bytes

    def to_docx(self, review_text: str, comparison_table: Optional[List[Dict]] = None,
                citations: Optional[List[Dict]] = None) -> bytes:
        """Convert the review to a DOCX document."""
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        # Title
        title = doc.add_heading("Literature Review", level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Add review text sections
        lines = review_text.split("\n")
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("## "):
                doc.add_heading(stripped[3:], level=2)
            elif stripped.startswith("# "):
                doc.add_heading(stripped[2:], level=1)
            elif stripped.startswith("### "):
                doc.add_heading(stripped[4:], level=3)
            elif stripped.startswith("- ") or stripped.startswith("* "):
                doc.add_paragraph(stripped[2:], style="List Bullet")
            else:
                p = doc.add_paragraph(stripped)
                # Style citations in bold
                # This is simplified; a more complete version would parse inline formatting

        # Add comparison table
        if comparison_table and len(comparison_table) > 0:
            doc.add_page_break()
            doc.add_heading("Paper Comparison Table", level=1)

            headers = ["Title", "Authors", "Year", "Methodology", "Datasets", "Key Results", "Limitations"]
            table = doc.add_table(rows=1, cols=len(headers))
            table.style = "Table Grid"

            # Header row
            for i, header in enumerate(headers):
                cell = table.rows[0].cells[i]
                cell.text = header
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.bold = True
                        run.font.size = Pt(9)

            # Data rows
            for paper in comparison_table:
                row = table.add_row()
                values = [
                    str(paper.get("title", ""))[:50],
                    ", ".join(paper.get("authors", []))[:40] if isinstance(paper.get("authors"), list) else str(paper.get("authors", ""))[:40],
                    str(paper.get("publication_year", "N/A")),
                    str(paper.get("methodology", ""))[:100],
                    ", ".join(paper.get("datasets", [])) if isinstance(paper.get("datasets"), list) else str(paper.get("datasets", "")),
                    str(paper.get("key_results", ""))[:100],
                    str(paper.get("limitations", ""))[:100],
                ]
                for i, value in enumerate(values):
                    row.cells[i].text = value
                    for paragraph in row.cells[i].paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(8)

        # Save to bytes
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        docx_bytes = buffer.read()

        logger.info("DOCX exported", size=len(docx_bytes))
        return docx_bytes

    def _render_html(self, review_text: str, comparison_table: Optional[List[Dict]],
                     citations: Optional[List[Dict]]) -> str:
        """Render review as styled HTML for PDF conversion."""
        # Convert markdown-like formatting to HTML
        html_body = self._markdown_to_html(review_text)

        # Build comparison table HTML
        table_html = ""
        if comparison_table:
            table_html = self._build_table_html(comparison_table)

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        @page {{
            margin: 2.5cm;
            @top-center {{
                content: "Literature Review";
                font-size: 9pt;
                color: #666;
            }}
            @bottom-center {{
                content: "Page " counter(page) " of " counter(pages);
                font-size: 9pt;
                color: #666;
            }}
        }}
        body {{
            font-family: 'Georgia', 'Times New Roman', serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #1a1a1a;
        }}
        h1 {{
            font-size: 18pt;
            color: #1a365d;
            text-align: center;
            margin-bottom: 1em;
            border-bottom: 2px solid #1a365d;
            padding-bottom: 0.5em;
        }}
        h2 {{
            font-size: 14pt;
            color: #2c5282;
            margin-top: 1.5em;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 0.3em;
        }}
        h3 {{
            font-size: 12pt;
            color: #2d3748;
            margin-top: 1em;
        }}
        p {{
            text-align: justify;
            margin-bottom: 0.8em;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1em 0;
            font-size: 9pt;
        }}
        th {{
            background-color: #2c5282;
            color: white;
            padding: 8px 6px;
            text-align: left;
            font-weight: bold;
        }}
        td {{
            padding: 6px;
            border: 1px solid #e2e8f0;
            vertical-align: top;
        }}
        tr:nth-child(even) {{
            background-color: #f7fafc;
        }}
        .citation {{
            color: #2c5282;
            font-weight: bold;
        }}
        ul, ol {{
            margin-left: 1.5em;
        }}
    </style>
</head>
<body>
    <h1>Literature Review</h1>
    {html_body}
    {table_html}
</body>
</html>"""

    def _markdown_to_html(self, text: str) -> str:
        """Simple markdown to HTML conversion."""
        import markdown
        return markdown.markdown(text, extensions=["tables", "fenced_code"])

    def _build_table_html(self, comparison_table: List[Dict]) -> str:
        """Build HTML comparison table."""
        if not comparison_table:
            return ""

        html = "<h2>Paper Comparison Table</h2>\n<table>\n<thead><tr>"
        headers = ["Title", "Authors", "Year", "Methodology", "Datasets", "Key Results", "Limitations"]
        for h in headers:
            html += f"<th>{h}</th>"
        html += "</tr></thead>\n<tbody>\n"

        for paper in comparison_table:
            html += "<tr>"
            authors = ", ".join(paper.get("authors", [])) if isinstance(paper.get("authors"), list) else str(paper.get("authors", ""))
            datasets = ", ".join(paper.get("datasets", [])) if isinstance(paper.get("datasets"), list) else str(paper.get("datasets", ""))
            values = [
                str(paper.get("title", ""))[:60],
                authors[:50],
                str(paper.get("publication_year", "N/A")),
                str(paper.get("methodology", ""))[:120],
                datasets[:80],
                str(paper.get("key_results", ""))[:120],
                str(paper.get("limitations", ""))[:120],
            ]
            for v in values:
                html += f"<td>{v}</td>"
            html += "</tr>\n"

        html += "</tbody></table>"
        return html
