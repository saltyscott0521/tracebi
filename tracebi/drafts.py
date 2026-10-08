"""Drafts: where a report or model is written before it is published.

A draft is a private working copy owned by whoever is acting (an MCP agent, a
signed-in person). It lives under ``TRACEBI_DRAFTS_DIR`` (default ``drafts/``)::

    drafts/<owner>/reports/<path>/    report.json, template.html, style.css
    drafts/<owner>/models/<name>.json a declarative model

Nothing a draft holds runs on the server: a report package is a closed
vocabulary that can only ask the model questions, so the allowed files are
exactly those above (no ``report.py``, no ``script.js``), each at most
:data:`MAX_FILE_BYTES` of UTF-8 text. Publishing validates the draft, keeps the
version it replaces under ``.tracebi/history/<kind>/<path>/<timestamp>/``,
copies the files into the library and records a ``publish`` run. The draft is
kept. See ``docs/strategy/remote-authoring.md``.

``kind`` is ``"reports"`` or ``"models"`` (the singular is accepted).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tracebi.report_paths import library_roots, open_report, report_name_error

#: Each file a draft holds, in bytes of UTF-8.
MAX_FILE_BYTES = 512 * 1024

REPORT_FILES = ("report.json", "template.html", "style.css")

_KINDS = {"report": "reports", "reports": "reports",
          "model": "models", "models": "models"}
_MODEL_NAME = re.compile(r"[a-z0-9_]+")
_LAPTOP = "edit it from a laptop (git, or `tracebi push`)"


class DraftError(ValueError):
    """A draft request that cannot be done; the message says why and what to do."""


class DraftNotFound(DraftError):
    """There is no such draft."""


def slug_owner(owner: Optional[str]) -> str:
    """The owner as a folder name: lowercase ``[a-z0-9._-]``, never dot-leading."""
    slug = re.sub(r"[^a-z0-9._-]", "-", (owner or "").lower())
    slug = re.sub(r"^\.+", lambda m: "-" * len(m.group()), slug)
    return slug or "anonymous"


def _owner(owner: str) -> str:
    if not isinstance(owner, str) or not owner or slug_owner(owner) != owner:
        raise DraftError(f"invalid draft owner {owner!r}")
    return owner


def _kind(kind: str) -> str:
    try:
        return _KINDS[kind]
    except (KeyError, TypeError):
        raise DraftError(
            f"kind must be 'reports' or 'models', not {kind!r}") from None


def _check_path(kind: str, path: str) -> None:
    if kind == "reports":
        err = report_name_error(path)
        if err:
            raise DraftError(err)
    elif not isinstance(path, str) or not _MODEL_NAME.fullmatch(path):
        raise DraftError(
            f"invalid model name {path!r}: use lowercase letters, digits and _")


def draft_url(owner: str, kind: str, path: str) -> str:
    """The draft's page in the app: stable, outlives any chat. A bare path when
    ``TRACEBI_PUBLIC_URL`` is unset."""
    base = (os.environ.get("TRACEBI_PUBLIC_URL") or "").strip().rstrip("/")
    return f"{base}/drafts/{owner}/{_kind(kind)}/{path}"


def drafts_root() -> Path:
    return Path(os.environ.get("TRACEBI_DRAFTS_DIR", "drafts"))


def draft_dir(owner: str, kind: str, path: str) -> Path:
    """Where the draft lives: its directory for a report, its ``.json`` file for
    a model. Validates all three; the path may not exist yet."""
    owner, kind = _owner(owner), _kind(kind)
    _check_path(kind, path)
    base = drafts_root() / owner / kind
    return base / f"{path}.json" if kind == "models" else base / path


def _allowed_file(kind: str, path: str, file: str) -> str:
    allowed = REPORT_FILES if kind == "reports" else (f"{path}.json",)
    if file not in allowed:
        raise DraftError(
            f"a {kind[:-1]} draft may hold only {', '.join(allowed)}; "
            f"not {file!r}")
    return file


def _text(content) -> str:
    if not isinstance(content, str):
        raise DraftError("content must be text")
    try:
        size = len(content.encode("utf-8"))
    except UnicodeEncodeError:
        raise DraftError("content is not valid UTF-8 text") from None
    if size > MAX_FILE_BYTES:
        raise DraftError(
            f"file is {size} bytes; a draft file holds at most "
            f"{MAX_FILE_BYTES // 1024} KB")
    return content


def _write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _read_text(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise DraftError(f"{path.name} is larger than "
                         f"{MAX_FILE_BYTES // 1024} KB")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise DraftError(f"{path.name} is not UTF-8 text") from None


def _draft_files(kind: str, path: str, where: Path) -> dict:
    """name -> Path of the allowed files that exist in the draft."""
    if kind == "models":
        return {where.name: where} if where.is_file() else {}
    return {n: where / n for n in REPORT_FILES if (where / n).is_file()}


def _exists(owner: str, kind: str, path: str) -> Path:
    where = draft_dir(owner, kind, path)
    if not (where.is_file() if _kind(kind) == "models" else where.is_dir()):
        raise DraftNotFound(
            f"no draft {_kind(kind)}/{path} for {owner}: start_draft first")
    return where


def _mtime(paths) -> str:
    latest = max((p.stat().st_mtime for p in paths), default=0)
    return datetime.fromtimestamp(latest, timezone.utc).isoformat()


def _published(kind: str, path: str) -> dict:
    """name -> text of what is published now (empty when nothing is)."""
    if kind == "models":
        f = _models_dir() / f"{path}.json"
        return {f.name: f.read_text(encoding="utf-8")} if f.is_file() else {}
    root, rel = _report_target(path)
    pkg = root / rel
    return {n: (pkg / n).read_text(encoding="utf-8")
            for n in REPORT_FILES if (pkg / n).is_file()}


def _summary(owner: str, kind: str, path: str, where: Path) -> dict:
    files = _draft_files(kind, path, where)
    try:
        same = {n: _read_text(p) for n, p in files.items()} == _published(kind, path)
    except (OSError, DraftError):
        same = False
    return {"owner": owner, "kind": kind, "path": path,
            "updated": _mtime(list(files.values()) or [where]),
            "differs_from_published": not same}


def _models_dir() -> Path:
    return Path(os.environ.get("TRACEBI_MODELS_DIR", "models"))


def _report_target(path: str) -> "tuple[Path, str]":
    """(library root, path below it) for publishing report *path*.

    The first library root; under mounts, a path that starts with a mount's
    label goes to that mount, so a draft of a published report returns to
    where it came from.
    """
    roots = library_roots()
    first = path.split("/", 1)
    if len(first) == 2:
        for label, root in roots:
            if label == first[0]:
                return root, first[1]
    return roots[0][1], path


def start_draft(owner: str, kind: str, path: str,
                from_published: bool = False) -> dict:
    """Create the draft, empty or as a copy of the published one."""
    kind = _kind(kind)
    where = draft_dir(owner, kind, path)
    if where.exists():
        raise DraftError(f"draft {kind}/{path} already exists: read_draft it, "
                         f"or delete it to start over")
    files: dict[str, str] = {}
    if from_published and kind == "reports":
        opened = open_report(path, purpose="source")
        pkg = opened.package_dir
        if pkg is None:
            raise DraftError(
                f"no published report package {path!r} to copy "
                f"(a JSON spec: run `tracebi migrate spec` on a laptop first)")
        for extra in ("report.py", "script.js"):
            if (pkg / extra).exists():
                raise DraftError(
                    f"{path} has a {extra}, which runs on the server and "
                    f"cannot be drafted remotely: {_LAPTOP}")
        files = {n: _text(_read_text(pkg / n)) for n in REPORT_FILES
                 if (pkg / n).is_file()}
    elif from_published:
        published = _models_dir()
        if (published / f"{path}.py").is_file():
            raise DraftError(
                f"model {path} is Python (models/{path}.py), which cannot be "
                f"drafted remotely: {_LAPTOP}")
        source = published / f"{path}.json"
        if not source.is_file():
            raise DraftError(f"no published declarative model {path!r} to copy")
        files = {where.name: _text(_read_text(source))}
    elif kind == "models":
        files = {where.name: json.dumps({"name": path}, indent=2) + "\n"}
    if kind == "reports":
        where.mkdir(parents=True)
        for name, content in files.items():
            _write(where / name, content)
    else:
        for name, content in files.items():
            _write(where, content)
    return _summary(owner, kind, path, where)


def list_drafts(owner: Optional[str] = None) -> list:
    """Drafts, newest first: one owner's, or everyone's when *owner* is None."""
    root = drafts_root()
    owners = [_owner(owner)] if owner is not None else (
        sorted(d.name for d in root.iterdir() if d.is_dir())
        if root.is_dir() else [])
    found = []
    for who in owners:
        base = root / who / "reports"
        if base.is_dir():
            for d in sorted(p for p in base.rglob("*") if p.is_dir()):
                if any(c.is_dir() for c in d.iterdir()):
                    continue                    # a folder of drafts, not one
                rel = d.relative_to(base).as_posix()
                if report_name_error(rel) is None:
                    found.append(_summary(who, "reports", rel, d))
        base = root / who / "models"
        if base.is_dir():
            for f in sorted(base.glob("*.json")):
                if _MODEL_NAME.fullmatch(f.stem):
                    found.append(_summary(who, "models", f.stem, f))
    return sorted(found, key=lambda d: d["updated"], reverse=True)


def read_draft(owner: str, kind: str, path: str) -> dict:
    kind = _kind(kind)
    where = _exists(owner, kind, path)
    files = _draft_files(kind, path, where)
    return {"owner": owner, "kind": kind, "path": path,
            "files": {n: _read_text(p) for n, p in files.items()},
            "updated": _mtime(list(files.values()) or [where])}


def write_draft_file(owner: str, kind: str, path: str, file: str,
                     content: str) -> dict:
    kind = _kind(kind)
    where = _exists(owner, kind, path)
    _allowed_file(kind, path, file)
    _write(where if kind == "models" else where / file, _text(content))
    return _summary(owner, kind, path, where)


def delete_draft(owner: str, kind: str, path: str) -> bool:
    """Remove the draft. ``False`` when there was none."""
    kind = _kind(kind)
    where = draft_dir(owner, kind, path)
    if kind == "models":
        if not where.is_file():
            return False
        where.unlink()
        return True
    if not where.is_dir():
        return False
    shutil.rmtree(where)
    base = drafts_root() / owner / "reports"
    for parent in where.parents:                # prune now-empty folders
        if parent == base or any(parent.iterdir()):
            break
        parent.rmdir()
    return True


def draft_version(owner: str, kind: str, path: str) -> str:
    """A cheap fingerprint of what the draft preview shows; poll it."""
    kind = _kind(kind)
    where = _exists(owner, kind, path)
    if kind == "reports":
        from tracebi.workbench import package_version
        return package_version(str(where))
    import hashlib
    return hashlib.sha1(where.read_bytes()).hexdigest()


def _validate_model_draft(path: Path) -> None:
    """Check a declarative-model draft: valid JSON, an object whose ``name``
    equals the file name, and a model that compiles (the same loader
    discovery uses, against this project)."""
    from tracebi.model.model_spec import validate_model_file

    try:
        doc = json.loads(_read_text(path))
    except json.JSONDecodeError as exc:
        raise DraftError(f"{path.name} is not valid JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise DraftError(f"{path.name} must be a JSON object")
    if doc.get("name") != path.stem:
        raise DraftError(
            f"the model's name must equal its file name: {path.name} "
            f"declares {doc.get('name')!r}, expected {path.stem!r}")
    errors = validate_model_file(path, root=Path.cwd())
    if errors:
        raise DraftError(f"{path.name} does not compile: {'; '.join(errors)}")


def _load_models() -> dict:
    from tracebi.mcp_server import _load_models as load
    return load()


def preview_models(owner: str, published: dict) -> dict:
    """The published models with *owner*'s draft models in place of any of the
    same name, so a report can be previewed against a model still in draft.
    Preview only: publishing a report checks it against published models."""
    from tracebi.model.model_spec import load_model_spec

    models = dict(published)
    base = drafts_root() / owner / "models"
    for f in sorted(base.glob("*.json")) if base.is_dir() else []:
        try:
            model = load_model_spec(f, root=Path.cwd())
        except Exception:  # noqa: BLE001 — a broken draft model is its own draft's problem
            continue
        models[model.name] = model
    return models


def render_preview(owner: str, kind: str, path: str,
                   models: Optional[dict] = None) -> Optional[str]:
    """The draft as the working page: exploration blocks kept, in memory, no
    file written, no receipt. ``None`` for a model (validated, no page).
    Raises the render's own exception when the package is broken."""
    from tracebi.reports.template_package import TemplatePackage

    kind = _kind(kind)
    where = _exists(owner, kind, path)
    if kind == "models":
        _validate_model_draft(where)
        return None
    page, _inputs, _outputs = TemplatePackage(str(where)).render_exploration(
        preview_models(owner, _load_models()) if models is None else models)
    return page


def _validate_report(where: Path, models: dict) -> None:
    from tracebi.reports.template_package import TemplatePackage

    missing = [n for n in ("report.json", "template.html")
               if not (where / n).is_file()]
    if missing:
        raise DraftError(f"the draft has no {' or '.join(missing)}")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            TemplatePackage(str(where)).render(
                models, os.path.join(tmp, "check.html"), save_manifest=False)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 — a refusal is a result
            line = str(exc).splitlines()[0] if str(exc) else ""
            raise DraftError(
                f"the report does not render: {type(exc).__name__}: {line}"
            ) from exc


def _keep_previous(kind: str, path: str, current: Path, stamp: str) -> Optional[Path]:
    if not current.exists():
        return None
    keep = Path(".tracebi") / "history" / kind / path / stamp
    keep.parent.mkdir(parents=True, exist_ok=True)
    if current.is_dir():
        shutil.copytree(current, keep)
    else:
        keep.mkdir()
        shutil.copy2(current, keep / current.name)
    return keep


def publish_draft(owner: str, kind: str, path: str, actor: Optional[str],
                  note: Optional[str] = None,
                  models: Optional[dict] = None) -> dict:
    """Validate the draft, keep what it replaces, copy it into the library and
    record a ``publish`` run. The draft stays."""
    kind = _kind(kind)
    where = _exists(owner, kind, path)
    if kind == "models":
        _validate_model_draft(where)
        target = _models_dir() / f"{path}.json"
        if (_models_dir() / f"{path}.py").is_file():
            raise DraftError(
                f"models/{path}.py is a Python model of that name; a draft "
                f"cannot replace it: {_LAPTOP}")
    else:
        root, rel = _report_target(path)
        target = root / rel
        if (target / "report.py").exists():
            raise DraftError(
                f"{path} is published with a report.py, which a draft cannot "
                f"replace: {_LAPTOP}")
        _validate_report(where, _load_models() if models is None else models)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    kept = _keep_previous(kind, path, target, stamp)
    if kind == "models":
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(where, target)
        published = [target.name]
    else:
        target.mkdir(parents=True, exist_ok=True)
        files = _draft_files(kind, path, where)
        for name in REPORT_FILES:               # a file the draft dropped goes too
            if name not in files and (target / name).is_file():
                (target / name).unlink()
        for name, src in files.items():
            shutil.copy2(src, target / name)
        published = sorted(files)
    result = {"owner": owner, "kind": kind, "path": path, "version": stamp,
              "files": published, "previous": str(kept) if kept else None}

    from tracebi.audit import get_actor
    from tracebi.state import record_run
    now = datetime.now(timezone.utc).isoformat()
    try:
        record_run(kind="publish", target=f"{kind}/{path}", status="ok",
                   finished=now, actor=actor, actor_role=get_actor()[1],
                   detail={"version": stamp, "note": note or ""})
    except Exception as exc:  # noqa: BLE001 — published is published; say the audit row is missing
        result["note"] = f"the publish was not recorded: {exc}"
    return result
