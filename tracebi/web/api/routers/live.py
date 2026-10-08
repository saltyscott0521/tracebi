"""A watch link's events: what one MCP session's agent did, for the Live page."""

import re

from fastapi import APIRouter, HTTPException

from tracebi.state import install_extra, live_events

router = APIRouter(prefix="/live", tags=["live"])

_WATCH = re.compile(r"^[0-9a-f]{32}$")


@router.get("/{watch}")
def get_live(watch: str, after: int = 0):
    """Events after ``after``, oldest first. The id is the capability: anyone
    holding the link may read it, and nothing else lists the ids."""
    if not _WATCH.match(watch):
        raise HTTPException(status_code=404, detail="No such watch link.")
    from tracebi.workbench import with_display

    with install_extra("web"):
        return {"events": [with_display(e) for e in live_events(watch, after=after)]}
