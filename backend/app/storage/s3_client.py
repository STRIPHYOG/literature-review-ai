"""
S3-compatible and local file storage client for managing uploaded PDFs.
Supports local filesystem storage (zero external dependencies) and S3/MinIO.
"""

import os
import io
import uuid
import structlog
from pathlib import Path
from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class StorageClient:
    """Storage client with automatic fallback between S3 and local disk."""

    def __init__(self):
        self.use_s3 = False
        self.client = None
        self.bucket = getattr(settings, "s3_bucket_name", "research-papers")

        # Try to connect to S3 if configured
        if getattr(settings, "s3_endpoint_url", None) and not os.environ.get("USE_LOCAL_STORAGE"):
            try:
                import boto3
                from botocore.config import Config
                self.client = boto3.client(
                    "s3",
                    endpoint_url=settings.s3_endpoint_url,
                    aws_access_key_id=settings.s3_access_key,
                    aws_secret_access_key=settings.s3_secret_key,
                    region_name=settings.s3_region,
                    config=Config(signature_version="s3v4", connect_timeout=3, retries={"max_attempts": 1}),
                )
                # Quick test
                self.client.head_bucket(Bucket=self.bucket)
                self.use_s3 = True
                logger.info("Connected to S3 object storage", bucket=self.bucket)
            except Exception:
                logger.info("S3 not reachable, using fast local disk storage", path=str(UPLOAD_DIR))
                self.use_s3 = False
        else:
            logger.info("Using local filesystem storage", path=str(UPLOAD_DIR))

    def generate_key(self, session_id: str, filename: str) -> str:
        """Generate a unique key for a file."""
        file_id = uuid.uuid4().hex[:12]
        safe_filename = filename.replace(" ", "_")
        return f"sessions/{session_id}/{file_id}_{safe_filename}"

    async def upload_file(self, file_content: bytes, s3_key: str, content_type: str = "application/pdf") -> str:
        """Upload a file to storage and return the key."""
        # 1. Always save to local disk as primary/cache
        local_path = UPLOAD_DIR / s3_key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(file_content)

        # 2. Upload to S3 if available
        if self.use_s3 and self.client:
            try:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=s3_key,
                    Body=file_content,
                    ContentType=content_type,
                )
                logger.info("File uploaded to S3", key=s3_key, size=len(file_content))
            except Exception as e:
                logger.warning("S3 sync failed, file saved locally", error=str(e))

        logger.info("File stored successfully", key=s3_key, size=len(file_content))
        return s3_key

    async def download_file(self, s3_key: str) -> bytes:
        """Download a file from storage."""
        # Check local disk first
        local_path = UPLOAD_DIR / s3_key
        if local_path.exists():
            return local_path.read_bytes()

        # Fallback to S3
        if self.use_s3 and self.client:
            try:
                response = self.client.get_object(Bucket=self.bucket, Key=s3_key)
                content = response["Body"].read()
                # Cache locally
                local_path.parent.mkdir(parents=True, exist_ok=True)
                local_path.write_bytes(content)
                return content
            except Exception as e:
                logger.error("S3 download failed", key=s3_key, error=str(e))
                raise

        raise FileNotFoundError(f"File not found: {s3_key}")

    async def delete_file(self, s3_key: str):
        """Delete a file from storage."""
        local_path = UPLOAD_DIR / s3_key
        if local_path.exists():
            local_path.unlink()

        if self.use_s3 and self.client:
            try:
                self.client.delete_object(Bucket=self.bucket, Key=s3_key)
            except Exception as e:
                logger.warning("S3 delete failed", error=str(e))

    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """Generate access URL."""
        if self.use_s3 and self.client:
            try:
                return self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": s3_key},
                    ExpiresIn=expiration,
                )
            except Exception:
                pass
        return f"/api/papers/{s3_key}"


# Singleton instance named s3_client for backwards compatibility
s3_client = StorageClient()
S3Client = StorageClient
