"""
Semantic chunking with section awareness for scientific documents.
Splits documents into meaningful chunks preserving section boundaries.
"""

import re
import structlog
from typing import List, Dict, Any, Optional

logger = structlog.get_logger(__name__)

# Approximate tokens per character ratio for English text
CHARS_PER_TOKEN = 4


class SemanticChunker:
    """
    Intelligent document chunking that respects scientific paper structure.
    Uses section-aware splitting with overlap for context preservation.
    """

    # Section header patterns
    SECTION_HEADER_RE = re.compile(
        r"^(?:\d+\.?\d*\.?\s*)?(?:abstract|introduction|related\s+work|"
        r"literature\s+review|background|method(?:ology|s)?|proposed|"
        r"experiment(?:al|s)?|results?|discussion|evaluation|analysis|"
        r"datasets?|implementation|limitations?|conclusions?|"
        r"future\s+work|references|appendix|acknowledge?ments?)",
        re.IGNORECASE | re.MULTILINE,
    )

    def __init__(
        self,
        max_chunk_size: int = 512,  # Max tokens per chunk
        chunk_overlap: int = 64,     # Overlap tokens between chunks
        min_chunk_size: int = 50,    # Min tokens per chunk
    ):
        self.max_chunk_chars = max_chunk_size * CHARS_PER_TOKEN
        self.overlap_chars = chunk_overlap * CHARS_PER_TOKEN
        self.min_chunk_chars = min_chunk_size * CHARS_PER_TOKEN

    def chunk_document(self, full_text: str, paper_id: str) -> List[Dict[str, Any]]:
        """
        Split a scientific document into semantic chunks.
        
        Strategy:
        1. First split by sections (abstract, intro, methodology, etc.)
        2. Within each section, split by paragraphs
        3. If paragraphs are too long, split by sentences with overlap
        """
        if not full_text or len(full_text.strip()) < self.min_chunk_chars:
            return [{
                "content": full_text.strip(),
                "section_name": "full_document",
                "page_number": 1,
                "token_count": len(full_text.strip()) // CHARS_PER_TOKEN,
            }]

        # Step 1: Split into sections
        sections = self._split_into_sections(full_text)

        # Step 2: Chunk each section
        all_chunks = []
        for section_name, section_text in sections:
            section_chunks = self._chunk_section(section_text, section_name)
            all_chunks.extend(section_chunks)

        # Step 3: Estimate page numbers
        self._estimate_page_numbers(all_chunks, full_text)

        logger.info(
            "Document chunked",
            paper_id=paper_id,
            total_chunks=len(all_chunks),
            sections=len(sections),
        )

        return all_chunks

    def _split_into_sections(self, text: str) -> List[tuple]:
        """Split document text into named sections."""
        sections = []
        lines = text.split("\n")
        current_section = "preamble"
        current_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                current_lines.append("")
                continue

            # Check if this line is a section header
            if self.SECTION_HEADER_RE.match(stripped) and len(stripped) < 120:
                # Save current section if it has content
                if current_lines:
                    content = "\n".join(current_lines).strip()
                    if content:
                        sections.append((current_section, content))

                # Start new section
                current_section = self._normalize_section(stripped)
                current_lines = []
            else:
                current_lines.append(stripped)

        # Save last section
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append((current_section, content))

        # If no sections were detected, treat entire text as one section
        if not sections:
            sections = [("full_document", text.strip())]

        return sections

    def _chunk_section(self, section_text: str, section_name: str) -> List[Dict[str, Any]]:
        """Chunk a single section into appropriately sized pieces."""
        if len(section_text) <= self.max_chunk_chars:
            return [{
                "content": section_text,
                "section_name": section_name,
                "page_number": None,
                "token_count": len(section_text) // CHARS_PER_TOKEN,
            }]

        # Split by paragraphs first
        paragraphs = re.split(r"\n\s*\n", section_text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            # If adding this paragraph exceeds max size
            if len(current_chunk) + len(paragraph) + 2 > self.max_chunk_chars:
                # Save current chunk if it has content
                if current_chunk:
                    chunks.append(self._make_chunk(current_chunk, section_name))

                # If single paragraph is too long, split by sentences
                if len(paragraph) > self.max_chunk_chars:
                    sentence_chunks = self._split_by_sentences(paragraph, section_name)
                    chunks.extend(sentence_chunks)
                    current_chunk = ""
                else:
                    current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph

        # Save remaining content
        if current_chunk and len(current_chunk) >= self.min_chunk_chars:
            chunks.append(self._make_chunk(current_chunk, section_name))
        elif current_chunk and chunks:
            # Append short remaining content to last chunk
            chunks[-1]["content"] += "\n\n" + current_chunk
            chunks[-1]["token_count"] = len(chunks[-1]["content"]) // CHARS_PER_TOKEN

        return chunks

    def _split_by_sentences(self, text: str, section_name: str) -> List[Dict[str, Any]]:
        """Split text by sentences with overlap."""
        # Sentence splitting regex (handles common abbreviations)
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks = []
        current_chunk = ""
        overlap_buffer = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 > self.max_chunk_chars:
                if current_chunk:
                    chunks.append(self._make_chunk(current_chunk, section_name))
                    # Keep overlap from end of current chunk
                    overlap_buffer = current_chunk[-self.overlap_chars:] if len(current_chunk) > self.overlap_chars else current_chunk

                current_chunk = overlap_buffer + " " + sentence if overlap_buffer else sentence
            else:
                current_chunk = current_chunk + " " + sentence if current_chunk else sentence

        if current_chunk and len(current_chunk) >= self.min_chunk_chars:
            chunks.append(self._make_chunk(current_chunk, section_name))

        return chunks

    def _make_chunk(self, content: str, section_name: str) -> Dict[str, Any]:
        """Create a chunk dictionary."""
        return {
            "content": content.strip(),
            "section_name": section_name,
            "page_number": None,
            "token_count": len(content.strip()) // CHARS_PER_TOKEN,
        }

    def _estimate_page_numbers(self, chunks: List[Dict], full_text: str):
        """Estimate page numbers for chunks based on position in document."""
        if not chunks:
            return

        total_chars = len(full_text)
        # Assume ~3000 chars per page for academic papers
        chars_per_page = 3000
        estimated_pages = max(1, total_chars // chars_per_page)

        cumulative_pos = 0
        for chunk in chunks:
            # Find approximate position of this chunk in the full text
            pos = full_text.find(chunk["content"][:100], cumulative_pos)
            if pos >= 0:
                cumulative_pos = pos
                chunk["page_number"] = min(estimated_pages, max(1, pos // chars_per_page + 1))
            else:
                chunk["page_number"] = 1

    def _normalize_section(self, header: str) -> str:
        """Normalize section header text."""
        header = re.sub(r"^\d+\.?\d*\.?\s*", "", header).strip().lower()

        mappings = {
            "abstract": "abstract",
            "introduction": "introduction",
            "related work": "related_work",
            "literature": "related_work",
            "background": "background",
            "method": "methodology",
            "proposed": "methodology",
            "experiment": "experiments",
            "result": "results",
            "discussion": "discussion",
            "evaluation": "evaluation",
            "analysis": "analysis",
            "dataset": "datasets",
            "implementation": "implementation",
            "limitation": "limitations",
            "conclusion": "conclusion",
            "future": "future_work",
            "reference": "references",
            "appendix": "appendix",
            "acknowledge": "acknowledgements",
        }

        for key, value in mappings.items():
            if key in header:
                return value

        return header.replace(" ", "_")[:50]
