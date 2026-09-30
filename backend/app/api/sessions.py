"""
Session management API endpoints.
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import structlog

from app.db.database import get_db
from app.models import Session as SessionModel, Paper, ProcessingJob
from app.schemas import SessionResponse, SessionStatus, PaperSummary, JobStatus

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(db: AsyncSession = Depends(get_db)):
    """Create a new upload session."""
    session = SessionModel(status="created")
    db.add(session)
    await db.flush()
    await db.refresh(session)

    logger.info("Session created", session_id=str(session.id))
    return session


@router.get("/{session_id}", response_model=SessionStatus)
async def get_session_status(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get full session status including papers and processing jobs."""
    result = await db.execute(
        select(SessionModel)
        .options(
            selectinload(SessionModel.papers),
            selectinload(SessionModel.jobs),
        )
        .where(SessionModel.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    return SessionStatus(
        id=session.id,
        status=session.status,
        paper_count=session.paper_count,
        created_at=session.created_at,
        papers=[PaperSummary.model_validate(p) for p in session.papers],
        jobs=[JobStatus.model_validate(j) for j in session.jobs],
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Delete a session and all associated data."""
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    await db.delete(session)
    logger.info("Session deleted", session_id=str(session_id))
