"""
SQLAlchemy ORM models for the Evidence-Aware Research Assistant.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Integer, Float, BigInteger, Boolean,
    DateTime, ForeignKey, ARRAY, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Session(Base):
    """A user upload session containing multiple papers."""
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    status = Column(String(50), default="created", index=True)
    # Status: created -> uploading -> processing -> generating -> completed -> failed
    paper_count = Column(Integer, default=0)

    # Relationships
    papers = relationship("Paper", back_populates="session", cascade="all, delete-orphan")
    evidence_links = relationship("EvidenceLink", back_populates="session", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="session", cascade="all, delete-orphan")
    jobs = relationship("ProcessingJob", back_populates="session", cascade="all, delete-orphan")


class Paper(Base):
    """An uploaded scientific research paper."""
    __tablename__ = "papers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    s3_key = Column(String(1000), nullable=False)
    file_size_bytes = Column(BigInteger)

    # Extracted metadata
    title = Column(Text)
    authors = Column(ARRAY(Text))
    publication_year = Column(Integer)
    abstract = Column(Text)
    full_text = Column(Text)
    methodology = Column(Text)
    datasets = Column(ARRAY(Text))
    evaluation_metrics = Column(ARRAY(Text))
    key_results = Column(Text)
    limitations = Column(Text)
    page_count = Column(Integer)

    # Processing
    processing_status = Column(String(50), default="pending", index=True)
    # Status: pending -> extracting -> extracted -> analyzing -> completed -> failed
    processing_error = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    # Relationships
    session = relationship("Session", back_populates="papers")
    chunks = relationship("Chunk", back_populates="paper", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="paper", cascade="all, delete-orphan")


class Chunk(Base):
    """A semantically segmented text chunk from a paper."""
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    section_name = Column(String(200))
    page_number = Column(Integer)
    chunk_index = Column(Integer)
    embedding_id = Column(String(200))  # Qdrant point ID
    token_count = Column(Integer)

    # Relationships
    paper = relationship("Paper", back_populates="chunks")
    evidence_links = relationship("EvidenceLink", back_populates="supporting_chunk", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_chunks_paper_section", "paper_id", "section_name"),
    )


class Claim(Base):
    """A scientific claim extracted from a paper."""
    __tablename__ = "claims"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_text = Column(Text, nullable=False)
    claim_type = Column(String(100))  # finding, methodology, limitation, gap, comparison
    confidence = Column(Float)
    section_name = Column(String(200))
    page_number = Column(Integer)

    # Relationships
    paper = relationship("Paper", back_populates="claims")
    evidence_links = relationship("EvidenceLink", back_populates="source_claim", cascade="all, delete-orphan")


class EvidenceLink(Base):
    """A link between a scientific claim and supporting/contradicting evidence."""
    __tablename__ = "evidence_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_claim_id = Column(UUID(as_uuid=True), ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    supporting_chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    relationship_type = Column(String(100))  # supports, contradicts, extends, insufficient
    similarity_score = Column(Float)
    context_text = Column(Text)

    # Relationships
    session = relationship("Session", back_populates="evidence_links")
    source_claim = relationship("Claim", back_populates="evidence_links")
    supporting_chunk = relationship("Chunk", back_populates="evidence_links")


class Review(Base):
    """A generated literature review for a session."""
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    review_text = Column(Text)
    comparison_table = Column(JSONB)
    evidence_summary = Column(JSONB)
    research_gaps = Column(JSONB)
    citations = Column(JSONB)
    generation_metadata = Column(JSONB)  # model used, tokens, latency, etc.
    created_at = Column(DateTime(timezone=True), default=utcnow)

    # Relationships
    session = relationship("Session", back_populates="reviews")


class ProcessingJob(Base):
    """Tracks background processing jobs for progress reporting."""
    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(100))  # pdf_extraction, metadata_extraction, chunking, embedding, claim_extraction, evidence_mapping, review_generation
    status = Column(String(50), default="queued", index=True)
    # Status: queued -> running -> completed -> failed
    progress = Column(Float, default=0.0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    session = relationship("Session", back_populates="jobs")
