"""
Dev-mode endpoints — only mounted when ``TRACEBI_DEV_MODE=1``.

Lets you reload discovered request modules without bouncing the server,
which is useful when iterating on report scripts from a notebook or
editor.
"""

from __future__ import annotations

from fastapi import APIRouter

from tracebi.web.discovery import discovered_modules, reload_modules
from tracebi.web.api.registry import registry


router = APIRouter(prefix="/_dev", tags=["dev"])


@router.post("/reload")
def reload_discovered():
    """Re-import every request module discovered at startup, and forget the
    desk's kept verdicts (a re-imported module can change what one reads)."""
    from tracebi.desk import invalidate

    reloaded = reload_modules()
    invalidate()
    return {
        "reloaded": reloaded,
        "count":    len(reloaded),
        "reports":  [r["name"] for r in registry.list_reports()],
    }


@router.get("/discovered")
def list_discovered():
    """List the request modules that auto-discovery picked up."""
    return discovered_modules()
