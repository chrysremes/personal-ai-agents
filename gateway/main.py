"""
Agent Gateway - Main FastAPI Application
Personal AI Agent Platform
"""

import uuid
from datetime import datetime, timezone
import time

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from sqlalchemy import text

# Initialize logging (must be before other imports that use logging)
import logging_config

from db import SessionLocal, engine, startup_db, shutdown_db
from routes_auth import admin_router, router as auth_router
from routes_chat import ollama_provider, router as chat_router
from routes_audit import router as audit_router
from routes_tools import router as tools_router
from errors import error_response
from inference_queue import get_queue_depth
from middleware_auth import get_current_user
from models import ModelConfig, RefreshToken

# Setup logging
logger = logging.getLogger(__name__)
STARTED_AT = time.monotonic()


# Lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown"""
    # Startup
    logger.info("Agent Gateway starting...")
    startup_db()
    
    yield
    
    # Shutdown
    logger.info("Agent Gateway shutting down...")
    shutdown_db()

# Create FastAPI app
app = FastAPI(
    title="Agent Gateway",
    description="Central routing and authentication for Personal AI Agent Platform",
    version="3.0.0",
    lifespan=lifespan
)

# Configure CORS (Phase 4+ will tighten this)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def request_id_from(request: Request) -> str:
    """Use a caller-provided request ID when present, otherwise create one."""
    return request.headers.get("X-Request-ID", str(uuid.uuid4()))


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """Return the Phase 3 error envelope for normal HTTP failures."""
    if isinstance(exc.detail, dict):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=exc.headers,
        )

    error_codes = {
        400: "invalid_request",
        401: "authentication_error",
        403: "forbidden",
        404: "not_found",
    }
    return error_response(
        exc.status_code,
        error_codes.get(exc.status_code, "request_failed"),
        str(exc.detail),
        request_id_from(request),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Expose request-validation failures through the standard error envelope."""
    return error_response(
        422,
        "invalid_request",
        "Request validation failed.",
        request_id_from(request),
    )

# Include routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(audit_router)
app.include_router(tools_router)

# Setup logging
logger = logging.getLogger(__name__)


# Health check endpoint (no auth required)
@app.get("/health")
async def health():
    """Report process health plus required dependency state."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_status = "connected"
    except Exception:
        logger.exception("Database health check failed")
        database_status = "unavailable"

    ollama_status = "connected" if await ollama_provider.health_check() else "unavailable"
    overall_status = (
        "healthy"
        if database_status == "connected" and ollama_status == "connected"
        else "degraded"
    )
    return {
        "status": overall_status,
        "database": database_status,
        "ollama": ollama_status,
        "queue_depth": get_queue_depth(),
    }


@app.get("/status")
async def gateway_status(user_id: int = Depends(get_current_user)) -> dict:
    """Return authenticated operational status for Gateway clients."""
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    db = SessionLocal()
    try:
        models = [
            row.model_name
            for row in db.query(ModelConfig)
            .filter(ModelConfig.enabled.is_(True))
            .order_by(ModelConfig.id)
            .all()
        ]
        active_sessions = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now_iso,
            )
            .count()
        )
    finally:
        db.close()

    return {
        "gateway_version": app.version,
        "phase": 3,
        "uptime_seconds": int(time.monotonic() - STARTED_AT),
        "models_available": models,
        "active_sessions": active_sessions,
        "queue_depth": get_queue_depth(),
    }


# Placeholder root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Agent Gateway v3.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
