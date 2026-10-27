"""The project as one graph (``GET /api/graph``): what Data's map draws and
what the gateway's ``describe_project`` answers. Read-only, so a viewer may
read it; reports in a folder the caller cannot view are left out."""

from fastapi import APIRouter, HTTPException

from tracebi.web.api.registry import registry

router = APIRouter(tags=["graph"])


@router.get("/graph")
def project_graph():
    """``{summary, nodes, edges}``: every source, transform, warehouse group
    and table, model and report, the four facts that wire them, and each
    node's passport (:func:`tracebi.graph.project_graph`)."""
    from tracebi.graph import project_graph as graph

    return graph(registry)


@router.get("/graph/downstream")
def graph_downstream(node: str):
    """Every report figure that depends on *node* (a warehouse table, a source
    table, or ``measure:<model>:<measure>``), grouped by report, each with what
    its built page printed and its report's verdict
    (:func:`tracebi.graph.downstream`). Read-only: it starts nothing."""
    from tracebi.graph import downstream

    try:
        return downstream(registry, node)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
