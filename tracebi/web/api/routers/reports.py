import json
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

from tracebi.web.api.errors import error_detail as _error_detail
from tracebi.web.api.registry import registry
from tracebi.web.api.run_store import run_store

router = APIRouter(prefix="/reports", tags=["reports"])


def _safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._- ") or "report"


def _output_html(name: str) -> str:
    """``output/<name>.html``, keeping a foldered report's folders
    (``finance/weekly`` → ``output/finance/weekly.html``), each part made
    safe for a filename."""
    from tracebi.report_paths import output_html
    return output_html(_output_dir(),
                       "/".join(_safe_filename(p) for p in name.split("/")))


def _opened_report(name: str, purpose: str):
    """Resolve *name* through the one report-read seam."""
    from tracebi.report_paths import open_report
    return open_report(name, purpose=purpose, registry=registry)


def _require_registered(name: str, purpose: str):
    opened = _opened_report(name, purpose)
    if not opened.registered:
        raise HTTPException(status_code=404, detail=f"Report '{name}' not found")
    return opened


def _run_report_or_502(name: str):
    _require_registered(name, "view")
    try:
        return registry.run_report(name)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=_error_detail("Report factory failed", exc)
        )

def _iso_mtime(stamp: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def _newer_mtime(*paths) -> str | None:
    stamps = []
    for path in paths:
        try:
            stamps.append(path.stat().st_mtime)
        except OSError:
            continue
    if not stamps:
        return None
    return _iso_mtime(max(stamps))


def _schedule_of(report_json) -> dict | None:
    """Cron and timezone from a package ``report.json``, or None.

    A broken file or a schedule that is not an object does not fail the
    list. Only those two fields are returned — there is no owner column.
    """
    try:
        raw = json.loads(report_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    block = raw.get("schedule") if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        return None
    cron = block.get("cron")
    if not isinstance(cron, str) or not cron.strip():
        return None
    tz = block.get("timezone")
    return {"cron": cron, "timezone": tz if isinstance(tz, str) and tz else None}


def _models_named(doc) -> list[str]:
    """Every model a report's data bindings read, in ``report.json`` or a spec.

    A binding is ``{"model": ..., "query": ...}`` wherever it sits. This is
    what a report belongs to; its folder is only a convention.
    """
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("model"), str) and "query" in node:
                found.add(node["model"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(doc)
    return sorted(found)


def _library_package(name: str) -> tuple[dict | None, str | None, list[str]]:
    """Schedule, last-change time and the models read, for one report.

    Via :func:`open_report`. An on-disk package uses ``report.json`` and
    ``template.html``. A spec uses the spec file: its compiled package is a
    temp dir rewritten at discovery, so that mtime is not a change the author
    made.
    """
    opened = _opened_report(name, "view")
    if opened.package_dir is not None:
        manifest = opened.package_dir / "report.json"
        return (
            _schedule_of(manifest),
            _newer_mtime(manifest, opened.package_dir / "template.html"),
            _models_in(manifest),
        )
    if opened.spec_path is not None and opened.spec_path.is_file():
        return None, _newer_mtime(opened.spec_path), _models_in(opened.spec_path)
    # Registered by an app module rather than found under reports/: the
    # registry knows its package (a spec's is the compiled one).
    if opened.registry_package_dir:
        return None, None, _models_in(Path(opened.registry_package_dir) / "report.json")
    return None, None, []


def _models_in(path) -> list[str]:
    try:
        named = _models_named(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return []
    return sorted({_listed_name(n) for n in named})


def _listed_name(name: str) -> str:
    """The name the app lists a model under, for a name a binding used.

    A binding may name a model by its file stem (``wealth_model``, how the
    model registry finds it) or by the name it declares (``WealthModel``, how
    the app lists it); the renderer accepts both. The app shows declared
    names, so that is the one a report belongs to.
    """
    if registry.get_model(name) is not None:
        return name
    try:
        from tracebi.model_registry import get_model
        declared = getattr(get_model(name), "name", None)
    except Exception:  # noqa: BLE001 — an unloadable model keeps the name it was given
        return name
    return declared if declared and registry.get_model(declared) is not None else name


def _library_runs() -> tuple[dict, dict]:
    """Newest schedule run and report-build count, keyed by report name.

    A store that cannot be opened leaves both empty: the list still loads.
    This does not read the warehouse.
    """
    try:
        from tracebi.state import count_by_target, install_extra, newest_by_target
        with install_extra("web"):
            newest = newest_by_target("schedule")
            counts = count_by_target("report_build")
    except Exception:  # noqa: BLE001 — columns stay blank; the list still loads
        return {}, {}
    last = {}
    for target, row in newest.items():
        last[target] = {
            "status": row.get("status"),
            "time": row.get("finished") or row.get("started"),
        }
    return last, counts


@router.get("")
def list_reports():
    """Registered reports, plus the library columns for the Reports list."""
    last_runs, build_counts = _library_runs()
    out = []
    for item in registry.list_reports():
        schedule, last_change, models = _library_package(item["name"])
        out.append({
            **item,
            "schedule": schedule,
            "last_run": last_runs.get(item["name"]),
            "past_builds": build_counts.get(item["name"], 0),
            "last_change": last_change,
            # What it belongs to: the models its data bindings read.
            "models": models,
        })
    return out


#: Web renders of artifact-backed reports, cached per name: the full
#: TemplatePackage render is real work (queries + embedding), and the UI
#: polls. Keyed on the package files' max mtime plus a short TTL so a
#: warehouse-only change still shows up promptly. Persist nothing to disk.
_ARTIFACT_CACHE: dict = {}
_ARTIFACT_TTL_S = 5.0


def _output_dir() -> str:
    """Where a web render keeps ``output/<name>.html``.

    One function so tests can send builds somewhere other than the repo
    without patching ``os.getcwd`` (other code still resolves the project
    from the working directory).
    """
    return os.path.join(os.getcwd(), "output")


def _writable_output_html(name: str):
    """``output/<name>.html`` when that directory can be written, else None.

    Same names ``tracebi report build`` uses. A probe file distinguishes
    "the disk refused" from a later render error, which must still raise.
    """
    path = _output_html(name)
    out_dir = os.path.dirname(path)
    probe = os.path.join(out_dir, ".tracebi-write-probe")
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.unlink(probe)
    except OSError:
        return None
    return path


def _artifact_payload(name: str):
    """The REAL artifact render for a package-backed report, or None.

    Web parity (architecture v2 §2.3): a report backed by a template
    package must serve the same self-contained page + schema-2 manifest the
    build step produces — embedded fingerprinted data included — so
    web-rendered HTML passes ``verify --file``. The carrier-report path
    below remains for spec and code-factory reports.
    """
    import os
    import tempfile
    import time

    pkg_dir = _opened_report(name, "view").registry_package_dir
    if not pkg_dir:
        return None

    try:
        mtime = max(
            os.path.getmtime(os.path.join(pkg_dir, f))
            for f in os.listdir(pkg_dir)
        )
    except (OSError, ValueError):
        mtime = 0.0
    cached = _ARTIFACT_CACHE.get(name)
    now = time.monotonic()
    if cached and cached["mtime"] == mtime and now - cached["at"] < _ARTIFACT_TTL_S:
        return cached["payload"]

    from tracebi.model_registry import get_model, list_models
    from tracebi.reports.template_package import TemplatePackage

    models = {}
    for mname in list_models():
        try:
            m = get_model(mname)
        except Exception:  # noqa: BLE001 — a broken model is that model's problem
            continue
        models[mname] = m
        models[getattr(m, "name", mname)] = m

    retained_path = _writable_output_html(name)
    if retained_path is not None:
        manifest = TemplatePackage(pkg_dir).render(
            models, retained_path, save_manifest=True)
        with open(retained_path, encoding="utf-8") as f:
            html = f.read()
        receipt = {
            "retained": True,
            "html_path": retained_path,
            "manifest_path": retained_path + ".manifest.json",
        }
    else:
        # output/ is not writable. Keep the page under the system temp dir
        # and record that path, so another worker can still open it.
        root = os.path.join(tempfile.gettempdir(), "tracebi-builds")
        os.makedirs(root, exist_ok=True)
        tmp = os.path.join(root, _safe_filename(name.replace("/", "_")) + ".html")
        manifest = TemplatePackage(pkg_dir).render(
            models, tmp, save_manifest=True)
        with open(tmp, encoding="utf-8") as f:
            html = f.read()
        receipt = {
            "retained": False,
            "html_path": tmp,
            "manifest_path": tmp + ".manifest.json",
        }

    payload = {
        "name": name,
        "html": html,
        "manifest": manifest.to_dict(),
        **receipt,
    }
    _ARTIFACT_CACHE[name] = {"mtime": mtime, "at": now, "payload": payload}
    from tracebi.state import install_extra, record_report_build
    with install_extra("web"):
        record_report_build(
            name,
            payload.get("html_path"),
            manifest_path=payload.get("manifest_path"),
        )
    return payload


#: Every served report is built from its own package — the analyst's
#: ``template.html`` + ``style.css`` + ``script.js``, or a ``.json`` spec
#: compiled into exactly that. There is no second renderer: the old fallback
#: produced a page with no runtime, no receipt drawer, no figure claims and a
#: schema-1 manifest, which reads as a report while carrying materially less
#: of one. A report with no package is refused here rather than served weaker.
_NO_PACKAGE = (
    "Report '{name}' has no report package, so there is nothing to render. "
    "A report is a directory reports/{name}/ (report.json + template.html, "
    "plus optional style.css / script.js), or a reports/{name}.json spec that "
    "compiles into one. Scaffold it with: tracebi new-report \"{name}\"."
)


def _artifact_payload_or_refuse(name: str) -> dict:
    """The one render path: the package artifact, or a clear refusal."""
    payload = _artifact_payload(name)
    if payload is None:
        raise HTTPException(status_code=422,
                            detail=_NO_PACKAGE.format(name=name))
    return payload


def _selection_models(model_name: str) -> dict:
    """The one model a selection recomputes, keyed both ways a binding names it."""
    from tracebi.model_registry import get_model

    model = get_model(model_name)
    return {model_name: model, getattr(model, "name", model_name): model}


def _package_or_404(name: str, purpose: str = "view"):
    pkg_dir = _require_registered(name, purpose).registry_package_dir
    if not pkg_dir:
        raise HTTPException(status_code=422, detail=_NO_PACKAGE.format(name=name))
    return pkg_dir


@router.post("/{name:path}/selection")
def report_selection(name: str, payload: dict):
    """Recompute an opted-in report under a selection.

    Computes and returns stamps. Does not write the warehouse. A question
    that names one declared dimension the report does not already cut writes
    that binding into the package, rebuilds, and verifies. Pins are read
    before that write. Auth is the report-run rule: this is a POST, so
    analyst when enforcement is on.
    """
    from tracebi.reports.selection import (
        answer_question, evaluate_selection, open_pins,
    )
    from tracebi.reports.template_package import TemplatePackage

    pkg_dir = _package_or_404(name)
    payload = payload or {}
    question = payload.get("question")
    filters = payload.get("filters")
    if filters is not None and not isinstance(filters, dict):
        raise HTTPException(status_code=400, detail="filters must be an object")
    if question is not None and not isinstance(question, str):
        raise HTTPException(status_code=400, detail="question must be a string")
    try:
        package = TemplatePackage(pkg_dir)
        if package.selection is None:
            raise ValueError(
                f"Report '{name}' has no selection block. Controls on this "
                f"report subset stamped rows; they do not recompute measures."
            )
        models = _selection_models(package.selection["model"])
        if isinstance(question, str) and question.strip():
            if filters:
                raise HTTPException(
                    status_code=400,
                    detail="Send a question or filters, not both.",
                )
            result = answer_question(
                pkg_dir, models, question,
                output_html=_writable_output_html(name),
                project_root=os.getcwd(),
            )
            if result.get("added_binding"):
                _ARTIFACT_CACHE.pop(name, None)
            return result
        if not filters:
            filters = {}
        result = evaluate_selection(package, models, filters)
        result["pins"] = open_pins(os.getcwd(), package.package_id)
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=_error_detail("Selection failed", exc)
        )


@router.post("/{name:path}/selection/keep")
def keep_report_selection(name: str, payload: dict):
    """Write the cut into the package, rebuild, and verify.

    The authored selection becomes the filters on screen. This writes
    ``report.json`` and the artifact. It does not write the warehouse.
    """
    from tracebi.reports.selection import keep_cut

    pkg_dir = _package_or_404(name, "manage")
    filters = (payload or {}).get("filters") or {}
    if not isinstance(filters, dict):
        raise HTTPException(status_code=400, detail="filters must be an object")
    try:
        from tracebi.reports.template_package import TemplatePackage
        package = TemplatePackage(pkg_dir)
        if package.selection is None:
            raise ValueError(
                f"Report '{name}' has no selection block to keep a cut in."
            )
        models = _selection_models(package.selection["model"])
        output = _writable_output_html(name)
        if output is None:
            raise HTTPException(
                status_code=500,
                detail="Cannot keep this cut: output/ is not writable.",
            )
        result = keep_cut(pkg_dir, filters, models, output)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=_error_detail("Keep failed", exc)
        )
    _ARTIFACT_CACHE.pop(name, None)
    return result


def _read_build(name: str, path: str, manifest_path: str, *, retained: bool) -> dict:
    with open(path, encoding="utf-8") as fh:
        html = fh.read()
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    return {
        "name": name,
        "html": html,
        "manifest": manifest,
        "retained": retained,
        "built": True,
        "html_path": path,
        "manifest_path": manifest_path,
    }


def _stored_build(name: str):
    """The newest page-producing run whose file is still on disk."""
    from tracebi.state import install_extra, latest_output

    with install_extra("web"):
        row = latest_output(name)
    if not row:
        return None
    path = row.get("output_path")
    if not path or not os.path.isfile(path):
        return None
    detail = row.get("detail") or {}
    if not isinstance(detail, dict):
        detail = {}
    manifest_path = detail.get("manifest_path") or (path + ".manifest.json")
    if not os.path.isfile(manifest_path):
        return None
    return _read_build(name, path, manifest_path, retained=bool(detail.get("retained")))


def _last_build(name: str) -> dict:
    """The last build of *name*: ``output/<name>.html`` on disk, else the
    path recorded in the run store, else — when the report has never been
    built — one build now, kept for everyone after.

    Opening and downloading read this; they never re-query on their own.
    Fresh data comes from a schedule or Rebuild.
    """
    _package_or_404(name)
    path = _output_html(name)
    manifest_path = path + ".manifest.json"
    if os.path.isfile(path) and os.path.isfile(manifest_path):
        return _read_build(name, path, manifest_path, retained=True)
    stored = _stored_build(name)
    if stored is not None:
        return stored
    try:
        return {**_artifact_payload_or_refuse(name), "built": True}
    except Exception:  # noqa: BLE001 — a failed first build is a Run away, not a 500
        raise HTTPException(
            status_code=404, detail=f"No built artifact for '{name}'.",
        ) from None


@router.get("/{name:path}/built")
def built_report(name: str):
    """The last build: on disk, in the run store, or built once if there is none.

    Report opens this. Rebuild is a separate action.
    """
    return _last_build(name)


@router.post("/{name:path}/run")
def run_report(name: str):
    """
    Run a registered report and return the rendered HTML + manifest.

    The HTML is self-contained and can be rendered in an iframe with srcdoc.
    It is the real artifact render (embedded data, figure claims), so what
    the browser shows is what ``verify --file`` can check.
    """
    # Outside the render try: a refusal from the read seam must not become
    # a generic 500.
    _opened_report(name, "view")
    try:
        return _artifact_payload_or_refuse(name)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("Render failed", exc))


def _render_report_payload(name: str) -> dict:
    """Run + render a report; shared by the sync and background paths."""
    return _artifact_payload_or_refuse(name)


@router.post("/{name:path}/runs", status_code=202)
def start_report_run(name: str):
    """
    Start a report run in the background.

    Returns a ``run_id`` immediately; poll ``GET /reports/{name}/runs/{run_id}``
    until ``status`` is ``succeeded`` (payload in ``result``) or ``failed``
    (structured detail in ``error``).
    """
    _require_registered(name, "view")
    record = run_store.start(
        "background_run", name, lambda: _render_report_payload(name))
    return {
        "run_id":     record["run_id"],
        "status":     record["status"],
        "started_at": record["started_at"],
    }


@router.get("/{name:path}/runs")
def report_run_history(name: str, limit: int = 10):
    """Recent background runs for this report, newest first (no payloads)."""
    _opened_report(name, "view")
    return run_store.list_for("background_run", name, limit)


@router.get("/{name:path}/runs/{run_id}")
def report_run_status(name: str, run_id: str):
    """Status + result of one background run."""
    _opened_report(name, "view")
    record = run_store.get(run_id)
    if record is None or record["kind"] != "background_run" or record["name"] != name:
        raise HTTPException(
            status_code=404, detail=f"Run '{run_id}' not found for report '{name}'"
        )
    return record


def _pdf_of_last_build(name: str, fname: str):
    """Print the last build to PDF. A missing Playwright is a structured error."""
    built = _last_build(name)
    html_path = built.get("html_path")
    tmp_html = None
    if not html_path or not os.path.isfile(html_path):
        fd, tmp_html = tempfile.mkstemp(suffix=".html")
        os.close(fd)
        with open(tmp_html, "w", encoding="utf-8") as fh:
            fh.write(built["html"])
        html_path = tmp_html
    fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        from tracebi.reports.pdf import print_pdf
        print_pdf(html_path, pdf_path)
    except (ImportError, RuntimeError) as exc:
        os.unlink(pdf_path)
        raise HTTPException(
            status_code=500,
            detail=_error_detail("PDF export unavailable", exc),
        ) from exc
    except Exception as exc:
        os.unlink(pdf_path)
        raise HTTPException(
            status_code=500, detail=_error_detail("PDF export failed", exc)
        ) from exc
    finally:
        if tmp_html:
            os.unlink(tmp_html)
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{fname}.pdf",
        background=BackgroundTask(os.unlink, pdf_path),
    )


@router.get("/{name:path}/download")
def download_report(name: str, format: str = "xlsx"):
    """
    Run a report and download the rendered file.

    Formats: ``xlsx`` (Excel via openpyxl), ``html`` (self-contained page),
    or ``pdf`` (a print of that page). HTML and PDF are the last build.
    """
    if format not in ("xlsx", "html", "pdf"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{format}'. Use xlsx, html, or pdf.",
        )
    fname = _safe_filename(name.rsplit("/", 1)[-1])  # the report's own name, no folders

    # The HTML download is the last build — the file the reader is looking
    # at, the same bytes ``verify --file`` checks — never a fresh render.
    # PDF is a print of that same file. Neither re-queries on its own.
    if format == "html":
        return HTMLResponse(
            _last_build(name)["html"],
            headers={
                "Content-Disposition": f'attachment; filename="{fname}.html"',
            },
        )
    if format == "pdf":
        return _pdf_of_last_build(name, fname)

    report = _run_report_or_502(name)

    try:
        from tracebi.reports.excel_renderer import ExcelRenderer
        fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        ExcelRenderer().render(report, tmp_path, save_manifest=False)
        return FileResponse(
            tmp_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=f"{fname}.xlsx",
            background=BackgroundTask(os.unlink, tmp_path),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("Render failed", exc))


#: The files that define a report package, in reading order. Anything else in
#: the package (assets/, notes) is listed by name only.
_PACKAGE_SOURCE_FILES = ("report.json", "template.html", "style.css", "script.js", "report.py")
_SOURCE_LANG = {".json": "json", ".html": "html", ".css": "css", ".js": "javascript", ".py": "python"}
_SOURCE_MAX_BYTES = 256 * 1024


def _display_path(path: str, reports_dir: str) -> str:
    """A path the reader recognises: relative to the working directory when
    the file is inside it, else relative to the reports folder's parent."""
    cwd = os.getcwd()
    if os.path.commonpath([os.path.abspath(path), cwd]) == cwd:
        return os.path.relpath(path, cwd)
    return os.path.relpath(path, os.path.dirname(reports_dir))


def _source_file(path: str, reports_dir: str) -> dict:
    with open(path, "rb") as fh:
        raw = fh.read(_SOURCE_MAX_BYTES + 1)
    return {
        "path": _display_path(path, reports_dir),
        "language": _SOURCE_LANG.get(os.path.splitext(path)[1], "text"),
        "content": raw[:_SOURCE_MAX_BYTES].decode("utf-8", errors="replace"),
        "truncated": len(raw) > _SOURCE_MAX_BYTES,
    }


@router.get("/{name:path}/source")
def report_source(name: str):
    """The files that define a report: the spec, or the package's files.

    Read-only, and limited to the files discovery registered for this report,
    so a request can never name an arbitrary path.
    """
    src = _require_registered(name, "source").source
    if not src:
        return {"form": "code", "files": [], "other_files": [],
                "hint": "Registered in Python code (a report factory), not from reports/."}

    files, other = [], []
    if src["form"] == "spec":
        reports_dir = os.path.dirname(src["path"])
        # Extras are the spec's theme/script siblings: basenames only, so a spec
        # can't point this view outside its folder.
        for p in [src["path"], *(os.path.join(reports_dir, os.path.basename(e))
                                  for e in src["extras"])]:
            if os.path.isfile(p):
                files.append(_source_file(p, reports_dir))
        hint = (f"A JSON spec in the default style. To give it a custom layout and look, "
                f"run: tracebi migrate spec {_display_path(src['path'], reports_dir)}")
    else:
        pkg = src["path"]
        reports_dir = os.path.dirname(pkg)
        for fname in _PACKAGE_SOURCE_FILES:
            p = os.path.join(pkg, fname)
            if os.path.isfile(p):
                files.append(_source_file(p, reports_dir))
        for root, dirs, fnames in os.walk(pkg):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for fname in sorted(fnames):
                rel = os.path.relpath(os.path.join(root, fname), pkg)
                if rel not in _PACKAGE_SOURCE_FILES:
                    other.append(rel)
        hint = f"A custom report package. Edit it with a live preview: tracebi dev {name}"
    return {"form": src["form"], "files": files, "other_files": other, "hint": hint}


@router.get("/{name:path}/mermaid")
def report_mermaid(name: str):
    """Return a Mermaid flowchart string for the report's combined lineage."""
    report = _run_report_or_502(name)
    try:
        from tracebi.lineage.diagram import LineageDiagram
        mermaid = LineageDiagram(report).to_mermaid()
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=_error_detail("Lineage diagram failed", exc)
        )
    return {"mermaid": mermaid}


@router.get("/{name:path}/lineage")
def report_lineage(name: str):
    """
    A report's lineage as a layered flow — transform → stored tables → model →
    queries → figures — read from the last build's receipt, so it shows what
    the reader was shown and never re-runs the report.
    """
    from tracebi.reports.lineage_flow import report_flow

    def storage_of(connector_name: str):
        connector = registry.get_connector(connector_name)
        return connector.storage() if connector else None

    built = _last_build(name.strip("/"))
    manifest = built["manifest"]
    return {
        "report": name,
        "built_at": manifest.get("rendered_at"),
        "flow": report_flow(manifest, storage_of=storage_of),
    }


# ── Share link ──────────────────────────────────────────────────────────────
# ``/r/<name>`` is the report itself as a full page: the last build, the same
# bytes the HTML download carries, served inline so a phone's browser runs the
# charts and calculators. It sits outside /api so the link reads like a page.
# Access follows the server's auth like every other GET: open on a server with
# no auth configured (a public demo), a viewer login otherwise. The page's own
# CSP has connect-src 'none', so its scripts cannot call this API.

share_router = APIRouter(tags=["reports"])


@share_router.get("/r/{name:path}", response_class=HTMLResponse)
def share_report(name: str):
    return HTMLResponse(_last_build(name.strip("/"))["html"])
