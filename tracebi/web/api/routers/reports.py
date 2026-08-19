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

    fd, tmp = tempfile.mkstemp(suffix=".html")
    os.close(fd)
    try:
        manifest = TemplatePackage(pkg_dir).render(
            models, tmp, save_manifest=False)
        with open(tmp, encoding="utf-8") as f:
            html = f.read()
    finally:
        os.unlink(tmp)

    payload = {"name": name, "html": html, "manifest": manifest.to_dict()}
    _ARTIFACT_CACHE[name] = {"mtime": mtime, "at": now, "payload": payload}
    return payload


@router.post("/{name}/run")
def run_report(name: str):
    """
    Run a registered report and return the rendered HTML + manifest.

    The HTML is self-contained and can be rendered in an iframe with srcdoc.
    An artifact-backed report serves the real artifact render (embedded
    data, figure claims), so what the browser shows is what ``verify
    --file`` can check.
    """
    try:
        payload = _artifact_payload(name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("Render failed", exc))
    if payload is not None:
        return payload

    report = _run_report_or_502(name)

    try:
        from tracebi.reports.html_renderer import HTMLRenderer
        html = HTMLRenderer.for_project().to_html(report)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("Render failed", exc))

    manifest = report.build_manifest(format="html", output_path="(in-memory)")

    return {
        "name": name,
        "html": html,
        "manifest": manifest.to_dict(),
    }


def _render_report_payload(name: str) -> dict:
    """Run + render a report; shared by the sync and background paths."""
    payload = _artifact_payload(name)
    if payload is not None:
        return payload
    report = registry.run_report(name)
    from tracebi.reports.html_renderer import HTMLRenderer
    html = HTMLRenderer.for_project().to_html(report)
    manifest = report.build_manifest(format="html", output_path="(in-memory)")
    return {"name": name, "html": html, "manifest": manifest.to_dict()}


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
    report = _run_report_or_502(name)
    fname = _safe_filename(name)

    try:
        if format == "html":
            from tracebi.reports.html_renderer import HTMLRenderer
            html = HTMLRenderer.for_project().to_html(report)
            return HTMLResponse(
                html,
                headers={
                    "Content-Disposition": f'attachment; filename="{fname}.html"',
                },
            )

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
