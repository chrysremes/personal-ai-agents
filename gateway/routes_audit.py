"""
Audit log query endpoints
GET /audit/logs - Query audit logs (user can only see their own)
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from schemas import AuditLogFilter, AuditLogEntry, AuditLogsResponse
from middleware_auth import get_current_user
from audit import db_audit_logger

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs", response_model=AuditLogsResponse, status_code=200)
async def get_audit_logs(
    user_id: int = Depends(get_current_user),
    start_time: Optional[str] = Query(None, description="ISO 8601 start time"),
    end_time: Optional[str] = Query(None, description="ISO 8601 end time"),
    agent: Optional[str] = Query(None, description="Filter by agent name"),
    result: Optional[str] = Query(None, description="Filter by result"),
    limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
) -> AuditLogsResponse:
    """Query a limited page and exact total for the current user's events."""
    logger.info(
        f"Audit log query from user_id={user_id}, "
        f"start={start_time}, end={end_time}, agent={agent}, result={result}"
    )
    
    try:
        # Query audit logs from database
        logs, total = await db_audit_logger.query_logs(
            user_id=user_id,  # Only their own logs
            start_time=start_time,
            end_time=end_time,
            agent=agent,
            result=result,
            limit=limit,
        )
        
        # Convert to response schema
        log_entries = [
            AuditLogEntry(**log) for log in logs
        ]
        
        logger.info(f"Audit query returned {len(log_entries)} logs for user_id={user_id}")
        
        return AuditLogsResponse(
            logs=log_entries,
            total=total,
        )
    
    except Exception as e:
        logger.error(f"Error querying audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error querying audit logs",
        )
