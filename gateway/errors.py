"""Consistent API error responses for Gateway request failures."""

from typing import Mapping, Optional

from fastapi.responses import JSONResponse


def error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    retry_after: Optional[int] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> JSONResponse:
    """Create the Phase 3 standard top-level error response."""
    detail = {
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if retry_after is not None:
        detail["retry_after"] = retry_after

    return JSONResponse(
        status_code=status_code,
        content={"error": detail},
        headers=headers,
    )
