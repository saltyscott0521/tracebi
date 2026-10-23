"""The credentials a project's connections need, and where each is set.

A value never leaves the server: the read lists names and where each one
resolves (:func:`tracebi.project_credentials.status`), a write takes a value
and answers with that same status row, and a connection test answers with a
table count or a reason scrubbed of every resolved value.

Who may do what is decided in the middleware (``auth._required_role`` names
the writes and the test ``admin``; a write also needs an *identified* admin,
``auth.credential_write_refusal``), never here.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from tracebi.web.api.registry import registry

router = APIRouter(tags=["credentials"])


class _Value(BaseModel):
    value: str


def _root() -> Path:
    return Path.cwd()


def _row(name: str) -> dict:
    from tracebi.project_credentials import status

    return next(r for r in status(_root()) if r["name"] == name)


@router.get("/credentials")
def list_credentials(request: Request):
    """Every ``${NAME}`` the project references, where each one is set, and
    whether this caller may change them here (``can_change``)."""
    from tracebi.project_credentials import CredentialError, key_source, status

    try:
        rows = status(_root())
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    role = getattr(request.state, "role", None) or "admin"
    identified = getattr(request.state, "identified", False)
    return {"credentials": rows, "key_source": key_source(_root()),
            "can_change": role == "admin" and identified}


@router.put("/credentials/{name}")
def put_credential(name: str, body: _Value, response: Response):
    """Save a value in the project's store. 201 when the name was new, 200
    when it replaced one; the answer is the status row, never the value."""
    from tracebi.audit import get_actor
    from tracebi.project_credentials import (
        NAME, CredentialError, record_change, required, set_secret,
    )

    if not NAME.fullmatch(name):
        raise HTTPException(status_code=422, detail=f"{name!r} is not a credential name")
    if name not in {r["name"] for r in required(_root())}:
        raise HTTPException(
            status_code=422,
            detail=f"Nothing in this project references ${{{name}}}: name it in a "
                   f"connections/<name>.yaml first.")
    try:
        new = set_secret(name, body.value, _root(), actor=get_actor()[0])
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    record_change(name, "set")
    response.status_code = 201 if new else 200
    return _row(name)


@router.delete("/credentials/{name}", status_code=204)
def delete_credential(name: str):
    """Remove the store's value. An environment or ``.env`` value is not
    touched; the status row then says where the name still resolves."""
    from tracebi.project_credentials import CredentialError, record_change, unset_secret

    try:
        removed = unset_secret(name, _root())
    except CredentialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if not removed:
        raise HTTPException(status_code=404, detail=f"The store holds no value for {name}.")
    record_change(name, "unset")
    return Response(status_code=204)


@router.post("/connectors/{name}/test")
def test_connection(name: str):
    """Open the connection, list its tables, close it: ``{ok: true, tables:
    n}`` or ``{ok: false, reason}``. The reason is scrubbed of every value the
    project's credentials resolve to, since a driver's error can echo one."""
    from tracebi.project_credentials import redact
    from tracebi.sources import connection_tables

    c = registry.get_connector(name)
    if not c:
        raise HTTPException(status_code=404, detail=f"Connector '{name}' not found")
    got = connection_tables(c)
    if got.get("connected"):
        return {"ok": True, "tables": len(got.get("tables") or [])}
    return {"ok": False, "reason": redact(str(got.get("reason") or "It could not be reached."), _root())}
