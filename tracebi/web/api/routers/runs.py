"""Read the shared run store. HTML stays on disk; this returns the rows."""

from typing import Optional

from fastapi import APIRouter, Query

from tracebi.state import count_runs, install_extra, list_runs
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

    ``target`` stays the identifier. A pipeline run goes by the label of the
    first model its pipeline names (``portfolio_model`` reads "Portfolio"), the
    words History's model chips use; one of its steps keeps the step's name.
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
    if row.get("kind") == "pipeline_run":
        model = _pipeline_model(target)
        return getattr(registry.get_model(model), "label", None) or default_label(model)
    return None


def _pipeline_model(pipeline: str) -> str:
    """The model a pipeline belongs to: the first it names, else the one
    ``model_pipeline`` stamped, else its own name (as ``/api/pipelines`` says)."""
    runner = registry.get_pipeline(pipeline)
    named = [m for m in (getattr(runner, "models", None) or []) if isinstance(m, str) and m]
    stamped = getattr(runner, "model", None)
    return named[0] if named else stamped if isinstance(stamped, str) and stamped else pipeline


@router.get("/counts")
def get_run_counts(kind: list[str] = Query(default=[])):
    """How many runs the store holds for each target, and how many failed.

    History folds a report's or pipeline's older runs under its newest, and the
    list it holds is the newest 50; this says how many there are in all, so
    "N older runs" counts the store, not the page. One row per kind and target,
    only for targets the caller may see.
    """
    with install_extra("web"):
        rows = count_runs(kinds=kind or None)
    return [r for r in rows if _may_see(r)]


def _may_see(row: dict) -> bool:
    """A report's builds and schedule runs are no more visible than the report."""
    from tracebi.permissions import can

    target = row.get("target") or ""
    if row.get("kind") in _REPORT_KINDS:
        return can("view", target)
    if row.get("kind") == "publish" and target.startswith("reports/"):
        return can("view", target.removeprefix("reports/"))
    return True
