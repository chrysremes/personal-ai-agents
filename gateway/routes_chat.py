"""
Chat and inference endpoints
/chat - Main inference endpoint
/chat/approve - Approval workflow endpoint
"""

import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from schemas import (
    ChatRequest,
    ChatResponse,
    ApprovalRequiredResponse,
    ApprovalRequest,
    ApprovalResponse,
    DataClassification,
)
from models import User, AuditLog
from db import get_db
from middleware_auth import get_current_user
from classifier import classify_data
from queue import acquire_inference_queue
from providers.ollama import OllamaProvider
from providers.claude import ClaudeProvider
from logging_config import audit_logger

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/chat", tags=["chat"])

# Initialize providers
ollama_provider = OllamaProvider()
claude_provider = ClaudeProvider()

# Approval cache: request_id -> {prompt, model_preference, user_id}
_approval_cache = {}


def get_iso_timestamp() -> str:
    """Get current UTC time in ISO 8601 format"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================================
# POST /chat Endpoint
# ============================================================================

@router.post("/", response_model=ChatResponse, status_code=200)
async def chat(
    request: ChatRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """
    Main chat/inference endpoint
    
    Request:
        - prompt: User prompt text
        - model_preference: Optional model name (e.g., "qwen3.5:2b")
        - agent: Optional agent name
        - streaming: Optional streaming flag (not implemented yet)
    
    Response:
        - id: Request ID
        - model_used: Model that was used
        - data_class: Classification (RED/YELLOW/GREEN)
        - approval_required: Whether approval was needed
        - response: Generated response text
        - tokens_used: Input/output token counts
        - duration_ms: Total request duration
    
    Error Responses:
        - 202: Approval required (YELLOW data)
        - 403: RED data blocked
        - 503: Ollama unavailable
    """
    request_id = str(uuid.uuid4())
    request_start = time.time()
    queue_wait_ms = 0
    
    try:
        logger.info(
            f"[{request_id}] Chat request from user_id={user_id}, "
            f"prompt_len={len(request.prompt)}, "
            f"model={request.model_preference or 'auto'}"
        )
        
        # Step 1: Classify data
        classification = classify_data(request.prompt)
        data_class_str = classification.level.value
        patterns = classification.patterns
        
        logger.debug(
            f"[{request_id}] Data classified as {data_class_str}, "
            f"patterns={patterns}"
        )
        
        # Step 2: Check data classification rules
        # RED data: Local only, requires approval
        if classification.level.name == "RED":
            logger.warning(
                f"[{request_id}] RED data detected, blocking cloud models. "
                f"patterns={patterns}"
            )
            
            await audit_logger.log_action(
                user_id=user_id,
                request_id=request_id,
                agent=request.agent,
                action="chat_blocked_red_data",
                data_class=data_class_str,
                patterns=patterns,
                approval_required=True,
                result="blocked_red_data",
                error="RED data cannot be sent to cloud",
            )
            
            # Cache this request for approval
            _approval_cache[request_id] = {
                "user_id": user_id,
                "prompt": request.prompt,
                "model_preference": request.model_preference,
                "agent": request.agent,
            }
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "id": request_id,
                    "approval_required": True,
                    "cloud_model_blocked": True,
                    "data_class": "RED",
                    "data_class_patterns": patterns,
                    "message": "Sensitive financial/tax data detected and cannot be sent to cloud models. Local processing only. Approve?",
                    "allowed_models": ["qwen3.5:2b", "qwen3.5:4b", "qwen3.5:9b"],
                    "duration_ms": int((time.time() - request_start) * 1000),
                },
            )
        
        # YELLOW data: Requires approval if cloud model is requested
        if classification.level.name == "YELLOW" and request.model_preference == "claude-code":
            logger.warning(
                f"[{request_id}] YELLOW data + cloud model requested, "
                f"requiring approval. patterns={patterns}"
            )
            
            await audit_logger.log_action(
                user_id=user_id,
                request_id=request_id,
                agent=request.agent,
                action="chat_requires_approval",
                data_class=data_class_str,
                patterns=patterns,
                approval_required=True,
                result="requires_approval",
            )
            
            # Cache this request for approval
            _approval_cache[request_id] = {
                "user_id": user_id,
                "prompt": request.prompt,
                "model_preference": request.model_preference,
                "agent": request.agent,
            }
            
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail={
                    "id": request_id,
                    "approval_required": True,
                    "cloud_model_blocked": False,
                    "data_class": "YELLOW",
                    "data_class_patterns": patterns,
                    "message": "This data appears private/sensitive. Approve sending to Claude Code?",
                    "allowed_models": ["qwen3.5:2b", "qwen3.5:4b"],
                    "duration_ms": int((time.time() - request_start) * 1000),
                },
            )
        
        # Step 3: Select model
        model_to_use = request.model_preference or "qwen3.5:2b"
        provider = claude_provider if "claude" in model_to_use else ollama_provider
        
        logger.debug(f"[{request_id}] Using model: {model_to_use}")
        
        # Step 4: Acquire inference queue
        try:
            queue_context = await acquire_inference_queue(request_id)
            
            async with queue_context:
                queue_wait_ms = queue_context.queue_wait_ms
                
                # Step 5: Call provider
                logger.debug(f"[{request_id}] Calling {provider.__class__.__name__}")
                result = await provider.generate(
                    prompt=request.prompt,
                    model=model_to_use,
                )
                
                generated_text = result.get("response", "")
                tokens_used = result.get("tokens_used", {"input": 0, "output": 0})
                duration_ms = result.get("duration_ms", 0)
                
                logger.info(
                    f"[{request_id}] Generation successful. "
                    f"output_len={len(generated_text)}, "
                    f"tokens={tokens_used}, "
                    f"duration={duration_ms}ms"
                )
                
                # Log to audit trail
                await audit_logger.log_action(
                    user_id=user_id,
                    request_id=request_id,
                    agent=request.agent,
                    action="chat_success",
                    model=model_to_use,
                    data_class=data_class_str,
                    patterns=patterns,
                    approval_required=False,
                    approval_status="auto_approved",
                    tokens=tokens_used,
                    result="success",
                    duration_ms=duration_ms,
                    queue_wait_ms=queue_wait_ms,
                )
                
                total_duration = int((time.time() - request_start) * 1000)
                
                return ChatResponse(
                    id=request_id,
                    model_used=model_to_use,
                    data_class=DataClassification.GREEN if not patterns else (
                        DataClassification.YELLOW if classification.level.name == "YELLOW"
                        else DataClassification.RED
                    ),
                    data_class_patterns=patterns,
                    approval_required=False,
                    approval_status="auto_approved",
                    response=generated_text,
                    tokens_used=tokens_used,
                    duration_ms=total_duration,
                )
        
        except TimeoutError as e:
            logger.error(f"[{request_id}] Request timeout: {e}")
            await audit_logger.log_action(
                user_id=user_id,
                request_id=request_id,
                agent=request.agent,
                action="chat_timeout",
                model=model_to_use,
                data_class=data_class_str,
                patterns=patterns,
                result="timeout",
                error=str(e),
                duration_ms=int((time.time() - request_start) * 1000),
                queue_wait_ms=queue_wait_ms,
            )
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Model request timed out. Please try again.",
            )
        
        except ConnectionError as e:
            logger.error(f"[{request_id}] Connection error: {e}")
            await audit_logger.log_action(
                user_id=user_id,
                request_id=request_id,
                agent=request.agent,
                action="chat_error",
                model=model_to_use,
                data_class=data_class_str,
                patterns=patterns,
                result="error",
                error=str(e),
                duration_ms=int((time.time() - request_start) * 1000),
                queue_wait_ms=queue_wait_ms,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Ollama service is unavailable. Please try again later.",
            )
        
        except Exception as e:
            logger.error(f"[{request_id}] Unexpected error: {e}")
            await audit_logger.log_action(
                user_id=user_id,
                request_id=request_id,
                agent=request.agent,
                action="chat_error",
                model=model_to_use,
                data_class=data_class_str,
                patterns=patterns,
                result="error",
                error=str(e),
                duration_ms=int((time.time() - request_start) * 1000),
                queue_wait_ms=queue_wait_ms,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred during inference. Please try again.",
            )
    
    except HTTPException:
        # Re-raise HTTP exceptions (already logged)
        raise
    except Exception as e:
        logger.error(f"[{request_id}] Unhandled exception: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred.",
        )


# ============================================================================
# POST /chat/approve Endpoint
# ============================================================================

@router.post("/approve", response_model=ApprovalResponse, status_code=200)
async def approve_chat(
    request: ApprovalRequest,
    user_id: int = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApprovalResponse:
    """
    Approve a pending chat request
    
    Request:
        - request_id: ID of request to approve/deny
        - approved: True to approve, False to deny
    
    Response:
        - request_id: Request ID
        - status: "approved", "denied", or "expired"
        - message: Status message
    
    If approved, re-submits the original request and returns response.
    If denied, cancels the request.
    """
    logger.info(
        f"Approval request for {request.request_id}: "
        f"approved={request.approved}, "
        f"user_id={user_id}"
    )
    
    # Check if request is in approval cache
    if request.request_id not in _approval_cache:
        logger.warning(f"Approval request not found: {request.request_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval request not found or expired",
        )
    
    cached_request = _approval_cache.pop(request.request_id)
    
    if request.approved:
        logger.info(f"Request approved: {request.request_id}")
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request.request_id,
            action="chat_approved",
            result="success",
        )
        return ApprovalResponse(
            request_id=request.request_id,
            status="approved",
            message="Request approved. Please resubmit to process.",
        )
    else:
        logger.info(f"Request denied: {request.request_id}")
        await audit_logger.log_action(
            user_id=user_id,
            request_id=request.request_id,
            action="chat_denied",
            result="user_denied",
        )
        return ApprovalResponse(
            request_id=request.request_id,
            status="denied",
            message="Request was denied.",
        )
