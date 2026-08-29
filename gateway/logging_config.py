"""
Logging infrastructure for Agent Gateway
JSON structured logging with token redaction
"""

import logging
import json
import sys
from typing import Any, Dict
from datetime import datetime
import re

from config import settings


class RedactedJSONFormatter(logging.Formatter):
    """
    Custom JSON formatter that:
    - Outputs structured JSON logs
    - Redacts JWT tokens and sensitive data
    - Never logs API keys or passwords
    """
    
    # Patterns to redact
    JWT_PATTERN = re.compile(r'Bearer\s+([a-zA-Z0-9\-_\.]+)', re.IGNORECASE)
    TOKEN_PATTERN = re.compile(r'token\s*[:=]\s*([a-zA-Z0-9\-_\.]+)', re.IGNORECASE)
    APIKEY_PATTERN = re.compile(r'(api[_-]?key|apikey|secret|password|passwd|pwd)\s*[:=]\s*([^\s,}]+)', re.IGNORECASE)
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with redaction"""
        # Create log dict
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": self._redact(record.getMessage()),
        }
        
        # Add extra fields if present
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "action"):
            log_data["action"] = record.action
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self._redact(self.formatException(record.exc_info))
        
        return json.dumps(log_data)
    
    def _redact(self, text: str) -> str:
        """Redact sensitive patterns from text"""
        # Redact JWT tokens
        text = self.JWT_PATTERN.sub("Bearer [REDACTED]", text)
        
        # Redact generic tokens
        text = self.TOKEN_PATTERN.sub("token: [REDACTED]", text)
        
        # Redact API keys, passwords, etc.
        text = self.APIKEY_PATTERN.sub(r"\1: [REDACTED]", text)
        
        return text


class ContextFilter(logging.Filter):
    """Filter that adds request context to log records"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        # Add context from thread-local storage if available (Phase 4+)
        # For now, this is a placeholder
        return True


def setup_logging() -> None:
    """Configure logging for the entire application"""
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.gateway_log_level))
    
    # Clear any existing handlers
    root_logger.handlers.clear()
    
    # Console handler with JSON formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, settings.gateway_log_level))
    console_handler.setFormatter(RedactedJSONFormatter())
    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)
    
    # Set specific logger levels
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging initialized: level={settings.gateway_log_level}, "
        f"env={settings.gateway_env}"
    )


# Initialize logging on import
setup_logging()


# Create application logger
logger = logging.getLogger("gateway")


# ============================================================================
# Audit Logger
# ============================================================================

class AuditLogger:
    """
    Separate logger for audit trail
    Will write to SQLite in full implementation
    """
    
    def __init__(self):
        self.logger = logging.getLogger("gateway.audit")
    
    async def log_action(
        self,
        user_id: int = None,
        request_id: str = None,
        agent: str = None,
        action: str = None,
        model: str = None,
        data_class: str = None,
        patterns: list = None,
        approval_required: bool = False,
        approval_status: str = None,
        tokens: dict = None,
        result: str = None,
        error: str = None,
        duration_ms: int = 0,
        queue_wait_ms: int = 0,
    ) -> None:
        """
        Log action to audit trail
        This will be saved to SQLite by the AuditLog model
        """
        log_entry = {
            "user_id": user_id,
            "request_id": request_id,
            "agent": agent,
            "action": action,
            "model": model,
            "data_class": data_class,
            "patterns": patterns or [],
            "approval_required": approval_required,
            "approval_status": approval_status,
            "tokens": tokens,
            "result": result,
            "error": self._redact_error(error) if error else None,
            "duration_ms": duration_ms,
            "queue_wait_ms": queue_wait_ms,
        }
        
        self.logger.info(json.dumps(log_entry))
    
    def _redact_error(self, error: str) -> str:
        """Redact RED patterns from error messages before logging"""
        # This will be fully implemented in Issue 4.2
        # For now, just return as-is
        return error


# Global audit logger instance
audit_logger = AuditLogger()
