"""Authenticated REST facade for the in-process MCP tool registry."""

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from logging_config import audit_logger
from mcp import registry
from middleware_auth import get_current_user
from schemas import ToolCallRequest, ToolCallResponse

router = APIRouter(prefix="/tools", tags=["tools"])


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
    tool = registry.get(tool_name)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")

    try:
        result = await registry.call(tool_name, request.arguments)
    except ValueError as error:
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request_id,
            action="request_tool",
            agent=tool_name,
            result="error",
            error=str(error),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    except Exception as error:
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request_id,
            action="request_tool",
            agent=tool_name,
            result="error",
            error=str(error),
            duration_ms=int((time.monotonic() - started) * 1000),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tool execution failed",
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    await audit_logger.log_action(
        user_id=user_id,
        request_id=request_id,
        action="request_tool",
        agent=tool_name,
        result="success",
        duration_ms=duration_ms,
    )
    return ToolCallResponse(
        id=request_id,
        tool=tool_name,
        status="success",
        result=result,
        duration_ms=duration_ms,
    )
