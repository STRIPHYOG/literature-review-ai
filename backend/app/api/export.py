"""
Export API endpoints for downloading literature reviews as PDF/DOCX.
"""

import io
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.db.database import get_db
from app.models import Review
from app.services.exporter import ReviewExporter

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["export"])


@router.get("/{session_id}/export/pdf")
async def export_review_pdf(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Download the generated literature review as a PDF document."""
    result = await db.execute(
        select(Review).where(Review.session_id == session_id).order_by(Review.created_at.desc())
    )
    review = result.scalar_one_or_none()

    if not review:
        raise HTTPException(status_code=404, detail="No review found to export")

    try:
        exporter = ReviewExporter()
        pdf_bytes = exporter.to_pdf(
            review_text=review.review_text,
            comparison_table=review.comparison_table,
            citations=review.citations,
        )

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=literature_review_{session_id}.pdf"
            },
        )
    except Exception as e:
        logger.error("PDF export failed", session_id=str(session_id), error=str(e))
        raise HTTPException(status_code=500, detail=f"PDF export failed: {str(e)}")


@router.get("/{session_id}/export/docx")
async def export_review_docx(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """Download the generated literature review as a DOCX document."""
    result = await db.execute(
        select(Review).where(Review.session_id == session_id).order_by(Review.created_at.desc())
    )
    review = result.scalar_one_or_none()

    if not review:
        raise HTTPException(status_code=404, detail="No review found to export")

    try:
        exporter = ReviewExporter()
        docx_bytes = exporter.to_docx(
            review_text=review.review_text,
            comparison_table=review.comparison_table,
            citations=review.citations,
        )

        return StreamingResponse(
            io.BytesIO(docx_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename=literature_review_{session_id}.docx"
            },
        )
    except Exception as e:
        logger.error("DOCX export failed", session_id=str(session_id), error=str(e))
        raise HTTPException(status_code=500, detail=f"DOCX export failed: {str(e)}")
