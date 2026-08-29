"""
Base provider interface for model backends
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class Provider(ABC):
    """Abstract base class for model providers"""
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate response to prompt
        
        Args:
            prompt: User prompt
            model: Model name/ID
            temperature: Sampling temperature (0-1)
            max_tokens: Max tokens to generate (optional)
            
        Returns:
            Dict with:
                - response: Generated text
                - tokens_used: {"input": N, "output": M}
                - duration_ms: Execution time
                
        Raises:
            Exception: On provider error
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if provider is available
        
        Returns:
            True if provider is healthy
        """
        pass
    
    @abstractmethod
    def get_available_models(self) -> list:
        """
        Get list of available models
        
        Returns:
            List of model names/IDs
        """
        pass
