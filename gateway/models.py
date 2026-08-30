"""
SQLAlchemy ORM models for Agent Gateway
Database schema definition
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    """Users table"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(32), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)  # Argon2 hash
    created_at = Column(String(30), nullable=False)  # ISO 8601
    last_login_at = Column(String(30), nullable=True)  # ISO 8601
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    """Refresh tokens table"""
    __tablename__ = "refresh_tokens"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token = Column(String(128), unique=True, nullable=False, index=True)  # hex-encoded random bytes
    issued_at = Column(String(30), nullable=False)  # ISO 8601
    expires_at = Column(String(30), nullable=False)  # ISO 8601
    revoked_at = Column(String(30), nullable=True)  # ISO 8601, NULL = not revoked
    
    # Relationships
    user = relationship("User", back_populates="refresh_tokens")


class AuditLog(Base):
    """Audit logs table"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String(30), nullable=False, index=True)  # ISO 8601 UTC
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable for unauthenticated
    request_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    agent = Column(String(128), nullable=True)
    action = Column(String(64), nullable=False)  # 'request_inference', 'login', etc.
    model = Column(String(64), nullable=True)
    data_class = Column(String(10), nullable=True)  # 'GREEN', 'YELLOW', 'RED'
    data_class_patterns = Column(Text, nullable=True)  # JSON array
    approval_required = Column(Boolean, default=False, nullable=False)
    approval_status = Column(String(32), nullable=True)  # 'auto_approved', 'user_approved', etc.
    tokens_used = Column(Text, nullable=True)  # JSON: {"input": N, "output": M}
    result = Column(String(32), nullable=False)  # 'success', 'error', 'timeout', etc.
    error_message = Column(Text, nullable=True)  # with RED patterns redacted
    queue_wait_ms = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="audit_logs")
    
    # Index for fast time-range queries
    __table_args__ = (
        Index("ix_timestamp_user_id", "timestamp", "user_id"),
    )


class ModelConfig(Base):
    """Model configuration table"""
    __tablename__ = "model_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(64), unique=True, nullable=False, index=True)
    provider = Column(String(32), nullable=False)  # 'ollama' or 'claude'
    tier = Column(String(32), nullable=True)  # 'default', 'heavier', 'batch', 'cloud'
    timeout_seconds = Column(Integer, nullable=False, default=120)
    enabled = Column(Boolean, default=True, nullable=False)
    metadata_json = Column("metadata", Text, nullable=True)  # Provider JSON config
