"""Tests for the Phase 3 provider resilience and chat error contracts."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from retry import retry_async
from routes_chat import chat, ollama_provider
from schemas import ChatRequest
from providers.ollama import OllamaProvider


class TestRetryAsync:
    """The provider seam retries transient failures but not permanent ones."""

    @pytest.mark.asyncio
    async def test_retries_transient_failures_with_configured_backoff(self):
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise TimeoutError("Ollama request timed out")
            return "generated response"

        result = await retry_async(
            operation,
            max_retries=3,
            backoff_seconds=(0, 0, 0),
            retryable_exceptions=(TimeoutError,),
        )

        assert result == "generated response"
        assert attempts == 3

    @pytest.mark.asyncio
    async def test_does_not_retry_permanent_failures(self):
        attempts = 0

        async def operation():
            nonlocal attempts
            attempts += 1
            raise ValueError("model not found")

        with pytest.raises(ValueError, match="model not found"):
            await retry_async(
                operation,
                max_retries=3,
                backoff_seconds=(0, 0, 0),
                retryable_exceptions=(TimeoutError,),
            )

        assert attempts == 1


class TestOllamaProviderTimeouts:
    """Configured model tiers must determine the request timeout."""

    @pytest.mark.asyncio
    async def test_uses_the_heavier_tier_timeout_for_its_model(self, monkeypatch):
        provider = OllamaProvider()
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "response": "A concise response.",
            "prompt_eval_count": 4,
            "eval_count": 5,
        }
        post = AsyncMock(return_value=response)
        monkeypatch.setattr(provider.client, "post", post)

        await provider.generate("Explain the result", "qwen3.5:4b")

        assert post.call_args.kwargs["timeout"] == 180
        await provider.close()


class TestChatErrorContract:
    """The HTTP chat seam returns the specification's top-level error object."""

    @pytest.mark.asyncio
    async def test_returns_standard_timeout_error_with_request_id(self, monkeypatch):
        monkeypatch.setattr(
            ollama_provider,
            "generate",
            AsyncMock(side_effect=TimeoutError("request timed out")),
        )
        monkeypatch.setattr("routes_chat.audit_logger.log_action", AsyncMock())

        response = await chat(
            ChatRequest(prompt="Tell me about public RSS feeds."),
            user_id=1,
            db=object(),
        )

        assert response.status_code == 504
        body = json.loads(response.body)
        assert body["error"]["code"] == "timeout"
        assert body["error"]["request_id"]
        assert body["error"]["retry_after"] == 5

    @pytest.mark.asyncio
    async def test_returns_standard_unavailable_error_with_request_id(self, monkeypatch):
        monkeypatch.setattr(
            ollama_provider,
            "generate",
            AsyncMock(side_effect=ConnectionError("connection refused")),
        )
        monkeypatch.setattr("routes_chat.audit_logger.log_action", AsyncMock())

        response = await chat(
            ChatRequest(prompt="Tell me about public RSS feeds."),
            user_id=1,
            db=object(),
        )

        assert response.status_code == 503
        body = json.loads(response.body)
        assert body["error"]["code"] == "ollama_unavailable"
        assert body["error"]["request_id"]
        assert body["error"]["retry_after"] == 5
