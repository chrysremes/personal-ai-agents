"""
Ollama provider implementation
Calls local Qwen models via Ollama HTTP API
"""

import logging
import time
from typing import Dict, Any, Optional, List

import httpx

from config import settings
from providers import Provider
from retry import retry_async

logger = logging.getLogger(__name__)


class OllamaRequestTimeout(TimeoutError):
    """Ollama did not complete within the configured model timeout."""


class OllamaUnavailable(ConnectionError):
    """Ollama cannot be reached or returned a transient server failure."""


class OllamaRequestError(RuntimeError):
    """Ollama rejected a request that should not be retried."""


class OllamaProvider(Provider):
    """Provider for local Ollama inference"""
    
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.default_timeout_seconds = settings.ollama_timeout_seconds
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.default_timeout_seconds,
        )

    def timeout_for_model(self, model: str) -> int:
        """Return the configured timeout for a model tier."""
        return settings.inference_timeouts_by_model.get(
            model,
            self.default_timeout_seconds,
        )
    
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate response using Ollama API
        
        Makes HTTP POST request to: /api/generate
        
        Returns:
            {
                "response": generated_text,
                "tokens_used": {"input": N, "output": M},
                "duration_ms": elapsed_ms,
            }
        """
        return await retry_async(
            lambda: self._generate_once(prompt, model, temperature, max_tokens),
            retryable_exceptions=(OllamaRequestTimeout, OllamaUnavailable),
            retry_limits={OllamaUnavailable: 1},
        )

    async def _generate_once(
        self,
        prompt: str,
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> Dict[str, Any]:
        """Make one Ollama request, translating HTTP failures to domain errors."""
        request_start = time.time()

        try:
            logger.debug(f"Generating with Ollama: model={model}, prompt_len={len(prompt)}")
            
            # Prepare request payload
            payload = {
                "model": model,
                "prompt": prompt,
                "temperature": temperature,
                "stream": False,
            }
            
            if max_tokens:
                payload["num_predict"] = max_tokens
            
            # Call Ollama API
            response = await self.client.post(
                "/api/generate",
                json=payload,
                timeout=self.timeout_for_model(model),
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Extract response and token counts
            generated_text = data.get("response", "")
            
            input_tokens = data.get("prompt_eval_count", len(prompt) // 4)
            output_tokens = data.get("eval_count", len(generated_text) // 4)
            
            duration_ms = int((time.time() - request_start) * 1000)
            
            logger.info(
                f"Ollama generation complete: "
                f"model={model}, "
                f"output_len={len(generated_text)}, "
                f"duration_ms={duration_ms}"
            )
            
            return {
                "response": generated_text,
                "tokens_used": {
                    "input": input_tokens,
                    "output": output_tokens,
                },
                "duration_ms": duration_ms,
            }
            
        except httpx.TimeoutException:
            duration_ms = int((time.time() - request_start) * 1000)
            logger.error(f"Ollama timeout after {duration_ms}ms")
            raise OllamaRequestTimeout(
                f"Ollama request timed out after {duration_ms}ms"
            )
        
        except httpx.ConnectError as e:
            logger.error(f"Ollama connection error: {e}")
            raise OllamaUnavailable(f"Cannot connect to Ollama at {self.base_url}: {e}")
        
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            logger.error(f"Ollama HTTP error: {status_code} {e}")
            if status_code >= 500:
                raise OllamaUnavailable(f"Ollama API error: {status_code}")
            raise OllamaRequestError(f"Ollama API error: {status_code}")

        except (OllamaRequestTimeout, OllamaUnavailable, OllamaRequestError):
            raise
        
        except Exception as e:
            duration_ms = int((time.time() - request_start) * 1000)
            logger.error(f"Ollama generation error: {e}")
            raise OllamaRequestError(f"Ollama generation failed: {e}")
    
    async def health_check(self) -> bool:
        """
        Check if Ollama is available
        
        Returns:
            True if Ollama is responding to /api/tags
        """
        try:
            logger.debug("Checking Ollama health...")
            response = await self.client.get("/api/tags", timeout=5.0)
            is_healthy = response.status_code == 200
            
            if is_healthy:
                logger.info("Ollama health check passed")
            else:
                logger.warning(f"Ollama health check failed: {response.status_code}")
            
            return is_healthy
            
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False
    
    def get_available_models(self) -> List[str]:
        """
        Get list of available models
        
        Note: This is currently a stub - Phase 3+ needs async implementation
        """
        # TODO: Make this async and call /api/tags endpoint
        return [
            "qwen3.5:2b",
            "qwen3.5:4b",
            "qwen3.5:9b",
        ]
    
    async def close(self) -> None:
        """Close HTTP client"""
        await self.client.aclose()
    
    def __del__(self):
        """Cleanup on destruction"""
        # Note: Can't use await in __del__, so rely on explicit close() call
        pass
