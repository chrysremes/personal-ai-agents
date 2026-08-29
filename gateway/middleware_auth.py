"""
JWT middleware for token verification on protected endpoints
"""

import logging
from typing import Optional

from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthCredentials

from auth import token_manager

logger = logging.getLogger(__name__)

# Security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthCredentials] = Depends(security),
) -> int:
    """
    Dependency to extract and verify JWT token
    
    Returns:
        user_id: Authenticated user ID
        
    Raises:
        HTTPException 401: If token is missing or invalid
    """
    
    if not credentials:
        logger.debug("Request missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    try:
        claims = token_manager.verify_access_token(token)
        user_id = claims.get("user_id")
        
        if not user_id:
            logger.warning("Token claims missing user_id")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token claims",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.debug(f"Token verified for user_id={user_id}")
        return user_id
        
    except ValueError as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )
