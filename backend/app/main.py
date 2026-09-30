"""
Evidence-Aware AI Research Assistant - FastAPI Application
Main entry point with CORS, routers, WebSocket, and lifecycle events.
"""

import json
import asyncio
from uuid import UUID
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import structlog
import redis.asyncio as aioredis

from app.config import get_settings
from app.db.database import engine, init_db
from app.api import sessions, upload, review, export

logger = structlog.get_logger(__name__)
settings = get_settings()


# ─── Application Lifecycle ───

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Evidence-Aware Research Assistant", environment=settings.environment)

    # Initialize database tables automatically (Neon, Supabase, PostgreSQL)
    try:
        await init_db()
        logger.info("Database tables initialized")
    except Exception as e:
        logger.warning("Database init check completed", error=str(e))

    # Initialize Redis connection for WebSocket pub/sub (graceful fallback)
    try:
        app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning("Redis connection skipped or standalone", error=str(e))
        app.state.redis = None

    yield

    # Cleanup
    if getattr(app.state, "redis", None):
        try:
            await app.state.redis.close()
        except Exception:
            pass
    await engine.dispose()
    logger.info("Application shutdown complete")


# ─── FastAPI App ───

app = FastAPI(
    title="Evidence-Aware AI Research Assistant",
    description=(
        "Transform uploaded scientific PDFs into a unified, evidence-aware "
        "literature review with interactive comparison tables and verifiable citations."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ─── Middleware ───

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Register Routers ───

app.include_router(sessions.router)
app.include_router(upload.router)
app.include_router(review.router)
app.include_router(export.router)


# ─── Health Check ───

@app.get("/health", tags=["system"])
async def health_check():
    """Health check endpoint for monitoring and load balancers."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
        "version": "1.0.0",
    }


@app.get("/", tags=["system"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


# ─── WebSocket for Real-Time Progress ───

class ConnectionManager:
    """Manages WebSocket connections for real-time progress updates."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info("WebSocket connected", session_id=session_id)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info("WebSocket disconnected", session_id=session_id)

    async def send_progress(self, session_id: str, data: dict):
        if session_id in self.active_connections:
            disconnected = []
            for ws in self.active_connections[session_id]:
                try:
                    await ws.send_json(data)
                except Exception:
                    disconnected.append(ws)
            for ws in disconnected:
                self.disconnect(ws, session_id)


manager = ConnectionManager()


@app.websocket("/ws/sessions/{session_id}/progress")
async def websocket_progress(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time processing progress.
    Listens to Redis pub/sub channel for progress updates from Celery workers.
    """
    await manager.connect(websocket, session_id)

    try:
        redis = getattr(app.state, "redis", None)
        if redis:
            pubsub = redis.pubsub()
            await pubsub.subscribe(f"progress:{session_id}")
        else:
            pubsub = None

        # Listen for messages
        while True:
            if pubsub:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    await manager.send_progress(session_id, data)
            else:
                await asyncio.sleep(2.0)

            # Also check for client messages (keepalive pings)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.error("WebSocket error", session_id=session_id, error=str(e))
        manager.disconnect(websocket, session_id)
