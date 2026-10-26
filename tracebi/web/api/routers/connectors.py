import re
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from tracebi.web.api.registry import registry
from tracebi.web.api.source_view import source_payload

router = APIRouter(prefix="/connectors", tags=["connectors"])
# Setting a connection up in the app: /api/connections and /api/inputs.
connections_router = APIRouter(tags=["connections"])


def _runners() -> list:
    return [(p, registry.get_pipeline(p)) for p in registry.list_pipeline_names()]


@router.get("")
def list_connectors():
    """List all registered connectors, each with who reads it (``read_by``)
    and ``warehouse``: whether it is a warehouse (the Warehouse tab lists
    those; Sources lists the rest)."""
    from tracebi.sources import is_warehouse, read_by, transform_reads

    reads, runners = transform_reads(), _runners()
    return [{**c, "read_by": read_by(c["name"], c.get("used_by", []), reads, runners),
             "warehouse": is_warehouse(c)}
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
    from tracebi.connections import agent_may_read
    from tracebi.sources import connection_tables

    c = registry.get_connector(name)
    if not c:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not found")
    got = connection_tables(c)
    # Which tables agents may read (``agents:`` in the connection file); the
    # Sources page ticks them.
    for t in got.get("tables") or []:
        t["agents"] = agent_may_read(c, t["name"])
    return {**got, "agent_tables": getattr(c, "agent_tables", None)}


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


# ── Setting a connection up in the app ──────────────────────────────────────
#
# A person adds, edits and deletes connections/<name>.yaml here, as they
# would by hand or with `tracebi connect`. Every write needs an identified
# admin (``auth._required_role`` and ``auth._credential_write``, the same rule
# as a credential write); nothing is decided here. A secret typed into the
# form goes to the project's encrypted store and the file holds ``${NAME}``.
# After a write, discovery registers (or forgets) the file at once rather than
# on its next scan, so the answer describes the connection as it now is.

#: The largest file the app uploads into inputs/.
UPLOAD_LIMIT = 50 * 1024 * 1024
_UPLOAD_NAME = re.compile(r"[A-Za-z_]\w*\.(csv|parquet)", re.I)


class _ConnectionBody(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    fields: dict[str, Optional[str]] = {}
    label: Optional[str] = None
    agents: Optional[Any] = None


def _sync(name: str) -> None:
    from tracebi.connections import connections_dir
    from tracebi.web.discovery import register_connections

    register_connections(str(connections_dir()), refresh=(name,))


def _allowlist(agents: Any) -> Optional[dict]:
    """``{tables: [a, b] | "*"}`` as the file will say it; none ticked is
    no allowlist."""
    from tracebi.connections import agents_allowlist

    if agents is None:
        return None
    if not isinstance(agents, dict) or set(agents) != {"tables"}:
        raise HTTPException(status_code=422, detail='agents: {tables: [a, b]} or {tables: "*"}')
    return agents_allowlist(agents["tables"])


def _save(name: str, doc: dict, secrets: dict, text_for) -> None:
    """Validate *doc*, put its secrets in the store, then write the file."""
    from tracebi.audit import get_actor
    from tracebi.connections import connections_dir, validate_connection_doc
    from tracebi.project_credentials import CredentialError, record_change, set_secret

    errors = validate_connection_doc(doc)
    if errors:
        raise HTTPException(status_code=422, detail={
            "message": f"connection '{name}': " + "; ".join(errors), "errors": errors})
    try:
        for key, value in secrets.items():
            set_secret(key, value, Path.cwd(), actor=get_actor()[0])
            record_change(key, "set")
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    folder = connections_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.yaml"
    path.write_text(text_for(path), encoding="utf-8")
    _sync(name)


@connections_router.get("/connections/types")
def connection_types():
    """The types a connection may have, each with its group and fields
    (``name, label, kind: text|number|secret|url|path|choice, required,
    help, advanced, choices?, default?``) and ``url_scheme`` when its fields
    are also one URL: the app's Add a connection form is drawn from this."""
    from tracebi.connections import connection_types as types

    return types()


@connections_router.post("/connections", status_code=201)
def create_connection(body: _ConnectionBody):
    """Write ``connections/<name>.yaml`` from the form: 201 with the
    connection as ``GET /api/connectors/{name}`` describes it, 409 when the
    name is taken, 422 with the validator's ``errors``."""
    from tracebi.connections import connection_file, connection_text, plan_connection
    from tracebi.model.model_spec import _NAME, ModelSpecError

    name = (body.name or "").strip()
    if not _NAME.fullmatch(name):
        raise HTTPException(status_code=422, detail="name: letters, digits and underscores")
    if connection_file(name) is not None or registry.get_connector(name) is not None:
        raise HTTPException(status_code=409, detail=f"A connection named '{name}' already exists.")
    try:
        doc, secrets = plan_connection(name, body.type or "", body.fields,
                                       label=(body.label or "").strip() or None,
                                       agents=_allowlist(body.agents))
    except ModelSpecError as exc:
        raise HTTPException(status_code=422, detail={
            "message": "; ".join(exc.errors), "errors": exc.errors}) from None
    _save(name, doc, secrets, lambda _path: connection_text(doc))
    return get_connector(name)


@connections_router.post("/connections/test")
def test_new_connection(body: _ConnectionBody):
    """Test what the form holds before it is saved: open it, list its tables,
    close it, as ``POST /api/connectors/{name}/test`` does for a saved one.
    A secret typed into the form stands in for its ``${NAME}`` for this test
    only; nothing is written, and the reason is scrubbed of it. ``{ok: true,
    tables, version?}`` (the server's version where the driver says it), or
    ``{ok: false, reason, variable?}``; a password the form says is not saved
    (Save password off) and is set nowhere is said as exactly that."""
    from tracebi.connections import (
        build_connection, connection_file, plan_connection, read_connection_doc,
        server_version, validate_connection_doc,
    )
    from tracebi.model.model_spec import _NAME, ModelSpecError
    from tracebi.project_credentials import REF, redact
    from tracebi.sources import connection_tables

    name = (body.name or "").strip()
    name = name if _NAME.fullmatch(name) else "new_connection"
    path = connection_file(name)
    existing = read_connection_doc(path) if path is not None else None
    ctype = existing["type"] if isinstance(existing, dict) and existing.get("type") else body.type
    try:
        doc, secrets = plan_connection(name, ctype or "", body.fields, existing=existing)
    except ModelSpecError as exc:
        raise HTTPException(status_code=422, detail={
            "message": "; ".join(exc.errors), "errors": exc.errors}) from None
    errors = validate_connection_doc(doc)
    if errors:
        raise HTTPException(status_code=422, detail={
            "message": "; ".join(errors), "errors": errors})
    probe = {}
    for key, value in doc.items():
        ref = REF.fullmatch(value) if isinstance(value, str) else None
        probe[key] = secrets[ref.group(1)] if ref and ref.group(1) in secrets else value
    got = connection_tables(build_connection(probe, Path.cwd()))
    if got.get("connected"):
        out = {"ok": True, "tables": len(got.get("tables") or [])}
        if version := server_version(build_connection(probe, Path.cwd())):
            out["version"] = version
        return out
    variable = got.get("variable")
    sent = body.fields.get("password") or ""
    if variable and REF.fullmatch(sent) and REF.fullmatch(sent).group(1) == variable:
        return {"ok": False, "variable": variable, "reason": (
            f"Save password is off and {variable} is not set in the server's "
            f"environment or .env.")}
    reason = redact(str(got.get("reason") or "It could not be reached."), Path.cwd())
    for value in secrets.values():
        reason = reason.replace(value, "***")
    return {"ok": False, "reason": reason, **({"variable": variable} if variable else {})}



def _declared(name: str):
    from tracebi.connections import connection_file, read_connection_doc

    path = connection_file(name)
    if path is None:
        raise HTTPException(status_code=404, detail=(
            f"'{name}' is not a file in connections/; a connector declared in "
            f"code is changed in its code."))
    doc = read_connection_doc(path)
    if not isinstance(doc, dict) or not doc.get("type"):
        raise HTTPException(status_code=422, detail=f"{path.name} does not parse as a connection")
    return path, doc


@connections_router.put("/connections/{name}")
def update_connection(name: str, body: _ConnectionBody):
    """Edit the file: the fields sent (a secret sent empty is kept), the
    label, and the allowlist when ``agents`` is sent (null removes it). The
    type stays; the file's comments and order stay too."""
    from tracebi.connections import plan_connection, rewrite_connection_text

    path, existing = _declared(name)
    if body.type and body.type != existing["type"]:
        raise HTTPException(status_code=422, detail=(
            "A connection's type does not change: delete it and add a new one."))
    sent = body.model_fields_set
    label = ((body.label or "").strip() or None) if "label" in sent else existing.get("label")
    agents = _allowlist(body.agents) if "agents" in sent else existing.get("agents")
    doc, secrets = plan_connection(name, existing["type"], body.fields, label=label,
                                   agents=agents, existing=existing)
    _save(name, doc, secrets,
          lambda p: rewrite_connection_text(p.read_text(encoding="utf-8"), doc))
    return get_connector(name)


@connections_router.delete("/connections/{name}", status_code=204)
def delete_connection(name: str):
    """Remove the file when nothing reads the connection; otherwise 409 with
    ``read_by`` (the transforms, pipeline steps and models that do). Values
    in the store are left: another connection may name them."""
    from tracebi.sources import read_by, transform_reads

    path, _doc = _declared(name)
    used_by = next((e.get("used_by", []) for e in registry.list_connectors()
                    if e["name"] == name), [])
    readers = read_by(name, used_by, transform_reads(), _runners())
    if any(readers.values()):
        said = ([f"transform {t['name']}" for t in readers["transforms"]]
                + [f"pipeline {x['pipeline']}" for x in readers["layers"]]
                + [f"model {m}" for m in readers["models"]])
        raise HTTPException(status_code=409, detail={
            "message": f"'{name}' is read by {', '.join(said)}; change those first.",
            "read_by": readers})
    path.unlink()
    _sync(name)
    return Response(status_code=204)


@connections_router.post("/inputs", status_code=201)
async def upload_input(request: Request, name: str, replace: bool = False):
    """Put one CSV or Parquet file under ``inputs/`` (the request body is the
    file, ``?name=orders.csv``) for an ``upload`` connection to read. At most
    50 MB; 409 when the file exists and ``replace`` is not set."""
    from tracebi.sources import inputs_dir

    if not _UPLOAD_NAME.fullmatch(name):
        raise HTTPException(status_code=422, detail=(
            "name: a file name like orders.csv or orders.parquet (letters, "
            "digits and underscores), with no folder"))
    folder = inputs_dir()
    target = folder / name
    if target.exists() and not replace:
        raise HTTPException(status_code=409, detail=f"inputs/{name} already exists.")
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / f".{name}.uploading"
    size = 0
    try:
        with partial.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > UPLOAD_LIMIT:
                    raise HTTPException(status_code=413, detail="The file is over 50 MB.")
                out.write(chunk)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return {"path": f"inputs/{name}", "size": size}
