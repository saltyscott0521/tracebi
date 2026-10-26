"""Saving back, for the gateway: one thin call over
:func:`tracebi.warehouse.export_table`, which is the implementation the route
(``POST /api/tables/{source}/{table}/export``) and ``tracebi export`` use too.
The gateway's result keeps its own shape (``source``, ``written``), so an agent
that learned it keeps working."""
from __future__ import annotations

import os
from typing import Optional

from tracebi.warehouse import ExportError  # noqa: F401  (re-exported for callers)
from tracebi.warehouse import export_table as _export_table


def export_table(connector, table: str, to: str, root: Optional[str] = None) -> dict:
    """Write warehouse *table* (a table or a view) of *connector* to *to*: a
    connection's name or an object prefix (a value with a ``/``). Returns
    ``{source, table, to, rows, written, run_id}``; raises
    :class:`~tracebi.warehouse.ExportError`. Only the project's warehouse is
    exported: the rows are read through the locked query connection."""
    from tracebi.sources import is_warehouse

    if not is_warehouse(connector.describe()):
        raise ExportError(f"'{connector.name}' is not a warehouse; only a warehouse "
                          f"table or view is exported")
    out = _export_table(table, to, root=os.path.abspath(root or os.getcwd()))
    written = out.get("path") if out.get("kind") == "object" else f"{to}.{table}"
    return {"source": connector.name, "table": table, "to": to, "rows": out["rows"],
            "written": written, "run_id": None}
