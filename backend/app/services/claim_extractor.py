"""
Scientific claim extraction using LLM.
Identifies factual claims, methodology descriptions, findings, and limitations.
"""

import re
import json
import structlog
from typing import List, Dict, Any
import google.generativeai as genai

from app.config import get_settings
from app.services.llm import get_llm_client

logger = structlog.get_logger(__name__)
settings = get_settings()


class ClaimExtractor:
    """Extracts structured scientific claims from paper text using LLM (Groq Llama 3.3 70B / Gemini)."""

    def __init__(self):
        self.llm = get_llm_client()

    def extract_claims(self, paper) -> List[Dict[str, Any]]:
        """Extract scientific claims from a paper."""
        if self.llm.is_configured and paper.full_text and len(paper.full_text) > 200:
            try:
                return self._extract_with_llm(paper)
            except Exception as e:
                logger.warning("LLM claim extraction failed, using heuristic", error=str(e))

        return self._extract_heuristic(paper)

    def _extract_with_llm(self, paper) -> List[Dict[str, Any]]:
        """Use LLM to extract structured claims."""
        # Use abstract + methodology + results + conclusion sections
        text_parts = []
        if paper.abstract:
            text_parts.append(f"ABSTRACT:\n{paper.abstract}")
        if paper.methodology:
            text_parts.append(f"METHODOLOGY:\n{paper.methodology}")
        if paper.key_results:
            text_parts.append(f"RESULTS:\n{paper.key_results}")
        if paper.limitations:
            text_parts.append(f"LIMITATIONS:\n{paper.limitations}")

        # Include full text excerpt if specific sections are missing
        if len(text_parts) < 2 and paper.full_text:
            text_parts.append(f"FULL TEXT (excerpt):\n{paper.full_text[:6000]}")

        combined_text = "\n\n".join(text_parts)[:8000]

        prompt = f"""Analyze this scientific paper and extract ALL significant scientific claims.
For each claim, classify it and provide context.

Return ONLY a valid JSON array of objects with these fields:
[
    {{
        "claim_text": "the exact or closely paraphrased claim",
        "claim_type": "finding|methodology|limitation|comparison|gap",
        "confidence": 0.95,
        "section_name": "which section this claim appears in",
        "page_number": null
    }}
]

Claim types:
- "finding": experimental results, empirical observations, performance numbers
- "methodology": descriptions of methods, techniques, algorithms, architectures used
- "limitation": acknowledged weaknesses, constraints, trade-offs
- "comparison": comparisons with other methods, baselines, state-of-the-art
- "gap": identified research gaps or open problems

Rules:
- Extract 5-20 claims per paper (focus on the most significant)
- Include specific numerical results when available (e.g., "achieved 95.3% accuracy on CIFAR-10")
- Preserve the factual precision of each claim
- Set confidence between 0.0-1.0 based on how clearly the claim is stated
- Do NOT invent or speculate - only extract claims explicitly stated in the text

Paper: "{paper.title or paper.filename}"
{combined_text}
"""

        claims = self.llm.generate_json(
            prompt,
            temperature=0.1,
            max_tokens=4000,
        )
        if not isinstance(claims, list):
            claims = [claims]

        # Validate claims
        validated = []
        for claim in claims:
            if isinstance(claim, dict) and claim.get("claim_text"):
                validated.append({
                    "claim_text": str(claim["claim_text"])[:2000],
                    "claim_type": claim.get("claim_type", "finding"),
                    "confidence": min(1.0, max(0.0, float(claim.get("confidence", 0.5)))),
                    "section_name": claim.get("section_name"),
                    "page_number": claim.get("page_number"),
                })

        logger.info("Claims extracted via LLM",
                    paper_title=paper.title, claim_count=len(validated))
        return validated

    def _extract_heuristic(self, paper) -> List[Dict[str, Any]]:
        """Heuristic claim extraction without LLM."""
        claims = []
        text = paper.full_text or ""

        # Finding patterns (results with numbers)
        finding_patterns = [
            r"(?:achieve[sd]?|obtain(?:ed|s)?|reach(?:ed|es)?|attain(?:ed|s)?)\s+(?:a\s+)?(?:an?\s+)?(\d+\.?\d*%?\s+\w+)",
            r"(?:accuracy|precision|recall|f1|bleu|rouge)\s+(?:of|is|was|=)\s+(\d+\.?\d*%?)",
            r"(?:outperform(?:ed|s)?|surpass(?:ed|es)?|exceed(?:ed|s)?)\s+.{10,100}",
            r"(?:results?\s+show|demonstrate|indicate|suggest|reveal)\s+.{20,200}",
        ]

        for pattern in finding_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 100)
                sentence = text[start:end].strip()
                # Clean to full sentence
                sentence = self._extract_sentence(text, match.start())
                if sentence and len(sentence) > 20:
                    claims.append({
                        "claim_text": sentence,
                        "claim_type": "finding",
                        "confidence": 0.6,
                        "section_name": "results",
                        "page_number": None,
                    })

        # Methodology patterns
        method_patterns = [
            r"(?:we\s+(?:propose|present|introduce|develop|design))\s+.{20,200}",
            r"(?:our\s+(?:approach|method|model|framework|system))\s+.{20,200}",
        ]

        for pattern in method_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                sentence = self._extract_sentence(text, match.start())
                if sentence and len(sentence) > 20:
                    claims.append({
                        "claim_text": sentence,
                        "claim_type": "methodology",
                        "confidence": 0.5,
                        "section_name": "methodology",
                        "page_number": None,
                    })

        # Limitation patterns
        limitation_patterns = [
            r"(?:limitation|drawback|weakness|shortcoming|constraint)s?\s+.{20,200}",
            r"(?:however|although|despite|nevertheless)\s*,?\s+.{20,200}",
        ]

        for pattern in limitation_patterns:
            for match in re.finditer(pattern, text[-3000:], re.IGNORECASE):
                sentence = self._extract_sentence(text[-3000:], match.start())
                if sentence and len(sentence) > 20:
                    claims.append({
                        "claim_text": sentence,
                        "claim_type": "limitation",
                        "confidence": 0.4,
                        "section_name": "limitations",
                        "page_number": None,
                    })

        # Deduplicate and limit
        seen = set()
        unique_claims = []
        for claim in claims:
            key = claim["claim_text"][:100].lower()
            if key not in seen:
                seen.add(key)
                unique_claims.append(claim)

        logger.info("Claims extracted via heuristic",
                    paper_title=paper.title, claim_count=len(unique_claims))
        return unique_claims[:20]

    def _extract_sentence(self, text: str, position: int) -> str:
        """Extract the full sentence containing the given position."""
        # Find sentence start
        start = position
        while start > 0 and text[start - 1] not in ".!?\n":
            start -= 1

        # Find sentence end
        end = position
        while end < len(text) and text[end] not in ".!?\n":
            end += 1
        if end < len(text):
            end += 1

        sentence = text[start:end].strip()
        return sentence[:500] if sentence else None
