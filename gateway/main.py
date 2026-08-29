"""
Agent Gateway - Main FastAPI Application
Personal AI Agent Platform
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

# Initialize logging (must be before other imports that use logging)
import logging_config

from db import startup_db, shutdown_db
from routes_auth import router as auth_router
from routes_chat import router as chat_router
from routes_audit import router as audit_router

# Setup logging
logger = logging.getLogger(__name__)


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

# Include routers
app.include_router(auth_router)
app.include_router(chat_router)

# Setup logging
logger = logging.getLogger(__name__)


# Health check endpoint (no auth required)
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "ok"}


# Placeholder root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Agent Gateway v3.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
