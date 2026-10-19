"""
The SQL engine under the medallion layers.

A Manipulation layer's declarative steps (``cast``, ``drop_nulls``,
``deduplicate``, ``rename``, ``filter``) each compile to one SELECT over the
relation the step before left, and run in DuckDB. Where the rows come from
decides where that SQL runs:

* source and sink are the same DuckDB database — the steps run inside it and
  the sink is written with ``CREATE OR REPLACE TABLE … AS SELECT``; no frame is
  ever loaded;
* any other source — its ``load()`` frame is registered in an in-memory DuckDB
  as an Arrow table, the same SQL runs over it, and the result goes to the sink
  connector's ``write()`` as before.

``transform(func)`` is the escape hatch: the rows so far are handed to the
pandas callable and its frame comes back in as Arrow. Its lineage node says
``escape_hatch: python`` so the run record can say which layers left SQL.

Row order is part of a table's fingerprint, so every chain carries a hidden
row number (:data:`ROW`) taken from the source's order and writes the result
ordered by it. ``deduplicate`` keeps the row with the lowest one, which is the
first occurrence pandas' ``drop_duplicates`` kept.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from tracebi.model.dataset import LineageNode

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

#: The hidden column that carries the source's row order through the chain.
ROW = "__tb_row"

#: pandas dtype names a ``cast`` accepts, and the DuckDB type each becomes.
#: Anything else is refused by name rather than guessed. ``object`` is not
#: here on purpose: in pandas it means "leave the values as they are", which
#: is no cast at all. Three conversions follow DuckDB rather than pandas, and
#: no number changes in any of them: to text, a boolean reads ``true`` (pandas
#: wrote ``True``) and a null stays null (pandas wrote ``'None'``); text to a
#: boolean reads ``'false'`` as false (pandas read any non-empty text as True).
#: Integer targets are guarded in :func:`_cast_expr` so that they never round.
CAST_TYPES = {
    "int8": "TINYINT",
    "int16": "SMALLINT",
    "int32": "INTEGER",
    "int64": "BIGINT",
    "int": "BIGINT",
    "uint8": "UTINYINT",
    "uint16": "USMALLINT",
    "uint32": "UINTEGER",
    "uint64": "UBIGINT",
    "float32": "FLOAT",
    "float64": "DOUBLE",
    "float": "DOUBLE",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "str": "VARCHAR",
    "string": "VARCHAR",
    "datetime64[ns]": "TIMESTAMP_NS",
    "datetime64[us]": "TIMESTAMP",
    "datetime64[ms]": "TIMESTAMP_MS",
    "datetime64[s]": "TIMESTAMP_S",
}

_INTEGER_TYPES = {"TINYINT", "SMALLINT", "INTEGER", "BIGINT",
                  "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT"}


def require_duckdb():
    try:
        import duckdb
    except ImportError:
        raise ImportError(
            "duckdb is required to run the medallion layers.\n"
            "Install with: pip install 'tracebi[pipeline]'"
        )
    return duckdb


def _require_pyarrow():
    try:
        import pyarrow
    except ImportError:
        raise ImportError(
            "pyarrow is required to hand a connector's rows to the medallion "
            "layers' SQL.\nInstall with: pip install 'tracebi[pipeline]'"
        )
    return pyarrow


def quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def same_database(source: Any, sink: Any) -> bool:
    """True when *source* and *sink* are the same DuckDB database, so a step
    can read one and write the other without the rows leaving it."""
    from tracebi.connectors.duckdb_connector import DuckDBConnector
    if not (isinstance(source, DuckDBConnector) and isinstance(sink, DuckDBConnector)):
        return False
    if "object" in (source.tier, sink.tier):
        # Parquet files, not tables: the step reads through the source and
        # lands through write(), which writes each table's file.
        return False
    if source is sink:
        return True
    if ":memory:" in (source.database, sink.database):
        return False  # an in-memory database is its own connection
    import os
    return os.path.realpath(source.database) == os.path.realpath(sink.database)


def table_kind(con, table: str) -> Optional[str]:
    """``"table"``, ``"view"``, or None when *table* is not a relation in the
    connection's main schema (a file path or a SELECT, say)."""
    row = con.execute(
        "SELECT table_type FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ?", [table],
    ).fetchone()
    if row is None:
        return None
    return "table" if row[0] == "BASE TABLE" else "view"


def describe(con, relation: str) -> list[tuple[str, str]]:
    """``[(column, duckdb_type)]`` of *relation*, the hidden row column left out."""
    rows = con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
    return [(str(r[0]), str(r[1])) for r in rows if r[0] != ROW]


def count(con, relation: str) -> int:
    return int(con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0])


def arrow_with_rows(df: "pd.DataFrame"):
    """*df* as an Arrow table with :data:`ROW` appended: the frame's own order."""
    pa = _require_pyarrow()
    import numpy as np
    table = pa.Table.from_pandas(df, preserve_index=False)
    return table.append_column(ROW, pa.array(np.arange(len(df), dtype="int64")))


def to_frame(con, relation: str) -> "pd.DataFrame":
    """The rows of *relation* as pandas, in source order, without :data:`ROW`.

    Through Arrow rather than DuckDB's ``.df()``: Arrow hands back exact
    ``Decimal`` values where ``.df()`` would turn them into floats.
    """
    return con.execute(
        f"SELECT * EXCLUDE ({ROW}) FROM {relation} ORDER BY {ROW}"
    ).to_arrow_table().to_pandas()


def _cast_expr(column: str, source_type: str, target: str) -> str:
    col = quote(column)
    if target not in _INTEGER_TYPES:
        return f"CAST({col} AS {target})"
    # DuckDB rounds a fraction to the nearest integer where pandas truncated a
    # float and refused text with a fraction in it. Neither may change a
    # number silently, so do what pandas did.
    if source_type in ("FLOAT", "DOUBLE") or source_type.startswith("DECIMAL"):
        return f"CAST(trunc({col}) AS {target})"
    if source_type == "VARCHAR":
        message = f"cast of {column} to {target}: not a whole number: ".replace("'", "''")
        return (
            f"CASE WHEN {col} IS NULL OR regexp_full_match(trim({col}), '[+-]?[0-9]+') "
            f"THEN CAST(trim({col}) AS {target}) "
            f"ELSE error('{message}' || {col}) END"
        )
    return f"CAST({col} AS {target})"


def compile_step(step: dict, relation: str, columns: list[tuple[str, str]]) -> str:
    """The SELECT one declarative step compiles to, over *relation*."""
    op = step["op"]
    names = [c for c, _ in columns]
    if op == "cast":
        types = dict(columns)
        replaced = []
        for column, dtype in step["type_map"].items():
            if column not in types:
                continue  # pandas' astype skipped absent columns too
            target = CAST_TYPES.get(str(dtype))
            if target is None:
                raise ValueError(
                    f"cast: unknown dtype {dtype!r} for column {column!r}. "
                    f"Known: {', '.join(sorted(CAST_TYPES))}"
                )
            replaced.append(f"{_cast_expr(column, types[column], target)} AS {quote(column)}")
        if not replaced:
            return f"SELECT * FROM {relation}"
        return f"SELECT * REPLACE ({', '.join(replaced)}) FROM {relation}"
    if op == "drop_nulls":
        subset = step["subset"] or names
        cond = " AND ".join(f"{quote(c)} IS NOT NULL" for c in subset)
        return f"SELECT * FROM {relation} WHERE {cond}"
    if op == "deduplicate":
        subset = step["subset"] or names
        keys = ", ".join(quote(c) for c in subset)
        return (f"SELECT * FROM {relation} "
                f"QUALIFY row_number() OVER (PARTITION BY {keys} ORDER BY {ROW}) = 1")
    if op == "rename":
        pairs = [f"{quote(old)} AS {quote(new)}"
                 for old, new in step["columns"].items() if old in names]
        if not pairs:
            return f"SELECT * FROM {relation}"
        return f"SELECT * RENAME ({', '.join(pairs)}) FROM {relation}"
    if op == "filter":
        return f"SELECT * FROM {relation} WHERE ({step['where']})"
    raise ValueError(f"unknown step {op!r}")


def run_steps(con, relation: str, steps: list[dict], operation: str,
              layer_label: str) -> tuple[str, list[LineageNode], list[str]]:
    """Run *steps* over *relation* in *con*, one temporary table per step.

    Returns the last relation, a lineage node per step, and the temporary
    names the caller drops when it is done with the connection.
    """
    nodes: list[LineageNode] = []
    created: list[str] = []
    for i, step in enumerate(steps, start=1):
        op = step["op"]
        target = quote(f"__tb_step_{i}")
        if op == "transform":
            desc = step.get("description") or f"{layer_label} transform"
            out = step["func"](to_frame(con, relation))
            con.register(f"__tb_step_{i}", arrow_with_rows(out))
            created.append(("registered", f"__tb_step_{i}"))
            nodes.append(LineageNode(
                operation=operation,
                description=desc,
                metadata={"step": "transform", "escape_hatch": "python"},
            ))
            relation = target
            continue

        columns = describe(con, relation)
        sql = compile_step(step, relation, columns)
        rows_before = count(con, relation) if op in ("drop_nulls", "deduplicate", "filter") else None
        con.execute(f"CREATE TEMP TABLE {target} AS {sql}")
        created.append(("table", f"__tb_step_{i}"))
        engine = {"engine": "duckdb", "sql": sql}

        if op == "cast":
            type_map = step["type_map"]
            nodes.append(LineageNode(
                operation=operation,
                description=f"Cast columns: {type_map}",
                metadata={"step": "cast", "type_map": type_map, **engine},
            ))
        elif op == "drop_nulls":
            subset = step["subset"]
            rows_after = count(con, target)
            nodes.append(LineageNode(
                operation=operation,
                description=(
                    f"Dropped nulls in {subset or 'all columns'} "
                    f"({rows_before - rows_after} rows removed)"
                ),
                metadata={
                    "step":         "drop_nulls",
                    "subset":       subset,
                    "rows_before":  rows_before,
                    "rows_after":   rows_after,
                    "rows_removed": rows_before - rows_after,
                    **engine,
                },
            ))
        elif op == "deduplicate":
            subset = step["subset"]
            rows_after = count(con, target)
            nodes.append(LineageNode(
                operation=operation,
                description=(
                    f"Deduplicated on {subset or 'all columns'} "
                    f"({rows_before - rows_after} rows removed)"
                ),
                metadata={
                    "step":               "deduplicate",
                    "subset":             subset,
                    "rows_before":        rows_before,
                    "rows_after":         rows_after,
                    "duplicates_dropped": rows_before - rows_after,
                    **engine,
                },
            ))
        elif op == "rename":
            columns_map = step["columns"]
            nodes.append(LineageNode(
                operation=operation,
                description=f"Renamed columns: {columns_map}",
                metadata={"step": "rename", "columns": columns_map, **engine},
            ))
        elif op == "filter":
            rows_after = count(con, target)
            nodes.append(LineageNode(
                operation=operation,
                description=step.get("description") or (
                    f"Filtered where {step['where']} "
                    f"({rows_before - rows_after} rows removed)"
                ),
                metadata={
                    "step":         "filter",
                    "where":        step["where"],
                    "rows_before":  rows_before,
                    "rows_after":   rows_after,
                    "rows_removed": rows_before - rows_after,
                    **engine,
                },
            ))
        relation = target
    return relation, nodes, created


def drop(con, created: list) -> None:
    """Drop the temporary relations :func:`run_steps` (or a caller) made.

    Needed where the connection outlives the run: an in-memory warehouse's
    connection is the connector's own.
    """
    for kind, name in reversed(created):
        if kind == "table":
            con.execute(f"DROP TABLE IF EXISTS {quote(name)}")
        elif kind == "view":
            con.execute(f"DROP VIEW IF EXISTS {quote(name)}")
        else:
            con.unregister(name)


class SinkTable:
    """What a layer that ran inside the warehouse returns.

    The same surface the runner reads from a ``DataSet`` — ``len()``, the
    lineage, the columns — with no frame behind it: the rows are in the sink
    table, and ``to_pandas()`` reads them from there only when asked.
    """

    def __init__(self, sink: Any, table: str, rows: int, columns: list[str],
                 lineage: list[LineageNode]) -> None:
        self.name = table
        self._sink = sink
        self._rows = rows
        self._columns = list(columns)
        self._lineage = list(lineage)

    @property
    def lineage(self) -> list[LineageNode]:
        return list(self._lineage)

    @property
    def columns(self) -> list[str]:
        return list(self._columns)

    @property
    def shape(self) -> tuple[int, int]:
        return (self._rows, len(self._columns))

    def __len__(self) -> int:
        return self._rows

    def to_pandas(self) -> "pd.DataFrame":
        return self._sink.load(self.name)

    def __repr__(self) -> str:
        return f"<SinkTable {self.name!r} rows={self._rows} cols={len(self._columns)}>"
