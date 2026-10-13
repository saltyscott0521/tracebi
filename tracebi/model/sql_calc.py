"""SQL calculations: a named SELECT over a model's warehouse, run read-only.

A report declares one in ``report.json`` (``sql_calculations``) and a data
binding names it (``{"model": ..., "sql": ...}``). It runs in DuckDB against
the model's file-backed warehouse. The warehouse is attached read-only into a
fresh in-memory engine, which then switches external access off and locks the
configuration, so the SQL reaches no other file, extension, network or write.

It is stamped like a model query: the lineage carries the SQL, a fingerprint
of each warehouse table it reads, and the result fingerprint, so
``tracebi verify`` re-runs it and compares.

``{{ measure('name') }}`` expands to a model measure in SQL. Only simple
measures (sum, count, mean, min, max, nunique of one column), optionally with
their own filter on the fact's columns, expand; any other kind is refused by
name. The rows come back in a canonical order (by columns, left to right), so
the fingerprint does not depend on the engine's scan order.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Any

from tracebi.model.dataset import (
    CURRENT_FINGERPRINT_ALGO,
    DataSet,
    LineageNode,
    frame_fingerprint,
)

_MEASURE_REF = re.compile(
    r"\{\{\s*measure\(\s*(['\"])([A-Za-z_][A-Za-z0-9_]*)\1\s*\)\s*\}\}")
_OPENERS = frozenset({"SELECT", "WITH"})
_AGGREGATES = {"sum": "SUM", "count": "COUNT", "mean": "AVG", "avg": "AVG",
               "min": "MIN", "max": "MAX"}
_COMPARE = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}


@dataclass(frozen=True)
class SqlQuery:
    """A SQL calculation as data: the SELECT text, with ``{{ measure() }}``
    placeholders still in it. It is what a binding stamps, so the receipt holds
    the SQL the author wrote; the expansion uses the model's current definitions,
    as a model query does.

    It has no fact, measures or filters of its own. The attributes below are
    the empty values the report plumbing reads from any query, so a SQL binding
    passes through code written for model queries.
    """
    sql: str

    fact = None
    measures = ()
    dimensions = ()
    filters = None
    having = None
    calculated = None
    order_by = ()
    limit = None

    def to_dict(self) -> dict:
        return {"sql": self.sql}

    @classmethod
    def from_dict(cls, d: dict) -> "SqlQuery":
        unknown = set(d) - {"sql"}
        if unknown:
            raise ValueError(
                f"Unknown SQL calculation field(s): {sorted(unknown)}. Allowed: sql.")
        sql = d.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("A SQL calculation needs its 'sql' text.")
        return cls(sql=sql)


def _first_keyword(sql: str) -> str:
    """The leading keyword, past whitespace and comments, upper-cased."""
    text = sql
    while True:
        text = text.lstrip()
        if text.startswith("--"):
            nl = text.find("\n")
            text = "" if nl < 0 else text[nl + 1:]
        elif text.startswith("/*"):
            end = text.find("*/")
            text = "" if end < 0 else text[end + 2:]
        else:
            break
    match = re.match(r"[A-Za-z]+", text)
    return match.group(0).upper() if match else ""


def check_read_only(sql: str) -> None:
    """Refuse anything but one SELECT or WITH statement.

    Structural: needs no warehouse, so a report is refused at discovery and a
    draft at write time. The engine enforces it again at run time. The type
    check alone is not enough: DuckDB types ``PRAGMA database_list`` as a
    SELECT, so the leading keyword must also be SELECT or WITH.
    """
    import duckdb

    text = _MEASURE_REF.sub("NULL", sql)
    try:
        statements = list(duckdb.extract_statements(text))
    except duckdb.Error as exc:
        raise ValueError(f"SQL calculation does not parse: {exc}") from exc
    if not statements:
        raise ValueError("SQL calculation is empty: write one SELECT statement.")
    if len(statements) != 1:
        raise ValueError(
            f"SQL calculation must be one statement, found {len(statements)}. "
            "Write one SELECT per calculation.")
    # The author's own leading keyword: DuckDB's rewritten query text turns
    # PRAGMA into SELECT * FROM pragma_..., so it cannot be read from there.
    head = _first_keyword(text)
    if statements[0].type != duckdb.StatementType.SELECT or head not in _OPENERS:
        raise ValueError(
            f"SQL calculation may only read: it must start with SELECT or WITH, "
            f"not {head or statements[0].type}. Writes, ATTACH, COPY, PRAGMA, "
            "SET, INSTALL and LOAD are refused.")


def _ident(name: Any) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _lit(value: Any) -> str:
    """A filter value as a SQL literal. Values come from the model file or the
    report's own declaration, never from a request."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"A filter value {value!r} is not a finite number.")
        return repr(float(value))
    return "'" + str(value).replace("'", "''") + "'"


def _filter_keys(node: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in ("or", "and") and isinstance(value, (list, tuple)):
                for sub in value:
                    out |= _filter_keys(sub)
            else:
                out.add(str(key))
    return out


def _predicate_sql(pred, name: str) -> str:
    if pred.is_dim:
        raise ValueError(
            f"Measure '{name}' filters on '{pred.target}', a dimension attribute. "
            "A SQL calculation can expand only a measure whose filter names the "
            "fact's own columns.")
    col, op, value = _ident(pred.target), pred.op, pred.value
    if op in _COMPARE:
        return f"{col} {_COMPARE[op]} {_lit(value)}"
    if op == "between":
        return f"{col} BETWEEN {_lit(value[0])} AND {_lit(value[1])}"
    if op in ("in", "not_in"):
        if not value:
            return "FALSE" if op == "in" else "TRUE"
        neg = "NOT " if op == "not_in" else ""
        return f"{col} {neg}IN ({', '.join(_lit(v) for v in value)})"
    if op == "is_null":
        return f"{col} IS NULL"
    if op == "not_null":
        return f"{col} IS NOT NULL"
    raise ValueError(
        f"Measure '{name}' filters with '{op}', which a SQL calculation cannot "
        "expand yet.")


def _condition_sql(node, name: str) -> str:
    if node.op == "leaf":
        return _predicate_sql(node.predicate, name)
    parts = [_condition_sql(child, name) for child in node.children]
    return "(" + (" AND " if node.op == "and" else " OR ").join(parts) + ")"


def _measure_sql(model, mdef) -> str:
    """One simple measure as an aggregate expression over the fact's columns."""
    name = mdef.name
    if mdef.kind != "simple" or not mdef.column:
        raise ValueError(
            f"Measure '{name}' is a {mdef.kind} measure. A SQL calculation can "
            "reference simple measures (sum, count, mean, min, max, nunique of "
            "one column) and filtered measures; write that calculation out in SQL "
            "or query the model.")
    agg = str(mdef.agg or "").lower()
    col = _ident(mdef.column)
    if agg == "nunique":
        body = f"COUNT(DISTINCT {col})"
    elif agg in _AGGREGATES:
        body = f"{_AGGREGATES[agg]}({col})"
    else:
        raise ValueError(
            f"Measure '{name}' aggregates '{agg}', which a SQL calculation cannot "
            "expand yet (sum, count, mean, min, max, nunique).")
    if mdef.filters:
        node = model._parse_filter_dict(mdef.filters, None, _filter_keys(mdef.filters))
        body += f" FILTER (WHERE {_condition_sql(node, name)})"
    return body


def expand(model, sql: str) -> tuple[str, dict]:
    """Replace each ``{{ measure('name') }}`` with the model's measure in SQL.

    Returns ``(resolved_sql, definitions_used)``. A name the model does not
    declare is refused by name.
    """
    defs = model.measures()
    used: dict[str, dict] = {}

    def replace(match) -> str:
        name = match.group(2)
        if name not in defs:
            raise ValueError(
                f"SQL calculation refers to measure '{name}', which model "
                f"'{model.name}' does not declare.")
        used[name] = defs[name].to_dict()
        return "(" + _measure_sql(model, defs[name]) + ")"

    resolved = _MEASURE_REF.sub(replace, sql)
    if "{{" in resolved:
        raise ValueError(
            "The only template in a SQL calculation is {{ measure('name') }}.")
    return resolved, used


def _warehouse(model):
    """The model's one file-backed DuckDB warehouse."""
    from tracebi.connectors.duckdb_connector import DuckDBConnector

    files = [c for c in model.connectors()
             if isinstance(c, DuckDBConnector) and c.database != ":memory:"]
    if len(files) != 1:
        raise ValueError(
            f"Model '{model.name}' needs exactly one file-backed DuckDB warehouse "
            f"to run a SQL calculation; it has {len(files)}.")
    return files[0]


def _tables_read(con, sql: str) -> set[str]:
    """Base-table names the statement references (CTE names included; the
    caller intersects them with the warehouse's own tables)."""
    import json

    tree = json.loads(con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0])
    if tree.get("error"):
        raise ValueError(f"SQL calculation does not bind: {tree.get('error_message')}")
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "BASE_TABLE" and node.get("table_name"):
                names.add(str(node["table_name"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(tree)
    return names


def run(model, query: SqlQuery) -> DataSet:
    """Run a SQL calculation against the model's warehouse, read-only, and
    return a lineage-tracked DataSet (the same shape a model query returns)."""
    import duckdb

    check_read_only(query.sql)
    connector = _warehouse(model)
    resolved, used = expand(model, query.sql)
    check_read_only(resolved)
    path = os.path.abspath(connector.database)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"DuckDB database file '{connector.database}' does not exist. Run the "
            "transform that sinks this warehouse first.")

    quoted = path.replace("'", "''")
    con = duckdb.connect(":memory:")
    try:
        con.execute(f"ATTACH '{quoted}' AS wh (READ_ONLY)")
        con.execute("USE wh")
        # Locked before the author's SQL runs: no file, extension, or network
        # access, and no way to switch it back on.
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")
        base = {row[0] for row in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog = 'wh' AND table_schema = 'main' "
            "AND table_type = 'BASE TABLE'").fetchall()}
        inputs = [(t, con.execute(f"SELECT * FROM {_ident(t)}").df())
                  for t in sorted(_tables_read(con, resolved) & base)]
        df = con.execute(resolved).df()
        engine_version = duckdb.__version__
    finally:
        con.close()

    cols = list(df.columns)
    if cols and len(df):
        try:
            df = df.sort_values(by=cols, kind="mergesort").reset_index(drop=True)
        except TypeError:
            df = df.sort_values(by=cols, key=lambda s: s.astype(str),
                                kind="mergesort").reset_index(drop=True)

    lineage = [
        LineageNode(
            operation="load",
            description=f"Read '{table}' from warehouse '{connector.name}' for a SQL calculation",
            connector={"connector_name": connector.name,
                       "connector_type": type(connector).__name__},
            source=table,
            metadata={"input": {"table": table,
                                "fingerprint": frame_fingerprint(frame),
                                "rows": len(frame)}},
        )
        for table, frame in inputs
    ]
    lineage.append(LineageNode(
        operation="transform",
        description="SQL calculation executed read-only via DuckDB",
        metadata={
            "engine": "duckdb",
            "engine_version": engine_version,
            "fingerprint_algo": CURRENT_FINGERPRINT_ALGO,
            "rows_out": len(df),
            "model": model.name,
            "query_spec": query.to_dict(),
            "sql_resolved": resolved,
            "sql_measures": used,
        },
    ))
    return DataSet(df=df, name="sql_calculation", lineage=lineage)
