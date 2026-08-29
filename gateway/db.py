"""
Database configuration and session management
SQLAlchemy ORM setup for Agent Gateway
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging
from typing import Generator

from models import Base, User, RefreshToken, AuditLog, ModelConfig
from config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Database Engine Configuration
# ============================================================================

def get_database_url() -> str:
    """Get database URL from config"""
    db_path = settings.gateway_db_path
    
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    return f"sqlite:///{db_path}"


# Create engine based on environment
DATABASE_URL = get_database_url()

if settings.gateway_env == "test":
    # Use in-memory SQLite for tests
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # Use file-based SQLite for production/development
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=(settings.gateway_log_level == "DEBUG"),
    )

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# ============================================================================
# Database Functions
# ============================================================================

def get_db() -> Generator[Session, None, None]:
    """Dependency injection for database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database - create all tables and seed data"""
    logger.info("Initializing database...")
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")
    
    # Seed model configuration
    db = SessionLocal()
    try:
        # Check if models already exist
        if db.query(ModelConfig).count() == 0:
            logger.info("Seeding model configuration...")
            
            models = [
                ModelConfig(
                    model_name="qwen3.5:2b",
                    provider="ollama",
                    tier="default",
                    timeout_seconds=120,
                    enabled=True,
                    metadata='{}',
                ),
                ModelConfig(
                    model_name="qwen3.5:4b",
                    provider="ollama",
                    tier="heavier",
                    timeout_seconds=180,
                    enabled=True,
                    metadata='{}',
                ),
                ModelConfig(
                    model_name="qwen3.5:9b",
                    provider="ollama",
                    tier="batch",
                    timeout_seconds=600,
                    enabled=True,
                    metadata='{}',
                ),
                ModelConfig(
                    model_name="claude-code",
                    provider="claude",
                    tier="cloud",
                    timeout_seconds=120,
                    enabled=True,
                    metadata='{"api_endpoint": "https://api.anthropic.com/v1/messages"}',
                ),
            ]
            
            for model in models:
                db.add(model)
            
            db.commit()
            logger.info(f"Seeded {len(models)} models")
        else:
            logger.info("Models already seeded")
    except Exception as e:
        logger.error(f"Error seeding models: {e}")
        db.rollback()
        raise
    finally:
        db.close()
    
    logger.info("Database initialization complete")


def reset_db() -> None:
    """Drop all tables and reinitialize (for testing)"""
    logger.warning("Resetting database...")
    Base.metadata.drop_all(bind=engine)
    init_db()
    logger.info("Database reset complete")


# ============================================================================
# Database Initialization on Startup
# ============================================================================

def startup_db() -> None:
    """Called on application startup"""
    logger.info(f"Using database: {DATABASE_URL}")
    init_db()


def shutdown_db() -> None:
    """Called on application shutdown"""
    engine.dispose()
    logger.info("Database connection closed")
