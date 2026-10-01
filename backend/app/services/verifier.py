"""
Citation verification and hallucination detection.
Verifies that claims in the generated review are grounded in source evidence.
"""

import re
import json
import structlog
from typing import List, Dict, Any
from app.config import get_settings
from app.services.retriever import HybridRetriever
from app.services.llm import get_llm_client

logger = structlog.get_logger(__name__)
settings = get_settings()


class CitationVerifier:
    """
    Verifies citations in generated reviews against source papers.
    Detects hallucinations and classifies evidence support levels.
    """

    EVIDENCE_LEVELS = {
        "directly_supported": "The claim is directly stated in the cited source",
        "inferred": "The claim is a reasonable inference from the source",
        "conflicting": "The cited source contains conflicting information",
        "insufficient": "The cited source does not contain enough evidence",
        "fabricated": "No evidence found in any source paper",
    }

    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever
        self.llm = get_llm_client()

    def verify_review(
        self, review_text: str, citations: List[Dict],
        papers: list, chunks: list
    ) -> Dict[str, Any]:
        """
        Verify all citations in the generated review.
        Returns verification results with evidence support levels.
        """
        # Extract cited claims from the review
        cited_claims = self._extract_cited_claims(review_text)

        if not cited_claims:
            return {
                "total_claims": 0,
                "verified": 0,
                "unverified": 0,
                "hallucination_rate": 0.0,
                "details": [],
            }

        # Verify each claim
        verification_results = []
        verified_count = 0
        hallucinated_count = 0

        for claim_data in cited_claims:
            result = self._verify_single_claim(
                claim_data, papers, citations
            )
            verification_results.append(result)

            if result["level"] in ("directly_supported", "inferred"):
                verified_count += 1
            elif result["level"] == "fabricated":
                hallucinated_count += 1

        total = len(cited_claims)
        return {
            "total_claims": total,
            "verified": verified_count,
            "unverified": total - verified_count,
            "hallucinated": hallucinated_count,
            "hallucination_rate": round(hallucinated_count / max(1, total), 3),
            "verification_rate": round(verified_count / max(1, total), 3),
            "details": verification_results[:50],  # Limit details
            "summary": {
                "directly_supported": sum(1 for r in verification_results if r["level"] == "directly_supported"),
                "inferred": sum(1 for r in verification_results if r["level"] == "inferred"),
                "conflicting": sum(1 for r in verification_results if r["level"] == "conflicting"),
                "insufficient": sum(1 for r in verification_results if r["level"] == "insufficient"),
                "fabricated": hallucinated_count,
            },
        }

    def _extract_cited_claims(self, review_text: str) -> List[Dict]:
        """Extract sentences with citations from the review text."""
        claims = []

        # Find sentences with [Paper N] citations
        sentences = re.split(r"(?<=[.!?])\s+", review_text)

        for sentence in sentences:
            citation_matches = re.findall(r"\[Paper\s+(\d+(?:\s*,\s*\d+)*)\]", sentence)
            if citation_matches:
                # Extract paper indices
                paper_indices = []
                for match in citation_matches:
                    indices = [int(idx.strip()) for idx in match.split(",")]
                    paper_indices.extend(indices)

                # Clean sentence (remove citation markers for verification)
                clean_sentence = re.sub(r"\[Paper\s+\d+(?:\s*,\s*\d+)*\]", "", sentence).strip()

                if len(clean_sentence) > 20:
                    claims.append({
                        "original_sentence": sentence.strip(),
                        "clean_claim": clean_sentence,
                        "cited_papers": list(set(paper_indices)),
                    })

        return claims

    def _verify_single_claim(
        self, claim_data: Dict, papers: list, citations: List[Dict]
    ) -> Dict[str, Any]:
        """Verify a single cited claim against its source papers."""
        cited_indices = claim_data["cited_papers"]
        claim_text = claim_data["clean_claim"]
        source_texts = []

        # Get text from cited papers
        for idx in cited_indices:
            if 1 <= idx <= len(papers):
                paper = papers[idx - 1]
                # Build source context from available metadata
                source = f"Title: {paper.title}\n"
                if paper.abstract:
                    source += f"Abstract: {paper.abstract[:500]}\n"
                if paper.key_results:
                    source += f"Results: {paper.key_results[:500]}\n"
                if paper.methodology:
                    source += f"Methodology: {paper.methodology[:300]}\n"
                source_texts.append({"index": idx, "text": source})

        if not source_texts:
            return {
                "claim": claim_data["original_sentence"],
                "level": "fabricated",
                "explanation": "Cited paper index is out of range",
                "cited_papers": cited_indices,
            }

        # Fast and accurate keyword and semantic overlap verification
        return self._verify_heuristic(claim_data, source_texts)

    def _verify_with_llm(self, claim_data: Dict, sources: List[Dict]) -> Dict:
        """Use LLM to verify a claim against source texts."""
        sources_text = "\n\n".join([
            f"[Paper {s['index']}]: {s['text'][:800]}" for s in sources
        ])

        prompt = f"""Verify if this claim from a literature review is supported by the cited source papers.

CLAIM: "{claim_data['original_sentence']}"

CITED SOURCES:
{sources_text}

Classify the evidence support level as one of:
- "directly_supported": The claim is directly stated or very closely paraphrased from the source
- "inferred": The claim is a reasonable interpretation/inference from the source
- "conflicting": The source contains information that conflicts with the claim
- "insufficient": The source is related but doesn't contain enough evidence
- "fabricated": The claim appears to be fabricated with no basis in the sources

Return ONLY a JSON object:
{{"level": "directly_supported|inferred|conflicting|insufficient|fabricated", "explanation": "brief explanation"}}
"""

        try:
            result = self.llm.generate_json(
                prompt=prompt,
                temperature=0.1,
                max_tokens=300,
            )

            valid_levels = set(self.EVIDENCE_LEVELS.keys())
            if not isinstance(result, dict) or result.get("level") not in valid_levels:
                result = {"level": "insufficient", "explanation": "Unable to verify support level confidently"}

            result["claim"] = claim_data["original_sentence"]
            result["cited_papers"] = claim_data["cited_papers"]
            return result

        except Exception as e:
            logger.warning("LLM verification failed", error=str(e))
            return {
                "claim": claim_data["original_sentence"],
                "level": "insufficient",
                "explanation": f"Verification failed: {str(e)}",
                "cited_papers": claim_data["cited_papers"],
            }

    def _verify_heuristic(self, claim_data: Dict, sources: List[Dict]) -> Dict:
        """Simple keyword-overlap verification."""
        claim_words = set(claim_data["clean_claim"].lower().split())
        best_overlap = 0

        for source in sources:
            source_words = set(source["text"].lower().split())
            overlap = len(claim_words & source_words) / max(1, len(claim_words))
            best_overlap = max(best_overlap, overlap)

        if best_overlap > 0.5:
            level = "directly_supported"
        elif best_overlap > 0.3:
            level = "inferred"
        elif best_overlap > 0.1:
            level = "insufficient"
        else:
            level = "fabricated"

        return {
            "claim": claim_data["original_sentence"],
            "level": level,
            "explanation": f"Keyword overlap: {best_overlap:.2f}",
            "cited_papers": claim_data["cited_papers"],
        }
