"""Authenticated chat, model routing, and approval workflow endpoints."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
import time
from typing import Union
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


_approval_cache: dict[str, PendingApproval] = {}

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


def _provider_for(model: ResolvedModel):
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
    queue_wait_ms = 0
    try:
        queue_context = await acquire_inference_queue(request_id)
        async with queue_context:
            queue_wait_ms = queue_context.queue_wait_ms
            result = await _provider_for(model).generate(
                prompt=request.prompt,
                model=model.name,
            )

        tokens_used = result.get("tokens_used", {"input": 0, "output": 0})
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request_id,
            agent=request.agent,
            action="chat_success",
            model=model.name,
            data_class=classification.level.value,
            patterns=classification.patterns,
            approval_required=approval_status == "user_approved",
            approval_status=approval_status,
            tokens=tokens_used,
            result="success",
            duration_ms=result.get("duration_ms", 0),
            queue_wait_ms=queue_wait_ms,
        )
        return ChatResponse(
            id=request_id,
            model_used=model.name,
            data_class=DataClassification(classification.level.value),
            data_class_patterns=classification.patterns,
            approval_required=False,
            approval_status=approval_status,
            response=result.get("response", ""),
            tokens_used=tokens_used,
            duration_ms=int((time.time() - request_start) * 1000),
        )
    except TimeoutError as error:
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request_id,
            agent=request.agent,
            action="chat_timeout",
            model=model.name,
            data_class=classification.level.value,
            patterns=classification.patterns,
            approval_status=approval_status,
            result="timeout",
            error=str(error),
            duration_ms=int((time.time() - request_start) * 1000),
            queue_wait_ms=queue_wait_ms,
        )
        return error_response(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "timeout",
            "Model request timed out after retries. Please try again.",
            request_id,
            retry_after=5,
        )
    except ConnectionError as error:
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request_id,
            agent=request.agent,
            action="chat_error",
            model=model.name,
            data_class=classification.level.value,
            patterns=classification.patterns,
            approval_status=approval_status,
            result="error",
            error=str(error),
            duration_ms=int((time.time() - request_start) * 1000),
            queue_wait_ms=queue_wait_ms,
        )
        return error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ollama_unavailable",
            "Ollama service is unavailable. Please try again later.",
            request_id,
            retry_after=5,
        )
    except Exception as error:
        logger.exception("[%s] Inference failed", request_id)
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request_id,
            agent=request.agent,
            action="chat_error",
            model=model.name,
            data_class=classification.level.value,
            patterns=classification.patterns,
            approval_status=approval_status,
            result="error",
            error=str(error),
            duration_ms=int((time.time() - request_start) * 1000),
            queue_wait_ms=queue_wait_ms,
        )
        return error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "inference_failed",
            "An error occurred during inference. Please try again.",
            request_id,
        )


def _cache_pending(
    request_id: str,
    user_id: int,
    request: ChatRequest,
    model: ResolvedModel,
    classification: Classification,
) -> None:
    _approval_cache[request_id] = PendingApproval(
        user_id=user_id,
        request=request,
        model=model,
        classification=classification,
        expires_at=datetime.now(timezone.utc) + APPROVAL_TTL,
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

    if classification.level is DataClass.RED:
        local_model = model if model.provider == "ollama" else _BUILTIN_MODELS[DEFAULT_MODEL]
        _cache_pending(request_id, user_id, request, local_model, classification)
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request_id,
            agent=request.agent,
            action="chat_blocked_red_data",
            model=model.name,
            data_class="RED",
            patterns=classification.patterns,
            approval_required=True,
            approval_status="pending",
            result="blocked_red_data",
            error="RED data cannot be sent to cloud",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "id": request_id,
                "approval_required": True,
                "cloud_model_blocked": True,
                "data_class": "RED",
                "data_class_patterns": classification.patterns,
                "message": "Sensitive data detected. Local processing only. Approve?",
                "allowed_models": ["qwen3.5:2b", "qwen3.5:4b", "qwen3.5:9b"],
                "duration_ms": int((time.time() - request_start) * 1000),
            },
        )

    if classification.level is DataClass.YELLOW and model.provider == "claude":
        _cache_pending(request_id, user_id, request, model, classification)
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request_id,
            agent=request.agent,
            action="chat_requires_approval",
            model=model.name,
            data_class="YELLOW",
            patterns=classification.patterns,
            approval_required=True,
            approval_status="pending",
            result="requires_approval",
        )
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail={
                "id": request_id,
                "approval_required": True,
                "cloud_model_blocked": False,
                "data_class": "YELLOW",
                "data_class_patterns": classification.patterns,
                "message": "This data appears private/sensitive. Approve sending to Claude Code?",
                "allowed_models": ["qwen3.5:2b", "qwen3.5:4b"],
                "duration_ms": int((time.time() - request_start) * 1000),
            },
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
    if pending is None or pending.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found",
        )

    if datetime.now(timezone.utc) >= pending.expires_at:
        _approval_cache.pop(request.request_id, None)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Approval request expired",
        )

    _approval_cache.pop(request.request_id, None)
    if not request.approved:
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request.request_id,
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
            request_id=request.request_id,
            status="denied",
            message="Request was denied.",
        )

    return await _execute_inference(
        request_id=request.request_id,
        request=pending.request,
        user_id=user_id,
        model=pending.model,
        classification=pending.classification,
        approval_status="user_approved",
        request_start=time.time(),
    )
