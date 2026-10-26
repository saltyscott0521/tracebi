"""Saving back: a warehouse table or view written to a connection or to an
object prefix (``design/agent-data-onboarding.md`` §3).

One function, :func:`export_table`, so every surface that offers **Export
to…** writes the same way and records the same run: the gateway's
``export_table`` tool calls it, and so does the app's route.

The table is read through the locked, read-only query connection
(:mod:`tracebi.model.engine`), after its name has been found in the
warehouse's own catalog, so nothing free-form reaches SQL. It then goes out
through a connector's ``write``: the named connection's own connector, or a
DuckDB connector on an object-tier address for a prefix, which writes
``<prefix>/<table>.parquet`` exactly as an object-tier warehouse lands a
table. Every export, written or failed, is a run row of kind ``export``.
"""

from __future__ import annotations

import os
from typing import Optional

#: Remote object stores a prefix may name; anything else is a local directory.
_OBJECT_SCHEMES = ("s3://", "gs://", "gcs://", "r2://")


class ExportError(ValueError):
    """An export that cannot happen: the table or the destination is not
    there, or the destination takes no writes. The message says which."""


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _warehouse_target(connector):
    wh = getattr(connector, "warehouse", None)
    return wh.sink if wh is not None else str(connector.describe()["database"])


def _read(connector, table: str):
    """The whole table as a frame, read only once its name is in the catalog."""
    from tracebi.model.engine import query_connection
    from tracebi.sources import is_framework_table
    from tracebi.warehouse import as_warehouse

    missing = ExportError(f"No table '{table}' in '{connector.name}'")
    if is_framework_table(table):
        raise missing
    warehouse = as_warehouse(_warehouse_target(connector))
    with query_connection({"wh": warehouse}, default="wh") as con:
        if "wh" not in con.attached:
            raise ExportError(f"'{connector.name}' cannot be read: "
                              f"{con.attach_errors.get('wh') or 'nothing is built yet'}")
        names = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog = 'wh' AND table_schema = 'main'").fetchall()}
        if table not in names:
            raise missing
        return con.execute(f'SELECT * FROM "wh"."main".{_ident(table)}').df()


def _to_prefix(frame, table: str, prefix: str, root: str) -> str:
    """Write ``<prefix>/<table>.parquet``. A local prefix stays inside the
    project; a remote one uses the project warehouse's object credentials."""
    from tracebi import project_config
    from tracebi.connectors.duckdb_connector import DuckDBConnector
    from tracebi.model.model_spec import _escapes
    from tracebi.warehouse import Warehouse

    remote = prefix.startswith(_OBJECT_SCHEMES)
    if not remote and _escapes(prefix):
        raise ExportError(f"A local prefix must stay inside the project (no absolute "
                          f"path, no '..'), got {prefix!r}")
    if not remote:
        os.makedirs(os.path.join(root, prefix), exist_ok=True)
    project = project_config.warehouse(root)
    options = project.options if project.tier == "object" else ()
    dest = Warehouse("object", prefix, root, options)
    DuckDBConnector("export", database=dest.sink).write(frame, table)
    return dest.table_path(table)


def _to_connection(frame, table: str, name: str, root: str) -> str:
    from tracebi.connections import connection_file, load_connection

    path = connection_file(name, root)
    if path is None:
        raise ExportError(f"No connection '{name}': connections/{name}.yaml does not exist")
    target = load_connection(path, root=root)
    try:
        target.write(frame, table)
    except NotImplementedError as exc:
        raise ExportError(f"Connection '{name}' ({type(target).__name__}) takes no writes") from exc
    finally:
        release = getattr(target, "disconnect", None)
        if release is not None:
            release()
    return f"{name}.{table}"


def export_table(connector, table: str, to: str, root: Optional[str] = None) -> dict:
    """Write warehouse *table* (a table or a view) of *connector* to *to*: a
    connection's name (``connections/<to>.yaml``; the table keeps its name
    there and is replaced) or an object prefix (a value with a ``/``:
    ``s3://bucket/exports``, or a directory inside the project). Returns
    ``{source, table, to, rows, written, run_id}``; raises
    :class:`ExportError`."""
    from tracebi.sources import is_warehouse
    from tracebi.state import record_run

    if not is_warehouse(connector.describe()):
        raise ExportError(f"'{connector.name}' is not a warehouse; only a warehouse "
                          f"table or view is exported")
    if not isinstance(to, str) or not to.strip():
        raise ExportError("Say where to: a connection's name or an object prefix")
    root = os.path.abspath(root or os.getcwd())
    frame = _read(connector, table)
    detail = {"to": to, "rows": len(frame)}
    try:
        if "/" in to:
            written = _to_prefix(frame, table, to, root)
        else:
            written = _to_connection(frame, table, to, root)
    except Exception as exc:
        record_run(kind="export", target=f"{connector.name}.{table}", status="failed",
                   detail={**detail, "error": f"{type(exc).__name__}: {exc}"})
        if isinstance(exc, ExportError):
            raise
        raise ExportError(f"Export of {table} to {to} failed: {exc}") from exc
    run_id = record_run(kind="export", target=f"{connector.name}.{table}", status="ok",
                        detail={**detail, "written": written})
    return {"source": connector.name, "table": table, "to": to, "rows": len(frame),
            "written": written, "run_id": run_id}
