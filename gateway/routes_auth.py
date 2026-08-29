"""
Authentication endpoints for Agent Gateway
/auth/login, /auth/refresh, /auth/logout, /admin/setup/user
"""

import logging
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from schemas import (
    LoginRequest,
    LoginResponse,
    RefreshRequest,
    TokenResponse,
    LogoutResponse,
    SetupUserRequest,
    SetupUserResponse,
)
from models import User, RefreshToken
from db import get_db
from auth import password_manager, token_manager
from logging_config import audit_logger

logger = logging.getLogger(__name__)


# Create router
router = APIRouter(prefix="/auth", tags=["authentication"])


def get_iso_timestamp() -> str:
    """Get current UTC time in ISO 8601 format"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================================
# Login Endpoint
# ============================================================================

@router.post("/login", response_model=LoginResponse, status_code=200)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """
    User login endpoint
    
    Request:
        - username: username (3-32 alphanumeric)
        - password: password (min 8 chars)
    
    Response:
        - access_token: JWT token (15 min TTL)
        - refresh_token: Refresh token (7 day TTL)
        - token_type: "bearer"
        - expires_in: 900 (seconds)
    
    Errors:
        - 401: Invalid username or password
        - 403: User account is inactive
    """
    request_id = str(uuid.uuid4())
    
    # Look up user by username
    user = db.query(User).filter(User.username == request.username).first()
    
    if not user:
        logger.warning(f"[{request_id}] Login failed: user not found (username={request.username})")
        await audit_logger.log_action(
            request_id=request_id,
            action="login",
            result="error",
            error=f"User not found: {request.username}",
            duration_ms=0,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    # Check if user is active
    if not user.is_active:
        logger.warning(f"[{request_id}] Login failed: user inactive (user_id={user.id})")
        await audit_logger.log_action(
            user_id=user.id,
            request_id=request_id,
            action="login",
            result="error",
            error="User account is inactive",
            duration_ms=0,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    
    # Verify password
    if not password_manager.verify_password(request.password, user.password_hash):
        logger.warning(f"[{request_id}] Login failed: invalid password (user_id={user.id})")
        await audit_logger.log_action(
            user_id=user.id,
            request_id=request_id,
            action="login",
            result="error",
            error="Invalid password",
            duration_ms=0,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    
    # Generate JWT token
    access_token = token_manager.create_access_token(user.id)
    
    # Generate refresh token and store in DB
    refresh_token_str = token_manager.create_refresh_token()
    expires_at = token_manager.get_refresh_token_expiry()
    
    refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        issued_at=get_iso_timestamp(),
        expires_at=expires_at.isoformat().replace("+00:00", "Z"),
        revoked_at=None,
    )
    db.add(refresh_token)
    
    # Update last login
    user.last_login_at = get_iso_timestamp()
    db.commit()
    
    logger.info(f"[{request_id}] Login successful (user_id={user.id})")
    await audit_logger.log_action(
        user_id=user.id,
        request_id=request_id,
        action="login",
        result="success",
        duration_ms=0,
    )
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        token_type="bearer",
        expires_in=900,  # 15 minutes in seconds
    )


# ============================================================================
# Refresh Token Endpoint
# ============================================================================

@router.post("/refresh", response_model=TokenResponse, status_code=200)
async def refresh(
    request: RefreshRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Refresh access token using refresh token
    
    Request:
        - refresh_token: Refresh token from login
    
    Response:
        - access_token: New JWT token
        - token_type: "bearer"
        - expires_in: 900 (seconds)
    
    Errors:
        - 401: Refresh token expired, revoked, or invalid
    """
    request_id = str(uuid.uuid4())
    
    # Look up refresh token
    refresh_token = (
        db.query(RefreshToken)
        .filter(RefreshToken.token == request.refresh_token)
        .first()
    )
    
    if not refresh_token:
        logger.warning(f"[{request_id}] Token refresh failed: refresh token not found")
        await audit_logger.log_action(
            request_id=request_id,
            action="refresh_token",
            result="error",
            error="Refresh token not found",
            duration_ms=0,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or invalid",
        )
    
    # Check if token is revoked
    if refresh_token.revoked_at:
        logger.warning(f"[{request_id}] Token refresh failed: token revoked (user_id={refresh_token.user_id})")
        await audit_logger.log_action(
            user_id=refresh_token.user_id,
            request_id=request_id,
            action="refresh_token",
            result="error",
            error="Refresh token revoked",
            duration_ms=0,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or invalid",
        )
    
    # Check if token is expired
    expires_at = datetime.fromisoformat(refresh_token.expires_at.replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > expires_at:
        logger.warning(f"[{request_id}] Token refresh failed: token expired (user_id={refresh_token.user_id})")
        await audit_logger.log_action(
            user_id=refresh_token.user_id,
            request_id=request_id,
            action="refresh_token",
            result="error",
            error="Refresh token expired",
            duration_ms=0,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired or invalid",
        )
    
    # Generate new access token
    access_token = token_manager.create_access_token(refresh_token.user_id)
    
    logger.info(f"[{request_id}] Token refresh successful (user_id={refresh_token.user_id})")
    await audit_logger.log_action(
        user_id=refresh_token.user_id,
        request_id=request_id,
        action="refresh_token",
        result="success",
        duration_ms=0,
    )
    
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=900,
    )


# ============================================================================
# Logout Endpoint
# ============================================================================

@router.post("/logout", response_model=LogoutResponse, status_code=200)
async def logout(
    user_id: int = None,  # Will be injected by middleware
    refresh_token: str = None,  # Will come from request context (Phase 4)
    db: Session = Depends(get_db),
) -> LogoutResponse:
    """
    Logout user and revoke refresh token
    
    Note: In Phase 4, this will extract refresh_token from request context
    For Phase 3, this is a placeholder
    
    Response:
        - message: Logout confirmation message
    """
    request_id = str(uuid.uuid4())
    
    # TODO: Phase 4 - Extract refresh_token from request context
    logger.info(f"[{request_id}] Logout endpoint called")
    
    return LogoutResponse(message="Logged out successfully")


# ============================================================================
# Admin Setup User Endpoint (One-time)
# ============================================================================

_setup_mode_enabled = True  # Will be disabled after first user


@router.post("/admin/setup/user", response_model=SetupUserResponse, status_code=200)
async def setup_user(
    request: SetupUserRequest,
    db: Session = Depends(get_db),
) -> SetupUserResponse:
    """
    One-time setup endpoint to create first user
    
    Only active if users table is empty.
    After first user is created, this endpoint returns 403.
    
    Request:
        - username: Username (3-32 alphanumeric)
        - password: Password (min 8 chars)
    
    Response:
        - user_id: Created user ID
        - username: Created username
        - message: Setup confirmation message
    
    Errors:
        - 403: Setup mode disabled (users already exist)
    """
    global _setup_mode_enabled
    request_id = str(uuid.uuid4())
    
    # Check if setup mode is still active
    user_count = db.query(User).count()
    
    if user_count > 0:
        if _setup_mode_enabled:
            _setup_mode_enabled = False
        logger.warning(f"[{request_id}] Setup endpoint called but users already exist")
        await audit_logger.log_action(
            request_id=request_id,
            action="setup_user",
            result="error",
            error="Setup endpoint disabled - users already exist",
            duration_ms=0,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup endpoint is disabled (users already exist)",
        )
    
    # Create first user
    try:
        password_hash = password_manager.hash_password(request.password)
    except ValueError as e:
        logger.error(f"[{request_id}] Password validation failed: {e}")
        await audit_logger.log_action(
            request_id=request_id,
            action="setup_user",
            result="error",
            error=f"Password validation failed: {e}",
            duration_ms=0,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    user = User(
        username=request.username,
        password_hash=password_hash,
        created_at=get_iso_timestamp(),
        is_active=True,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Disable setup mode after first user
    _setup_mode_enabled = False
    
    logger.info(f"[{request_id}] First user created: {request.username} (user_id={user.id})")
    await audit_logger.log_action(
        user_id=user.id,
        request_id=request_id,
        action="setup_user",
        result="success",
        duration_ms=0,
    )
    
    return SetupUserResponse(
        user_id=user.id,
        username=user.username,
        message="First user created. Setup endpoint is now disabled.",
    )
