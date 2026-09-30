"""
PDF text and table extraction using PyMuPDF and pdfplumber.
Handles scientific document structure with page-level extraction.
"""

import io
import re
import fitz  # PyMuPDF
import pdfplumber
import structlog
from typing import Dict, List, Any, Optional

from app.storage.s3_client import s3_client

logger = structlog.get_logger(__name__)


class PDFProcessor:
    """Extracts text, tables, and structural information from scientific PDFs."""

    # Common section headers in scientific papers
    SECTION_PATTERNS = [
        r"^(?:\d+\.?\s*)?abstract",
        r"^(?:\d+\.?\s*)?introduction",
        r"^(?:\d+\.?\s*)?related\s+work",
        r"^(?:\d+\.?\s*)?literature\s+review",
        r"^(?:\d+\.?\s*)?background",
        r"^(?:\d+\.?\s*)?methodology|methods?",
        r"^(?:\d+\.?\s*)?proposed\s+(?:method|approach|framework|model|system)",
        r"^(?:\d+\.?\s*)?experiment(?:al)?\s*(?:setup|results|evaluation)?",
        r"^(?:\d+\.?\s*)?results?\s*(?:and\s+discussion)?",
        r"^(?:\d+\.?\s*)?discussion",
        r"^(?:\d+\.?\s*)?evaluation",
        r"^(?:\d+\.?\s*)?analysis",
        r"^(?:\d+\.?\s*)?datasets?",
        r"^(?:\d+\.?\s*)?implementation",
        r"^(?:\d+\.?\s*)?limitations?",
        r"^(?:\d+\.?\s*)?conclusion(?:s)?",
        r"^(?:\d+\.?\s*)?future\s+(?:work|direction)",
        r"^(?:\d+\.?\s*)?references",
        r"^(?:\d+\.?\s*)?appendix",
        r"^(?:\d+\.?\s*)?acknowledge?ments?",
    ]

    def __init__(self):
        self._section_re = re.compile(
            "|".join(self.SECTION_PATTERNS),
            re.IGNORECASE | re.MULTILINE,
        )

    def extract_from_s3(self, s3_key: str) -> Dict[str, Any]:
        """Download PDF from S3 and extract text."""
        import asyncio
        # Run the async S3 download synchronously for Celery
        loop = asyncio.new_event_loop()
        try:
            pdf_bytes = loop.run_until_complete(s3_client.download_file(s3_key))
        finally:
            loop.close()
        return self.extract_from_bytes(pdf_bytes)

    def extract_from_bytes(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Extract text and structure from PDF bytes."""
        result = {
            "full_text": "",
            "pages": [],
            "tables": [],
            "page_count": 0,
            "sections": {},
        }

        try:
            # Primary extraction with PyMuPDF (fast, good text quality)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            result["page_count"] = len(doc)

            page_texts = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text("text")
                cleaned = self._clean_text(text)
                page_texts.append({
                    "page_number": page_num + 1,
                    "text": cleaned,
                })
            doc.close()

            result["pages"] = page_texts
            result["full_text"] = "\n\n".join(p["text"] for p in page_texts)

            # Table extraction with pdfplumber (better at tables)
            try:
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    for page_num, page in enumerate(pdf.pages):
                        tables = page.extract_tables()
                        for table in tables:
                            if table and len(table) > 1:
                                result["tables"].append({
                                    "page_number": page_num + 1,
                                    "data": table,
                                    "headers": table[0] if table else [],
                                    "rows": table[1:] if len(table) > 1 else [],
                                })
            except Exception as e:
                logger.warning("pdfplumber table extraction failed", error=str(e))

            # Section detection
            result["sections"] = self._detect_sections(result["full_text"])

            logger.info(
                "PDF extracted",
                pages=result["page_count"],
                text_length=len(result["full_text"]),
                tables=len(result["tables"]),
                sections=list(result["sections"].keys()),
            )

        except Exception as e:
            logger.error("PDF extraction failed", error=str(e))
            raise ValueError(f"Failed to extract PDF content: {str(e)}")

        return result

    def _clean_text(self, text: str) -> str:
        """Clean extracted text: fix encoding, remove excessive whitespace."""
        if not text:
            return ""

        # Fix common encoding issues
        text = text.replace("\x00", "")
        text = text.replace("\ufeff", "")

        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)

        # Fix broken hyphenation (word- \n continuation)
        text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

        # Fix line breaks within paragraphs (but preserve double newlines)
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

        # Normalize multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    def _detect_sections(self, full_text: str) -> Dict[str, str]:
        """Detect and extract named sections from the paper text."""
        sections = {}
        lines = full_text.split("\n")
        current_section = "preamble"
        current_content = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                current_content.append("")
                continue

            # Check if line is a section header
            match = self._section_re.match(stripped)
            if match and len(stripped) < 100:  # Section headers are typically short
                # Save previous section
                if current_content:
                    sections[current_section] = "\n".join(current_content).strip()
                # Start new section
                current_section = self._normalize_section_name(stripped)
                current_content = []
            else:
                current_content.append(stripped)

        # Save last section
        if current_content:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _normalize_section_name(self, header: str) -> str:
        """Normalize section header to a standard name."""
        header = re.sub(r"^\d+\.?\s*", "", header).strip().lower()

        mappings = {
            "abstract": "abstract",
            "introduction": "introduction",
            "related work": "related_work",
            "literature review": "related_work",
            "background": "background",
            "method": "methodology",
            "methods": "methodology",
            "methodology": "methodology",
            "proposed": "methodology",
            "experiment": "experiments",
            "experimental": "experiments",
            "results": "results",
            "discussion": "discussion",
            "evaluation": "evaluation",
            "analysis": "analysis",
            "dataset": "datasets",
            "datasets": "datasets",
            "implementation": "implementation",
            "limitation": "limitations",
            "limitations": "limitations",
            "conclusion": "conclusion",
            "conclusions": "conclusion",
            "future": "future_work",
            "references": "references",
            "appendix": "appendix",
            "acknowledgement": "acknowledgements",
            "acknowledgements": "acknowledgements",
        }

        for key, value in mappings.items():
            if key in header:
                return value

        return header.replace(" ", "_")[:50]
