"""
Literature review generator using evidence-aware RAG.
Generates a structured, academically formatted literature review with verifiable citations.
"""

import re
import json
import time
import structlog
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import select
from app.config import get_settings
from app.services.retriever import HybridRetriever
from app.services.llm import get_llm_client
from app.models import Paper, Claim, EvidenceLink, Chunk

logger = structlog.get_logger(__name__)
settings = get_settings()


class ReviewGenerator:
    """
    Generates evidence-grounded literature reviews using RAG.
    Ensures all claims are traceable to source papers with citations.
    """

    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever
        self.llm = get_llm_client()
        if not self.llm.is_configured:
            raise ValueError("An LLM API key (GROQ_API_KEY or GEMINI_API_KEY) is required for review generation")

    def generate(self, session_id: str, papers: list, claims: list, db: DBSession) -> Dict[str, Any]:
        """Generate a complete literature review with all components."""
        start_time = time.time()

        # Build paper context
        paper_contexts = self._build_paper_contexts(papers)

        # Build evidence context
        evidence_context = self._build_evidence_context(session_id, claims, db)

        # Build comparison table
        comparison_table = self._build_comparison_table(papers)

        # Generate the literature review text
        review_text = self._generate_review_text(paper_contexts, evidence_context, comparison_table)

        # Extract research gaps
        research_gaps = self._identify_research_gaps(paper_contexts, evidence_context)

        # Build citation index
        citations = self._build_citation_index(papers, claims, db)

        generation_time = round(time.time() - start_time, 2)

        return {
            "review_text": review_text,
            "comparison_table": comparison_table,
            "evidence_summary": evidence_context.get("summary", {}),
            "research_gaps": research_gaps,
            "citations": citations,
            "generation_metadata": {
                "model": self.llm.model_name,
                "paper_count": len(papers),
                "claim_count": len(claims),
                "generation_time_seconds": generation_time,
            },
        }

    def _build_paper_contexts(self, papers: list) -> List[Dict]:
        """Build structured context for each paper."""
        contexts = []
        for i, paper in enumerate(papers):
            ctx = {
                "index": i + 1,
                "id": str(paper.id),
                "title": paper.title or paper.filename,
                "authors": ", ".join(paper.authors) if paper.authors else "Unknown",
                "year": paper.publication_year or "N/A",
                "abstract": paper.abstract or "",
                "methodology": paper.methodology or "",
                "datasets": ", ".join(paper.datasets) if paper.datasets else "Not specified",
                "metrics": ", ".join(paper.evaluation_metrics) if paper.evaluation_metrics else "Not specified",
                "results": paper.key_results or "",
                "limitations": paper.limitations or "",
            }
            contexts.append(ctx)
        return contexts

    def _build_evidence_context(self, session_id: str, claims: list, db: DBSession) -> Dict:
        """Build evidence relationship context."""
        evidence_links = db.query(EvidenceLink).filter(
            EvidenceLink.session_id == session_id
        ).all()

        supports = []
        contradictions = []
        extensions = []

        for link in evidence_links:
            claim = db.query(Claim).filter(Claim.id == link.source_claim_id).first()
            chunk = db.query(Chunk).filter(Chunk.id == link.supporting_chunk_id).first()

            if not claim or not chunk:
                continue

            claim_paper = db.query(Paper).filter(Paper.id == claim.paper_id).first()
            chunk_paper = db.query(Paper).filter(Paper.id == chunk.paper_id).first()

            entry = {
                "claim": claim.claim_text,
                "claim_paper": claim_paper.title if claim_paper else "Unknown",
                "evidence": chunk.content[:500],
                "evidence_paper": chunk_paper.title if chunk_paper else "Unknown",
                "evidence_section": chunk.section_name,
                "evidence_page": chunk.page_number,
                "score": link.similarity_score,
            }

            if link.relationship_type == "supports":
                supports.append(entry)
            elif link.relationship_type == "contradicts":
                contradictions.append(entry)
            elif link.relationship_type == "extends":
                extensions.append(entry)

        return {
            "supports": supports[:20],
            "contradictions": contradictions[:10],
            "extensions": extensions[:10],
            "summary": {
                "total_links": len(evidence_links),
                "supporting": len(supports),
                "contradicting": len(contradictions),
                "extending": len(extensions),
            },
        }

    def _build_comparison_table(self, papers: list) -> List[Dict]:
        """Build the paper comparison table data."""
        table = []
        for paper in papers:
            table.append({
                "paper_id": str(paper.id),
                "title": paper.title or paper.filename,
                "authors": paper.authors or [],
                "publication_year": paper.publication_year,
                "methodology": paper.methodology or "Not specified",
                "datasets": paper.datasets or [],
                "evaluation_metrics": paper.evaluation_metrics or [],
                "key_results": paper.key_results or "Not specified",
                "limitations": paper.limitations or "Not specified",
            })
        return table

    def _generate_review_text(self, paper_contexts: List[Dict], evidence_context: Dict,
                               comparison_table: List[Dict]) -> str:
        """Generate the full literature review text using evidence-aware RAG."""

        # Build the comprehensive prompt
        papers_section = ""
        for ctx in paper_contexts:
            papers_section += f"""
--- Paper [{ctx['index']}]: "{ctx['title']}" ---
Authors: {ctx['authors']}
Year: {ctx['year']}
Abstract: {ctx['abstract'][:500]}
Methodology: {ctx['methodology'][:500]}
Datasets: {ctx['datasets']}
Evaluation Metrics: {ctx['metrics']}
Key Results: {ctx['results'][:500]}
Limitations: {ctx['limitations'][:300]}
"""

        # Evidence relationships
        evidence_section = ""
        if evidence_context["supports"]:
            evidence_section += "\n--- SUPPORTING EVIDENCE ---\n"
            for s in evidence_context["supports"][:10]:
                evidence_section += f'Claim from "{s["claim_paper"]}": {s["claim"][:200]}\n'
                evidence_section += f'  Supported by "{s["evidence_paper"]}" (Section: {s["evidence_section"]}, Page: {s["evidence_page"]}): {s["evidence"][:200]}\n\n'

        if evidence_context["contradictions"]:
            evidence_section += "\n--- CONTRADICTING EVIDENCE ---\n"
            for c in evidence_context["contradictions"][:5]:
                evidence_section += f'Claim from "{c["claim_paper"]}": {c["claim"][:200]}\n'
                evidence_section += f'  Contradicted by "{c["evidence_paper"]}": {c["evidence"][:200]}\n\n'

        prompt = f"""You are an expert academic researcher writing a comprehensive literature review.
Based on the following {len(paper_contexts)} research papers and their evidence relationships, write a COMPLETE, academically structured literature review.

{papers_section}

{evidence_section}

REQUIRED STRUCTURE:
Write the literature review with these exact sections:

## 1. Introduction
Introduce the research domain, explain its importance, and state the scope of this review covering {len(paper_contexts)} papers.

## 2. Thematic Literature Synthesis
Group the papers thematically by their research focus areas. Discuss how they relate to each other and build upon previous work. Cite papers as [Paper N] where N is the paper number.

## 3. Comparative Methodology Analysis
Compare and contrast the methodologies used across papers. Identify methodological trends, innovations, and limitations. Discuss experimental designs and their suitability.

## 4. Dataset Comparison
Compare the datasets used across studies. Discuss dataset sizes, domains, characteristics, and implications for result generalizability.

## 5. Findings and Results Analysis
Synthesize the key findings across all papers. Highlight areas of agreement and quantify results where possible. Discuss statistical significance and effect sizes when available.

## 6. Contradictions and Conflicts
Identify and discuss any contradicting findings between papers. Analyze why contradictions may exist (different datasets, methodologies, evaluation settings).

## 7. Limitations
Discuss the collective limitations of the reviewed research. Identify common weaknesses and methodological concerns.

## 8. Research Gaps and Future Directions
Based on the analysis, identify clear gaps in the current research. Suggest specific, actionable future research directions.

## 9. Conclusion
Summarize the key takeaways from the review. Provide a balanced assessment of the field's current state.

## References
List all reviewed papers in a numbered format:
[1] Authors, "Title", Year.

CITATION RULES:
- Cite every factual claim using [Paper N] notation (e.g., [Paper 1], [Paper 2, 3])
- When citing specific results, include the values (e.g., "achieved 95.3% accuracy [Paper 2]")
- NEVER fabricate citations, results, or references
- If evidence is insufficient for a claim, explicitly state this
- Distinguish between findings directly stated in papers vs. your synthesis/interpretation
- For contradictions, cite both papers and explain the discrepancy

Write in a formal, academic tone. Be thorough, analytical, and critical.
The review should be 2000-4000 words long.
"""

        review_text = self.llm.generate(
            prompt=prompt,
            temperature=0.3,
            max_tokens=8000,
        )

        # Post-process: ensure proper citation formatting
        review_text = self._post_process_citations(review_text, paper_contexts)

        return review_text

    def _identify_research_gaps(self, paper_contexts: List[Dict], evidence_context: Dict) -> List[Dict]:
        """Identify research gaps using LLM analysis."""
        papers_summary = "\n".join([
            f"[{ctx['index']}] \"{ctx['title']}\" - {ctx['methodology'][:200]}"
            for ctx in paper_contexts
        ])

        prompt = f"""Based on these {len(paper_contexts)} research papers, identify specific research gaps.

Papers:
{papers_summary}

Return a JSON array of research gaps:
[
    {{
        "gap": "description of the research gap",
        "evidence": "what evidence supports this being a gap",
        "severity": "high|medium|low",
        "suggested_direction": "suggested future research direction"
    }}
]

Identify 3-7 specific, well-justified gaps. Do NOT fabricate gaps - base them on the actual limitations and missing aspects across these papers.
"""

        try:
            gaps = self.llm.generate_json(
                prompt=prompt,
                temperature=0.2,
                max_tokens=2000,
            )
            return gaps if isinstance(gaps, list) else []

        except Exception as e:
            logger.warning("Research gap identification failed", error=str(e))
            return []

    def _build_citation_index(self, papers: list, claims: list, db: DBSession) -> List[Dict]:
        """Build a structured citation index linking paper references to metadata."""
        citations = []
        for i, paper in enumerate(papers):
            authors_str = ", ".join(paper.authors) if paper.authors else "Unknown"
            citations.append({
                "index": i + 1,
                "paper_id": str(paper.id),
                "label": f"[Paper {i + 1}]",
                "title": paper.title or paper.filename,
                "authors": authors_str,
                "year": paper.publication_year,
                "formatted": f"[{i + 1}] {authors_str}, \"{paper.title or paper.filename}\", {paper.publication_year or 'N/A'}.",
            })
        return citations

    def _post_process_citations(self, text: str, paper_contexts: List[Dict]) -> str:
        """Ensure citations in the review text are properly formatted and valid."""
        # Check that all [Paper N] references are valid
        max_index = len(paper_contexts)
        invalid_refs = re.findall(r"\[Paper\s+(\d+)\]", text)
        for ref in invalid_refs:
            if int(ref) > max_index:
                text = text.replace(f"[Paper {ref}]", f"[Paper {max_index}]")

        return text
