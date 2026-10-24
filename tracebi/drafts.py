"""Drafts: where a report or model is written before it is published.

A draft is a private working copy owned by whoever is acting (an MCP agent, a
signed-in person). It lives under ``TRACEBI_DRAFTS_DIR`` (default ``drafts/``)::

    drafts/<owner>/reports/<path>/    report.json, template.html, style.css, script.js
    drafts/<owner>/models/<name>.yaml a declarative model (or <name>.json)

Nothing a draft holds runs on the server: a report package asks the model
questions through a closed vocabulary, and its ``script.js`` runs only in the
reader's browser, in a sandboxed frame with no access to the app (the browser
is the boundary, not a review of the code). So the allowed files are exactly
those above (no ``report.py``), each at most
:data:`MAX_FILE_BYTES` of UTF-8 text. Publishing validates the draft, keeps the
version it replaces under ``.tracebi/history/<kind>/<path>/<timestamp>/``,
copies the files into the library and records a ``publish`` run. The draft is
kept. See ``design/strategy/remote-authoring.md``.

``kind`` is ``"reports"`` or ``"models"`` (the singular is accepted).

A model draft is exactly one file, ``<name>.yaml`` or ``<name>.json``: writing
the other form replaces it, so the two never coexist. A new draft starts as
YAML. Publishing copies the file as it is to ``models/``, replacing any other
declarative form of that name there (the previous one is kept in history).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tracebi.audit import get_actor
from tracebi.report_paths import library_roots, open_report, report_name_error

#: Each file a draft holds, in bytes of UTF-8.
MAX_FILE_BYTES = 512 * 1024

REPORT_FILES = ("report.json", "template.html", "app.jsx", "style.css", "script.js")

_KINDS = {"report": "reports", "reports": "reports",
          "model": "models", "models": "models"}
_MODEL_NAME = re.compile(r"[a-z0-9_]+")
#: The forms a model draft may take; ``.yml`` is published but not drafted.
_DRAFT_MODEL_FORMS = (".yaml", ".json")
_PUBLISHED_MODEL_FORMS = (".yaml", ".yml", ".json")
_LAPTOP = "edit it from a laptop (git, or `tracebi push`)"
#: Why a draft holds no Python: it would run on the server, with its secrets.
_WHY_NO_CODE = ("Python would run on the server with its "
                "secrets, so it comes only through a laptop and review")


class DraftError(ValueError):
    """A draft request that cannot be done; the message says why and what to do."""


class DraftNotFound(DraftError):
    """There is no such draft."""


def slug_owner(owner: Optional[str]) -> str:
    """The owner as a folder name: lowercase ``[a-z0-9._@+-]``, never
    dot-leading. When a character had to be replaced, a short hash of the
    original is appended, so two people never share a folder
    (``a/b@x.com`` and ``a-b@x.com`` stay apart)."""
    lowered = (owner or "").lower()
    slug = re.sub(r"[^a-z0-9._@+-]", "-", lowered)
    slug = re.sub(r"^\.+", lambda m: "-" * len(m.group()), slug)
    if slug != lowered:
        slug = f"{slug}-{hashlib.sha256(lowered.encode('utf-8')).hexdigest()[:8]}"
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
    """Where the draft lives: its directory for a report, its file for a model
    (the ``.yaml`` or ``.json`` that exists; ``.yaml`` for a new one). Validates
    all three; the path may not exist yet."""
    owner, kind = _owner(owner), _kind(kind)
    _check_path(kind, path)
    base = drafts_root() / owner / kind
    if kind == "models":
        return next((f for f in (base / f"{path}{e}" for e in _DRAFT_MODEL_FORMS)
                     if f.is_file()), base / f"{path}.yaml")
    return base / path


def _allowed_file(kind: str, path: str, file: str) -> str:
    allowed = REPORT_FILES if kind == "reports" else tuple(
        f"{path}{e}" for e in _DRAFT_MODEL_FORMS)
    if file not in allowed:
        raise DraftError(
            f"a {kind[:-1]} draft may hold only {', '.join(allowed)}; "
            f"not {file!r}. A draft holds no Python because {_WHY_NO_CODE}.")
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
        f = next(iter(_published_model_files(path)), None)
        return {f.name: f.read_text(encoding="utf-8")} if f else {}
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


def _published_model_files(path: str) -> list:
    """The declarative files of model *path* in ``models/`` (one, normally)."""
    return [f for f in (_models_dir() / f"{path}{e}"
                        for e in _PUBLISHED_MODEL_FORMS) if f.is_file()]


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


def model_python_blocker(path: str) -> Optional[str]:
    """Why model *path* cannot be drafted remotely, when it is a Python model
    (``models/<path>.py`` wins over any declarative file). None otherwise."""
    if (_models_dir() / f"{path}.py").is_file():
        return (f"model {path} is Python (models/{path}.py), which cannot be "
                f"drafted remotely: {_LAPTOP}")
    return None


def model_draft_status(path: str) -> "tuple[bool, Optional[str]]":
    """Whether published model *path* can be drafted, and if not, why.

    The one decision the MCP model listings report, so they cannot disagree
    with :func:`start_draft`, which refuses the same Python models.
    """
    blocker = model_python_blocker(path)
    if blocker:
        return False, blocker
    if not _published_model_files(path):
        return False, (f"model {path} has no declarative file in models/, "
                       f"and only a file there can be drafted: {_LAPTOP}")
    return True, None


def start_draft(owner: str, kind: str, path: str,
                from_published: bool = False) -> dict:
    """Create the draft, empty or as a copy of the published one."""
    kind = _kind(kind)
    where = draft_dir(owner, kind, path)
    if where.exists():
        raise DraftError(f"draft {kind}/{path} already exists: read_draft it, "
                         f"or delete it to start over")
    if kind == "models" and (blocker := model_python_blocker(path)):
        raise DraftError(blocker)
    files: dict[str, str] = {}
    if kind == "reports":
        _require_folder("build", path)
    if from_published and kind == "reports":
        opened = open_report(path, purpose="source")
        pkg = opened.package_dir
        if pkg is None:
            raise DraftError(
                f"no published report package {path!r} to copy "
                f"(a JSON spec: run `tracebi migrate spec` on a laptop first)")
        if (pkg / "report.py").exists():
            raise DraftError(
                f"{path} has a report.py, which runs on the server and "
                f"cannot be drafted remotely: {_LAPTOP}")
        files = {n: _text(_read_text(pkg / n)) for n in REPORT_FILES
                 if (pkg / n).is_file()}
    elif from_published:
        [source, *_] = _published_model_files(path) or [None]
        if source is None:
            raise DraftError(f"no published declarative model {path!r} to copy")
        where = where.with_suffix(".json" if source.suffix == ".json" else ".yaml")
        files = {where.name: _text(_read_text(source))}
    elif kind == "models":
        files = {where.name: f"name: {path}\n"}
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
            stems = sorted({f.stem for e in _DRAFT_MODEL_FORMS
                            for f in base.glob(f"*{e}")})
            for stem in stems:
                if _MODEL_NAME.fullmatch(stem):
                    found.append(_summary(who, "models", stem,
                                          draft_dir(who, "models", stem)))
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
    if kind == "models":
        where = where.with_name(file)
        _write(where, _text(content))
        for other in _DRAFT_MODEL_FORMS:        # one form at a time
            if f"{path}{other}" != file:
                where.with_name(f"{path}{other}").unlink(missing_ok=True)
    else:
        _write(where / file, _text(content))
    return _summary(owner, kind, path, where)


def delete_draft(owner: str, kind: str, path: str) -> bool:
    """Remove the draft. ``False`` when there was none."""
    kind = _kind(kind)
    where = draft_dir(owner, kind, path)
    if kind == "models":
        if not where.is_file():
            return False
        for form in _DRAFT_MODEL_FORMS:
            where.with_name(f"{path}{form}").unlink(missing_ok=True)
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
    """Check a declarative-model draft: valid YAML or JSON, a mapping whose
    ``name`` equals the file name, and a model that compiles (the same loader
    discovery uses, against this project)."""
    from tracebi.model.model_spec import ModelSpecError, read_model_doc, validate_model_file

    _read_text(path)                            # size and encoding, before parsing
    try:
        doc = read_model_doc(path)
    except ModelSpecError as exc:
        raise DraftError(f"{path.name} is {exc.errors[0]}") from None
    if not isinstance(doc, dict):
        raise DraftError(f"{path.name} must hold one object (a mapping at the top level)")
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
    for f in sorted(base.glob("*.yaml")) + sorted(base.glob("*.json")) if base.is_dir() else []:
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
        preview_models(owner, _load_models()) if models is None else models,
        require_placed=True)
    return page


def _validate_report(where: Path, models: dict):
    """Render the package to check it; returns the build's manifest."""
    from tracebi.reports.template_package import TemplatePackage

    missing = [n for n in ("report.json",) if not (where / n).is_file()]
    if not (where / "template.html").is_file() and not (where / "app.jsx").is_file():
        missing.append("template.html (or app.jsx)")
    if missing:
        raise DraftError(f"the draft has no {' or '.join(missing)}")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            return TemplatePackage(str(where)).render(
                models, os.path.join(tmp, "check.html"), save_manifest=False)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 — a refusal is a result
            line = str(exc).splitlines()[0] if str(exc) else ""
            raise DraftError(
                f"the report does not render: {type(exc).__name__}: {line}"
            ) from exc


class FolderDenied(DraftError):
    """The folder's ``_folder.yaml`` does not give this person the permission
    (Build to draft in it, Publish to publish into it)."""


def _require_folder(action: str, path: str) -> None:
    from tracebi import permissions
    try:
        permissions.require(action, path)
    except permissions.NotPermitted as exc:
        raise FolderDenied(str(exc)) from exc


class NotAnOwner(DraftError):
    """The signed-in person may not publish this model: it names owners and
    they are not among them (and not an admin)."""


def model_owners(path: str) -> list:
    """Who owns *published* model *path*: its ``owners`` list ([] when none,
    or when nothing is published). Always the published file, never a draft,
    so a draft cannot grant itself ownership."""
    from tracebi.model.model_spec import ModelSpecError, read_model_doc

    published = next(iter(_published_model_files(path)), None)
    if published is None:
        return []
    try:
        owners = (read_model_doc(published) or {}).get("owners")
    except (ModelSpecError, OSError, AttributeError):
        return []
    return [o for o in owners if isinstance(o, str)] if isinstance(owners, list) else []


def check_may_publish_model(path: str, user: Optional[str], role: Optional[str]) -> None:
    """Raise :class:`NotAnOwner` unless *user* may publish model *path*: an
    admin (or an unauthenticated deployment, which resolves to admin) always
    may; otherwise the model must have no owners, or name *user*. Owners are
    sign-in names; the session carries no group membership, so groups are not
    matched. The one check HTTP and MCP both go through."""
    owners = model_owners(path)
    who = (user or "").removeprefix("mcp:").strip().casefold()
    if (role or "admin") == "admin" or not owners or who in {o.strip().casefold() for o in owners}:
        return
    raise NotAnOwner(
        f"model {path} is owned by {', '.join(owners)}; only they or an admin may "
        f"publish it. You can still draft it and run model_impact, then ask an owner to publish.")


class ImpactNotAccepted(DraftError):
    """A model publish that moves or breaks published reports, without
    ``accept_impact``. ``impact`` is the :func:`model_impact` result."""

    def __init__(self, message: str, impact: dict):
        super().__init__(message)
        self.impact = impact


def _walk(manifest: Optional[dict]) -> list:
    from tracebi.verify import _walk_sections
    return [s for s in _walk_sections((manifest or {}).get("sections") or [])
            if s.get("dataset_fingerprint")]


def _query_node(section: dict) -> Optional[dict]:
    """The recorded query of a section a query alone reproduces, else None
    (python-derived, ad hoc, or transformed after the query)."""
    from tracebi.model.dataset import last_query_node
    lineage = section.get("dataset_lineage") or []
    node = last_query_node(lineage)
    if section.get("verifiable") is False or node is None or lineage[-1] is not node:
        return None
    return node


def _models_a_report_reads(pkg: Path, manifest: Optional[dict]) -> set:
    """Model names a package binds in ``report.json``, plus the ones its last
    build actually queried."""
    names: set = set()
    try:
        data = json.loads((pkg / "report.json").read_text(encoding="utf-8")).get("data")
    except (OSError, ValueError, AttributeError):
        data = None
    for binding in (data if isinstance(data, dict) else {}).values():
        if isinstance(binding, dict) and isinstance(binding.get("model"), str):
            names.add(binding["model"])
    for section in _walk(manifest):
        node = _query_node(section)
        if node:
            names.add((node.get("metadata") or {}).get("model"))
    return names


def _run_recorded(node: dict, model):
    """(DataSet, None) or (None, error line) for a recorded query on *model*."""
    from tracebi.model.data_model import QuerySpec
    from tracebi.model.sql_calc import SqlQuery
    try:
        recorded = node["metadata"]["query_spec"]
        spec = (SqlQuery.from_dict(recorded) if "sql" in recorded
                else QuerySpec.from_dict(recorded))
        return model.execute(spec), None
    except Exception as exc:  # noqa: BLE001 — a query that no longer runs is the finding
        return None, f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}"


def _cell(frame, column: Optional[str]):
    """First-row value of *column* (or its last dotted part), JSON-safe."""
    if frame is None or column is None or len(frame) == 0:
        return None
    for c in (column, column.rsplit(".", 1)[-1]):
        if c in frame.columns:
            v = frame[c].iloc[0]
            return v.item() if hasattr(v, "item") else v
    return None


def _impact_of(report: str, manifest: Optional[dict], path: str, published, draft) -> dict:
    """One report's verdict: unchanged / moves / breaks / not_built / not_checkable."""
    if manifest is None:
        return {"report": report, "status": "not_built",
                "detail": "no last build, so there is nothing to compare; build it to check"}
    figures = manifest.get("figures") or []
    moved, broken, checked = [], [], 0
    for section in _walk(manifest):
        node = _query_node(section)
        if node is None or (node.get("metadata") or {}).get("model") != path:
            continue
        checked += 1
        binding = section.get("id") or section.get("title")
        was = _run_recorded(node, published)[0] if published is not None else None
        now, error = _run_recorded(node, draft)
        if now is None:
            if was is not None:         # it ran before this draft; the draft broke it
                broken.append({"binding": binding, "error": error})
            continue
        fp = now.fingerprint()
        if fp == section["dataset_fingerprint"] or (was is not None and fp == was.fingerprint()):
            continue            # as the last build had it, or moved by something other than this draft
        old = was.to_pandas() if was is not None else None
        new = now.to_pandas()
        moved.append({
            "binding": binding,
            "rows": [None if old is None else len(old), len(new)],
            "figures": [{"id": f.get("id"), "kind": f.get("kind"), "cell": f.get("cell"),
                         "old": _cell(old, f.get("cell")), "new": _cell(new, f.get("cell"))}
                        for f in figures if f.get("binding") == binding]})
    if broken:
        status, detail = "breaks", f"{len(broken)} recorded query(ies) no longer run"
    elif moved:
        status, detail = "moves", f"{len(moved)} binding(s) change"
    elif checked:
        status, detail = "unchanged", "every recorded query returns what the last build did"
    else:
        return {"report": report, "status": "not_checkable",
                "detail": "its last build holds no recorded query on this model to re-run"}
    return {"report": report, "status": status, "detail": detail,
            "moved": moved, "broken": broken}


def model_impact(owner: str, path: str, models: Optional[dict] = None) -> dict:
    """What publishing model draft *path* would do to the published reports.

    Every published report that reads the model has its last build's recorded
    queries re-run against the draft: ``unchanged``, ``moves`` (the figures,
    old and new) or ``breaks`` (the error). A report with no last build is
    ``not_built``; it is listed, never counted unchanged. ``needs_acceptance``
    is true when anything moves or breaks.
    """
    from tracebi.model.model_spec import load_model_spec
    from tracebi.report_paths import output_html, report_name_for_dir

    where = _exists(owner, "models", path)
    _validate_model_draft(where)
    published = (_load_models() if models is None else models).get(path)
    draft = load_model_spec(where, root=Path.cwd())
    base = os.getcwd()
    reports = []
    for _label, root in library_roots():
        for f in sorted(Path(base, root).rglob("report.json")):
            report = report_name_for_dir(str(f.parent), base)
            try:
                manifest = json.loads(Path(
                    output_html(os.path.join(base, "output"), report) + ".manifest.json"
                ).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = None
            if path in _models_a_report_reads(f.parent, manifest):
                reports.append(_impact_of(report, manifest, path, published, draft))
    summary: dict = {}
    for r in reports:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return {"owner": owner, "kind": "models", "path": path, "reports": reports,
            "summary": summary,
            "needs_acceptance": bool(summary.get("moves") or summary.get("breaks"))}


def _keep_previous(kind: str, path: str, current: Path, stamp: str) -> Optional[Path]:
    if not current.exists():
        return None
    keep = Path(".tracebi") / "history" / kind / path / stamp
    keep.parent.mkdir(parents=True, exist_ok=True)
    if current.is_dir():
        shutil.copytree(current, keep)
    else:
        keep.mkdir(exist_ok=True)
        shutil.copy2(current, keep / current.name)
    return keep


def _impact_line(r: dict) -> str:
    if r["status"] == "breaks":
        return f"{r['report']} breaks: " + "; ".join(
            f"{b['binding']}: {b['error']}" for b in r["broken"])
    return f"{r['report']} moves: " + ", ".join(
        f.get("id") or m["binding"] for m in r["moved"] for f in (m["figures"] or [m]))


def _destination(path: str, folder: Optional[str]) -> str:
    """The report name a draft publishes to: its own path, or its last part
    inside *folder* (a library path; it need not exist yet)."""
    if not folder:
        return path
    dest = f"{folder}/{path.rsplit('/', 1)[-1]}"
    if err := report_name_error(dest):
        raise DraftError(err)
    return dest


def checkable_problems(where: Path, manifest=None) -> list:
    """Why report package *where*, as just rendered to *manifest*, is not made
    only of numbers a query can re-run (empty when it is). A ``report.py``
    computes with Python; a section with ``verifiable: false`` or no single
    recorded query cannot be replayed by ``tracebi verify``. A figure a page
    script changes in the browser is not knowable here."""
    problems = []
    if (where / "report.py").exists():
        problems.append("report.py runs Python, so its numbers cannot be re-run from a query")
    figures = getattr(manifest, "figures", None) or []
    for section in _walk({"sections": getattr(manifest, "sections", [])}):
        if _query_node(section) is None:
            binding = section.get("id") or section.get("title")
            shown = [f["id"] for f in figures if f.get("binding") == binding and f.get("id")]
            why = ("computed by Python" if section.get("verifiable") is False
                   else "not a single re-runnable query")
            problems.append(f"binding {binding!r} is {why}"
                            + (f" (figures: {', '.join(shown)})" if shown else ""))
    return problems


def _prepare_report(where: Path, dest: str, models: dict) -> Path:
    """Everything a report must pass to be published (or requested) as *dest*;
    returns where it would land."""
    from tracebi import permissions

    def refuse(problems):
        raise DraftError(
            f"the folder of {dest} accepts only checkable reports (its _folder.yaml "
            f"says accepts: checkable), and this one is not: " + "; ".join(problems))

    root, rel = _report_target(dest)
    target = root / rel
    if (target / "report.py").exists():
        raise DraftError(
            f"{dest} is published with a report.py, which a draft cannot "
            f"replace: {_LAPTOP}")
    checkable = permissions.folder_accepts(dest) == "checkable"
    if checkable and (where / "report.py").exists():
        refuse(checkable_problems(where))
    manifest = _validate_report(where, models)
    if checkable and (problems := checkable_problems(where, manifest)):
        refuse(problems)
    return target


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def publish_draft(owner: str, kind: str, path: str, actor: Optional[str],
                  note: Optional[str] = None,
                  models: Optional[dict] = None,
                  accept_impact: bool = False,
                  folder: Optional[str] = None) -> dict:
    """Validate the draft, keep what it replaces, copy it into the library and
    record a ``publish`` run. The draft stays.

    A report goes to *folder* (default: its own path). With Publish on the
    destination it is published (``status: "published"``); with only Build
    there the result is a **request** (``status: "requested"``) for someone
    with Publish to approve (:func:`decide_request`). Under ``accepts:
    checkable`` a report that is not made of re-runnable numbers is refused
    either way.

    A model draft first has its :func:`model_impact` computed: when published
    reports would move or break, the publish is refused (:class:`ImpactNotAccepted`)
    unless *accept_impact* is true, and the accepted impact is recorded in the
    run's detail."""
    from tracebi import permissions

    kind = _kind(kind)
    where = _exists(owner, kind, path)
    if kind == "reports":
        dest = _destination(path, folder)
        level = permissions.granted_level(dest)
        if level < permissions.PUBLISH:
            if level < permissions.BUILD:
                _require_folder("publish", dest)
            return _request_publish(owner, path, dest, actor, note, where,
                                    _load_models() if models is None else models)
        return _publish_report(where, dest, owner, actor, note, models)
    if folder:
        raise DraftError("a model is not published into a folder: models/ holds them")
    check_may_publish_model(path, actor, get_actor()[1])
    _validate_model_draft(where)
    impact = model_impact(owner, path, models)
    accepted = None
    if impact["needs_acceptance"]:
        if not accept_impact:
            raise ImpactNotAccepted(
                "publishing this model would change published reports ("
                + "; ".join(_impact_line(r) for r in impact["reports"]
                            if r["status"] in ("moves", "breaks"))
                + "). Nothing was published. Review model_impact, then "
                "publish again with accept_impact=true to accept it"
                + (" (a break needs accepting too)"
                   if impact["summary"].get("breaks") else ""), impact)
        accepted = {"summary": impact["summary"],
                    "reports": [r for r in impact["reports"]
                                if r["status"] in ("moves", "breaks")]}
    target = _models_dir() / where.name
    if (_models_dir() / f"{path}.py").is_file():
        raise DraftError(
            f"models/{path}.py is a Python model of that name; a draft "
            f"cannot replace it: {_LAPTOP}")
    stamp = _stamp()
    kept = _keep_previous(kind, path, target, stamp)
    # Another declarative form of this name would clash with the new one.
    stale = [f for f in _published_model_files(path) if f != target]
    for old in stale:
        kept = _keep_previous(kind, path, old, stamp) or kept
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(where, target)
    for old in stale:
        old.unlink()
    return _record_publish(kind, path, owner, stamp, kept, [target.name], actor, note,
                           {"accepted_impact": accepted} if accepted else {}, {})


def _publish_report(src: Path, dest: str, owner: str, actor: Optional[str],
                    note: Optional[str], models: Optional[dict],
                    trail: Optional[dict] = None) -> dict:
    """Publish the report package in *src* as *dest*: the one path for a direct
    publish and for an approved request (whose story is *trail*)."""
    target = _prepare_report(src, dest, _load_models() if models is None else models)
    stamp = _stamp()
    kept = _keep_previous("reports", dest, target, stamp)
    target.mkdir(parents=True, exist_ok=True)
    files = _draft_files("reports", dest, src)
    for name in REPORT_FILES:               # a file the draft dropped goes too
        if name not in files and (target / name).is_file():
            (target / name).unlink()
    for name, f in files.items():
        shutil.copy2(f, target / name)
    return _record_publish("reports", dest, owner, stamp, kept, sorted(files), actor,
                           note, {}, trail or {})


def _history_log(kind: str, path: str) -> Path:
    return Path(".tracebi") / "history" / kind / path / "publishes.jsonl"


def publish_history(kind: str, path: str) -> list:
    """Every publish of *path*, oldest first: version, who published and when,
    the note, and for an approved request who asked, who approved and when.
    It sits beside the kept versions, in ``.tracebi/history/<kind>/<path>/``."""
    log = _history_log(_kind(kind), path)
    if not log.is_file():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def _record_publish(kind: str, path: str, owner: str, stamp: str, kept, published: list,
                    actor: Optional[str], note: Optional[str], extra: dict, trail: dict) -> dict:
    result = {"status": "published", "owner": owner, "kind": kind, "path": path,
              "version": stamp, "files": published, "previous": str(kept) if kept else None}
    now = datetime.now(timezone.utc).isoformat()
    story = {**trail, **({"approved_at": now} if "approved_by" in trail else {})}
    entry = {"version": stamp, "published_by": trail.get("requested_by", actor),
             "published_at": now, "note": note or "", "previous": result["previous"], **story}
    try:
        log = _history_log(kind, path)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError as exc:
        result["note"] = f"the publish history was not written: {exc}"

    from tracebi.state import record_run
    try:
        record_run(kind="publish", target=f"{kind}/{path}", status="ok",
                   finished=now, actor=actor, actor_role=get_actor()[1],
                   detail={"version": stamp, "note": note or "", **extra, **story})
    except Exception as exc:  # noqa: BLE001 — published is published; say the audit row is missing
        result["note"] = f"the publish was not recorded: {exc}"
    return result


# ── Publish requests ───────────────────────────────────────────────────────
# A person with Build (not Publish) on the destination folder asks; someone
# with Publish there decides. Each request is one file,
# ``drafts/_requests/<id>.json`` (an owner slug never starts with "_"), and it
# holds a snapshot of the draft's files: what the approver reviews is what is
# published, whatever the draft becomes meanwhile. The files survive a restart
# and live with the drafts.

_REQUEST_ID = re.compile(r"\d{8}T\d{6}-[0-9a-f]{6}")


def _requests_dir() -> Path:
    return drafts_root() / "_requests"


def _public_request(req: dict) -> dict:
    return {k: v for k, v in req.items() if k != "files"}


def _my_slug() -> str:
    return slug_owner((get_actor()[0] or "").removeprefix("mcp:"))


def _request_publish(owner: str, path: str, dest: str, actor: Optional[str],
                     note: Optional[str], where: Path, models: dict) -> dict:
    _prepare_report(where, dest, models)         # the same refusals as a publish
    now = datetime.now(timezone.utc)
    req = {"id": f"{now:%Y%m%dT%H%M%S}-{os.urandom(3).hex()}", "status": "pending",
           "owner": owner, "kind": "reports", "path": path, "destination": dest,
           "requested_by": actor, "requested_at": now.isoformat(), "note": note or "",
           "files": {n: _read_text(p) for n, p in _draft_files("reports", path, where).items()}}
    _write(_requests_dir() / f"{req['id']}.json", json.dumps(req, indent=1))
    return {"status": "requested", "request": _public_request(req)}


def _load_request(request_id: str) -> dict:
    """The request, or not-found when there is none or it is not the person's
    to see (their own, or into a folder where they hold Publish)."""
    from tracebi import permissions

    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise DraftNotFound(f"no publish request {request_id!r}")
    f = _requests_dir() / f"{request_id}.json"
    if not f.is_file():
        raise DraftNotFound(f"no publish request {request_id!r}")
    req = json.loads(f.read_text(encoding="utf-8"))
    if (req["owner"] != _my_slug()
            and permissions.granted_level(req["destination"]) < permissions.PUBLISH):
        raise DraftNotFound(f"no publish request {request_id!r}")
    return req


def list_requests(status: Optional[str] = None) -> list:
    """The publish requests the current person may see, newest first: their
    own, and those into folders where they hold Publish."""
    from tracebi import permissions

    me, found = _my_slug(), []
    names = sorted(_requests_dir().glob("*.json"), reverse=True) if _requests_dir().is_dir() else []
    for f in names:
        try:
            req = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if status and req.get("status") != status:
            continue
        decides = permissions.granted_level(req["destination"]) >= permissions.PUBLISH
        if req["owner"] == me or decides:
            found.append({**_public_request(req), "can_decide": decides})
    return found


def decide_request(request_id: str, approve: bool, actor: Optional[str],
                   note: Optional[str] = None, models: Optional[dict] = None) -> dict:
    """Approve (publish the snapshot exactly as a direct publish would, and
    record who approved and when) or reject (a note says why) a pending
    request. It needs Publish on the destination *now*, not when it was asked,
    so a requester holding only Build cannot decide their own."""
    req = _load_request(request_id)
    _require_folder("publish", req["destination"])
    if req["status"] != "pending":
        raise DraftError(f"request {request_id} is already {req['status']}")
    if approve:
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / req["path"].rsplit("/", 1)[-1]
            for name, text in req["files"].items():
                _write(snap / name, text)
            published = _publish_report(
                snap, req["destination"], req["owner"], actor, req["note"], models,
                {"request_id": req["id"], "requested_by": req["requested_by"],
                 "requested_at": req["requested_at"], "approved_by": actor})
        req["version"] = published["version"]
    elif not (note or "").strip():
        raise DraftError("a rejection needs a note saying why")
    req.update(status="approved" if approve else "rejected", decided_by=actor,
               decided_at=datetime.now(timezone.utc).isoformat(), decision_note=note or "")
    _write(_requests_dir() / f"{request_id}.json", json.dumps(req, indent=1))
    return {"status": req["status"], "request": _public_request(req)}
