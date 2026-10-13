"""Read the shared run store. HTML stays on disk; this returns the rows."""

from typing import Optional

from fastapi import APIRouter

from tracebi.state import install_extra, list_runs

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
def get_runs(kind: Optional[str] = None, target: Optional[str] = None,
             limit: int = 50):
    """Newest first. ``kind`` and ``target`` narrow the list. Viewer may read."""
    with install_extra("web"):
        rows = list_runs(kind=kind or None, target=target or None, limit=limit)
    return [r for r in rows if _may_see(r)]


def _may_see(row: dict) -> bool:
    """A report's builds and schedule runs are no more visible than the report."""
    from tracebi.permissions import can

    target = row.get("target") or ""
    if row.get("kind") in ("report_build", "schedule", "background_run"):
        return can("view", target)
    if row.get("kind") == "publish" and target.startswith("reports/"):
        return can("view", target.removeprefix("reports/"))
    return True
