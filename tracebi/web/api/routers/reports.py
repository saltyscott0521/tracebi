import os
import tempfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

from tracebi.web.api.errors import error_detail as _error_detail
from tracebi.web.api.lineage_graph import lineage_to_graph as _lineage_to_graph
from tracebi.web.api.registry import registry
from tracebi.web.api.run_store import run_store

router = APIRouter(prefix="/reports", tags=["reports"])


def _safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "._- ") or "report"


def _run_report_or_502(name: str):
    if name not in {r["name"] for r in registry.list_reports()}:
        raise HTTPException(status_code=404, detail=f"Report '{name}' not found")
    try:
        return registry.run_report(name)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=_error_detail("Report factory failed", exc)
        )

@router.get("")
def list_reports():
    """List all registered reports."""
    return registry.list_reports()


#: Web renders of artifact-backed reports, cached per name: the full
#: TemplatePackage render is real work (queries + embedding), and the UI
#: polls. Keyed on the package files' max mtime plus a short TTL so a
#: warehouse-only change still shows up promptly. Persist nothing to disk.
_ARTIFACT_CACHE: dict = {}
_ARTIFACT_TTL_S = 5.0


def _writable_output_html(name: str):
    """``output/<name>.html`` when that directory can be written, else None.

    Same names ``tracebi report build`` uses. A probe file distinguishes
    "the disk refused" from a later render error, which must still raise.
    """
    out_dir = os.path.join(os.getcwd(), "output")
    probe = os.path.join(out_dir, ".tracebi-write-probe")
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("")
        os.unlink(probe)
    except OSError:
        return None
    return os.path.join(out_dir, f"{_safe_filename(name)}.html")


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

    pkg_dir = registry.report_package_dir(name)
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
        # A read-only filesystem (the demo topology) still renders. The
        # response carries the manifest; it says the file was not kept.
        fd, tmp = tempfile.mkstemp(suffix=".html")
        os.close(fd)
        try:
            manifest = TemplatePackage(pkg_dir).render(
                models, tmp, save_manifest=False)
            with open(tmp, encoding="utf-8") as f:
                html = f.read()
        finally:
            os.unlink(tmp)
        receipt = {"retained": False}

    payload = {
        "name": name,
        "html": html,
        "manifest": manifest.to_dict(),
        **receipt,
    }
    _ARTIFACT_CACHE[name] = {"mtime": mtime, "at": now, "payload": payload}
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


def _package_or_404(name: str):
    if name not in {r["name"] for r in registry.list_reports()}:
        raise HTTPException(status_code=404, detail=f"Report '{name}' not found")
    pkg_dir = registry.report_package_dir(name)
    if not pkg_dir:
        raise HTTPException(status_code=422, detail=_NO_PACKAGE.format(name=name))
    return pkg_dir


@router.post("/{name}/selection")
def report_selection(name: str, payload: dict):
    """Recompute an opted-in report under a selection.

    Computes and returns stamps. Does not write the warehouse or the package.
    Auth is the report-run rule: this is a POST, so analyst when enforcement
    is on.
    """
    from tracebi.reports.selection import evaluate_selection
    from tracebi.reports.template_package import TemplatePackage

    pkg_dir = _package_or_404(name)
    filters = (payload or {}).get("filters") or {}
    if not isinstance(filters, dict):
        raise HTTPException(status_code=400, detail="filters must be an object")
    try:
        package = TemplatePackage(pkg_dir)
        if package.selection is None:
            raise ValueError(
                f"Report '{name}' has no selection block. Controls on this "
                f"report subset stamped rows; they do not recompute measures."
            )
        models = _selection_models(package.selection["model"])
        return evaluate_selection(package, models, filters)
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


@router.post("/{name}/selection/keep")
def keep_report_selection(name: str, payload: dict):
    """Write the cut into the package, rebuild, and verify.

    The authored selection becomes the filters on screen. This writes
    ``report.json`` and the artifact. It does not write the warehouse.
    """
    from tracebi.reports.selection import keep_cut

    pkg_dir = _package_or_404(name)
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


@router.post("/{name}/run")
def run_report(name: str):
    """
    Run a registered report and return the rendered HTML + manifest.

    The HTML is self-contained and can be rendered in an iframe with srcdoc.
    It is the real artifact render (embedded data, figure claims), so what
    the browser shows is what ``verify --file`` can check.
    """
    try:
        return _artifact_payload_or_refuse(name)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("Render failed", exc))


def _render_report_payload(name: str) -> dict:
    """Run + render a report; shared by the sync and background paths."""
    return _artifact_payload_or_refuse(name)


@router.post("/{name}/runs", status_code=202)
def start_report_run(name: str):
    """
    Start a report run in the background.

    Returns a ``run_id`` immediately; poll ``GET /reports/{name}/runs/{run_id}``
    until ``status`` is ``succeeded`` (payload in ``result``) or ``failed``
    (structured detail in ``error``).
    """
    if name not in {r["name"] for r in registry.list_reports()}:
        raise HTTPException(status_code=404, detail=f"Report '{name}' not found")
    record = run_store.start("report", name, lambda: _render_report_payload(name))
    return {
        "run_id":     record["run_id"],
        "status":     record["status"],
        "started_at": record["started_at"],
    }


@router.get("/{name}/runs")
def report_run_history(name: str, limit: int = 10):
    """Recent background runs for this report, newest first (no payloads)."""
    return run_store.list_for("report", name, limit)


@router.get("/{name}/runs/{run_id}")
def report_run_status(name: str, run_id: str):
    """Status + result of one background run."""
    record = run_store.get(run_id)
    if record is None or record["kind"] != "report" or record["name"] != name:
        raise HTTPException(
            status_code=404, detail=f"Run '{run_id}' not found for report '{name}'"
        )
    return record


@router.get("/{name}/download")
def download_report(name: str, format: str = "xlsx"):
    """
    Run a report and download the rendered file.

    Formats: ``xlsx`` (Excel via openpyxl) or ``html`` (self-contained page).
    """
    if format not in ("xlsx", "html"):
        raise HTTPException(
            status_code=400, detail=f"Unsupported format '{format}'. Use xlsx or html."
        )
    fname = _safe_filename(name)

    # The HTML download is the artifact itself — the same bytes ``verify
    # --file`` checks — so it goes through the one render path.
    if format == "html":
        return HTMLResponse(
            _artifact_payload_or_refuse(name)["html"],
            headers={
                "Content-Disposition": f'attachment; filename="{fname}.html"',
            },
        )

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


@router.get("/{name}/mermaid")
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


@router.get("/{name}/lineage")
def report_lineage(name: str):
    """
    Run a report and return its full data lineage as a React Flow graph.

    Returns nodes and edges ready to pass directly to <ReactFlow>.
    """
    report = _run_report_or_502(name)

    seen_ids: set[int] = set()
    all_nodes: list[dict] = []
    section_lineages: list[dict] = []

    for section in report.data_sections():
        ds = getattr(section, "dataset", None)
        if ds is None:
            continue
        nodes_for_section = []
        for node in ds.lineage:
            nid = id(node)
            if nid not in seen_ids:
                seen_ids.add(nid)
                all_nodes.append(node.to_dict())
            nodes_for_section.append(node.to_dict())
        section_lineages.append({
            "section_title": section.title,
            "dataset_name": ds.name,
            "graph": _lineage_to_graph(nodes_for_section),
        })

    return {
        "report": name,
        "combined_graph": _lineage_to_graph(all_nodes),
        "sections": section_lineages,
    }
