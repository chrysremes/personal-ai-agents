"""
Pydantic schemas for API requests/responses
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from enum import Enum


# ============================================================================
# Authentication Schemas
# ============================================================================

class LoginRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=32,
        pattern=r"^[A-Za-z0-9]+$",
    )
    password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(TokenResponse):
    refresh_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutResponse(BaseModel):
    message: str


class SetupUserRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=32,
        pattern=r"^[A-Za-z0-9]+$",
    )
    password: str = Field(..., min_length=8)


class SetupUserResponse(BaseModel):
    user_id: int
    username: str
    message: str


# ============================================================================
# Chat / Inference Schemas
# ============================================================================

class DataClassification(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


class ChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prompt: str = Field(..., min_length=1)
    model_preference: Optional[str] = None
    agent: Optional[str] = None
    streaming: bool = False


class TokenUsage(BaseModel):
    input: int
    output: int


class ChatResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    model_used: str
    data_class: DataClassification
    data_class_patterns: List[str]
    approval_required: bool
    approval_status: str
    response: str
    tokens_used: Optional[TokenUsage] = None
    duration_ms: int


class ApprovalRequiredResponse(BaseModel):
    id: str
    approval_required: bool
    cloud_model_blocked: bool
    data_class: DataClassification
    data_class_patterns: List[str]
    message: str
    allowed_models: List[str]
    duration_ms: int


class ApprovalRequest(BaseModel):
    request_id: str
    approved: bool


class ApprovalResponse(BaseModel):
    request_id: str
    status: str  # "approved", "denied", "expired"
    message: str


# ============================================================================
# Audit Log Schemas
# ============================================================================

class AuditLogFilter(BaseModel):
    user_id: Optional[int] = None
    start_time: Optional[str] = None  # ISO 8601
    end_time: Optional[str] = None    # ISO 8601
    agent: Optional[str] = None
    result: Optional[str] = None
    limit: int = 100


class AuditLogEntry(BaseModel):
    id: int
    event_id: str
    timestamp: str
    user_id: Optional[int]
    request_id: str
    agent: Optional[str]
    action: str
    model: Optional[str]
    data_class: Optional[str]
    data_class_patterns: Optional[List[str]]
    approval_required: bool
    approval_status: Optional[str]
    tokens_used: Optional[Dict[str, int]]
    tool_arguments: Optional[Dict[str, Any]]
    tool_result: Optional[Any]
    result: str
    error_message: Optional[str]
    queue_wait_ms: Optional[int]
    duration_ms: Optional[int]


class AuditLogsResponse(BaseModel):
    logs: List[AuditLogEntry]
    total: int


# ============================================================================
# Tool / MCP Schemas
# ============================================================================

class ToolArgument(BaseModel):
    name: str
    type: str
    description: str
    required: bool = False


class ToolDefinition(BaseModel):
    name: str
    description: str
    arguments: List[ToolArgument]


class ToolCallRequest(BaseModel):
    arguments: Dict[str, Any]


class ToolCallResponse(BaseModel):
    id: str
    tool: str
    status: str  # "success", "error"
    result: Any
    duration_ms: int


# ============================================================================
# Error Response Schema
# ============================================================================

class ErrorDetail(BaseModel):
    code: str
    message: str
    retry_after: Optional[int] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
