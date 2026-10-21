from fastapi import APIRouter, HTTPException
from tracebi.web.api.registry import registry
from tracebi.web.api.source_view import source_payload

router = APIRouter(prefix="/connectors", tags=["connectors"])


def _runners() -> list:
    return [(p, registry.get_pipeline(p)) for p in registry.list_pipeline_names()]


@router.get("")
def list_connectors():
    """List all registered connectors, each with who reads it (``read_by``)."""
    from tracebi.sources import read_by, transform_reads

    reads, runners = transform_reads(), _runners()
    return [{**c, "read_by": read_by(c["name"], c.get("used_by", []), reads, runners)}
            for c in registry.list_connectors()]


@router.get("/{name}")
def get_connector(name: str):
    """Get detail for a single connector, with who reads it: ``read_by``
    ``{transforms: [{name, tables}], layers: [{pipeline, layer}], models}``."""
    from tracebi.sources import read_by, transform_reads

    c = registry.get_connector(name)
    if not c:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not found")
    used_by = next((e.get("used_by", []) for e in registry.list_connectors() if e["name"] == name), [])
    return {**c.describe(), "read_by": read_by(name, used_by, transform_reads(), _runners())}


@router.get("/{name}/tables")
def connector_tables(name: str):
    """What the source holds, read now: its tables with their columns (and a
    row count where one is cheap). The connection is resolved on this request
    only and released before it returns; a source that cannot be reached here
    (its ``${VAR}`` unset, the database refusing) answers 200 with
    ``{connected: false, reason}``, never an error."""
    from tracebi.sources import connection_tables

    c = registry.get_connector(name)
    if not c:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not found")
    return connection_tables(c)


@router.get("/{name}/source")
def connector_source(name: str):
    """Where the connector is declared: the model file(s) that read from it."""
    connector = registry.get_connector(name)
    if not connector:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not found")
    from tracebi.model_registry import model_path

    used_by = next((c.get("used_by", []) for c in registry.list_connectors() if c["name"] == name), [])
    # A declared connection file holds ${ENV_VAR} references only (a literal
    # secret does not validate), so showing it shows no credential.
    declared = getattr(connector, "declared_in", None)
    return source_payload(
        [("connection", declared)] + [(f"model {m}", model_path(m)) for m in used_by],
        missing_hint="No model file declares this connector: it is registered in Python code (an app module).",
        hint="A connector is declared in connections/<name>.yaml, or in the model file that reads from it.",
    )


@router.get("/{name}/warehouse")
def connector_warehouse(name: str):
    """What a file-backed warehouse holds: tables, row counts, column profiles
    and each table's sink-contract status. Read-only; the file is opened and
    closed within the request. Other connectors answer ``supported: false``."""
    c = registry.get_connector(name)
    if not c:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not found")
    d = c.describe()
    database = d.get("database")
    if d.get("type") != "DuckDBConnector" or not database or database == ":memory:":
        return {"supported": False, "tables": []}
    from tracebi.workbench import warehouse_view

    # The project's warehouse (`type: warehouse`) is read on its own tier.
    wh = getattr(c, "warehouse", None)
    return {"supported": True,
            **warehouse_view(wh.sink if wh is not None else str(database))}
