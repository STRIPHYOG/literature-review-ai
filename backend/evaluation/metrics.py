"""
Evaluation metrics for measuring system quality.
Compares evidence-aware RAG vs conventional RAG baseline.
"""

import json
import time
import structlog
from typing import List, Dict, Any, Tuple
from collections import Counter

logger = structlog.get_logger(__name__)


class EvaluationMetrics:
    """Computes evaluation metrics for the literature review system."""

    @staticmethod
    def evidence_retrieval_precision_recall(
        retrieved_chunks: List[Dict],
        relevant_chunks: List[str],
    ) -> Dict[str, float]:
        """
        Measure evidence retrieval quality.
        
        Args:
            retrieved_chunks: Chunks returned by retrieval
            relevant_chunks: Ground truth relevant chunk IDs
        """
        retrieved_ids = {c.get("chunk_id") for c in retrieved_chunks}
        relevant_set = set(relevant_chunks)

        true_positives = len(retrieved_ids & relevant_set)
        precision = true_positives / max(1, len(retrieved_ids))
        recall = true_positives / max(1, len(relevant_set))
        f1 = 2 * precision * recall / max(0.001, precision + recall)

        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "retrieved_count": len(retrieved_ids),
            "relevant_count": len(relevant_set),
            "true_positives": true_positives,
        }

    @staticmethod
    def citation_correctness(
        verification_results: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Measure citation correctness from verification results.
        """
        if not verification_results:
            return {"citation_accuracy": 0.0, "hallucination_rate": 0.0}

        total = verification_results.get("total_claims", 0)
        verified = verification_results.get("verified", 0)
        hallucinated = verification_results.get("hallucinated", 0)

        return {
            "citation_accuracy": round(verified / max(1, total), 4),
            "hallucination_rate": round(hallucinated / max(1, total), 4),
            "total_claims_checked": total,
            "verified_claims": verified,
            "hallucinated_claims": hallucinated,
        }

    @staticmethod
    def claim_evidence_alignment(
        evidence_links: List[Dict],
    ) -> Dict[str, float]:
        """
        Measure how well claims align with evidence.
        """
        if not evidence_links:
            return {"alignment_score": 0.0}

        type_counts = Counter(l.get("relationship_type") for l in evidence_links)
        total = len(evidence_links)

        supporting = type_counts.get("supports", 0)
        contradicting = type_counts.get("contradicts", 0)
        extending = type_counts.get("extends", 0)
        insufficient = type_counts.get("insufficient", 0)

        # Alignment score: proportion of supporting + extending evidence
        alignment = (supporting + extending) / max(1, total)

        return {
            "alignment_score": round(alignment, 4),
            "supporting_ratio": round(supporting / max(1, total), 4),
            "contradicting_ratio": round(contradicting / max(1, total), 4),
            "extending_ratio": round(extending / max(1, total), 4),
            "insufficient_ratio": round(insufficient / max(1, total), 4),
            "total_links": total,
        }

    @staticmethod
    def factual_faithfulness(
        review_text: str,
        verification_details: List[Dict],
    ) -> Dict[str, float]:
        """
        Measure factual faithfulness of the generated review.
        """
        if not verification_details:
            return {"faithfulness_score": 0.0}

        level_scores = {
            "directly_supported": 1.0,
            "inferred": 0.7,
            "conflicting": 0.2,
            "insufficient": 0.3,
            "fabricated": 0.0,
        }

        total_score = sum(
            level_scores.get(d.get("level", "insufficient"), 0)
            for d in verification_details
        )

        avg_score = total_score / max(1, len(verification_details))

        return {
            "faithfulness_score": round(avg_score, 4),
            "total_checked": len(verification_details),
            "level_distribution": dict(Counter(d.get("level") for d in verification_details)),
        }

    @staticmethod
    def processing_latency(
        generation_metadata: Dict[str, Any],
    ) -> Dict[str, float]:
        """
        Report processing latency metrics.
        """
        total_time = generation_metadata.get("total_processing_time_seconds", 0)
        gen_time = generation_metadata.get("generation_time_seconds", 0)
        paper_count = generation_metadata.get("paper_count", 0)

        return {
            "total_processing_seconds": total_time,
            "generation_seconds": gen_time,
            "seconds_per_paper": round(total_time / max(1, paper_count), 2),
            "paper_count": paper_count,
        }


class BaselineRAGComparison:
    """
    Compare evidence-aware RAG against a conventional RAG baseline.
    """

    def __init__(self):
        self.metrics = EvaluationMetrics()

    def compare(
        self,
        evidence_aware_results: Dict[str, Any],
        baseline_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare two systems across all metrics.
        """
        comparison = {
            "evidence_aware": evidence_aware_results,
            "baseline": baseline_results,
            "improvements": {},
        }

        # Compare each metric
        for metric_name in evidence_aware_results:
            if metric_name in baseline_results:
                ea_val = evidence_aware_results[metric_name]
                bl_val = baseline_results[metric_name]

                if isinstance(ea_val, (int, float)) and isinstance(bl_val, (int, float)):
                    improvement = ea_val - bl_val
                    pct_improvement = (improvement / max(0.001, abs(bl_val))) * 100

                    comparison["improvements"][metric_name] = {
                        "absolute": round(improvement, 4),
                        "percentage": round(pct_improvement, 2),
                        "better": improvement > 0,
                    }

        return comparison

    def generate_report(self, comparison: Dict[str, Any]) -> str:
        """Generate a formatted comparison report."""
        report = "# Evidence-Aware RAG vs Conventional RAG Baseline\n\n"
        report += "## Metric Comparison\n\n"
        report += "| Metric | Evidence-Aware | Baseline | Δ Improvement |\n"
        report += "|--------|---------------|----------|---------------|\n"

        for metric, improvement in comparison.get("improvements", {}).items():
            ea_val = comparison["evidence_aware"].get(metric, "N/A")
            bl_val = comparison["baseline"].get(metric, "N/A")
            delta = f"+{improvement['absolute']}" if improvement["better"] else f"{improvement['absolute']}"
            pct = f"({improvement['percentage']:+.1f}%)"

            report += f"| {metric} | {ea_val} | {bl_val} | {delta} {pct} |\n"

        report += "\n## Key Findings\n\n"

        improvements = comparison.get("improvements", {})
        better_count = sum(1 for v in improvements.values() if v.get("better", False))
        total = len(improvements)

        report += f"- Evidence-aware RAG outperforms baseline on **{better_count}/{total}** metrics\n"

        return report
