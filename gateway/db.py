"""
Database configuration and session management
SQLAlchemy ORM setup for Agent Gateway
"""

import os
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
import logging
from typing import Any, Generator

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
    """Create tables, apply lightweight migrations, and seed model data."""
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    _migrate_audit_event_schema()
    _add_missing_audit_tool_columns()
    logger.info("Database tables created")
    _seed_model_config()
    logger.info("Database initialization complete")


def _initial_models() -> list[ModelConfig]:
    """Return the Phase 3 model records seeded into a new database."""
    return [
        ModelConfig(
            model_name="qwen3.5:2b",
            provider="ollama",
            tier="default",
            timeout_seconds=120,
            enabled=True,
            metadata_json="{}",
        ),
        ModelConfig(
            model_name="qwen3.5:4b",
            provider="ollama",
            tier="heavier",
            timeout_seconds=180,
            enabled=True,
            metadata_json="{}",
        ),
        ModelConfig(
            model_name="qwen3.5:9b",
            provider="ollama",
            tier="batch",
            timeout_seconds=600,
            enabled=True,
            metadata_json="{}",
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


def _seed_model_config() -> None:
    """Seed model configuration once and surface database failures."""
    db = SessionLocal()
    try:
        if db.query(ModelConfig).count() != 0:
            logger.info("Models already seeded")
            return
        logger.info("Seeding model configuration...")
        models = _initial_models()
        db.add_all(models)
        db.commit()
        logger.info("Seeded %s models", len(models))
    except Exception:
        db.rollback()
        logger.exception("Error seeding models")
        raise
    finally:
        db.close()


def _migrate_audit_event_schema() -> None:
    """Upgrade the pre-event Phase 3 audit table without losing its records."""
    inspector = inspect(engine)
    if "audit_logs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    if not _audit_event_migration_needed(inspector, columns):
        return
    logger.info("Migrating audit_logs to correlated event schema")
    with engine.begin() as connection:
        _create_replacement_audit_table(connection)
        _copy_audit_rows(connection, columns)
        _replace_audit_table(connection)


def _audit_event_migration_needed(
    inspector: Any,
    columns: set[str],
) -> bool:
    """Return whether request IDs are still unique or event IDs are absent."""
    request_id_is_unique = any(
        constraint.get("column_names") == ["request_id"]
        for constraint in inspector.get_unique_constraints("audit_logs")
    )
    request_id_is_unique = request_id_is_unique or any(
        index.get("unique") and index.get("column_names") == ["request_id"]
        for index in inspector.get_indexes("audit_logs")
    )
    return "event_id" not in columns or request_id_is_unique


def _create_replacement_audit_table(connection: Connection) -> None:
    """Create the correlated audit-event table used during migration."""
    connection.execute(text("DROP TABLE IF EXISTS audit_logs_new"))
    connection.execute(text("""
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
            tool_arguments TEXT,
            tool_result TEXT,
            result VARCHAR(32) NOT NULL,
            error_message TEXT,
            queue_wait_ms INTEGER,
            duration_ms INTEGER,
            FOREIGN KEY(user_id) REFERENCES users (id)
        )
    """))


def _copy_audit_rows(connection: Connection, columns: set[str]) -> None:
    """Copy legacy rows while generating event IDs and nullable tool fields."""
    generated_event = (
        "lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-' || "
        "lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2))) || '-' || "
        "lower(hex(randomblob(6)))"
    )
    source_event = "event_id" if "event_id" in columns else generated_event
    source_arguments = "tool_arguments" if "tool_arguments" in columns else "NULL"
    source_result = "tool_result" if "tool_result" in columns else "NULL"
    connection.execute(text(f"""
        INSERT INTO audit_logs_new (
            id, event_id, timestamp, user_id, request_id, agent, action,
            model, data_class, data_class_patterns, approval_required,
            approval_status, tokens_used, result, error_message,
            tool_arguments, tool_result, queue_wait_ms, duration_ms
        )
        SELECT
            id, {source_event}, timestamp, user_id, request_id, agent, action,
            model, data_class, data_class_patterns, approval_required,
            approval_status, tokens_used, result, error_message,
            {source_arguments}, {source_result}, queue_wait_ms, duration_ms
        FROM audit_logs
    """))


def _replace_audit_table(connection: Connection) -> None:
    """Swap in the migrated table and recreate its query indexes."""
    connection.execute(text("DROP TABLE audit_logs"))
    connection.execute(text("ALTER TABLE audit_logs_new RENAME TO audit_logs"))
    connection.execute(text("CREATE INDEX ix_audit_logs_timestamp ON audit_logs (timestamp)"))
    connection.execute(text("CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id)"))
    connection.execute(text("CREATE INDEX ix_audit_logs_request_id ON audit_logs (request_id)"))
    connection.execute(text("CREATE INDEX ix_timestamp_user_id ON audit_logs (timestamp, user_id)"))


def _add_missing_audit_tool_columns() -> None:
    """Add tool payload columns to databases already using event IDs."""
    inspector = inspect(engine)
    if "audit_logs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    missing = [
        name for name in ("tool_arguments", "tool_result") if name not in columns
    ]
    if not missing:
        return
    with engine.begin() as connection:
        for column_name in missing:
            connection.execute(
                text(f"ALTER TABLE audit_logs ADD COLUMN {column_name} TEXT")
            )


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
