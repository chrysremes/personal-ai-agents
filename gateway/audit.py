"""Durable, correlated audit event persistence and querying."""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from db import SessionLocal
from classifier import redact_red_data, redact_sensitive_value
from models import AuditLog

logger = logging.getLogger(__name__)


def audit_entry_to_dict(entry: AuditLog) -> dict[str, Any]:
    """Convert an ORM audit event into its external JSON representation."""
    return {
        "id": entry.id,
        "event_id": entry.event_id,
        "timestamp": entry.timestamp,
        "user_id": entry.user_id,
        "request_id": entry.request_id,
        "agent": entry.agent,
        "action": entry.action,
        "model": entry.model,
        "data_class": entry.data_class,
        "data_class_patterns": (
            json.loads(entry.data_class_patterns) if entry.data_class_patterns else None
        ),
        "approval_required": entry.approval_required,
        "approval_status": entry.approval_status,
        "tokens_used": json.loads(entry.tokens_used) if entry.tokens_used else None,
        "tool_arguments": (
            json.loads(entry.tool_arguments) if entry.tool_arguments else None
        ),
        "tool_result": json.loads(entry.tool_result) if entry.tool_result else None,
        "result": entry.result,
        "error_message": entry.error_message,
        "queue_wait_ms": entry.queue_wait_ms,
        "duration_ms": entry.duration_ms,
    }


class DatabaseAuditLogger:
    """Write and query audit events in SQLite."""

    async def log_action(
        self,
        user_id: Optional[int] = None,
        request_id: Optional[str] = None,
        agent: Optional[str] = None,
        action: Optional[str] = None,
        model: Optional[str] = None,
        data_class: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        approval_required: bool = False,
        approval_status: Optional[str] = None,
        tokens: Optional[Dict[str, int]] = None,
        tool_arguments: Optional[Dict[str, Any]] = None,
        tool_result: Any = None,
        result: str = "unknown",
        error: Optional[str] = None,
        duration_ms: int = 0,
        queue_wait_ms: Optional[int] = None,
    ) -> None:
        """Persist one unique event under a reusable request correlation ID."""
        event = {key: value for key, value in locals().items() if key != "self"}
        db = SessionLocal()
        try:
            log_entry = self._new_entry(event)
            db.add(log_entry)
            db.commit()
            logger.debug(
                "Audit event persisted: event_id=%s request_id=%s action=%s",
                log_entry.event_id,
                log_entry.request_id,
                log_entry.action,
            )
        except Exception:
            db.rollback()
            logger.exception("Failed to write audit event")
            raise
        finally:
            db.close()

    def _new_entry(self, event: dict[str, Any]) -> AuditLog:
        """Build a redacted ORM event from the logger's public arguments."""
        return AuditLog(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            user_id=event["user_id"],
            request_id=event["request_id"] or str(uuid.uuid4()),
            agent=event["agent"],
            action=event["action"] or "unknown",
            model=event["model"],
            data_class=event["data_class"],
            data_class_patterns=(
                json.dumps(event["patterns"]) if event["patterns"] else None
            ),
            approval_required=event["approval_required"],
            approval_status=event["approval_status"],
            tokens_used=json.dumps(event["tokens"]) if event["tokens"] else None,
            tool_arguments=self._json_redacted(event["tool_arguments"]),
            tool_result=self._json_redacted(event["tool_result"]),
            result=event["result"],
            error_message=self._redact_error(event["error"]) if event["error"] else None,
            queue_wait_ms=event["queue_wait_ms"],
            duration_ms=event["duration_ms"],
        )

    @staticmethod
    def _json_redacted(value: Any) -> Optional[str]:
        """Serialize a present JSON value after recursive RED redaction."""
        if value is None:
            return None
        return json.dumps(redact_sensitive_value(value))

    def _redact_error(self, error: str) -> str:
        """Apply the classifier's configured RED rules before persistence."""
        return redact_red_data(error)

    async def query_logs(
        self,
        user_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        agent: Optional[str] = None,
        result: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Return a limited page and the full count of matching events."""
        db = SessionLocal()
        try:
            query = db.query(AuditLog)
            if user_id is not None:
                query = query.filter(AuditLog.user_id == user_id)
            if start_time:
                query = query.filter(AuditLog.timestamp >= start_time)
            if end_time:
                query = query.filter(AuditLog.timestamp <= end_time)
            if agent:
                query = query.filter(AuditLog.agent == agent)
            if result:
                query = query.filter(AuditLog.result == result)

            total = query.count()
            entries = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
            return [audit_entry_to_dict(entry) for entry in entries], total
        except Exception:
            logger.exception("Failed to query audit events")
            raise
        finally:
            db.close()


db_audit_logger = DatabaseAuditLogger()


async def log_to_database(**event: Any) -> None:
    """Compatibility entry point for the structured audit logger."""
    await db_audit_logger.log_action(**event)
