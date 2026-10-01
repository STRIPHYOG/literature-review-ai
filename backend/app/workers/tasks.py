"""
Celery tasks for the async document processing pipeline.
Orchestrates the full flow from PDF upload to literature review generation.
"""

import json
import time
from datetime import datetime, timezone
from uuid import UUID
import redis
import structlog
from celery import chain
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session as DBSession, sessionmaker

from app.workers.celery_app import celery_app
from app.config import get_settings
from app.models import (
    Session as SessionModel, Paper, Chunk, Claim,
    EvidenceLink, Review, ProcessingJob
)
from app.db.database import Base

logger = structlog.get_logger(__name__)
settings = get_settings()

# Sync engine for Celery workers (asyncio not available in Celery)
sync_engine = create_engine(settings.sync_database_url, pool_pre_ping=True)
SyncSession = sessionmaker(bind=sync_engine)

# Redis client for publishing progress updates (graceful fallback)
try:
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
except Exception:
    redis_client = None


def publish_progress(session_id: str, stage: str, progress: float, message: str, details: dict = None):
    """Publish a progress update to the WebSocket channel via Redis pub/sub if available."""
    data = {
        "session_id": session_id,
        "stage": stage,
        "progress": progress,
        "message": message,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if redis_client:
        try:
            redis_client.publish(f"progress:{session_id}", json.dumps(data))
        except Exception:
            pass
    logger.info("Progress update", stage=stage, progress=progress, message=message)



def update_job_status(db: DBSession, session_id: str, job_type: str, status: str, progress: float = 0.0, error: str = None):
    """Create or update a processing job status record."""
    job = db.query(ProcessingJob).filter(
        ProcessingJob.session_id == session_id,
        ProcessingJob.job_type == job_type,
    ).first()

    if not job:
        job = ProcessingJob(
            session_id=session_id,
            job_type=job_type,
            status=status,
            progress=progress,
        )
        db.add(job)
    else:
        job.status = status
        job.progress = progress

    if status == "running" and not job.started_at:
        job.started_at = datetime.now(timezone.utc)
    elif status in ("completed", "failed"):
        job.completed_at = datetime.now(timezone.utc)

    if error:
        job.error_message = error

    db.commit()


@celery_app.task(bind=True, name="process_session_pipeline")
def process_session_pipeline(self, session_id: str):
    """
    Main orchestration task that runs the full processing pipeline:
    1. PDF text extraction
    2. Scientific metadata extraction
    3. Semantic chunking
    4. Embedding generation
    5. Claim extraction
    6. Evidence mapping & graph construction
    7. Literature review generation
    8. Citation verification
    """
    db = SyncSession()
    start_time = time.time()

    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        papers = db.query(Paper).filter(Paper.session_id == session_id).all()
        if not papers:
            raise ValueError(f"No papers found for session {session_id}")

        total_steps = 8
        current_step = 0

        # ─── Step 1: PDF Text Extraction ───
        current_step += 1
        publish_progress(session_id, "pdf_extraction", current_step / total_steps,
                        "Extracting text from uploaded PDFs...")
        update_job_status(db, session_id, "pdf_extraction", "running")

        from app.services.pdf_processor import PDFProcessor
        pdf_processor = PDFProcessor()

        for i, paper in enumerate(papers):
            publish_progress(session_id, "pdf_extraction", 
                           (current_step - 1 + (i + 1) / len(papers)) / total_steps,
                           f"Extracting text from {paper.filename} ({i+1}/{len(papers)})")

            extracted = pdf_processor.extract_from_s3(paper.s3_key)
            paper.full_text = extracted["full_text"]
            paper.page_count = extracted["page_count"]
            paper.processing_status = "extracted"
            db.commit()
            update_job_status(db, session_id, "pdf_extraction", "running", progress=round((i + 1) / len(papers), 2))

        update_job_status(db, session_id, "pdf_extraction", "completed", 1.0)

        # ─── Step 2: Scientific Metadata Extraction ───
        current_step += 1
        publish_progress(session_id, "metadata_extraction", current_step / total_steps,
                        "Extracting scientific metadata...")
        update_job_status(db, session_id, "metadata_extraction", "running")

        from app.services.metadata_extractor import MetadataExtractor
        metadata_extractor = MetadataExtractor()

        for i, paper in enumerate(papers):
            publish_progress(session_id, "metadata_extraction",
                           (current_step - 1 + (i + 1) / len(papers)) / total_steps,
                           f"Analyzing metadata for {paper.filename} ({i+1}/{len(papers)})")

            metadata = metadata_extractor.extract(paper.full_text, paper.filename)
            paper.title = metadata.get("title", paper.filename)
            paper.authors = metadata.get("authors", [])
            paper.publication_year = metadata.get("publication_year")
            paper.abstract = metadata.get("abstract")
            paper.methodology = metadata.get("methodology")
            paper.datasets = metadata.get("datasets", [])
            paper.evaluation_metrics = metadata.get("evaluation_metrics", [])
            paper.key_results = metadata.get("key_results")
            paper.limitations = metadata.get("limitations")
            paper.processing_status = "metadata_extracted"
            db.commit()
            update_job_status(db, session_id, "metadata_extraction", "running", progress=round((i + 1) / len(papers), 2))


        update_job_status(db, session_id, "metadata_extraction", "completed", 1.0)

        # ─── Step 3: Semantic Chunking ───
        current_step += 1
        publish_progress(session_id, "chunking", current_step / total_steps,
                        "Performing semantic chunking...")
        update_job_status(db, session_id, "chunking", "running", progress=0.1)

        from app.services.chunker import SemanticChunker
        chunker = SemanticChunker()

        all_chunks = []
        for i, paper in enumerate(papers):
            publish_progress(session_id, "chunking",
                           (current_step - 1 + (i + 1) / len(papers)) / total_steps,
                           f"Segmenting {paper.filename} ({i+1}/{len(papers)})")
            chunks = chunker.chunk_document(paper.full_text, str(paper.id))
            for idx, chunk_data in enumerate(chunks):
                chunk = Chunk(
                    paper_id=paper.id,
                    content=chunk_data["content"],
                    section_name=chunk_data.get("section_name"),
                    page_number=chunk_data.get("page_number"),
                    chunk_index=idx,
                    token_count=chunk_data.get("token_count", 0),
                )
                db.add(chunk)
                all_chunks.append(chunk)
            db.commit()
            update_job_status(db, session_id, "chunking", "running", progress=round((i + 1) / len(papers), 2))

        update_job_status(db, session_id, "chunking", "completed", 1.0)

        # ─── Step 4: Embedding Generation ───
        current_step += 1
        publish_progress(session_id, "embedding", current_step / total_steps,
                        "Generating vector embeddings...")
        update_job_status(db, session_id, "embedding", "running", progress=0.35)

        from app.services.retriever import HybridRetriever
        retriever = HybridRetriever()

        # Refresh chunks from DB to get IDs
        all_chunks = db.query(Chunk).filter(
            Chunk.paper_id.in_([p.id for p in papers])
        ).all()

        retriever.index_chunks(all_chunks, session_id)
        update_job_status(db, session_id, "embedding", "completed", 1.0)

        # ─── Step 5: Claim Extraction ───
        current_step += 1
        publish_progress(session_id, "claim_extraction", current_step / total_steps,
                        "Extracting scientific claims...")
        update_job_status(db, session_id, "claim_extraction", "running", progress=0.1)

        from app.services.claim_extractor import ClaimExtractor
        claim_extractor = ClaimExtractor()

        all_claims = []
        for i, paper in enumerate(papers):
            publish_progress(session_id, "claim_extraction",
                           (current_step - 1 + (i + 1) / len(papers)) / total_steps,
                           f"Extracting claims from {paper.filename} ({i+1}/{len(papers)})")
            claims = claim_extractor.extract_claims(paper)
            for claim_data in claims:
                claim = Claim(
                    paper_id=paper.id,
                    claim_text=claim_data["claim_text"],
                    claim_type=claim_data.get("claim_type", "finding"),
                    confidence=claim_data.get("confidence", 0.0),
                    section_name=claim_data.get("section_name"),
                    page_number=claim_data.get("page_number"),
                )
                db.add(claim)
                all_claims.append(claim)
            db.commit()
            update_job_status(db, session_id, "claim_extraction", "running", progress=round((i + 1) / len(papers), 2))

        update_job_status(db, session_id, "claim_extraction", "completed", 1.0)

        # ─── Step 6: Evidence Mapping ───
        current_step += 1
        publish_progress(session_id, "evidence_mapping", current_step / total_steps,
                        "Mapping claims to evidence across papers...")
        update_job_status(db, session_id, "evidence_mapping", "running", progress=0.4)

        from app.services.evidence_mapper import EvidenceMapper
        evidence_mapper = EvidenceMapper(retriever)

        # Refresh claims from DB
        all_claims = db.query(Claim).filter(
            Claim.paper_id.in_([p.id for p in papers])
        ).all()

        evidence_links = evidence_mapper.map_evidence(all_claims, session_id)
        for link_data in evidence_links:
            link = EvidenceLink(
                session_id=session_id,
                source_claim_id=link_data["source_claim_id"],
                supporting_chunk_id=link_data["supporting_chunk_id"],
                relationship_type=link_data["relationship_type"],
                similarity_score=link_data.get("similarity_score", 0.0),
                context_text=link_data.get("context_text"),
            )
            db.add(link)
        db.commit()

        update_job_status(db, session_id, "evidence_mapping", "completed", 1.0)

        # ─── Step 7: Literature Review Generation ───
        current_step += 1
        publish_progress(session_id, "review_generation", current_step / total_steps,
                        "Generating evidence-aware literature review...")
        update_job_status(db, session_id, "review_generation", "running", progress=0.45)

        from app.services.review_generator import ReviewGenerator
        review_generator = ReviewGenerator(retriever)

        review_data = review_generator.generate(session_id, papers, all_claims, db)

        review = Review(
            session_id=session_id,
            review_text=review_data["review_text"],
            comparison_table=review_data.get("comparison_table"),
            evidence_summary=review_data.get("evidence_summary"),
            research_gaps=review_data.get("research_gaps"),
            citations=review_data.get("citations"),
            generation_metadata=review_data.get("generation_metadata"),
        )
        db.add(review)
        db.commit()

        update_job_status(db, session_id, "review_generation", "completed", 1.0)

        # ─── Step 8: Citation Verification ───
        current_step += 1
        publish_progress(session_id, "verification", current_step / total_steps,
                        "Verifying citations and checking for hallucinations...")
        update_job_status(db, session_id, "verification", "running", progress=0.5)

        from app.services.verifier import CitationVerifier
        verifier = CitationVerifier(retriever)

        verification_result = verifier.verify_review(
            review.review_text, review.citations, papers, all_chunks
        )

        # Update review with verification metadata
        meta = review.generation_metadata or {}
        meta["verification"] = verification_result
        meta["total_processing_time_seconds"] = round(time.time() - start_time, 2)
        review.generation_metadata = meta

        # Update paper statuses
        for paper in papers:
            paper.processing_status = "completed"

        session.status = "completed"
        db.commit()

        update_job_status(db, session_id, "verification", "completed", 1.0)

        publish_progress(session_id, "completed", 1.0,
                        "Literature review generation complete!",
                        {"processing_time_seconds": round(time.time() - start_time, 2)})

        logger.info("Pipeline completed", session_id=session_id,
                    duration=round(time.time() - start_time, 2))

    except Exception as e:
        logger.error("Pipeline failed", session_id=session_id, error=str(e))
        publish_progress(session_id, "error", 0.0, f"Processing failed: {str(e)}")

        try:
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if session:
                session.status = "failed"
            db.commit()
        except Exception:
            db.rollback()

        raise

    finally:
        db.close()
