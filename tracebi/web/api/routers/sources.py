"""The two Data pages that are not one connector: the project's ``inputs/``
folder (on Sources) and its warehouses (Warehouse). Read-only."""

from fastapi import APIRouter

from tracebi.web.api.registry import registry

router = APIRouter(tags=["sources"])


@router.get("/inputs")
def list_inputs():
    """The files under ``inputs/``: path, size, modified, and the transforms
    whose files name each one (``read_by``)."""
    from tracebi.sources import inputs_listing

    return inputs_listing()


@router.get("/warehouse")
def list_warehouses():
    """Every warehouse the project's connectors name: tier, where, size, the
    DuckDB version its certificate records, the models that read it, and each
    table with rows, columns, ``written_by``, ``read_by``, ``contract`` and
    ``fed_from``."""
    from tracebi.sources import warehouses

    return {"warehouses": warehouses(registry)}
