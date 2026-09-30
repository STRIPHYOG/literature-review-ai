"""
Pydantic schemas for API request/response validation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


# ─── Session Schemas ───

class SessionCreate(BaseModel):
    """Response after creating a new session."""
    pass


class SessionStatus(BaseModel):
    """Session processing status response."""
    id: UUID
    status: str
    paper_count: int
    created_at: datetime
    papers: List["PaperSummary"] = []
    jobs: List["JobStatus"] = []

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseModel):
    id: UUID
    status: str
    paper_count: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Paper Schemas ───

class PaperSummary(BaseModel):
    """Summary of an uploaded paper."""
    id: UUID
    filename: str
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    publication_year: Optional[int] = None
    abstract: Optional[str] = None
    page_count: Optional[int] = None
    processing_status: str
    file_size_bytes: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class PaperMetadata(BaseModel):
    """Full extracted metadata for a paper."""
    id: UUID
    filename: str
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    publication_year: Optional[int] = None
    abstract: Optional[str] = None
    methodology: Optional[str] = None
    datasets: Optional[List[str]] = None
    evaluation_metrics: Optional[List[str]] = None
    key_results: Optional[str] = None
    limitations: Optional[str] = None
    page_count: Optional[int] = None
    processing_status: str

    model_config = ConfigDict(from_attributes=True)


# ─── Upload Schemas ───

class UploadResponse(BaseModel):
    """Response after uploading papers."""
    session_id: UUID
    uploaded_files: List[str]
    total_files: int
    message: str


class UploadError(BaseModel):
    """Upload error details."""
    filename: str
    error: str


# ─── Job Schemas ───

class JobStatus(BaseModel):
    """Background job status."""
    id: UUID
    job_type: str
    status: str
    progress: float
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Review Schemas ───

class ReviewResponse(BaseModel):
    """Generated literature review response."""
    id: UUID
    session_id: UUID
    review_text: str
    comparison_table: Optional[List[Dict[str, Any]]] = None
    evidence_summary: Optional[Dict[str, Any]] = None
    research_gaps: Optional[List[Dict[str, Any]]] = None
    citations: Optional[List[Dict[str, Any]]] = None
    generation_metadata: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─── Evidence Schemas ───

class EvidenceDetail(BaseModel):
    """Evidence supporting or contradicting a claim."""
    claim_id: UUID
    claim_text: str
    claim_type: Optional[str] = None
    source_paper_title: Optional[str] = None
    source_paper_id: UUID
    evidence_chunks: List["EvidenceChunk"] = []


class EvidenceChunk(BaseModel):
    """A specific chunk of evidence text."""
    chunk_id: UUID
    content: str
    section_name: Optional[str] = None
    page_number: Optional[int] = None
    paper_title: Optional[str] = None
    paper_id: UUID
    relationship_type: str  # supports, contradicts, extends, insufficient
    similarity_score: Optional[float] = None


# ─── Comparison Table Schemas ───

class ComparisonRow(BaseModel):
    """A row in the paper comparison table."""
    paper_id: UUID
    title: str
    authors: List[str]
    publication_year: Optional[int] = None
    research_objective: Optional[str] = None
    methodology: Optional[str] = None
    dataset: Optional[str] = None
    evaluation_metrics: Optional[List[str]] = None
    key_results: Optional[str] = None
    limitations: Optional[str] = None
    supporting_evidence: Optional[str] = None


class ComparisonTableResponse(BaseModel):
    """Interactive comparison table response."""
    session_id: UUID
    rows: List[ComparisonRow]


# ─── Progress WebSocket Schema ───

class ProgressUpdate(BaseModel):
    """Real-time progress update sent via WebSocket."""
    session_id: UUID
    stage: str
    progress: float  # 0.0 to 1.0
    message: str
    details: Optional[Dict[str, Any]] = None


# ─── Export Schemas ───

class ExportRequest(BaseModel):
    """Export format request."""
    format: str = Field(default="pdf", pattern="^(pdf|docx)$")


# ─── Error Schemas ───

class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None
