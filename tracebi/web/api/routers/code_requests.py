"""Code publish requests over HTTP (``tracebi push`` sends them; the Drafts
page reviews them). Submitting needs ``analyst`` (the unlisted-write default);
approving and rejecting need ``admin`` (``auth._required_role``)."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from tracebi import code_requests, drafts
from tracebi.audit import get_actor
from tracebi.web.api.errors import error_detail

router = APIRouter(prefix="/code-requests", tags=["drafts"])


class RequestBody(BaseModel):
    files: dict[str, str]
    note: str = ""


class DecideBody(BaseModel):
    note: str = ""


def _refused(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail={
            **error_detail("Code request refused", exc), "role": get_actor()[1],
            "required_role": "admin"})
    status = 404 if isinstance(exc, drafts.DraftNotFound) else 422
    return HTTPException(status_code=status, detail=error_detail("Code request refused", exc))


@router.post("", status_code=201)
def create_code_request(body: RequestBody):
    """Store the files as a request for an admin to review."""
    try:
        return code_requests.create_request(body.files, body.note, get_actor()[0])
    except drafts.DraftError as exc:
        raise _refused(exc)


@router.get("")
def list_code_requests(status: Optional[Literal["pending", "approved", "rejected"]] = None):
    return {"requests": code_requests.list_requests(status)}


@router.get("/{request_id}")
def get_code_request(request_id: str):
    """The files, each with its diff against what is published."""
    try:
        return code_requests.get_request(request_id)
    except drafts.DraftError as exc:
        raise _refused(exc)


def _run(names: list) -> list:
    """Start each pipeline once, in the background, from its file as it is now."""
    import os

    from tracebi import pipeline_registry
    from tracebi.web.api import pipeline_runs
    from tracebi.web.api.registry import registry
    from tracebi.web.api.routers.pipelines import _pipeline_order

    pdir = os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines")
    runs = []
    for name in names:
        try:
            runner = pipeline_registry.reload(name, pdir)
            registry.add_pipeline(name, runner)
            started = pipeline_runs.start(name, runner, _pipeline_order(runner, True))
            runs.append({"pipeline": name, "run_id": started["run_id"]})
        except Exception as exc:  # noqa: BLE001 — the files are in; say which run did not start
            runs.append({"pipeline": name, "error": f"{type(exc).__name__}: {exc}"})
    return runs


@router.post("/{request_id}/approve")
def approve_code_request(request_id: str, body: Optional[DecideBody] = None):
    """Copy the files in, then run the pipelines they touch once, and any
    transform no pipeline runs, with this server's secrets; the request
    records each run."""
    try:
        out = code_requests.decide(request_id, True, get_actor()[0],
                                   (body.note if body else "") or None)
    except (drafts.DraftError, PermissionError) as exc:
        raise _refused(exc)
    runs = _run(out.pop("pipelines", []))
    runs += code_requests.run_transforms(out.pop("transforms", []))
    code_requests.record_runs(request_id, runs)
    return {**out, "runs": runs}


@router.post("/{request_id}/reject")
def reject_code_request(request_id: str, body: DecideBody):
    try:
        return code_requests.decide(request_id, False, get_actor()[0], body.note)
    except (drafts.DraftError, PermissionError) as exc:
        raise _refused(exc)
