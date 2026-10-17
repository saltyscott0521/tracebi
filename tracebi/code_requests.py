"""Code publish requests: Python (and the files that decide what it runs)
submitted from a laptop, published only when an admin approves.

A report package or a declarative model is a closed vocabulary and goes
through drafts (:mod:`tracebi.drafts`). What runs on the server with its
secrets does not: a transform, a pipeline, a Python model, a ``report.py``, a
connection. ``tracebi push`` sends those as one request::

    .tracebi/requests/<id>/files/<path>    the files, exactly as submitted
    tracebi_code_requests                  one row: who asked, why, the decision, the runs

Paths are project paths under the canonical folders (``transforms/x.py``),
mapped on the server to its configured directories. An admin reviews the
files and their diff against what is published, then approves (the files are
copied in, what they replace is kept under ``.tracebi/history/code/``, and the
pipelines they touch run once, with the server's secrets) or rejects with a
note. See ``docs/strategy/remote-authoring.md``, step 4.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tracebi.audit import get_actor
from tracebi.drafts import MAX_FILE_BYTES, DraftError, DraftNotFound, _report_target, _write

#: Files per request, so one push cannot fill the disk.
MAX_FILES = 50

_NAME = r"[A-Za-z0-9_][A-Za-z0-9_-]*"
#: The paths a request may hold: (pattern, folder, environment variable).
_CODE_PATHS = (
    (re.compile(rf"transforms/{_NAME}\.(py|ipynb)"), "transforms", "TRACEBI_TRANSFORMS_DIR"),
    (re.compile(rf"pipelines/{_NAME}\.(py|yaml|yml)"), "pipelines", "TRACEBI_PIPELINES_DIR"),
    (re.compile(rf"models/{_NAME}\.py"), "models", "TRACEBI_MODELS_DIR"),
    (re.compile(rf"connections/{_NAME}\.(yaml|yml)"), "connections", "TRACEBI_CONNECTIONS_DIR"),
    (re.compile(rf"reports/(?:{_NAME}/)+report\.py"), "reports", None),
)
_ID = re.compile(r"\d{8}T\d{6}-[0-9a-f]{6}")


def is_code_path(path: str) -> bool:
    """Whether *path* (a project path) is one a code request may hold."""
    return isinstance(path, str) and any(p.fullmatch(path) for p, _, _ in _CODE_PATHS)


def library_path(path: str) -> Path:
    """Where project path *path* lives on this server."""
    if not is_code_path(path):
        raise DraftError(
            f"{path!r} is not a file a code request holds: transforms/<name>.py or "
            f".ipynb, pipelines/<name>.py or .yaml, models/<name>.py, "
            f"connections/<name>.yaml, reports/<package>/report.py")
    folder, rest = path.split("/", 1)
    if folder == "reports":
        root, below = _report_target(rest.rsplit("/", 1)[0])
        return root / below / "report.py"
    env = next(e for p, f, e in _CODE_PATHS if f == folder)
    return Path(os.environ.get(env, folder)) / rest


def _root() -> Path:
    return Path(".tracebi") / "requests"


def _history(version: str) -> Path:
    """Where an approval keeps the files it replaced."""
    return Path(".tracebi") / "history" / "code" / version


def _exec(sql: str, **params) -> None:
    from sqlalchemy import text

    from tracebi import state
    with state.ensure().begin() as conn:
        conn.execute(text(sql), params)


def _rows(sql: str, **params) -> list:
    from sqlalchemy import text

    from tracebi import state
    with state.ensure().connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings()]


def _public(row: dict) -> dict:
    out = dict(row)
    for key in ("files", "runs"):
        out[key] = json.loads(out[key]) if out.get(key) else []
    return out


def _me() -> tuple:
    who, role = get_actor()
    return who, role


def _may_decide(role: Optional[str]) -> bool:
    # No sign-in role (the CLI, an app without sign-in) acts as admin, as
    # everywhere else; a signed-in person decides only as admin.
    return role in (None, "admin")


def create_request(files: dict, note: str, actor: Optional[str]) -> dict:
    """Store *files* (``{project path: text}``) as a pending request."""
    if not isinstance(files, dict) or not files:
        raise DraftError("a code request holds at least one file")
    if len(files) > MAX_FILES:
        raise DraftError(f"a code request holds at most {MAX_FILES} files")
    if not (note or "").strip():
        raise DraftError("say why: a code request needs a note for the reviewer")
    for path, text in files.items():
        library_path(path)
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_FILE_BYTES:
            raise DraftError(f"{path}: text of at most {MAX_FILE_BYTES // 1024} KB")
    now = datetime.now(timezone.utc)
    rid = f"{now:%Y%m%dT%H%M%S}-{os.urandom(3).hex()}"
    for path, text in files.items():
        _write(_root() / rid / "files" / path, text)
    _exec("INSERT INTO tracebi_code_requests (id, status, requested_by, requested_role, "
          "requested_at, note, files) VALUES (:id, 'pending', :by, :role, :at, :note, :files)",
          id=rid, by=actor, role=_me()[1], at=now.isoformat(), note=note.strip(),
          files=json.dumps(sorted(files)))
    return get_request(rid)


def list_requests(status: Optional[str] = None) -> list:
    """Requests the current person may see, newest first: an admin (or no
    sign-in role) sees every one, anyone else their own."""
    who, role = _me()
    rows = _rows("SELECT * FROM tracebi_code_requests ORDER BY id DESC")
    return [{**_public(r), "can_decide": _may_decide(role)} for r in rows
            if (not status or r["status"] == status)
            and (_may_decide(role) or r["requested_by"] == who)]


def _load(request_id: str) -> dict:
    who, role = _me()
    if not isinstance(request_id, str) or not _ID.fullmatch(request_id):
        raise DraftNotFound(f"no code request {request_id!r}")
    rows = _rows("SELECT * FROM tracebi_code_requests WHERE id = :id", id=request_id)
    if not rows or not (_may_decide(role) or rows[0]["requested_by"] == who):
        raise DraftNotFound(f"no code request {request_id!r}")
    return _public(rows[0])


def get_request(request_id: str) -> dict:
    """The request with each file's text and its diff against what is
    published now — once approved, against what it replaced (``new`` when
    there was nothing)."""
    req = _load(request_id)
    files = []
    for path in req["files"]:
        text = (_root() / request_id / "files" / path).read_text(encoding="utf-8")
        live = (_history(req["version"]) / path if req["status"] == "approved"
                else library_path(path))
        before = live.read_text(encoding="utf-8") if live.is_file() else None
        diff = "".join(difflib.unified_diff(
            (before or "").splitlines(keepends=True), text.splitlines(keepends=True),
            fromfile=f"published/{path}" if before is not None else "/dev/null",
            tofile=f"requested/{path}"))
        files.append({"path": path, "text": text, "new": before is None, "diff": diff})
    return {**req, "files": files, "runs": [_with_status(r) for r in req["runs"]],
            "can_decide": _may_decide(_me()[1])}


def _with_status(run: dict) -> dict:
    """A recorded approval run with where it is now (running, ok, failed)."""
    if not run.get("run_id"):
        return run
    from tracebi.pipeline import run_record
    try:
        now = run_record.get(run["pipeline"], str(run["run_id"]))
    except Exception:  # noqa: BLE001 — the run row is gone or unreadable; show what was recorded
        now = None
    return {**run, "status": now["status"], "error": now.get("error")} if now else run


def pipelines_touched(paths: list) -> list:
    """The pipelines an approval runs: those in the request, and every
    declarative pipeline whose transform the request changes."""
    import yaml

    names, transforms = set(), set()
    for path in paths:
        folder, rest = path.split("/", 1)
        stem = rest.rsplit(".", 1)[0]
        if folder == "pipelines":
            names.add(stem)
        elif folder == "transforms":
            transforms.add(stem)
    pdir = Path(os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines"))
    for f in sorted(pdir.glob("*.y*ml")) if pdir.is_dir() else []:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        t = str(doc.get("transform") or "").rsplit(".", 1)[0] if isinstance(doc, dict) else ""
        if t in transforms:
            names.add(f.stem)
    return sorted(names)


def decide(request_id: str, approve: bool, actor: Optional[str],
           note: Optional[str] = None) -> dict:
    """Approve (copy the files in, keeping what they replace) or reject (with a
    note) a pending request. Only an admin decides. Returns the request; on
    approval its ``pipelines`` are the ones to run now (:func:`record_runs`)."""
    req = _load(request_id)
    if not _may_decide(_me()[1]):
        raise PermissionError("only an admin approves code")
    if req["status"] != "pending":
        raise DraftError(f"request {request_id} is already {req['status']}")
    if not approve and not (note or "").strip():
        raise DraftError("a rejection needs a note saying why")
    now = datetime.now(timezone.utc)
    version = None
    if approve:
        version = now.strftime("%Y%m%dT%H%M%S%fZ")
        for path in req["files"]:
            live = library_path(path)
            if live.is_file():
                keep = _history(version) / path
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(live, keep)
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_root() / request_id / "files" / path, live)
    status = "approved" if approve else "rejected"
    _exec("UPDATE tracebi_code_requests SET status = :s, decided_by = :by, decided_at = :at, "
          "decision_note = :note, version = :v WHERE id = :id",
          s=status, by=actor, at=now.isoformat(), note=note or "", v=version, id=request_id)
    from tracebi.state import record_run
    try:
        record_run(kind="code_request", target=request_id, status="ok", finished=now.isoformat(),
                   actor=actor, actor_role=_me()[1],
                   detail={"decision": status, "files": req["files"],
                           "requested_by": req["requested_by"], "version": version})
    except Exception:  # noqa: BLE001 — the decision stands; the row above records it
        pass
    out = get_request(request_id)
    if approve:
        out["pipelines"] = pipelines_touched(req["files"])
    return out


def record_runs(request_id: str, runs: list) -> None:
    """Record the pipeline runs an approval started (``[{pipeline, run_id}]``,
    or ``{pipeline, error}`` when one could not start)."""
    _exec("UPDATE tracebi_code_requests SET runs = :r WHERE id = :id",
          r=json.dumps(runs), id=request_id)
