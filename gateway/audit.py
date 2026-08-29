"""
Audit logging to SQLite database
Persistent audit trail of all actions
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from db import SessionLocal
from models import AuditLog
from classifier import classify_data

logger = logging.getLogger(__name__)


class DatabaseAuditLogger:
    """Writes audit logs to SQLite database"""
    
    async def log_action(
        self,
        user_id: Optional[int] = None,
        request_id: Optional[str] = None,
        agent: Optional[str] = None,
        action: str = None,
        model: Optional[str] = None,
        data_class: Optional[str] = None,
        patterns: Optional[List[str]] = None,
        approval_required: bool = False,
        approval_status: Optional[str] = None,
        tokens: Optional[Dict[str, int]] = None,
        result: str = "unknown",
        error: Optional[str] = None,
        duration_ms: int = 0,
        queue_wait_ms: Optional[int] = None,
    ) -> None:
        """
        Log action to audit_logs table
        
        Args:
            user_id: User ID (optional for unauthenticated actions)
            request_id: Unique request ID
            agent: Agent name (e.g., "news", "calendar")
            action: Action name (e.g., "login", "chat", "refresh_token")
            model: Model name if inference was used
            data_class: Data classification (RED/YELLOW/GREEN)
            patterns: List of matched classification patterns
            approval_required: Whether approval was needed
            approval_status: Approval outcome
            tokens: Token usage {"input": N, "output": M}
            result: Result ("success", "error", "timeout", "blocked", etc.)
            error: Error message (with RED patterns redacted)
            duration_ms: Request duration in milliseconds
            queue_wait_ms: Time spent waiting in queue
        """
        try:
            db = SessionLocal()
            
            # Redact error message before storing
            error_redacted = self._redact_error(error) if error else None
            
            # Serialize JSON fields
            patterns_json = json.dumps(patterns) if patterns else None
            tokens_json = json.dumps(tokens) if tokens else None
            
            # Create audit log entry
            log_entry = AuditLog(
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                user_id=user_id,
                request_id=request_id,
                agent=agent,
                action=action,
                model=model,
                data_class=data_class,
                data_class_patterns=patterns_json,
                approval_required=approval_required,
                approval_status=approval_status,
                tokens_used=tokens_json,
                result=result,
                error_message=error_redacted,
                queue_wait_ms=queue_wait_ms,
                duration_ms=duration_ms,
            )
            
            # Add and commit
            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)
            
            logger.debug(
                f"Audit log written: request_id={request_id}, "
                f"action={action}, result={result}, entry_id={log_entry.id}"
            )
            
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            # Don't raise - audit logging failures shouldn't crash the app
        finally:
            db.close()
    
    def _redact_error(self, error: str) -> str:
        """
        Redact RED patterns from error message
        
        Args:
            error: Error message to redact
            
        Returns:
            Error message with RED patterns replaced by [REDACTED]
        """
        # TODO: Implement full redaction using classifier patterns
        # For now, basic redaction
        
        import re
        
        # Redact common sensitive patterns
        redactions = [
            (r'\d{3}\.\d{3}\.\d{3}-\d{2}', '[REDACTED_CPF]'),  # CPF
            (r'\b\d{6,10}\b', '[REDACTED_NUMBER]'),  # Account numbers
            (r'(password|senha|key|api)[:\s=]+[^\s,}]+', r'\1: [REDACTED]'),  # Passwords/keys
        ]
        
        for pattern, replacement in redactions:
            error = re.sub(pattern, replacement, error, flags=re.IGNORECASE)
        
        return error
    
    async def query_logs(
        self,
        user_id: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        agent: Optional[str] = None,
        result: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query audit logs
        
        Args:
            user_id: Filter by user
            start_time: ISO 8601 start time
            end_time: ISO 8601 end time
            agent: Filter by agent name
            result: Filter by result (success/error/etc)
            limit: Max rows to return
            
        Returns:
            List of log entries as dicts
        """
        try:
            db = SessionLocal()
            
            query = db.query(AuditLog)
            
            if user_id:
                query = query.filter(AuditLog.user_id == user_id)
            if start_time:
                query = query.filter(AuditLog.timestamp >= start_time)
            if end_time:
                query = query.filter(AuditLog.timestamp <= end_time)
            if agent:
                query = query.filter(AuditLog.agent == agent)
            if result:
                query = query.filter(AuditLog.result == result)
            
            # Order by timestamp descending, limit results
            entries = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
            
            # Convert to dicts
            logs = []
            for entry in entries:
                log_dict = {
                    "id": entry.id,
                    "timestamp": entry.timestamp,
                    "user_id": entry.user_id,
                    "request_id": entry.request_id,
                    "agent": entry.agent,
                    "action": entry.action,
                    "model": entry.model,
                    "data_class": entry.data_class,
                    "data_class_patterns": json.loads(entry.data_class_patterns) if entry.data_class_patterns else None,
                    "approval_required": entry.approval_required,
                    "approval_status": entry.approval_status,
                    "tokens_used": json.loads(entry.tokens_used) if entry.tokens_used else None,
                    "result": entry.result,
                    "error_message": entry.error_message,
                    "queue_wait_ms": entry.queue_wait_ms,
                    "duration_ms": entry.duration_ms,
                }
                logs.append(log_dict)
            
            logger.debug(f"Queried audit logs: returned {len(logs)} entries")
            return logs
            
        except Exception as e:
            logger.error(f"Failed to query audit logs: {e}")
            return []
        finally:
            db.close()


# Global database audit logger instance
db_audit_logger = DatabaseAuditLogger()


async def log_to_database(
    user_id: Optional[int] = None,
    request_id: Optional[str] = None,
    agent: Optional[str] = None,
    action: str = None,
    model: Optional[str] = None,
    data_class: Optional[str] = None,
    patterns: Optional[List[str]] = None,
    approval_required: bool = False,
    approval_status: Optional[str] = None,
    tokens: Optional[Dict[str, int]] = None,
    result: str = "unknown",
    error: Optional[str] = None,
    duration_ms: int = 0,
    queue_wait_ms: Optional[int] = None,
) -> None:
    """Convenience function to log to database"""
    await db_audit_logger.log_action(
        user_id=user_id,
        request_id=request_id,
        agent=agent,
        action=action,
        model=model,
        data_class=data_class,
        patterns=patterns,
        approval_required=approval_required,
        approval_status=approval_status,
        tokens=tokens,
        result=result,
        error=error,
        duration_ms=duration_ms,
        queue_wait_ms=queue_wait_ms,
    )
