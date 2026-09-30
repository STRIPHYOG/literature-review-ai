"""
Celery application configuration for async document processing.
"""

from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "research_assistant",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    # Task settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Worker settings
    worker_prefetch_multiplier=1,  # Process one task at a time (heavy tasks)
    worker_max_tasks_per_child=10,  # Restart worker after 10 tasks (memory management)
    task_acks_late=True,  # Acknowledge tasks after completion

    # Result settings
    result_expires=86400,  # Results expire after 24 hours

    # Task routing
    task_routes={
        "app.workers.tasks.process_session_pipeline": {"queue": "pipeline"},
        "app.workers.tasks.extract_pdf_text": {"queue": "processing"},
        "app.workers.tasks.extract_metadata": {"queue": "processing"},
        "app.workers.tasks.generate_embeddings": {"queue": "ml"},
        "app.workers.tasks.generate_review": {"queue": "ml"},
    },

    # Default queue
    task_default_queue="default",
)
