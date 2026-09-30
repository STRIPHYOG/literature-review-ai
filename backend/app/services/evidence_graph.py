"""
Evidence graph construction connecting papers, claims, methods, and findings.
"""

import structlog
from typing import List, Dict, Any
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import select

from app.models import Paper, Claim, EvidenceLink, Chunk

logger = structlog.get_logger(__name__)


class EvidenceGraph:
    """
    Builds an evidence graph connecting:
    - Papers -> Claims
    - Claims -> Evidence chunks
    - Papers -> Papers (via shared evidence)
    """

    def build_graph(self, session_id: str, db: DBSession) -> Dict[str, Any]:
        """Build the complete evidence graph for a session."""
        papers = db.query(Paper).filter(Paper.session_id == session_id).all()
        claims = db.query(Claim).filter(
            Claim.paper_id.in_([p.id for p in papers])
        ).all()
        links = db.query(EvidenceLink).filter(
            EvidenceLink.session_id == session_id
        ).all()

        # Build nodes
        nodes = []
        edges = []

        # Paper nodes
        for paper in papers:
            nodes.append({
                "id": f"paper_{paper.id}",
                "type": "paper",
                "label": paper.title or paper.filename,
                "metadata": {
                    "authors": paper.authors,
                    "year": paper.publication_year,
                },
            })

        # Claim nodes
        for claim in claims:
            nodes.append({
                "id": f"claim_{claim.id}",
                "type": claim.claim_type or "claim",
                "label": claim.claim_text[:100],
                "metadata": {
                    "confidence": claim.confidence,
                    "section": claim.section_name,
                },
            })
            # Paper -> Claim edge
            edges.append({
                "source": f"paper_{claim.paper_id}",
                "target": f"claim_{claim.id}",
                "type": "has_claim",
            })

        # Evidence edges
        for link in links:
            chunk = db.query(Chunk).filter(Chunk.id == link.supporting_chunk_id).first()
            if chunk:
                edges.append({
                    "source": f"claim_{link.source_claim_id}",
                    "target": f"paper_{chunk.paper_id}",
                    "type": link.relationship_type,
                    "score": link.similarity_score,
                })

        # Compute paper-to-paper connections
        paper_connections = self._compute_paper_connections(links, claims, db)

        return {
            "nodes": nodes,
            "edges": edges,
            "paper_connections": paper_connections,
            "statistics": {
                "total_papers": len(papers),
                "total_claims": len(claims),
                "total_evidence_links": len(links),
                "supporting_links": sum(1 for l in links if l.relationship_type == "supports"),
                "contradicting_links": sum(1 for l in links if l.relationship_type == "contradicts"),
                "extending_links": sum(1 for l in links if l.relationship_type == "extends"),
            },
        }

    def _compute_paper_connections(self, links: list, claims: list, db: DBSession) -> List[Dict]:
        """Compute direct paper-to-paper relationships via shared evidence."""
        connections = {}

        for link in links:
            # Get the claim's paper
            claim = next((c for c in claims if str(c.id) == str(link.source_claim_id)), None)
            if not claim:
                continue

            # Get the evidence chunk's paper
            chunk = db.query(Chunk).filter(Chunk.id == link.supporting_chunk_id).first()
            if not chunk:
                continue

            paper_pair = tuple(sorted([str(claim.paper_id), str(chunk.paper_id)]))
            if paper_pair[0] == paper_pair[1]:
                continue

            if paper_pair not in connections:
                connections[paper_pair] = {
                    "paper_a": paper_pair[0],
                    "paper_b": paper_pair[1],
                    "supporting": 0,
                    "contradicting": 0,
                    "extending": 0,
                    "total": 0,
                }

            connections[paper_pair]["total"] += 1
            if link.relationship_type == "supports":
                connections[paper_pair]["supporting"] += 1
            elif link.relationship_type == "contradicts":
                connections[paper_pair]["contradicting"] += 1
            elif link.relationship_type == "extends":
                connections[paper_pair]["extending"] += 1

        return list(connections.values())
