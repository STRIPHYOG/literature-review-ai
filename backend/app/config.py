"""
Evidence-Aware AI Research Assistant - Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ─── Application ───
    app_name: str = "Evidence-Aware Research Assistant"
    environment: str = "development"
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # ─── Backend ───
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_cors_origins: str = "*"

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",")]

    # ─── PostgreSQL ───
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "literature_review"
    postgres_user: str = "litreview"
    postgres_password: str = "litreview_dev_password"
    database_url: str = "postgresql+asyncpg://litreview:litreview_dev_password@postgres:5432/literature_review"

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg uses ssl=require instead of sslmode=require
        url = url.replace("sslmode=require", "ssl=require")
        url = url.replace("&channel_binding=require", "")
        return url

    @property
    def sync_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url

    # ─── Redis ───
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ─── Qdrant ───
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "paper_chunks"
    qdrant_api_key: str = ""

    # ─── S3 / MinIO ───
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "research-papers"
    s3_region: str = "us-east-1"

    # ─── LLM Provider (OpenRouter / Hugging Face / NVIDIA / Groq / Gemini) ───
    llm_provider: str = "openrouter"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct"

    # Hugging Face (Alternative)
    hf_api_key: str = ""
    hf_base_url: str = "https://router.huggingface.co/v1"
    hf_model: str = "meta-llama/Llama-3.3-70B-Instruct"

    # NVIDIA NIM (Alternative)
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-3.2-90b-vision-instruct"

    # Groq (Alternative)
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Google Gemini (Alternative)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ─── ML Models ───
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ─── Upload Limits ───
    max_upload_size_mb: int = 50
    max_papers_per_session: int = 10
    min_papers_per_session: int = 1

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
