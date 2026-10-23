"""The Data pages that are not one connector: the project's ``inputs/``
folder (on Sources), its warehouses (Warehouse) and its transforms
(Transforms). Read-only."""

from fastapi import APIRouter, HTTPException

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


@router.get("/transforms")
def list_transforms():
    """Every transform file in ``transforms/``: ``name``, ``form`` (sql |
    python | notebook), ``file``, ``contract_file`` and ``note``, the
    ``pipelines`` that run it, the ``models`` they refresh or that read what
    it wrote, and the ``tables`` a certificate says it wrote, ``written_at``
    (``tracebi.sources.transforms_listing``)."""
    from tracebi.sources import transforms_listing

    return transforms_listing(registry)


@router.get("/transforms/{name}/source")
def transform_source(name: str):
    """The transform's file and the contract beside it, read-only. *name*
    must be one the listing names: a file is found by the folder, never by a
    path the caller types."""
    from tracebi.transforms import FORMS, TransformError, contract_file, find_transform, transforms_dir
    from tracebi.web.api.source_view import source_payload

    tdir = transforms_dir()
    if not tdir.is_dir() or "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=404, detail=f"Transform '{name}' not found")
    try:
        found = find_transform(name)
    except TransformError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if found is None or found.suffix not in FORMS or found.parent.resolve() != tdir.resolve():
        raise HTTPException(status_code=404, detail=f"Transform '{name}' not found")
    contract = contract_file(found)
    return source_payload(
        [("transform", str(found)), ("contract", str(contract) if contract else None)],
        missing_hint="The transform's file could not be read.",
    )
