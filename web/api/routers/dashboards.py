from fastapi import APIRouter, HTTPException

from web.api.registry import registry

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


_OP_COLORS: dict[str, str] = {
    "load":         "#003366",
    "filter":       "#2E7D32",
    "transform":    "#F59E0B",
    "join":         "#E65100",
    "sort":         "#6A1B9A",
    "select":       "#37474F",
    "rename":       "#00695C",
    "bronze":       "#CD7F32",
    "silver":       "#C0C0C0",
    "gold":         "#FFD700",
    "landing":      "#4A90E2",
    "manipulation": "#7B68EE",
    "final":        "#10B981",
    "warning":      "#D97706",
}
_DEFAULT_COLOR = "#757575"


def _lineage_to_graph(nodes: list[dict]) -> dict:
    rf_nodes = []
    rf_edges = []
    for i, node in enumerate(nodes):
        color = _OP_COLORS.get(node["operation"].lower(), _DEFAULT_COLOR)
        rf_nodes.append({
            "id": str(i),
            "type": "lineageNode",
            "data": {
                "operation":   node["operation"],
                "description": node["description"],
                "connector":   node.get("connector"),
                "source":      node.get("source"),
                "metadata":    node.get("metadata", {}),
                "timestamp":   node["timestamp"],
                "color":       color,
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
def list_dashboards():
    """List all registered dashboards."""
    return registry.list_dashboards()


@router.get("/{name}/lineage")
def dashboard_lineage(name: str):
    """
    Return data lineage for every panel in a dashboard.

    Each panel either ships with a pre-built DataSet (we use its lineage
    directly) or loads via ``table_name`` against the server's DataModel
    (we trigger that load to capture lineage). The combined graph
    deduplicates nodes by identity.
    """
    entry = registry.get_dashboard(name)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Dashboard '{name}' not found")

    server = entry["server"]
    dashboard = server.dashboard
    model = server.model

    seen_ids: set[int] = set()
    all_nodes: list[dict] = []
    panel_lineages: list[dict] = []

    panels = list(getattr(dashboard, "_filters", [])) + list(getattr(dashboard, "_panels", []))

    for panel in panels:
        ds = None
        if getattr(panel, "dataset", None) is not None:
            ds = panel.dataset
        elif getattr(panel, "table_name", None) and model is not None:
            try:
                ds = model.load(panel.table_name)
            except Exception:
                continue
        if ds is None:
            continue

        nodes_for_panel = []
        for node in ds.lineage:
            nid = id(node)
            if nid not in seen_ids:
                seen_ids.add(nid)
                all_nodes.append(node.to_dict())
            nodes_for_panel.append(node.to_dict())

        panel_lineages.append({
            "panel_id":    getattr(panel, "panel_id", None),
            "panel_title": getattr(panel, "title", None) or getattr(panel, "label", None),
            "dataset_name": ds.name,
            "graph":       _lineage_to_graph(nodes_for_panel),
        })

    return {
        "dashboard":      name,
        "combined_graph": _lineage_to_graph(all_nodes),
        "panels":         panel_lineages,
    }
