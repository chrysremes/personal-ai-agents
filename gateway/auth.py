"""
Authentication utilities for Agent Gateway
Argon2 password hashing + JWT token management
"""

import logging
from datetime import datetime, timedelta, timezone
import secrets
import string
from typing import Dict, Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from pydantic import ValidationError

from config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Password Hashing
# ============================================================================

class PasswordManager:
    """Manage password hashing and verification using Argon2"""
    
    def __init__(self):
        self.hasher = PasswordHasher()
    
    def hash_password(self, password: str) -> str:
        """
        Hash a password using Argon2
        
        Args:
            password: Plain text password
            
        Returns:
            Argon2 hash string
            
        Raises:
            ValueError: If password fails validation
        """
        # Validate password
        self._validate_password(password)
        
        # Hash password
        try:
            hash_result = self.hasher.hash(password)
            logger.debug("Password hashed successfully")
            return hash_result
        except Exception as e:
            logger.error(f"Password hashing failed: {e}")
            raise ValueError(f"Password hashing failed: {e}")
    
    def verify_password(self, password: str, hash_string: str) -> bool:
        """
        Verify a password against an Argon2 hash
        
        Args:
            password: Plain text password to verify
            hash_string: Argon2 hash to check against
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            self.hasher.verify(hash_string, password)
            return True
        except VerifyMismatchError:
            logger.debug("Password verification failed: hash mismatch")
            return False
        except InvalidHash as e:
            logger.error(f"Invalid hash format: {e}")
            return False
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    def _validate_password(self, password: str) -> None:
        """
        Validate password meets security requirements
        
        Args:
            password: Password to validate
            
        Raises:
            ValueError: If password doesn't meet requirements
        """
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not any(character.isupper() for character in password):
            raise ValueError("Password must contain an uppercase letter")
        if not any(character.islower() for character in password):
            raise ValueError("Password must contain a lowercase letter")
        if not any(character.isdigit() for character in password):
            raise ValueError("Password must contain a digit")
        if not any(not character.isalnum() for character in password):
            raise ValueError("Password must contain a symbol")

        logger.debug("Password validation passed")


# ============================================================================
# JWT Token Management
# ============================================================================

class TokenManager:
    """Manage JWT token generation and verification"""
    
    def __init__(self):
        self.secret = settings.gateway_jwt_secret
        self.access_token_ttl_minutes = settings.gateway_jwt_expiry_minutes
        self.algorithm = "HS256"
        
        if not self.secret or len(self.secret) < 32:
            logger.warning("JWT secret is too short. Minimum 32 characters recommended.")
    
    def create_access_token(self, user_id: int, expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT access token
        
        Args:
            user_id: User ID to encode in token
            expires_delta: Custom expiration time (default: from config)
            
        Returns:
            Signed JWT token string
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=self.access_token_ttl_minutes)
        
        # Calculate expiration time (UTC)
        now = datetime.now(timezone.utc)
        expire = now + expires_delta
        
        # Create claims
        claims = {
            "user_id": user_id,
            "iat": now,
            "exp": expire,
        }
        
        try:
            token = jwt.encode(claims, self.secret, algorithm=self.algorithm)
            logger.debug(f"Access token created for user_id={user_id}, expires in {expires_delta.total_seconds()} seconds")
            return token
        except Exception as e:
            logger.error(f"Failed to create access token: {e}")
            raise ValueError(f"Token creation failed: {e}")
    
    def verify_access_token(self, token: str) -> Dict:
        """
        Verify and decode a JWT access token
        
        Args:
            token: JWT token string to verify
            
        Returns:
            Decoded claims dictionary
            
        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            claims = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            logger.debug(f"Token verified for user_id={claims.get('user_id')}")
            return claims
        except jwt.ExpiredSignatureError:
            logger.debug("Token verification failed: expired")
            raise ValueError("Token expired")
        except jwt.InvalidSignatureError:
            logger.warning("Token verification failed: invalid signature")
            raise ValueError("Invalid token signature")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token verification failed: {e}")
            raise ValueError(f"Invalid token: {e}")
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            raise ValueError(f"Token verification failed: {e}")
    
    def create_refresh_token(self) -> str:
        """
        Create a cryptographically secure refresh token
        
        Returns:
            32-byte random token (hex-encoded, 64 characters)
        """
        token_bytes = secrets.token_hex(32)
        logger.debug("Refresh token created")
        return token_bytes
    
    def get_refresh_token_expiry(self) -> datetime:
        """
        Get the expiration datetime for a refresh token
        
        Returns:
            UTC datetime when token should expire
        """
        return datetime.now(timezone.utc) + timedelta(
            days=settings.gateway_refresh_token_expiry_days
        )


# ============================================================================
# Global Instances
# ============================================================================

password_manager = PasswordManager()
token_manager = TokenManager()


# ============================================================================
# Helper Functions
# ============================================================================

def get_password_manager() -> PasswordManager:
    """Get the global password manager instance"""
    return password_manager


def get_token_manager() -> TokenManager:
    """Get the global token manager instance"""
    return token_manager
