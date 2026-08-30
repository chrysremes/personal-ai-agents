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
from classifier import redact_red_data, redact_sensitive_value


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

        # Apply the classifier's RED rules to every structured log sink, not
        # only audit events. This also protects provider exception messages.
        return redact_red_data(text)


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
    Writes to both stdout (JSON) and SQLite database
    """
    
    def __init__(self) -> None:
        self.logger = logging.getLogger("gateway.audit")
    
    async def log_action(
        self,
        user_id: int | None = None,
        request_id: str | None = None,
        agent: str | None = None,
        action: str | None = None,
        model: str | None = None,
        data_class: str | None = None,
        patterns: list[str] | None = None,
        approval_required: bool = False,
        approval_status: str | None = None,
        tokens: dict[str, int] | None = None,
        tool_arguments: dict[str, Any] | None = None,
        tool_result: Any = None,
        result: str = "unknown",
        error: str | None = None,
        duration_ms: int = 0,
        queue_wait_ms: int = 0,
    ) -> None:
        """Write one redacted event to structured output and SQLite."""
        event = {key: value for key, value in locals().items() if key != "self"}
        self.logger.info(json.dumps(self._redacted_event(event)))
        await self._persist(event)

    async def _persist(self, event: dict[str, Any]) -> None:
        """Persist an event and surface failures to the initiating request."""
        try:
            from audit import log_to_database

            await log_to_database(**event)
        except Exception:
            self.logger.exception("Failed to persist database audit event")
            raise

    def _redacted_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Return the structured-log form without mutating persistence input."""
        redacted = dict(event)
        redacted["patterns"] = redacted["patterns"] or []
        redacted["tool_arguments"] = redact_sensitive_value(
            redacted["tool_arguments"]
        )
        redacted["tool_result"] = redact_sensitive_value(redacted["tool_result"])
        if redacted["error"]:
            redacted["error"] = self._redact_error(redacted["error"])
        return redacted
    
    def _redact_error(self, error: str) -> str:
        """Redact RED patterns from error messages before logging"""
        return redact_red_data(error)


# Global audit logger instance
audit_logger = AuditLogger()
