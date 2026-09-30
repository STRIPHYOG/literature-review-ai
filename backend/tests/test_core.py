"""
Tests for PDF upload and processing endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import io


@pytest.fixture
def client():
    """Create a test client."""
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock database session."""
    with patch("app.api.sessions.get_db") as mock:
        session = MagicMock()
        mock.return_value = session
        yield session


class TestHealthCheck:
    """Test system health endpoints."""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data


class TestUploadValidation:
    """Test PDF upload validation logic."""

    def test_validate_pdf_valid(self):
        from app.api.upload import validate_pdf
        # Valid PDF header
        content = b"%PDF-1.4 some content here" + b"x" * 1000
        validate_pdf(content, "test.pdf")  # Should not raise

    def test_validate_pdf_empty_file(self):
        from app.api.upload import validate_pdf
        with pytest.raises(ValueError, match="empty"):
            validate_pdf(b"", "test.pdf")

    def test_validate_pdf_not_pdf(self):
        from app.api.upload import validate_pdf
        with pytest.raises(ValueError, match="not a valid PDF"):
            validate_pdf(b"This is not a PDF file", "test.txt")

    def test_validate_pdf_too_large(self):
        from app.api.upload import validate_pdf
        # Create content larger than 50MB
        content = b"%PDF" + b"x" * (51 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds maximum size"):
            validate_pdf(content, "large.pdf")


class TestSemanticChunker:
    """Test the semantic chunking service."""

    def test_chunk_short_document(self):
        from app.services.chunker import SemanticChunker
        chunker = SemanticChunker()
        text = "This is a short document."
        chunks = chunker.chunk_document(text, "test-id")
        assert len(chunks) == 1
        assert chunks[0]["content"] == text

    def test_chunk_with_sections(self):
        from app.services.chunker import SemanticChunker
        chunker = SemanticChunker()
        text = """Abstract
This paper presents a novel approach.

Introduction
We introduce our methodology here. This section provides background on the problem space and discusses related work in the field.

Methodology
Our method uses a transformer-based architecture with attention mechanisms. We train on a large corpus of scientific papers and evaluate on standard benchmarks.

Results
Our approach achieves state-of-the-art performance on multiple benchmarks. Specifically, we achieve 95.3% accuracy on the test set.

Conclusion
We have demonstrated the effectiveness of our approach.
"""
        chunks = chunker.chunk_document(text, "test-id")
        assert len(chunks) >= 2
        # Check that sections are detected
        section_names = [c["section_name"] for c in chunks]
        assert any("abstract" in s for s in section_names if s)

    def test_chunk_sizes(self):
        from app.services.chunker import SemanticChunker
        chunker = SemanticChunker(max_chunk_size=100)
        # Create long text
        text = " ".join(["word"] * 2000)
        chunks = chunker.chunk_document(text, "test-id")
        for chunk in chunks:
            # Each chunk should not vastly exceed max size
            assert chunk["token_count"] <= 200  # Allow some flexibility


class TestEvaluationMetrics:
    """Test evaluation metrics computation."""

    def test_precision_recall(self):
        from evaluation.metrics import EvaluationMetrics

        retrieved = [
            {"chunk_id": "1"}, {"chunk_id": "2"}, {"chunk_id": "3"},
            {"chunk_id": "4"}, {"chunk_id": "5"},
        ]
        relevant = ["1", "2", "3", "6", "7"]

        result = EvaluationMetrics.evidence_retrieval_precision_recall(retrieved, relevant)
        assert result["true_positives"] == 3
        assert result["precision"] == 0.6
        assert result["recall"] == 0.6

    def test_citation_correctness(self):
        from evaluation.metrics import EvaluationMetrics

        verification = {
            "total_claims": 10,
            "verified": 8,
            "hallucinated": 1,
        }
        result = EvaluationMetrics.citation_correctness(verification)
        assert result["citation_accuracy"] == 0.8
        assert result["hallucination_rate"] == 0.1

    def test_claim_evidence_alignment(self):
        from evaluation.metrics import EvaluationMetrics

        links = [
            {"relationship_type": "supports"},
            {"relationship_type": "supports"},
            {"relationship_type": "contradicts"},
            {"relationship_type": "extends"},
            {"relationship_type": "insufficient"},
        ]
        result = EvaluationMetrics.claim_evidence_alignment(links)
        assert result["alignment_score"] == 0.6  # 3/5 (supports + extends)
        assert result["supporting_ratio"] == 0.4
        assert result["contradicting_ratio"] == 0.2


class TestLLMClient:
    """Test LLM Client fallback and configuration handling."""

    def test_llm_client_fallback_mode(self):
        from app.services.llm import LLMClient
        client = LLMClient()
        # When no key is set, client gracefully signals not configured
        if not client.is_configured:
            assert client.model_name == "heuristic-fallback"
            with pytest.raises(ValueError, match="No LLM API key configured"):
                client.generate("test prompt")

