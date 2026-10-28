"""``tracebi push``: send files from a laptop to a TraceBi server.

What goes where is decided by what a file can do on the server:

- a report package (``report.json`` + ``template.html`` or ``app.jsx`` …) and
  a declarative model (``models/<name>.yaml`` or ``.json``) become the
  person's **drafts**, with the same checks as a draft written in the app;
- Python and the files that decide what it runs (``transforms/``,
  ``pipelines/``, ``models/<name>.py``, ``connections/``, a package's
  ``report.py``) become one **code request** for an admin to approve.

Data never goes: the server builds its own warehouse with its own secrets.
Signed in with ``tracebi login --server <url>``.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

from tracebi.code_requests import is_code_path
from tracebi.drafts import REPORT_FILES

_DECLARATIVE_MODEL = (".yaml", ".json")


class PushError(Exception):
    pass


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        raise PushError(f"{path} is outside this workspace ({Path.cwd()})") from None


def _reports_dir() -> Path:
    return Path(os.environ.get("TRACEBI_REPORTS_DIR", "reports"))


def _package_name(pkg: Path) -> str:
    try:
        return pkg.resolve().relative_to(_reports_dir().resolve()).as_posix()
    except ValueError:
        raise PushError(f"{pkg} is a report package outside {_reports_dir()}/") from None


def collect(paths: list) -> tuple[dict, dict, dict]:
    """(report packages ``{name: {file: text}}``, model drafts
    ``{name: (file, text)}``, code ``{project path: text}``) for *paths*:
    files, report package directories, or a folder of them."""
    reports: dict = {}
    models: dict = {}
    code: dict = {}
    queue = [Path(p) for p in paths]
    while queue:
        p = queue.pop(0)
        if p.is_dir():
            if (p / "report.json").is_file():
                name = _package_name(p)
                reports[name] = {n: (p / n).read_text(encoding="utf-8")
                                 for n in REPORT_FILES if (p / n).is_file()}
                if (p / "report.py").is_file():
                    queue.append(p / "report.py")
                continue
            children = sorted(c for c in p.iterdir()
                              if not c.name.startswith((".", "_")))
            if not children:
                raise PushError(f"{p}/ holds nothing to push")
            queue.extend(children)
            continue
        if not p.is_file():
            raise PushError(f"{p} does not exist")
        rel = _rel(p)
        if rel.startswith("models/") and p.suffix in _DECLARATIVE_MODEL and "/" not in rel[7:]:
            models[p.stem] = (p.name, p.read_text(encoding="utf-8"))
        elif is_code_path(rel):
            code[rel] = p.read_text(encoding="utf-8")
        elif p.parent.joinpath("report.json").is_file() and p.name in REPORT_FILES:
            queue.append(p.parent)
        else:
            raise PushError(
                f"{rel} is not something a server takes: a report package, "
                f"models/<name>.yaml or .json, or code (transforms/, pipelines/, "
                f"models/<name>.py, connections/, a package's report.py). "
                f"Data stays on this machine; the server builds its own.")
    return reports, models, code


def _call(server: str, method: str, path: str, body=None) -> dict:
    from tracebi import credentials

    status, payload = credentials.api(server, method, path, body)
    if status >= 400:
        detail = payload.get("detail")
        msg = detail.get("message") if isinstance(detail, dict) else detail
        if isinstance(detail, dict) and detail.get("exception"):
            msg = f"{msg}: {detail['exception']}"
        raise PushError(f"{method} {path} → {status}: {msg or payload or 'refused'}")
    return payload


def _draft(server: str, kind: str, name: str, files: dict, echo) -> None:
    started = _call(server, "POST", "/api/drafts",
                    {"kind": kind, "path": name, "from_published": False})
    base = f"/api/drafts/{quote(started['owner'])}/{kind}/{quote(name)}"
    for file, text in files.items():
        _call(server, "PUT", f"{base}/files/{quote(file)}", {"content": text})
    held = _call(server, "GET", f"{base}/files").get("files") or {}
    extra = sorted(set(held) - set(files))
    where = server.rstrip("/") + started["url"] if started["url"].startswith("/") else started["url"]
    echo(f"  draft  {kind}/{name}  {where}")
    if extra:
        echo(f"         the draft also holds {', '.join(extra)}, which you did not push: "
             f"delete it in the app if it should go")


def push(server: str, paths: list, note: str = "", echo=print) -> int:
    """Send *paths* to *server*; prints where each landed. Returns the number
    of things sent."""
    from tracebi import credentials

    server = credentials.server_key(server)
    reports, models, code = collect(paths)
    if code and not note.strip():
        raise PushError(
            f"{len(code)} code file(s) go to an admin as a request: say why with "
            f"--note \"...\"")
    credentials.access_token(server)             # signed in, before anything is sent
    echo(f"Pushing to {server}")
    for name, files in reports.items():
        _draft(server, "reports", name, files, echo)
    for name, (file, text) in models.items():
        _draft(server, "models", name, {file: text}, echo)
    if code:
        req = _call(server, "POST", "/api/code-requests", {"files": code, "note": note})
        echo(f"  code   {len(code)} file(s) → request {req['id']}, waiting for an admin "
             f"(Review, Needs attention)")
        for path in sorted(code):
            echo(f"         {path}")
    if reports or models:
        echo("Drafts are yours until you publish them in the app.")
    return len(reports) + len(models) + (1 if code else 0)
