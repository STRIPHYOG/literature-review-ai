"""
PDF upload API endpoints with file validation, size limits, and S3 storage.
"""

from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import structlog

from app.db.database import get_db
from app.models import Session as SessionModel, Paper
from app.schemas import UploadResponse, UploadError
from app.storage.s3_client import s3_client
from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/sessions", tags=["upload"])

# Allowed MIME types for PDF files
ALLOWED_MIME_TYPES = {"application/pdf"}
PDF_MAGIC_BYTES = b"%PDF"


def validate_pdf(content: bytes, filename: str) -> None:
    """Validate that uploaded content is actually a PDF."""
    if not content:
        raise ValueError(f"File '{filename}' is empty")

    # Check file size
    if len(content) > settings.max_upload_size_bytes:
        raise ValueError(
            f"File '{filename}' exceeds maximum size of {settings.max_upload_size_mb}MB"
        )

    # Check magic bytes (PDF header)
    if not content[:4].startswith(PDF_MAGIC_BYTES):
        raise ValueError(f"File '{filename}' is not a valid PDF file")


@router.post("/{session_id}/papers", response_model=UploadResponse)
async def upload_papers(
    session_id: UUID,
    files: List[UploadFile] = File(..., description="PDF files to upload (1-10)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload one or more PDF files to a session.
    
    - Minimum 1 file, maximum 10 files per session
    - Each file must be a valid PDF
    - Maximum file size: 50MB per file
    """
    # Verify session exists
    result = await db.execute(
        select(SessionModel).where(SessionModel.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Check total file count
    existing_count_result = await db.execute(
        select(func.count(Paper.id)).where(Paper.session_id == session_id)
    )
    existing_count = existing_count_result.scalar() or 0
    total_count = existing_count + len(files)

    if len(files) < settings.min_papers_per_session and existing_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum {settings.min_papers_per_session} PDF file(s) required",
        )

    if total_count > settings.max_papers_per_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.max_papers_per_session} papers per session. "
                   f"Currently {existing_count} papers uploaded.",
        )

    uploaded_files = []
    errors = []

    for file in files:
        try:
            # Read file content
            content = await file.read()

            # Validate PDF
            validate_pdf(content, file.filename)

            # Generate S3 key and upload
            s3_key = s3_client.generate_key(str(session_id), file.filename)
            await s3_client.upload_file(content, s3_key)

            # Create paper record
            paper = Paper(
                session_id=session_id,
                filename=file.filename,
                s3_key=s3_key,
                file_size_bytes=len(content),
                processing_status="pending",
            )
            db.add(paper)
            uploaded_files.append(file.filename)

            logger.info(
                "Paper uploaded",
                session_id=str(session_id),
                filename=file.filename,
                size=len(content),
            )

        except ValueError as e:
            errors.append(UploadError(filename=file.filename, error=str(e)))
            logger.warning("Upload validation failed", filename=file.filename, error=str(e))
        except Exception as e:
            errors.append(UploadError(filename=file.filename, error=f"Upload failed: {str(e)}"))
            logger.error("Upload error", filename=file.filename, error=str(e))

    if not uploaded_files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No files were uploaded successfully. Errors: {[e.dict() for e in errors]}",
        )

    # Update session
    session.paper_count = existing_count + len(uploaded_files)
    session.status = "uploading"
    await db.flush()

    message = f"Successfully uploaded {len(uploaded_files)} file(s)"
    if errors:
        message += f". {len(errors)} file(s) failed validation."

    return UploadResponse(
        session_id=session_id,
        uploaded_files=uploaded_files,
        total_files=session.paper_count,
        message=message,
    )


@router.get("/{session_id}/papers", response_model=List[dict])
async def list_papers(session_id: UUID, db: AsyncSession = Depends(get_db)):
    """List all papers in a session with their metadata."""
    result = await db.execute(
        select(Paper).where(Paper.session_id == session_id).order_by(Paper.created_at)
    )
    papers = result.scalars().all()

    return [
        {
            "id": str(p.id),
            "filename": p.filename,
            "title": p.title,
            "authors": p.authors,
            "publication_year": p.publication_year,
            "abstract": p.abstract,
            "methodology": p.methodology,
            "datasets": p.datasets,
            "evaluation_metrics": p.evaluation_metrics,
            "key_results": p.key_results,
            "limitations": p.limitations,
            "page_count": p.page_count,
            "processing_status": p.processing_status,
            "file_size_bytes": p.file_size_bytes,
        }
        for p in papers
    ]
