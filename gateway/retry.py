"""Retry helpers for transient provider failures."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import TypeVar


logger = logging.getLogger(__name__)
T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    backoff_seconds: tuple[float, ...] = (1, 2, 4),
    retryable_exceptions: tuple[type[BaseException], ...] = (
        TimeoutError,
        ConnectionError,
    ),
    retry_limits: Mapping[type[BaseException], int] | None = None,
) -> T:
    """Run an async operation again only for explicitly transient failures.

    ``max_retries`` counts attempts after the initial call. ``retry_limits``
    narrows that limit for a particular error type; it is used for Ollama 5xx
    responses, which the Phase 3 specification retries only once.
    """
    attempts = 0
    retry_limits = retry_limits or {}

    while True:
        try:
            return await operation()
        except retryable_exceptions as error:
            allowed_retries = max_retries
            for error_type, limit in retry_limits.items():
                if isinstance(error, error_type):
                    allowed_retries = limit
                    break

            if attempts >= allowed_retries:
                raise

            delay = backoff_seconds[min(attempts, len(backoff_seconds) - 1)]
            attempts += 1
            logger.warning(
                "Retrying transient provider failure (%d/%d) in %ss: %s",
                attempts,
                allowed_retries,
                delay,
                error,
            )
            await asyncio.sleep(delay)
