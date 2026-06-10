"""
Requests router — browse and run the analyst request scripts in requests/.

Unlike /api/reports (which serves reports registered at startup via
@registry.report), these endpoints work directly on the files in the
requests directory, so in-progress scripts can be run and previewed from
the UI without registering them or restarting the server.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from web.api.errors import error_detail as _error_detail
from web.api.lineage_graph import lineage_to_graph as _lineage_to_graph

router = APIRouter(prefix="/requests", tags=["requests"])


def _requests_dir() -> Path:
    return Path(os.environ.get("TRACEBI_REQUESTS_DIR", "requests"))


def _resolve_or_404(name: str) -> Path:
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=400, detail=f"Invalid request name '{name}'")
    requests_dir = _requests_dir()
    for candidate in (name, f"{name}.py", f"{name}.ipynb"):
        path = requests_dir / candidate
        if path.is_file():
            return path
    raise HTTPException(status_code=404, detail=f"Request '{name}' not found")


def _execute_or_500(path: Path):
    from tracebi._request_runner import execute_request
    try:
        return execute_request(path)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=_error_detail("Request script failed", exc)
        )


@router.get("")
def list_requests():
    """List the request scripts (.py / .ipynb) in the requests directory."""
    requests_dir = _requests_dir()
    if not requests_dir.is_dir():
        return []
    out = []
    for path in sorted(requests_dir.iterdir()):
        if path.name.startswith("_") or path.suffix not in (".py", ".ipynb"):
            continue
        stat = path.stat()
        out.append({
            "name": path.stem,
            "file": path.name,
            "type": "notebook" if path.suffix == ".ipynb" else "script",
            "modified": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            "size": stat.st_size,
        })
    return out


@router.post("/{name}/run")
def run_request(name: str):
    """
    Execute a request script and return its rendered HTML + manifest.

    The script runs fresh on every call, so edits on disk are picked up
    without restarting the server.
    """
    path = _resolve_or_404(name)
    report = _execute_or_500(path)
    try:
        from tracebi.reports.html_renderer import HTMLRenderer
        html = HTMLRenderer().to_html(report)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=_error_detail("Render failed", exc))
    manifest = report.build_manifest(format="html", output_path="(in-memory)")
    return {"name": name, "file": path.name, "html": html,
            "manifest": manifest.to_dict()}


@router.get("/{name}/lineage")
def request_lineage(name: str):
    """Execute a request script and return its lineage as a React Flow graph."""
    path = _resolve_or_404(name)
    report = _execute_or_500(path)

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
        "request": name,
        "combined_graph": _lineage_to_graph(all_nodes),
        "sections": section_lineages,
    }
