"""
Evidence mapping: connects scientific claims to supporting/contradicting evidence
across all papers in a session using hybrid retrieval.
"""

import json
import re
import structlog
from typing import List, Dict, Any
from app.config import get_settings
from app.services.retriever import HybridRetriever
from app.services.llm import get_llm_client

logger = structlog.get_logger(__name__)
settings = get_settings()


class EvidenceMapper:
    """
    Maps claims from each paper to evidence found in other papers.
    Identifies support, contradiction, extension, and insufficient evidence relationships.
    """

    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever
        self.llm = get_llm_client()

    def map_evidence(self, claims: list, session_id: str) -> List[Dict[str, Any]]:
        """
        For each claim, find related evidence from OTHER papers and classify the relationship.
        Optimized for high speed and evidence coverage.
        """
        evidence_links = []
        # Filter to the most significant claims across papers (up to 15 claims)
        selected_claims = sorted(claims, key=lambda c: getattr(c, 'confidence', 0.0) or 0.0, reverse=True)[:15]

        for claim in selected_claims:
            try:
                # Retrieve top relevant chunks from other papers
                related_chunks = self.retriever.retrieve(
                    query=claim.claim_text,
                    session_id=session_id,
                    top_k=8,
                    rerank_top_k=3,
                    exclude_paper_id=str(claim.paper_id),  # Exclude the claim's own paper
                )

                if not related_chunks:
                    continue

                # Classify relationships using fast heuristic
                for chunk in related_chunks:
                    relationship = self._classify_heuristic(claim, chunk)
                    evidence_links.append({
                        "source_claim_id": str(claim.id),
                        "supporting_chunk_id": chunk["chunk_id"],
                        "relationship_type": relationship["type"],
                        "similarity_score": chunk.get("rerank_score", chunk.get("fused_score", 0.0)),
                        "context_text": relationship.get("explanation", ""),
                    })

            except Exception as e:
                logger.warning(
                    "Evidence mapping failed for claim",
                    claim_id=str(claim.id),
                    error=str(e),
                )

        logger.info(
            "Evidence mapping completed",
            session_id=session_id,
            total_claims=len(claims),
            total_links=len(evidence_links),
        )

        return evidence_links

    def _classify_relationship(self, claim, chunk: Dict) -> Dict[str, str]:
        """Classify the relationship between a claim and a chunk of evidence."""
        return self._classify_heuristic(claim, chunk)

    def _classify_with_llm(self, claim, chunk: Dict) -> Dict[str, str]:
        """Use LLM to classify claim-evidence relationship."""
        prompt = f"""Analyze the relationship between a scientific claim and a piece of evidence.

CLAIM: "{claim.claim_text}"
CLAIM TYPE: {claim.claim_type}

EVIDENCE (from a different paper):
"{chunk.get('content', '')[:1500]}"

Classify the relationship as one of:
- "supports": The evidence supports or corroborates the claim
- "contradicts": The evidence contradicts or conflicts with the claim
- "extends": The evidence extends, builds upon, or adds nuance to the claim
- "insufficient": The evidence is related but insufficient to support or refute the claim

Return ONLY a JSON object:
{{"type": "supports|contradicts|extends|insufficient", "explanation": "brief explanation of why"}}
"""

        try:
            result = self.llm.generate_json(
                prompt,
                temperature=0.1,
                max_tokens=300,
            )
            valid_types = {"supports", "contradicts", "extends", "insufficient"}
            if isinstance(result, dict) and result.get("type") in valid_types:
                return result
            return {"type": "insufficient", "explanation": "Unable to determine relationship confidently."}

        except Exception as e:
            logger.warning("LLM relationship classification failed", error=str(e))
            return self._classify_heuristic(claim, chunk)

    def _classify_heuristic(self, claim, chunk: Dict) -> Dict[str, str]:
        """Heuristic relationship classification based on score thresholds."""
        score = chunk.get("rerank_score", chunk.get("fused_score", 0.0))
        content = chunk.get("content", "").lower()
        claim_text = claim.claim_text.lower()

        # Check for contradiction indicators
        contradiction_words = [
            "however", "contrary", "contradict", "unlike", "in contrast",
            "disagree", "opposite", "refute", "challenge", "fail",
        ]
        has_contradiction = any(w in content for w in contradiction_words)

        if has_contradiction and score > 0.5:
            return {"type": "contradicts", "explanation": "Contains contradiction indicators with high relevance"}
        elif score > 0.7:
            return {"type": "supports", "explanation": "High semantic similarity suggests supporting evidence"}
        elif score > 0.4:
            return {"type": "extends", "explanation": "Moderate similarity suggests related but extending content"}
        else:
            return {"type": "insufficient", "explanation": "Low relevance score"}
