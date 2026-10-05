"""Pipeline runs in the background, each with a running log.

A run is a ``pipeline_run`` row in the shared state store (so it shows on the
Runs page like any other) and a log file under ``data/logs/pipelines/``. The row
holds the outcome; the file holds what the steps printed, as it was printed.
Polling reads the row first and the file second: a terminal status is written
only after the log is closed, so a poller that sees one has the whole log.
"""

from __future__ import annotations

import contextvars
import json
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

from tracebi.pipeline import runlog
from tracebi.web.api.errors import error_detail

KIND = "pipeline_run"

_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tracebi-pipeline")
_active: dict[str, int] = {}                 # pipeline -> the run in progress in this process
_active_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summary(row: dict) -> dict:
    detail = row.get("detail")
    if isinstance(detail, str) and detail:
        try:
            detail = json.loads(detail)
        except json.JSONDecodeError:
            detail = {}
    detail = detail if isinstance(detail, dict) else {}
    return {
        "run_id": str(row["id"]),
        "pipeline": row.get("target") or row.get("layer_name"),
        "status": row.get("status"),
        "started_at": row.get("started_at") or row.get("started"),
        "finished_at": row.get("finished") or row.get("completed_at"),
        "actor": row.get("actor"),
        "layers": detail.get("layers") or [],
        "error": detail.get("error"),
    }


def start(pipeline: str, runner, order: list[str]) -> dict:
    """Begin running *order* (layer names) of *runner*; the row exists on return.

    A pipeline already running in this process returns that run instead of
    starting a second (a double click, or two tabs).
    """
    from tracebi.state import get_run, install_extra, record_run

    with _active_lock:
        if pipeline in _active:
            with install_extra("web"):
                current = get_run(_active[pipeline])
            if current["status"] == "running":
                return {**_summary(current), "already_running": True}
            del _active[pipeline]           # finished; its worker has not cleared it yet
        with install_extra("web"):
            run_id = record_run(kind=KIND, target=pipeline, status="running",
                                started=_now(), detail={"layers": order})
            row = get_run(run_id)
        _active[pipeline] = run_id
    # Carry the audit actor into the worker thread, so each layer's run is
    # attributed to whoever started this one.
    _pool.submit(contextvars.copy_context().run, _execute, pipeline, run_id, runner, order)
    return {**_summary(row), "already_running": False}


def _execute(pipeline: str, run_id: int, runner, order: list[str]) -> None:
    from tracebi.state import install_extra, update_run

    log = runlog.RunLog(runlog.log_path(pipeline, run_id))
    began = time.monotonic()
    status, error = "failed", None
    try:
        with runlog.capture(log.write):
            log.line(f"Pipeline {pipeline}: {' → '.join(order)}")
            for name in order:
                runner.execute_layer(name)
            status = "succeeded"
    except Exception as exc:  # noqa: BLE001 — a failed run is the payload here
        error = error_detail("Run failed", exc)
        if os.environ.get("TRACEBI_DEV_MODE") == "1":
            for line in traceback.format_exc().splitlines():
                log.line(line)
    finally:
        log.line(f"{'Run succeeded' if status == 'succeeded' else 'Run failed'} "
                 f"in {time.monotonic() - began:.1f}s")
        log.close()
        detail: dict = {"layers": order}
        if error is not None:
            detail["error"] = error
        finished = _now()
        try:
            with install_extra("web"):
                update_run(None, run_id, status=status, finished=finished,
                           completed_at=finished, output_path=log.path, detail=detail)
        finally:
            with _active_lock:
                _active.pop(pipeline, None)
        runlog.prune(pipeline)


def get(pipeline: str, run_id: str) -> Optional[dict]:
    """One run's summary, or ``None`` when it is not a run of this pipeline."""
    from tracebi.state import get_run, install_extra

    if not str(run_id).isdigit():
        return None
    with install_extra("web"):
        row = get_run(int(run_id))
    if row is None or row.get("kind") != KIND or row.get("target") != pipeline:
        return None
    return _summary(row)


def history(pipeline: str, limit: int = 10) -> list[dict]:
    """Recent runs of a pipeline, newest first."""
    from tracebi.state import install_extra, list_runs

    with install_extra("web"):
        rows = list_runs(kind=KIND, target=pipeline, limit=limit)
    return [_summary(r) for r in rows]


def read_log(pipeline: str, run_id: str, after: int = 0) -> Optional[dict]:
    """The log from byte *after*, and where to ask from next; ``None`` for an unknown run."""
    run = get(pipeline, run_id)
    if run is None:
        return None
    # The row first, then the file: see the module docstring.
    done = run["status"] != "running"
    try:
        text, nxt = runlog.read_from(runlog.log_path(pipeline, run_id), after)
        expired = False
    except FileNotFoundError:
        text, nxt, expired = "", after, done
    return {"run_id": run["run_id"], "status": run["status"], "done": done,
            "text": text, "next": nxt, "expired": expired}
