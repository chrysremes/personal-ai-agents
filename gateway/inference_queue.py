"""Single-inference-at-a-time enforcement for model requests."""

import asyncio
import logging
import time
from typing import Optional


logger = logging.getLogger(__name__)


class InferenceQueue:
    """Serialize model inference through an ``asyncio.Semaphore``."""

    def __init__(self, max_concurrent: int = 1):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.current_request_id: Optional[str] = None
        self.queue_depth = 0

    async def acquire(self, request_id: str) -> "QueueContext":
        """Acquire an inference slot and measure the time spent waiting."""
        self.queue_depth += 1
        queue_entry_time = time.time()
        logger.debug("[%s] Entering inference queue. Queue depth: %s", request_id, self.queue_depth)

        await self.semaphore.acquire()
        queue_wait_ms = int((time.time() - queue_entry_time) * 1000)
        self.current_request_id = request_id
        logger.info("[%s] Acquired inference lock. Queue wait: %sms", request_id, queue_wait_ms)

        return QueueContext(self, request_id, queue_wait_ms)


class QueueContext:
    """Release an acquired inference slot when its request completes."""

    def __init__(self, queue: InferenceQueue, request_id: str, queue_wait_ms: int):
        self.queue = queue
        self.request_id = request_id
        self.queue_wait_ms = queue_wait_ms
        self.start_time = time.time()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self.start_time) * 1000)
        self.queue.semaphore.release()
        self.queue.queue_depth -= 1
        self.queue.current_request_id = None

        if exc_type:
            logger.error(
                "[%s] Released inference lock with error. Duration: %sms, Exception: %s",
                self.request_id,
                duration_ms,
                exc_type.__name__,
            )
        else:
            logger.info("[%s] Released inference lock. Duration: %sms", self.request_id, duration_ms)

        return False


_inference_queue = InferenceQueue(max_concurrent=1)


async def acquire_inference_queue(request_id: str) -> QueueContext:
    """Acquire a slot in the global inference queue."""
    return await _inference_queue.acquire(request_id)


def get_inference_queue() -> InferenceQueue:
    """Return the global inference queue."""
    return _inference_queue


def get_queue_depth() -> int:
    """Return the number of queued or currently running requests."""
    return _inference_queue.queue_depth


def get_current_request_id() -> Optional[str]:
    """Return the request currently holding the inference lock, if any."""
    return _inference_queue.current_request_id
