"""Authenticated chat, model routing, and approval workflow endpoints."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Any, Union
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from classifier import Classification, DataClass, classify_data
from db import get_db
from errors import error_response
from inference_queue import acquire_inference_queue
from logging_config import audit_logger
from middleware_auth import get_current_user
from models import ModelConfig
from providers import Provider
from providers.claude import ClaudeProvider
from providers.ollama import OllamaProvider
from schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ChatRequest,
    ChatResponse,
    DataClassification,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

ollama_provider = OllamaProvider()
claude_provider = ClaudeProvider()

APPROVAL_TTL = timedelta(minutes=5)
EXPIRED_TOMBSTONE_TTL = timedelta(minutes=5)
DEFAULT_MODEL = "qwen3.5:2b"


@dataclass(frozen=True)
class ResolvedModel:
    """Allowlisted model routing facts read from ModelConfig."""

    name: str
    provider: str


@dataclass
class PendingApproval:
    """Owner-bound request state retained for the five-minute approval window."""

    user_id: int
    request: ChatRequest
    model: ResolvedModel
    classification: Classification
    expires_at: datetime


@dataclass(frozen=True)
class ExpiredApproval:
    """Minimal owner-bound marker retained after sensitive prompt removal."""

    user_id: int


@dataclass(frozen=True)
class InferenceContext:
    """All facts shared by provider execution, auditing, and response mapping."""

    request_id: str
    request: ChatRequest
    user_id: int
    model: ResolvedModel
    classification: Classification
    approval_status: str
    request_start: float


_approval_cache: dict[str, PendingApproval] = {}
_expired_approvals: dict[str, ExpiredApproval] = {}
_approval_expiry_tasks: dict[str, asyncio.Task[None]] = {}

_BUILTIN_MODELS = {
    "qwen3.5:2b": ResolvedModel("qwen3.5:2b", "ollama"),
    "qwen3.5:4b": ResolvedModel("qwen3.5:4b", "ollama"),
    "qwen3.5:9b": ResolvedModel("qwen3.5:9b", "ollama"),
    "claude-code": ResolvedModel("claude-code", "claude"),
}


def _resolve_model(db: Session, requested_name: str | None) -> ResolvedModel | None:
    """Resolve an enabled allowlisted model and its provider from the database."""
    model_name = requested_name or DEFAULT_MODEL
    try:
        record = (
            db.query(ModelConfig)
            .filter(
                ModelConfig.model_name == model_name,
                ModelConfig.enabled.is_(True),
            )
            .first()
        )
    except AttributeError:
        # Supports direct unit invocation while production requests always use a Session.
        return _BUILTIN_MODELS.get(model_name)

    if record is None:
        return None
    return ResolvedModel(record.model_name, record.provider)


def _provider_for(model: ResolvedModel) -> Provider:
    """Select a provider only from the allowlisted provider value."""
    if model.provider == "ollama":
        return ollama_provider
    if model.provider == "claude":
        return claude_provider
    raise ValueError(f"Unsupported provider: {model.provider}")


async def _execute_inference(
    *,
    request_id: str,
    request: ChatRequest,
    user_id: int,
    model: ResolvedModel,
    classification: Classification,
    approval_status: str,
    request_start: float,
) -> ChatResponse | JSONResponse:
    """Run an approved request through the shared queue/provider/audit path."""
    context = InferenceContext(
        request_id=request_id,
        request=request,
        user_id=user_id,
        model=model,
        classification=classification,
        approval_status=approval_status,
        request_start=request_start,
    )
    queue_wait_ms = 0
    try:
        queue_context = await acquire_inference_queue(request_id)
        async with queue_context:
            queue_wait_ms = queue_context.queue_wait_ms
            result = await _provider_for(model).generate(
                prompt=request.prompt,
                model=model.name,
            )
    except Exception as error:
        return await _inference_error_response(context, error, queue_wait_ms)
    await _audit_inference_success(context, result, queue_wait_ms)
    return _chat_response(context, result)


async def _audit_inference_success(
    context: InferenceContext,
    result: dict[str, Any],
    queue_wait_ms: int,
) -> None:
    """Record successful provider execution with tokens and queue timing."""
    await audit_logger.log_action(
        user_id=context.user_id,
        request_id=context.request_id,
        agent=context.request.agent,
        action="chat_success",
        model=context.model.name,
        data_class=context.classification.level.value,
        patterns=context.classification.patterns,
        approval_required=context.approval_status == "user_approved",
        approval_status=context.approval_status,
        tokens=result.get("tokens_used", {"input": 0, "output": 0}),
        result="success",
        duration_ms=result.get("duration_ms", 0),
        queue_wait_ms=queue_wait_ms,
    )


def _chat_response(
    context: InferenceContext,
    result: dict[str, Any],
) -> ChatResponse:
    """Map a provider result into the stable chat response contract."""
    return ChatResponse(
        id=context.request_id,
        model_used=context.model.name,
        data_class=DataClassification(context.classification.level.value),
        data_class_patterns=context.classification.patterns,
        approval_required=False,
        approval_status=context.approval_status,
        response=result.get("response", ""),
        tokens_used=result.get("tokens_used", {"input": 0, "output": 0}),
        duration_ms=int((time.time() - context.request_start) * 1000),
    )


async def _inference_error_response(
    context: InferenceContext,
    error: Exception,
    queue_wait_ms: int,
) -> JSONResponse:
    """Audit one provider failure and map it into the error envelope."""
    if isinstance(error, TimeoutError):
        action, result = "chat_timeout", "timeout"
        status_code, code = status.HTTP_504_GATEWAY_TIMEOUT, "timeout"
        message, retry_after = "Model request timed out after retries. Please try again.", 5
    elif isinstance(error, ConnectionError):
        action, result = "chat_error", "error"
        status_code, code = status.HTTP_503_SERVICE_UNAVAILABLE, "ollama_unavailable"
        message, retry_after = "Ollama service is unavailable. Please try again later.", 5
    else:
        logger.exception("[%s] Inference failed", context.request_id, exc_info=error)
        action, result = "chat_error", "error"
        status_code, code = status.HTTP_500_INTERNAL_SERVER_ERROR, "inference_failed"
        message, retry_after = "An error occurred during inference. Please try again.", None
    await audit_logger.log_action(
        user_id=context.user_id,
        request_id=context.request_id,
        agent=context.request.agent,
        action=action,
        model=context.model.name,
        data_class=context.classification.level.value,
        patterns=context.classification.patterns,
        approval_status=context.approval_status,
        result=result,
        error=str(error),
        duration_ms=int((time.time() - context.request_start) * 1000),
        queue_wait_ms=queue_wait_ms,
    )
    return error_response(
        status_code,
        code,
        message,
        context.request_id,
        retry_after=retry_after,
    )


def _cache_pending(
    request_id: str,
    user_id: int,
    request: ChatRequest,
    model: ResolvedModel,
    classification: Classification,
) -> None:
    expires_at = datetime.now(timezone.utc) + APPROVAL_TTL
    _approval_cache[request_id] = PendingApproval(
        user_id=user_id,
        request=request,
        model=model,
        classification=classification,
        expires_at=expires_at,
    )
    task = asyncio.create_task(_expire_pending_after(request_id, expires_at))
    _approval_expiry_tasks[request_id] = task
    task.add_done_callback(
        lambda completed: _forget_expiry_task(request_id, completed)
    )


def _forget_expiry_task(
    request_id: str,
    completed: asyncio.Task[None],
) -> None:
    """Forget a completed expiry task without removing a newer task."""
    if _approval_expiry_tasks.get(request_id) is completed:
        _approval_expiry_tasks.pop(request_id, None)


def _cancel_expiry_task(request_id: str) -> None:
    """Cancel scheduled expiry after approval or denial consumes a request."""
    task = _approval_expiry_tasks.pop(request_id, None)
    if task is not None and task is not asyncio.current_task():
        task.cancel()


async def _expire_pending_after(request_id: str, expires_at: datetime) -> None:
    """Remove a cached prompt at its deadline and record the expiry event."""
    delay = max(0.0, (expires_at - datetime.now(timezone.utc)).total_seconds())
    try:
        await asyncio.sleep(delay)
        await _expire_pending(request_id, expires_at)
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Failed to expire pending approval %s", request_id)


async def _expire_pending(request_id: str, expected_expiry: datetime) -> None:
    """Purge one matching prompt, retain a tombstone, and audit expiration."""
    pending = _approval_cache.get(request_id)
    if pending is None or pending.expires_at != expected_expiry:
        return
    _approval_cache.pop(request_id, None)
    _cancel_expiry_task(request_id)
    _expired_approvals[request_id] = ExpiredApproval(user_id=pending.user_id)
    asyncio.get_running_loop().call_later(
        EXPIRED_TOMBSTONE_TTL.total_seconds(),
        _expired_approvals.pop,
        request_id,
        None,
    )
    await audit_logger.log_action(
        user_id=pending.user_id,
        request_id=request_id,
        agent=pending.request.agent,
        action="chat_expired",
        model=pending.model.name,
        data_class=pending.classification.level.value,
        patterns=pending.classification.patterns,
        approval_required=True,
        approval_status="expired",
        result="expired",
    )


async def _require_approval(
    *,
    request_id: str,
    request_start: float,
    request: ChatRequest,
    user_id: int,
    requested_model: ResolvedModel,
    pending_model: ResolvedModel,
    classification: Classification,
    blocked: bool,
) -> None:
    """Cache, audit, and return the appropriate approval-required response."""
    _cache_pending(request_id, user_id, request, pending_model, classification)
    is_red = classification.level is DataClass.RED
    await audit_logger.log_action(
        user_id=user_id,
        request_id=request_id,
        agent=request.agent,
        action="chat_blocked_red_data" if is_red else "chat_requires_approval",
        model=requested_model.name,
        data_class=classification.level.value,
        patterns=classification.patterns,
        approval_required=True,
        approval_status="pending",
        result="blocked_red_data" if is_red else "requires_approval",
        error="RED data cannot be sent to cloud" if is_red else None,
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN if is_red else status.HTTP_202_ACCEPTED,
        detail=_approval_detail(
            request_id,
            request_start,
            classification,
            blocked,
            is_red,
        ),
    )


def _approval_detail(
    request_id: str,
    request_start: float,
    classification: Classification,
    blocked: bool,
    is_red: bool,
) -> dict[str, Any]:
    """Build the RED or YELLOW approval response payload."""
    local_models = ["qwen3.5:2b", "qwen3.5:4b"]
    if is_red:
        local_models.append("qwen3.5:9b")
    message = (
        "Sensitive data detected. Local processing only. Approve?"
        if is_red
        else "This data appears private/sensitive. Approve sending to Claude Code?"
    )
    return {
        "id": request_id,
        "approval_required": True,
        "cloud_model_blocked": blocked,
        "data_class": classification.level.value,
        "data_class_patterns": classification.patterns,
        "message": message,
        "allowed_models": local_models,
        "duration_ms": int((time.time() - request_start) * 1000),
    }


async def _enforce_approval_policy(
    *,
    request_id: str,
    request_start: float,
    request: ChatRequest,
    user_id: int,
    model: ResolvedModel,
    classification: Classification,
) -> None:
    """Apply RED-local-only and YELLOW-cloud approval rules."""
    if classification.level is DataClass.RED:
        local_model = (
            model if model.provider == "ollama" else _BUILTIN_MODELS[DEFAULT_MODEL]
        )
        await _require_approval(
            request_id=request_id,
            request_start=request_start,
            request=request,
            user_id=user_id,
            requested_model=model,
            pending_model=local_model,
            classification=classification,
            blocked=True,
        )
    if classification.level is DataClass.YELLOW and model.provider == "claude":
        await _require_approval(
            request_id=request_id,
            request_start=request_start,
            request=request,
            user_id=user_id,
            requested_model=model,
            pending_model=model,
            classification=classification,
            blocked=False,
        )


@router.post("/", response_model=ChatResponse, status_code=200)
async def chat(
    request: ChatRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse | JSONResponse:
    """Classify, route, and execute a model request or request approval."""
    request_id = str(uuid.uuid4())
    request_start = time.time()
    model = _resolve_model(db, request.model_preference)
    if model is None:
        return error_response(
            status.HTTP_400_BAD_REQUEST,
            "invalid_model",
            "Requested model is not available.",
            request_id,
        )

    classification = classify_data(request.prompt)
    await _enforce_approval_policy(
        request_id=request_id,
        request_start=request_start,
        request=request,
        user_id=user_id,
        model=model,
        classification=classification,
    )
    return await _execute_inference(
        request_id=request_id,
        request=request,
        user_id=user_id,
        model=model,
        classification=classification,
        approval_status="auto_approved",
        request_start=request_start,
    )


async def _deny_approval(
    request_id: str,
    user_id: int,
    pending: PendingApproval,
) -> ApprovalResponse:
    """Audit a user rejection and return its stable response."""
    await audit_logger.log_action(
        user_id=user_id,
        request_id=request_id,
        agent=pending.request.agent,
        action="chat_denied",
        model=pending.model.name,
        data_class=pending.classification.level.value,
        patterns=pending.classification.patterns,
        approval_required=True,
        approval_status="user_rejected",
        result="user_denied",
    )
    return ApprovalResponse(
        request_id=request_id,
        status="denied",
        message="Request was denied.",
    )


@router.post(
    "/approve",
    response_model=Union[ChatResponse, ApprovalResponse],
    status_code=200,
)
async def approve_chat(
    request: ApprovalRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse | ApprovalResponse | JSONResponse:
    """Execute, reject, or expire an owner-bound pending request."""
    pending = _approval_cache.get(request.request_id)
    expired = _expired_approvals.get(request.request_id)
    if pending is None and expired is not None and expired.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Approval request expired",
        )
    if pending is None or pending.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found",
        )

    if datetime.now(timezone.utc) >= pending.expires_at:
        await _expire_pending(request.request_id, pending.expires_at)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Approval request expired",
        )

    _approval_cache.pop(request.request_id, None)
    _cancel_expiry_task(request.request_id)
    if not request.approved:
        return await _deny_approval(request.request_id, user_id, pending)

    return await _execute_inference(
        request_id=request.request_id,
        request=pending.request,
        user_id=user_id,
        model=pending.model,
        classification=pending.classification,
        approval_status="user_approved",
        request_start=time.time(),
    )
