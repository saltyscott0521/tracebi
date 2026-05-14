from fastapi import APIRouter, HTTPException
from web.api.registry import registry

router = APIRouter(prefix="/reports", tags=["reports"])

_OP_COLORS: dict[str, str] = {
    "load":      "#003366",
    "filter":    "#2E7D32",
    "transform": "#F59E0B",
    "join":      "#E65100",
    "sort":      "#6A1B9A",
    "select":    "#37474F",
    "rename":    "#00695C",
    "bronze":    "#CD7F32",
    "silver":    "#C0C0C0",
    "gold":      "#FFD700",
}
_DEFAULT_COLOR = "#757575"


def _lineage_to_graph(nodes: list[dict]) -> dict:
    """Convert a flat lineage list to React Flow nodes + edges."""
    rf_nodes = []
    rf_edges = []
    for i, node in enumerate(nodes):
        color = _OP_COLORS.get(node["operation"].lower(), _DEFAULT_COLOR)
        rf_nodes.append({
            "id": str(i),
            "type": "lineageNode",
            "data": {
                "operation": node["operation"],
                "description": node["description"],
                "connector": node.get("connector"),
                "source": node.get("source"),
                "metadata": node.get("metadata", {}),
                "timestamp": node["timestamp"],
                "color": color,
            },
            "position": {"x": i * 240, "y": 0},
        })
        if i > 0:
            rf_edges.append({
                "id": f"e{i-1}-{i}",
                "source": str(i - 1),
                "target": str(i),
                "type": "smoothstep",
            })
    return {"nodes": rf_nodes, "edges": rf_edges}


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
    if name not in {r["name"] for r in registry.list_reports()}:
        raise HTTPException(status_code=404, detail=f"Report '{name}' not found")

    try:
        report = registry.run_report(name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report factory failed: {exc}")

    try:
        from tracebi.reports.html_renderer import HTMLRenderer
        html = HTMLRenderer()._build_html(report)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Render failed: {exc}")

    manifest = report.build_manifest(format="html", output_path="(in-memory)")

    return {
        "name": name,
        "html": html,
        "manifest": manifest.to_dict(),
    }


@router.get("/{name}/mermaid")
def report_mermaid(name: str):
    """Return a Mermaid flowchart string for the report's combined lineage."""
    if name not in {r["name"] for r in registry.list_reports()}:
        raise HTTPException(status_code=404, detail=f"Report '{name}' not found")
    try:
        report = registry.run_report(name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report factory failed: {exc}")
    try:
        from tracebi.lineage.diagram import LineageDiagram
        mermaid = LineageDiagram(report).to_mermaid()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lineage diagram failed: {exc}")
    return {"mermaid": mermaid}


@router.get("/{name}/lineage")
def report_lineage(name: str):
    """
    Run a report and return its full data lineage as a React Flow graph.

    Returns nodes and edges ready to pass directly to <ReactFlow>.
    """
    if name not in {r["name"] for r in registry.list_reports()}:
        raise HTTPException(status_code=404, detail=f"Report '{name}' not found")

    try:
        report = registry.run_report(name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report factory failed: {exc}")

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
