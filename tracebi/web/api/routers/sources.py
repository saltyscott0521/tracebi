"""The two Data pages that are not one connector: the project's ``inputs/``
folder (on Sources) and its warehouses (Warehouse). Read-only."""

from fastapi import APIRouter

from tracebi.web.api.registry import registry

router = APIRouter(tags=["sources"])


@router.get("/inputs")
def list_inputs():
    """The files under ``inputs/``: path, size, modified, the transforms
    whose files name each one (``read_by``), and ``table``: whether the table
    API reads it as a table (a data file, not a script or a note)."""
    from pathlib import PurePosixPath

    from tracebi.sources import inputs_listing
    from tracebi.web.api.routers.tables import _FILE_READERS

    listing = inputs_listing()
    for f in listing["files"]:
        f["table"] = PurePosixPath(f["path"]).suffix.lower() in _FILE_READERS
    return listing


@router.get("/warehouse")
def list_warehouses():
    """Every warehouse the project's connectors name: tier, where, size, the
    DuckDB version its certificate records, the models that read it, and each
    table with rows, columns, ``written_by``, ``read_by`` and ``contract``;
    ``writers``, each transform that wrote tables there with what its run
    read (``tracebi.sources.warehouses``)."""
    from tracebi.sources import warehouses

    return {"warehouses": warehouses(registry)}
