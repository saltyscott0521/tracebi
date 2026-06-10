from fastapi import APIRouter, HTTPException

from web.api.lineage_graph import lineage_to_graph as _lineage_to_graph
from web.api.registry import registry

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


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
