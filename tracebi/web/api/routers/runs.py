"""Read the shared run store. HTML stays on disk; this returns the rows."""

from typing import Optional

from fastapi import APIRouter

from tracebi.state import install_extra, list_runs
from tracebi.web.api.registry import registry

router = APIRouter(prefix="/runs", tags=["runs"])

_REPORT_KINDS = ("report_build", "schedule", "background_run")


@router.get("")
def get_runs(kind: Optional[str] = None, target: Optional[str] = None,
             limit: int = 50):
    """Newest first. ``kind`` and ``target`` narrow the list. Viewer may read."""
    with install_extra("web"):
        rows = list_runs(kind=kind or None, target=target or None, limit=limit)
    names = {r["name"]: r["display_name"] for r in registry.list_reports()}
    return [{**r, "display_name": _display_name(r, names)} for r in rows if _may_see(r)]


def _display_name(row: dict, reports: dict) -> Optional[str]:
    """What people call the run's target (a report's or model's name), or None.

    ``target`` stays the identifier; a pipeline run has no display name.
    """
    from tracebi.model.data_model import default_label

    target = row.get("target") or ""
    if row.get("kind") in _REPORT_KINDS:
        return reports.get(target) or default_label(target)
    if row.get("kind") == "publish":
        family, _, path = target.partition("/")
        if family == "reports":
            return reports.get(path) or default_label(path)
        if family == "models":
            return getattr(registry.get_model(path), "label", None) or default_label(path)
    return None


def _may_see(row: dict) -> bool:
    """A report's builds and schedule runs are no more visible than the report."""
    from tracebi.permissions import can

    target = row.get("target") or ""
    if row.get("kind") in _REPORT_KINDS:
        return can("view", target)
    if row.get("kind") == "publish" and target.startswith("reports/"):
        return can("view", target.removeprefix("reports/"))
    return True
