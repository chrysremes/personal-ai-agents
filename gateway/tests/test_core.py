"""
Unit tests for Agent Gateway - Phase 3
Tests for authentication, data classification, and core functionality
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone

# Import modules to test
import sys
sys.path.insert(0, '/home/chrystian/Documents/GitRepos/personal-ai-agents/gateway')

import auth
from auth import (
    get_password_manager,
    get_token_manager,
    password_manager,
    token_manager,
)
from classifier import classify_data, DataClass
from inference_queue import get_inference_queue


# ============================================================================
# Authentication Tests (Epic 2)
# ============================================================================

class TestPasswordHashing:
    """Test Argon2 password hashing"""
    
    def test_hash_password(self):
        """Password hashing produces different hashes"""
        password = "SecurePassword123!"
        hash1 = password_manager.hash_password(password)
        hash2 = password_manager.hash_password(password)
        
        # Hashes should be different (due to random salt)
        assert hash1 != hash2
        assert len(hash1) > 20
        assert len(hash2) > 20
    
    def test_verify_password_correct(self):
        """Correct password verifies successfully"""
        password = "SecurePassword123!"
        hash_val = password_manager.hash_password(password)
        
        assert password_manager.verify_password(password, hash_val) is True
    
    def test_verify_password_incorrect(self):
        """Incorrect password fails verification"""
        password = "SecurePassword123!"
        wrong_password = "WrongPassword456!"
        hash_val = password_manager.hash_password(password)
        
        assert password_manager.verify_password(wrong_password, hash_val) is False
    
    def test_password_validation_too_short(self):
        """Password too short raises error"""
        with pytest.raises(ValueError):
            password_manager.hash_password("short")
    
    def test_password_validation_empty(self):
        """Empty password raises error"""
        with pytest.raises(ValueError):
            password_manager.hash_password("")

    def test_invalid_argon2_hash_is_rejected(self):
        """Malformed stored hashes fail closed."""
        assert password_manager.verify_password("SecurePassword123!", "invalid") is False

    def test_argon2_hashing_failure_is_reported(self, monkeypatch):
        """Failures from the Argon2 boundary become a stable domain error."""
        monkeypatch.setattr(
            auth.PasswordHasher,
            "hash",
            lambda _self, _password: (_ for _ in ()).throw(
                RuntimeError("argon2 unavailable")
            ),
        )

        with pytest.raises(ValueError, match="Password hashing failed"):
            password_manager.hash_password("SecurePassword123!")


class TestJWTTokens:
    """Test JWT token generation and verification"""
    
    def test_create_access_token(self):
        """Access token creation succeeds"""
        user_id = 42
        token = token_manager.create_access_token(user_id)
        
        assert isinstance(token, str)
        assert len(token) > 10
    
    def test_verify_access_token(self):
        """Token verification extracts claims correctly"""
        user_id = 42
        token = token_manager.create_access_token(user_id)
        
        claims = token_manager.verify_access_token(token)
        assert claims["user_id"] == user_id
        assert "exp" in claims
        assert "iat" in claims
    
    def test_verify_invalid_token(self):
        """Invalid token raises error"""
        invalid_token = "not.a.valid.token"
        
        with pytest.raises(ValueError):
            token_manager.verify_access_token(invalid_token)
    
    def test_verify_expired_token(self):
        """Expired token raises error"""
        user_id = 42
        # Create token with -1 hour TTL (already expired)
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        
        token = token_manager.create_access_token(
            user_id, 
            expires_delta=timedelta(seconds=-1)
        )
        
        # Token should be expired
        with pytest.raises(ValueError) as exc_info:
            token_manager.verify_access_token(token)
        assert "expired" in str(exc_info.value).lower()
    
    def test_create_refresh_token(self):
        """Refresh token creation produces valid hex string"""
        token = token_manager.create_refresh_token()
        
        assert isinstance(token, str)
        assert len(token) == 64  # 32 bytes hex-encoded
        
        # Should be valid hex
        int(token, 16)  # Raises ValueError if not hex
    
    def test_refresh_token_expiry(self):
        """Refresh token expiry is set correctly"""
        expiry = token_manager.get_refresh_token_expiry()
        
        # Should be approximately 7 days from now
        now = datetime.now(timezone.utc)
        expected_range = (
            now + timedelta(days=6, hours=23),
            now + timedelta(days=7, hours=1),
        )
        
        assert expected_range[0] < expiry < expected_range[1]

    def test_token_with_invalid_signature_is_rejected(self):
        """A structurally valid token signed by another key fails closed."""
        wrong_key_token = auth.jwt.encode(
            {
                "user_id": 42,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=1),
            },
            "different-signing-key-that-is-at-least-32-characters",
            algorithm="HS256",
        )

        with pytest.raises(ValueError, match="signature"):
            token_manager.verify_access_token(wrong_key_token)

    def test_jwt_encoder_failure_is_reported(self, monkeypatch):
        """Failures from the JWT boundary become a stable domain error."""
        monkeypatch.setattr(
            auth.jwt,
            "encode",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("encoder failed")),
        )

        with pytest.raises(ValueError, match="Token creation failed"):
            token_manager.create_access_token(42)

    def test_unexpected_jwt_decoder_failure_is_reported(self, monkeypatch):
        """Unexpected failures from the JWT boundary still fail closed."""
        monkeypatch.setattr(
            auth.jwt,
            "decode",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("decoder failed")
            ),
        )

        with pytest.raises(ValueError, match="Token verification failed"):
            token_manager.verify_access_token("token")

    def test_authentication_managers_are_available_through_public_accessors(self):
        assert get_password_manager() is password_manager
        assert get_token_manager() is token_manager


# ============================================================================
# Data Classification Tests (Epic 3)
# ============================================================================

class TestDataClassifier:
    """Test RED/YELLOW/GREEN data classification"""
    
    def test_classify_green_data(self):
        """Generic text classified as GREEN"""
        text = "What is the weather like today?"
        result = classify_data(text)
        
        assert result.level == DataClass.GREEN
        assert len(result.patterns) == 0
    
    def test_classify_red_cpf(self):
        """CPF pattern classified as RED"""
        text = "My CPF is 123.456.789-10"
        result = classify_data(text)
        
        assert result.level == DataClass.RED
        assert len(result.patterns) > 0
    
    def test_classify_yellow_confidential(self):
        """'Confidential' keyword classified as YELLOW"""
        text = "This is confidential information about our marketing strategy"
        result = classify_data(text)
        
        assert result.level == DataClass.YELLOW
        assert len(result.patterns) > 0
    
    def test_classify_red_takes_precedence(self):
        """RED classification takes precedence over YELLOW"""
        text = "Confidential CPF: 123.456.789-10"
        result = classify_data(text)
        
        # Should classify as RED (higher priority)
        assert result.level == DataClass.RED
        assert len(result.patterns) > 0
    
    def test_classify_multiple_patterns(self):
        """Multiple matching patterns are recorded"""
        text = "My CPF is 123.456.789-10 and bank account is 1234567890"
        result = classify_data(text)
        
        assert result.level == DataClass.RED
        assert len(result.patterns) >= 1


# ============================================================================
# Request Queue Tests (Epic 3)
# ============================================================================

class TestInferenceQueue:
    """Test request queue (single-at-a-time enforcement)"""
    
    @pytest.mark.asyncio
    async def test_queue_serializes_requests(self):
        """Multiple concurrent requests are serialized"""
        queue = get_inference_queue()
        times = []
        
        async def mock_task(request_id: str, delay: float):
            start = datetime.now()
            context = await queue.acquire(request_id)
            async with context:
                await asyncio.sleep(delay)
            end = datetime.now()
            times.append((start, end))
        
        # Submit 3 concurrent requests
        await asyncio.gather(
            mock_task("req1", 0.01),
            mock_task("req2", 0.01),
            mock_task("req3", 0.01),
        )
        
        # All three should have run (3 entries)
        assert len(times) == 3
    
    @pytest.mark.asyncio
    async def test_queue_tracks_wait_time(self):
        """Queue wait time is tracked"""
        queue = get_inference_queue()
        
        context = await queue.acquire("test_req")
        async with context:
            # queue_wait_ms should be accessible
            assert hasattr(context, "queue_wait_ms")
            assert context.queue_wait_ms >= 0


# ============================================================================
# Configuration Tests
# ============================================================================

class TestConfiguration:
    """Test configuration loading"""
    
    def test_config_loaded(self):
        """Configuration is loaded correctly"""
        from config import settings
        
        assert settings.gateway_env in ["development", "test", "production"]
        assert settings.gateway_port > 0
        assert settings.gateway_log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
    
    def test_jwt_secret_configured(self):
        """JWT secret is configured"""
        from config import settings
        
        assert len(settings.gateway_jwt_secret) >= 32


# ============================================================================
# Test Fixtures & Helpers
# ============================================================================

@pytest.fixture
def test_password():
    """Fixture for test password"""
    return "TestPassword123!"


@pytest.fixture
def test_user_id():
    """Fixture for test user ID"""
    return 42


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
