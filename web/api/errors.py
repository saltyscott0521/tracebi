"""Shared structured-error payload for API routers."""

from __future__ import annotations

import traceback


def error_detail(message: str, exc: Exception) -> dict:
    """HTTPException detail with message, exception type, and traceback."""
    return {
        "message": f"{message}: {exc}",
        "exception_type": type(exc).__name__,
        "traceback": traceback.format_exc(),
    }
