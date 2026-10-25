"""The desk review list. GET, so a viewer may read it."""

import os

from fastapi import APIRouter

from tracebi.desk import review
from tracebi.web.api.registry import registry

router = APIRouter(tags=["desk"])


def _loaded_models() -> dict:
    from tracebi.model_registry import get_model, list_models

    models: dict = {}
    for name in list_models():
        try:
            model = get_model(name)
        except Exception:  # noqa: BLE001 — one broken model stays off the desk
            continue
        models[name] = model
        named = getattr(model, "name", None)
        if named:
            models[named] = model
    return models


@router.get("/desk")
def desk(fresh: bool = False):
    """Pins, exploration drafts, receipts that do not reproduce, sink status.

    Only reports the caller may view are listed. Each entry naming a
    ``report`` also carries its ``display_name``. A
    verdict is reused while nothing it was computed from has changed
    (:func:`tracebi.desk.verdict`); ``?fresh=1`` re-runs every one.
    """
    from tracebi.permissions import can

    out = review(os.getcwd(), _loaded_models(), fresh=fresh)
    names = {r["name"]: r["display_name"] for r in registry.list_reports()}
    # A report in a folder the caller may not view is not on their desk: not
    # its build, its cover, its numbers or its verdict (core invariant 5).
    for group in ("pins", "drafts", "verdicts", "builds"):
        out[group] = [{**e, "display_name": _display_name(e["report"], names)}
                      for e in out[group] if can("view", e["report"])]
    if out["open"] and not can("view", out["open"]["report"]):
        out["open"] = None
    if out["open"]:
        out["open"] = {**out["open"],
                       "display_name": _display_name(out["open"]["report"], names)}
    return out


def _display_name(report: str, names: dict) -> str:
    """report.json's name for a registered report, else its title-cased identifier
    (a build on disk whose report is no longer registered still reads as a name)."""
    from tracebi.model.data_model import default_label

    return names.get(report) or default_label(report)
