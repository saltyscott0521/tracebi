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
pipelines they touch run once, with the server's secrets, as does a transform
no pipeline runs) or rejects with a note. See ``design/strategy/remote-authoring.md``, step 4.

A transform an agent proposes carries a **dry run** (:mod:`tracebi.dryrun`,
stored with :func:`record_dry_run`): what it made against a throwaway copy.
One whose dry run failed is never approved; a newer proposal replaces it.

**Approval commits to git** when the workspace is inside a git work tree and
the files it writes have no uncommitted changes: one commit of exactly those
files, authored by the requester, committed by the approver, with a
``TraceBi-Request: <id>`` trailer. It never pushes. When it cannot commit
(no git, not a repository, those files changed by hand) approval goes ahead
and the request records why (``commit_note``); the sha is ``commit_sha``.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
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
    (re.compile(rf"transforms/{_NAME}\.(sql|py|ipynb|contract\.yaml)"), "transforms",
     "TRACEBI_TRANSFORMS_DIR"),
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
            f"{path!r} is not a file a code request holds: transforms/<name>.sql, "
            f".py, .ipynb or .contract.yaml, pipelines/<name>.py or .yaml, models/<name>.py, "
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
    out["dry_run"] = json.loads(out["dry_run"]) if out.get("dry_run") else None
    return out


def _dry_run_brief(dry_run: Optional[dict]) -> Optional[dict]:
    """What a list shows of a dry run: whether it passed, in a sentence."""
    return {"ok": dry_run.get("ok"), "summary": dry_run.get("summary")} if dry_run else None


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
    return [{**(p := _public(r)), "dry_run": _dry_run_brief(p["dry_run"]),
             "can_decide": _may_decide(role)} for r in rows
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


def _stems(paths: list, folder: str) -> set:
    """The names *paths* hold under *folder*; x.contract.yaml belongs to
    transform x, as x.sql does."""
    out = set()
    for path in paths:
        top, rest = path.split("/", 1)
        if top == folder:
            out.add(rest.split(".", 1)[0] if folder == "transforms" else rest.rsplit(".", 1)[0])
    return out


def _declared_pipelines() -> dict:
    """``{pipeline name: the transform it runs}`` for every declarative pipeline."""
    import yaml

    out = {}
    pdir = Path(os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines"))
    for f in sorted(pdir.glob("*.y*ml")) if pdir.is_dir() else []:
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        out[f.stem] = str(doc.get("transform") or "").rsplit(".", 1)[0] if isinstance(doc, dict) else ""
    return out


def pipelines_touched(paths: list) -> list:
    """The pipelines an approval runs: those in the request, and every
    declarative pipeline whose transform the request changes."""
    transforms = _stems(paths, "transforms")
    names = _stems(paths, "pipelines")
    names |= {p for p, t in _declared_pipelines().items() if t in transforms}
    return sorted(names)


def transforms_alone(paths: list) -> list:
    """The transforms an approval runs by themselves: those the request
    changes that no declarative pipeline runs (a transform an agent proposed
    is one), so that every approved transform runs once."""
    piped = set(_declared_pipelines().values())
    return sorted(_stems(paths, "transforms") - piped)


def run_transforms(names: list) -> list:
    """Run each transform once, now, from its file as it is: ``[{transform,
    status: ok|failed, error?}]``, for :func:`record_runs`. A failed run (its
    SQL, or its sink contract) is recorded, not raised: the files are in."""
    from tracebi.transforms import find_transform, run_transform

    runs = []
    for name in names:
        try:
            path = find_transform(name)
            if path is None:
                raise FileNotFoundError(f"transforms/{name} is not there")
            run_transform(path)
            runs.append({"transform": name, "status": "ok"})
        except Exception as exc:  # noqa: BLE001 — the request records why it failed
            first = (str(exc).splitlines() or [""])[0]
            runs.append({"transform": name, "status": "failed",
                         "error": f"{type(exc).__name__}: {first}"})
    return runs


def record_dry_run(request_id: str, result: dict) -> None:
    """Store a proposal's dry run (:func:`tracebi.dryrun.run`) on its request."""
    _exec("UPDATE tracebi_code_requests SET dry_run = :d WHERE id = :id",
          d=json.dumps(result, default=str), id=request_id)


def review_url() -> str:
    """Where an admin reviews code requests in the app. A bare path when
    ``TRACEBI_PUBLIC_URL`` is unset, as a draft's url is."""
    base = (os.environ.get("TRACEBI_PUBLIC_URL") or "").strip().rstrip("/")
    return f"{base}/review"


def decide(request_id: str, approve: bool, actor: Optional[str],
           note: Optional[str] = None) -> dict:
    """Approve (copy the files in, keeping what they replace) or reject (with a
    note) a pending request. Only an admin decides. Returns the request; on
    approval its ``pipelines`` are the ones to run now, and its
    ``transforms`` the ones no pipeline runs (:func:`run_transforms`), each
    recorded with :func:`record_runs`."""
    req = _load(request_id)
    if not _may_decide(_me()[1]):
        raise PermissionError("only an admin approves code")
    if req["status"] != "pending":
        raise DraftError(f"request {request_id} is already {req['status']}")
    if not approve and not (note or "").strip():
        raise DraftError("a rejection needs a note saying why")
    if approve and req["dry_run"] and not req["dry_run"].get("ok"):
        raise DraftError(
            f"request {request_id} cannot be approved: its dry run did not pass "
            f"({req['dry_run'].get('summary')}). A newer proposal that passes replaces it")
    now = datetime.now(timezone.utc)
    version = None
    committed: tuple = (None, None)
    if approve:
        clean = _git_clean([library_path(p) for p in req["files"]])
        version = now.strftime("%Y%m%dT%H%M%S%fZ")
        for path in req["files"]:
            live = library_path(path)
            if live.is_file():
                keep = _history(version) / path
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(live, keep)
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_root() / request_id / "files" / path, live)
        committed = _commit(req, actor) if clean is None else (None, clean)
    status = "approved" if approve else "rejected"
    _exec("UPDATE tracebi_code_requests SET status = :s, decided_by = :by, decided_at = :at, "
          "decision_note = :note, version = :v, commit_sha = :sha, commit_note = :why "
          "WHERE id = :id",
          s=status, by=actor, at=now.isoformat(), note=note or "", v=version,
          sha=committed[0], why=committed[1], id=request_id)
    from tracebi.state import record_run
    try:
        record_run(kind="code_request", target=request_id, status="ok", finished=now.isoformat(),
                   actor=actor, actor_role=_me()[1],
                   detail={"decision": status, "files": req["files"],
                           "requested_by": req["requested_by"], "version": version,
                           "commit": committed[0]})
    except Exception:  # noqa: BLE001 — the decision stands; the row above records it
        pass
    out = get_request(request_id)
    if approve:
        out["pipelines"] = pipelines_touched(req["files"])
        out["transforms"] = transforms_alone(req["files"])
    return out


# ── Approval commits to git ─────────────────────────────────────────────────


def _git(*args: str, env: Optional[dict] = None, stdin: Optional[str] = None):
    return subprocess.run(["git", *args], cwd=os.getcwd(), capture_output=True, text=True,
                          input=stdin, env=env, timeout=60)


def _first(text: Optional[str]) -> str:
    lines = (text or "").strip().splitlines()
    return lines[0] if lines else ""


def _git_clean(paths: list) -> Optional[str]:
    """None when an approval may commit *paths* (the workspace is in a git
    work tree and they carry no uncommitted change), else why it may not."""
    try:
        inside = _git("rev-parse", "--is-inside-work-tree")
    except (OSError, subprocess.SubprocessError):
        return "git is not installed on the server, so the approval made no commit"
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return "the workspace is not inside a git work tree, so the approval made no commit"
    dirty = _git("status", "--porcelain", "--", *[str(p) for p in paths])
    if dirty.returncode != 0:
        return f"git could not read those files' status ({_first(dirty.stderr)}), so no commit"
    if dirty.stdout.strip():
        changed = ", ".join(line[3:] for line in dirty.stdout.splitlines() if line.strip())
        return (f"{changed} had uncommitted changes before the approval, so it made no "
                f"commit; commit or discard them by hand")
    return None


def _identity(who: Optional[str]) -> tuple:
    """``(name, email)`` for a git author or committer: an email-shaped name
    is its own email; anyone else is ``<name>@tracebi.local``."""
    name = (who or "").strip() or "tracebi"
    if re.fullmatch(r"[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+", name):
        return name, name
    return name, re.sub(r"[^A-Za-z0-9._+:-]", "-", name) + "@tracebi.local"


def _named(path: str) -> str:
    """What a commit subject calls a file's thing: ``transforms/x.contract.yaml``
    is ``x``, ``reports/a/b/report.py`` is ``a/b``."""
    folder, rest = path.split("/", 1)
    return rest.rsplit("/", 1)[0] if folder == "reports" else rest.split(".", 1)[0]


def commit_message(req: dict) -> str:
    """``transforms: <name> — <note>``, a line per file when there are
    several, and the ``TraceBi-Request`` trailer."""
    folders = sorted({p.split("/", 1)[0] for p in req["files"]})
    names = sorted({_named(p) for p in req["files"]})
    lines = [f"{', '.join(folders)}: {', '.join(names)} — {_first(req['note'])}"]
    if len(req["files"]) > 1:
        lines += [""] + list(req["files"])
    lines += ["", f"TraceBi-Request: {req['id']}"]
    return "\n".join(lines) + "\n"


def _commit(req: dict, approver: Optional[str]) -> tuple:
    """Commit exactly the request's files: ``(sha, None)``, or ``(None, why)``.
    Author: the requester; committer: the approver; never pushed."""
    paths = [str(library_path(p)) for p in req["files"]]
    author = _identity(req.get("requested_by"))
    committer = _identity(approver)
    env = {**os.environ, "GIT_COMMITTER_NAME": committer[0],
           "GIT_COMMITTER_EMAIL": committer[1], "GIT_TERMINAL_PROMPT": "0"}
    try:
        added = _git("add", "--", *paths, env=env)
        if added.returncode != 0:
            return None, f"git add failed ({_first(added.stderr)}), so the approval made no commit"
        done = _git("-c", "commit.gpgsign=false", "commit", "--quiet", "-F", "-",
                    f"--author={author[0]} <{author[1]}>", "--", *paths,
                    env=env, stdin=commit_message(req))
        if done.returncode != 0:
            return None, (f"git commit failed ({_first(done.stderr) or _first(done.stdout)}), "
                          f"so the approval made no commit")
        return _git("rev-parse", "HEAD").stdout.strip(), None
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git failed ({exc}), so the approval made no commit"


def record_runs(request_id: str, runs: list) -> None:
    """Record the runs an approval started (``[{pipeline, run_id}]``, or
    ``{pipeline, error}`` when one could not start, and ``{transform,
    status, error?}`` for a transform run by itself)."""
    _exec("UPDATE tracebi_code_requests SET runs = :r WHERE id = :id",
          r=json.dumps(runs), id=request_id)
