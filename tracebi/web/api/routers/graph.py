"""The project as one graph (``GET /api/graph``): what Data's map draws and
what the gateway's ``describe_project`` answers. Read-only, so a viewer may
read it; reports in a folder the caller cannot view are left out."""

from fastapi import APIRouter

from tracebi.web.api.registry import registry

router = APIRouter(tags=["graph"])


@router.get("/graph")
def project_graph():
    """``{summary, nodes, edges}``: every source, transform, warehouse group
    and table, model and report, the four facts that wire them, and each
    node's passport (:func:`tracebi.graph.project_graph`)."""
    from tracebi.graph import project_graph as graph

    return graph(registry)
