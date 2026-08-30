"""
Database configuration and session management
SQLAlchemy ORM setup for Agent Gateway
"""

import os
from sqlalchemy import create_engine, event, inspect, text
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
    _migrate_audit_event_schema()
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
                    metadata_json='{}',
                ),
                ModelConfig(
                    model_name="qwen3.5:4b",
                    provider="ollama",
                    tier="heavier",
                    timeout_seconds=180,
                    enabled=True,
                    metadata_json='{}',
                ),
                ModelConfig(
                    model_name="qwen3.5:9b",
                    provider="ollama",
                    tier="batch",
                    timeout_seconds=600,
                    enabled=True,
                    metadata_json='{}',
                ),
                ModelConfig(
                    model_name="claude-code",
                    provider="claude",
                    tier="cloud",
                    timeout_seconds=120,
                    enabled=True,
                    metadata_json='{"api_endpoint": "https://api.anthropic.com/v1/messages"}',
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


def _migrate_audit_event_schema() -> None:
    """Upgrade the pre-event Phase 3 audit table without losing its records."""
    inspector = inspect(engine)
    if "audit_logs" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    request_id_is_unique = any(
        constraint.get("column_names") == ["request_id"]
        for constraint in inspector.get_unique_constraints("audit_logs")
    )
    request_id_is_unique = request_id_is_unique or any(
        index.get("unique") and index.get("column_names") == ["request_id"]
        for index in inspector.get_indexes("audit_logs")
    )
    if "event_id" in columns and not request_id_is_unique:
        return

    logger.info("Migrating audit_logs to correlated event schema")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS audit_logs_new"))
        connection.execute(
            text(
                """
                CREATE TABLE audit_logs_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    event_id VARCHAR(36) NOT NULL UNIQUE,
                    timestamp VARCHAR(30) NOT NULL,
                    user_id INTEGER,
                    request_id VARCHAR(36) NOT NULL,
                    agent VARCHAR(128),
                    action VARCHAR(64) NOT NULL,
                    model VARCHAR(64),
                    data_class VARCHAR(10),
                    data_class_patterns TEXT,
                    approval_required BOOLEAN NOT NULL DEFAULT 0,
                    approval_status VARCHAR(32),
                    tokens_used TEXT,
                    result VARCHAR(32) NOT NULL,
                    error_message TEXT,
                    queue_wait_ms INTEGER,
                    duration_ms INTEGER,
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
                """
            )
        )
        event_expression = (
            "lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || "
            "lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || "
            "lower(hex(randomblob(6)))"
        )
        source_event = "event_id" if "event_id" in columns else event_expression
        connection.execute(
            text(
                f"""
                INSERT INTO audit_logs_new (
                    id, event_id, timestamp, user_id, request_id, agent, action,
                    model, data_class, data_class_patterns, approval_required,
                    approval_status, tokens_used, result, error_message,
                    queue_wait_ms, duration_ms
                )
                SELECT
                    id, {source_event}, timestamp, user_id, request_id, agent, action,
                    model, data_class, data_class_patterns, approval_required,
                    approval_status, tokens_used, result, error_message,
                    queue_wait_ms, duration_ms
                FROM audit_logs
                """
            )
        )
        connection.execute(text("DROP TABLE audit_logs"))
        connection.execute(text("ALTER TABLE audit_logs_new RENAME TO audit_logs"))
        connection.execute(text("CREATE INDEX ix_audit_logs_timestamp ON audit_logs (timestamp)"))
        connection.execute(text("CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id)"))
        connection.execute(text("CREATE INDEX ix_audit_logs_request_id ON audit_logs (request_id)"))
        connection.execute(text("CREATE INDEX ix_timestamp_user_id ON audit_logs (timestamp, user_id)"))


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
