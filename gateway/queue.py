"""
Request queue - Single-inference-at-a-time enforcement
Uses asyncio.Semaphore to serialize model calls
"""

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class InferenceQueue:
    """
    Manages single-inference-at-a-time queue
    
    Enforces that only one model inference runs at a time
    via asyncio.Semaphore(1)
    """
    
    def __init__(self, max_concurrent: int = 1):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.current_request_id: Optional[str] = None
        self.queue_depth = 0
    
    async def acquire(self, request_id: str) -> "QueueContext":
        """
        Acquire a slot in the inference queue
        
        Args:
            request_id: Request ID for logging/tracking
            
        Returns:
            Context manager to track queue time
        """
        self.queue_depth += 1
        queue_entry_time = time.time()
        
        logger.debug(
            f"[{request_id}] Entering inference queue. "
            f"Queue depth: {self.queue_depth}"
        )
        
        # Acquire semaphore (blocks if one inference is already running)
        await self.semaphore.acquire()
        
        queue_wait_ms = int((time.time() - queue_entry_time) * 1000)
        self.current_request_id = request_id
        
        logger.info(
            f"[{request_id}] Acquired inference lock. "
            f"Queue wait: {queue_wait_ms}ms"
        )
        
        return QueueContext(
            queue=self,
            request_id=request_id,
            queue_wait_ms=queue_wait_ms,
        )


class QueueContext:
    """Context manager for queue acquisition"""
    
    def __init__(self, queue: InferenceQueue, request_id: str, queue_wait_ms: int):
        self.queue = queue
        self.request_id = request_id
        self.queue_wait_ms = queue_wait_ms
        self.start_time = time.time()
    
    async def __aenter__(self):
        """Enter async context"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context and release semaphore"""
        duration_ms = int((time.time() - self.start_time) * 1000)
        
        self.queue.semaphore.release()
        self.queue.queue_depth -= 1
        self.queue.current_request_id = None
        
        if exc_type:
            logger.error(
                f"[{self.request_id}] Released inference lock with error. "
                f"Duration: {duration_ms}ms, Exception: {exc_type.__name__}"
            )
        else:
            logger.info(
                f"[{self.request_id}] Released inference lock. "
                f"Duration: {duration_ms}ms"
            )
        
        return False  # Don't suppress exceptions


# Global inference queue instance
_inference_queue = InferenceQueue(max_concurrent=1)


async def acquire_inference_queue(request_id: str) -> QueueContext:
    """
    Acquire a slot in the global inference queue
    
    Usage:
        async with await acquire_inference_queue(request_id):
            # Call model here
            result = await ollama_provider.generate(prompt, model)
    
    Args:
        request_id: Request ID for logging
        
    Returns:
        QueueContext async context manager
    """
    return await _inference_queue.acquire(request_id)


def get_inference_queue() -> InferenceQueue:
    """Get the global inference queue instance"""
    return _inference_queue


def get_queue_depth() -> int:
    """Get current queue depth (number of pending requests)"""
    return _inference_queue.queue_depth


def get_current_request_id() -> Optional[str]:
    """Get ID of request currently holding the inference lock"""
    return _inference_queue.current_request_id
