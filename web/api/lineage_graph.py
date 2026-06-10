"""
Shared lineage-graph helpers for API routers.

Converts a flat list of LineageNode dicts into React Flow nodes + edges.
Used by the reports and dashboards routers (and any future lineage view)
so operation colors stay consistent across pages.
"""

from __future__ import annotations

OP_COLORS: dict[str, str] = {
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
DEFAULT_COLOR = "#757575"


def lineage_to_graph(nodes: list[dict]) -> dict:
    """Convert a flat lineage list to React Flow nodes + edges."""
    rf_nodes = []
    rf_edges = []
    for i, node in enumerate(nodes):
        color = OP_COLORS.get(node["operation"].lower(), DEFAULT_COLOR)
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
