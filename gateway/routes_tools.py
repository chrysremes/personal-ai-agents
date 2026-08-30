"""Authenticated REST facade for the in-process MCP tool registry."""

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from logging_config import audit_logger
from mcp import registry
from middleware_auth import get_current_user
from schemas import ToolCallRequest, ToolCallResponse

router = APIRouter(prefix="/tools", tags=["tools"])


async def _audit_tool_call(
    *,
    user_id: int,
    request_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: object,
    status_value: str,
    started: float,
    error: str | None = None,
) -> None:
    """Record a redacted tool request and its result through the audit seam."""
    await audit_logger.log_action(
        user_id=user_id,
        request_id=request_id,
        action="request_tool",
        agent=tool_name,
        tool_arguments=arguments,
        tool_result=result,
        result=status_value,
        error=error,
        duration_ms=int((time.monotonic() - started) * 1000),
    )


async def _ensure_tool_exists(
    tool_name: str,
    request: ToolCallRequest,
    user_id: int,
    request_id: str,
    started: float,
) -> None:
    """Audit and reject an unknown tool name."""
    if registry.get(tool_name) is not None:
        return
    await _audit_tool_call(
        user_id=user_id,
        request_id=request_id,
        tool_name=tool_name,
        arguments=request.arguments,
        result={"error": "Tool not found"},
        status_value="error",
        error="Tool not found",
        started=started,
    )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")


async def _invoke_tool(
    tool_name: str,
    request: ToolCallRequest,
    user_id: int,
    request_id: str,
    started: float,
) -> Any:
    """Invoke one tool and translate audited execution failures."""
    try:
        return await registry.call(tool_name, request.arguments)
    except ValueError as error:
        status_code, detail = status.HTTP_400_BAD_REQUEST, str(error)
        error_message = str(error)
    except Exception as error:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = "Tool execution failed"
        error_message = str(error)
    await _audit_tool_call(
        user_id=user_id,
        request_id=request_id,
        tool_name=tool_name,
        arguments=request.arguments,
        result={"error": detail},
        status_value="error",
        error=error_message,
        started=started,
    )
    raise HTTPException(status_code=status_code, detail=detail)


@router.get("")
async def list_tools(user_id: int = Depends(get_current_user)) -> dict:
    """List registered tool definitions and argument schemas."""
    return {"tools": registry.list_definitions()}


@router.post("/{tool_name}", response_model=ToolCallResponse)
async def call_tool(
    tool_name: str,
    request: ToolCallRequest,
    user_id: int = Depends(get_current_user),
) -> ToolCallResponse:
    """Validate, invoke, and audit a registered tool."""
    request_id = str(uuid.uuid4())
    started = time.monotonic()
    await _ensure_tool_exists(tool_name, request, user_id, request_id, started)
    result = await _invoke_tool(tool_name, request, user_id, request_id, started)
    duration_ms = int((time.monotonic() - started) * 1000)
    await _audit_tool_call(
        user_id=user_id,
        request_id=request_id,
        tool_name=tool_name,
        arguments=request.arguments,
        result=result,
        status_value="success",
        started=started,
    )
    return ToolCallResponse(
        id=request_id,
        tool=tool_name,
        status="success",
        result=result,
        duration_ms=duration_ms,
    )
