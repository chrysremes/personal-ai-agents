"""
Claude provider stub for Phase 7+ implementation
Currently returns placeholder responses
"""

import logging
from typing import Dict, Any, Optional, List

from config import settings
from providers import Provider

logger = logging.getLogger(__name__)


class ClaudeProvider(Provider):
    """Provider for Claude Code inference (stub for Phase 7+)"""
    
    def __init__(self):
        self.api_key = settings.claude_api_key
        self.api_endpoint = settings.claude_api_endpoint
        
        if not self.api_key:
            logger.warning("Claude API key not configured")
    
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate response using Claude API (stub)
        
        Phase 7+: Implement actual Anthropic API calls
        
        Returns:
            Placeholder response
        """
        logger.info(f"Claude generate called (stub): model={model}, prompt_len={len(prompt)}")
        
        # TODO: Phase 7 - Implement actual Claude API calls
        # For now, return placeholder
        
        return {
            "response": "[CLAUDE STUB] This feature will be implemented in Phase 7.",
            "tokens_used": {
                "input": len(prompt) // 4,
                "output": 50,
            },
            "duration_ms": 100,
        }
    
    async def health_check(self) -> bool:
        """
        Check if Claude provider is available
        
        Phase 3: Only check if API key is configured
        Phase 7+: Actually test API connectivity
        """
        if not self.api_key:
            logger.debug("Claude API key not configured")
            return False
        
        logger.info("Claude health check: API key configured (actual test in Phase 7+)")
        return True
    
    def get_available_models(self) -> List[str]:
        """Get list of available Claude models"""
        return ["claude-code", "claude-opus"]
