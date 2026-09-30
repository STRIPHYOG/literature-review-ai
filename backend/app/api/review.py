"""
Review generation and evidence inspection API endpoints.
"""

from uuid import UUID
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import structlog

from app.db.database import get_db
from app.models import (
    Session as SessionModel, Paper, Review, Claim,
    EvidenceLink, Chunk
)
from app.schemas import ReviewResponse, EvidenceDetail, EvidenceChunk, ComparisonTableResponse, ComparisonRow

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["review"])


@router.post("/{session_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_review(
    session_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Trigger literature review generation for a session.
    This kicks off the full async pipeline:
    1. PDF text extraction
    2. Metadata extraction
    3. Semantic chunking & embedding
    4. Claim extraction
    5. Evidence mapping
    6. Hybrid retrieval + reranking
    7. Evidence-aware RAG generation
    8. Citation verification
    """
    result = await db.execute(
        select(SessionModel)
        .options(selectinload(SessionModel.papers))
        .where(SessionModel.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    if not session.papers:
        raise HTTPException(status_code=400, detail="No papers uploaded to this session")

    if session.status in ("processing", "generating"):
        raise HTTPException(status_code=409, detail="Session is already being processed")

    # Update session status
    session.status = "processing"
    await db.flush()

    task_id = str(uuid.uuid4())
    # Try Celery first; fall back to FastAPI BackgroundTasks if Redis is unavailable
    try:
        from app.workers.tasks import process_session_pipeline
        task = process_session_pipeline.delay(str(session_id))
        task_id = task.id
        logger.info("Review generation queued in Celery", session_id=str(session_id), task_id=task_id)
    except Exception as e:
        logger.warning("Celery/Redis not available, running via FastAPI BackgroundTasks", error=str(e))
        from app.workers.tasks import process_session_pipeline
        background_tasks.add_task(process_session_pipeline, str(session_id))
        logger.info("Review generation running in background", session_id=str(session_id), task_id=task_id)

    return {
        "session_id": str(session_id),
        "status": "processing",
        "task_id": task_id,
        "message": "Literature review generation started.",
    }



@router.get("/{session_id}/review", response_model=ReviewResponse)
async def get_review(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get the generated literature review for a session."""
    result = await db.execute(
        select(Review)
        .where(Review.session_id == session_id)
        .order_by(Review.created_at.desc())
    )
    review = result.scalar_one_or_none()

    if not review:
        raise HTTPException(
            status_code=404,
            detail="No review found. Generate one first using POST /generate",
        )

    return review


@router.get("/{session_id}/comparison", response_model=ComparisonTableResponse)
async def get_comparison_table(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get the interactive paper comparison table."""
    result = await db.execute(
        select(Paper)
        .where(Paper.session_id == session_id)
        .where(Paper.processing_status == "completed")
        .order_by(Paper.created_at)
    )
    papers = result.scalars().all()

    if not papers:
        raise HTTPException(status_code=404, detail="No processed papers found")

    rows = []
    for p in papers:
        rows.append(ComparisonRow(
            paper_id=p.id,
            title=p.title or p.filename,
            authors=p.authors or [],
            publication_year=p.publication_year,
            research_objective=p.abstract[:200] + "..." if p.abstract and len(p.abstract) > 200 else p.abstract,
            methodology=p.methodology,
            dataset=", ".join(p.datasets) if p.datasets else None,
            evaluation_metrics=p.evaluation_metrics,
            key_results=p.key_results,
            limitations=p.limitations,
            supporting_evidence=None,
        ))

    return ComparisonTableResponse(session_id=session_id, rows=rows)


@router.get("/{session_id}/evidence/{claim_id}", response_model=EvidenceDetail)
async def get_evidence_for_claim(
    session_id: UUID, claim_id: UUID, db: AsyncSession = Depends(get_db)
):
    """Get all evidence supporting or contradicting a specific claim."""
    # Get the claim
    claim_result = await db.execute(
        select(Claim)
        .options(selectinload(Claim.paper))
        .where(Claim.id == claim_id)
    )
    claim = claim_result.scalar_one_or_none()

    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim {claim_id} not found")

    # Get evidence links for this claim
    evidence_result = await db.execute(
        select(EvidenceLink)
        .options(selectinload(EvidenceLink.supporting_chunk).selectinload(Chunk.paper))
        .where(EvidenceLink.source_claim_id == claim_id)
        .where(EvidenceLink.session_id == session_id)
        .order_by(EvidenceLink.similarity_score.desc())
    )
    evidence_links = evidence_result.scalars().all()

    evidence_chunks = []
    for link in evidence_links:
        chunk = link.supporting_chunk
        if chunk:
            evidence_chunks.append(EvidenceChunk(
                chunk_id=chunk.id,
                content=chunk.content,
                section_name=chunk.section_name,
                page_number=chunk.page_number,
                paper_title=chunk.paper.title if chunk.paper else None,
                paper_id=chunk.paper_id,
                relationship_type=link.relationship_type,
                similarity_score=link.similarity_score,
            ))

    return EvidenceDetail(
        claim_id=claim.id,
        claim_text=claim.claim_text,
        claim_type=claim.claim_type,
        source_paper_title=claim.paper.title if claim.paper else None,
        source_paper_id=claim.paper_id,
        evidence_chunks=evidence_chunks,
    )
