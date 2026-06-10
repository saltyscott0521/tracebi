import os
import tempfile
import traceback

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.background import BackgroundTask

from web.api.lineage_graph import lineage_to_graph as _lineage_to_graph
from web.api.registry import registry

router = APIRouter(prefix="/reports", tags=["reports"])


def _error_detail(message: str, exc: Exception) -> dict:
    """Structured error payload: message plus the full traceback."""
    return {
        "message": f"{message}: {exc}",
        "exception_type": type(exc).__name__,
        "traceback": traceback.format_exc(),
    }


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


@router.post("/{name}/run")
def run_report(name: str):
    """
    Run a registered report and return the rendered HTML + manifest.

    The HTML is self-contained and can be rendered in an iframe with srcdoc.
    """
    report = _run_report_or_502(name)

    try:
        from tracebi.reports.html_renderer import HTMLRenderer
        html = HTMLRenderer().to_html(report)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("Render failed", exc))

    manifest = report.build_manifest(format="html", output_path="(in-memory)")

    return {
        "name": name,
        "html": html,
        "manifest": manifest.to_dict(),
    }


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
            html = HTMLRenderer().to_html(report)
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

    for section in report.sections:
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
