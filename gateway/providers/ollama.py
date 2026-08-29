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

logger = logging.getLogger(__name__)


class OllamaProvider(Provider):
    """Provider for local Ollama inference"""
    
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.timeout = 30.0
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
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
            response = await self.client.post("/api/generate", json=payload)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract response and token counts
            generated_text = data.get("response", "")
            
            # Calculate tokens (Ollama doesn't provide exact counts, estimate)
            # Rough approximation: ~4 chars per token
            input_tokens = len(prompt) // 4
            output_tokens = len(generated_text) // 4
            
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
            raise TimeoutError(f"Ollama request timed out after {duration_ms}ms")
        
        except httpx.ConnectError as e:
            logger.error(f"Ollama connection error: {e}")
            raise ConnectionError(f"Cannot connect to Ollama at {self.base_url}: {e}")
        
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama HTTP error: {e.response.status_code} {e}")
            raise RuntimeError(f"Ollama API error: {e.response.status_code}")
        
        except Exception as e:
            duration_ms = int((time.time() - request_start) * 1000)
            logger.error(f"Ollama generation error: {e}")
            raise RuntimeError(f"Ollama generation failed: {e}")
    
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
