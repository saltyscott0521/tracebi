"""One read-only table API for every place a table lives.

A table is addressed as ``(source, table)``: *source* is a connector's name
(a warehouse, a SQL connection, frames held in memory) or ``inputs``, the
project's ``inputs/`` folder, where *table* is a file's path inside it. Four
routes answer for any of them: what the table is, a page of its rows, a
profile of its columns, and its rows as CSV.

Nothing free-form reaches SQL. The table must be in the source's own catalog
(or be a file under ``inputs/``, the path confined to that folder) before a
statement is built; every column a request names (a sort, a filter) must be
one of the table's columns; identifiers are quoted and refused when they carry
a quote; values are bound, never spliced; the ``where`` grammar is a closed
list of operators, checked by :func:`parse_where` before any SQL is composed.

DuckDB reads (a warehouse on any tier, a file, frames held in memory) go
through the locked, read-only query connection (:mod:`tracebi.model.engine`):
the warehouse attached READ_ONLY, a file as a view whose one path the lock
still allows, a frame registered after the lock. A SQL connection gets its
own short-lived engine for the request, released before the response ends,
and the project's statement timeout (``engine.query_timeout_s``) cancels a
statement that runs past it, as the query connection's timer does.

A source that cannot be reached here (its ``${VAR}`` unset, the database
refusing, nothing built yet) answers ``200 {connected: false, reason,
variable?}`` on every route, the shape ``/connectors/{name}/tables`` uses.
Framework tables (:func:`tracebi.sources.is_framework_table`) answer 404, as a
missing table does. Every route is a GET: a viewer may read, and folder
permissions do not apply (a table is not a report), except that ``used_by``
lists only the reports the caller may view. The one write is
``POST …/export``: a warehouse table sent to a connection or an object
prefix, for an admin (:func:`tracebi.warehouse.export_table`).
"""

from __future__ import annotations

import contextlib
import contextvars
import csv
import datetime
import io
import json
import math
import os
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tracebi.web.api.errors import error_detail
from tracebi.web.api.registry import registry

router = APIRouter(prefix="/tables", tags=["tables"])

#: The most rows one page carries; a reader pages for more, or exports.
MAX_LIMIT = 500

#: The closed ``where`` grammar: these operators and no others.
OPS = ("eq", "ne", "lt", "le", "gt", "ge", "contains", "is_null", "not_null")
_COMPARE = {"eq": "=", "ne": "<>", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}

#: Files under ``inputs/`` DuckDB reads as a table, and the reader for each.
_FILE_READERS = {".csv": "read_csv_auto", ".tsv": "read_csv_auto",
                 ".parquet": "read_parquet",
                 ".json": "read_json_auto", ".jsonl": "read_json_auto",
                 ".ndjson": "read_json_auto"}

#: DuckDB type prefixes by the class a profile treats them as.
_TIME_SQL = ("DATE", "TIMESTAMP", "TIME")

_EXPORT_BATCH = 2000


class Refused(ValueError):
    """A request the closed grammar does not admit. Answered 422, and raised
    before any SQL is composed from the request."""


class NotConnected(Exception):
    """The source cannot be read here; carries the 200 answer to give."""

    def __init__(self, answer: dict) -> None:
        super().__init__(answer.get("reason"))
        self.answer = answer


class NotInCatalog(LookupError):
    """The source is readable but holds no such table (404)."""


class Unsupported(Exception):
    """A kind of source these routes do not read (it cannot list a catalog)."""


# ── The closed grammar ──────────────────────────────────────────────────────


def quote(name: str) -> str:
    """A double-quoted identifier. One carrying a quote is refused rather than
    escaped: no catalog name a person explores needs one, and refusing
    leaves nothing to get wrong."""
    if '"' in name:
        raise Refused(f"Invalid identifier: {name!r}")
    return f'"{name}"'


def _value_fits(value: Any, cls: str) -> bool:
    """Whether *value* is a literal of the column's class: a number for a
    number, an ISO date or timestamp for a time, a string for text, a boolean
    for a boolean. A mismatch is the caller's mistake, refused before the
    database sees it."""
    if cls == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if cls == "bool":
        return isinstance(value, bool)
    if cls == "time":
        if not isinstance(value, str):
            return False
        try:
            datetime.datetime.fromisoformat(value)
        except ValueError:
            return False
        return True
    if cls == "text":
        return isinstance(value, str)
    return isinstance(value, (str, int, float, bool))


def parse_where(where: Any, classes: dict[str, str]) -> list[dict]:
    """The ``where`` parameter, checked against the table's columns.

    *where* is JSON text (or the parsed list): ``[{column, op, value}]``, where
    ``op`` is one of :data:`OPS` and ``column`` one of *classes* (``{column:
    "number" | "time" | "text" | "bool" | "other"}``). ``is_null`` and
    ``not_null`` take no value; ``contains`` takes a string; the comparisons
    take a literal of the column's class. Anything else raises
    :class:`Refused`. Pure: it runs no SQL."""
    if where is None or where == "":
        return []
    if isinstance(where, str):
        try:
            where = json.loads(where)
        except ValueError:
            raise Refused("where must be a JSON list of {column, op, value}")
    if not isinstance(where, list):
        raise Refused("where must be a JSON list of {column, op, value}")
    out = []
    for i, cond in enumerate(where):
        if not isinstance(cond, dict) or not set(cond) <= {"column", "op", "value"}:
            raise Refused(f"where[{i}] must be an object with column, op and value only")
        column, op = cond.get("column"), cond.get("op")
        if op not in OPS:
            raise Refused(f"where[{i}]: unknown op {op!r}; one of {', '.join(OPS)}")
        if not isinstance(column, str):
            raise Refused(f"where[{i}]: column must be a column name")
        quote(column)
        if column not in classes:
            raise Refused(f"where[{i}]: unknown column {column!r}")
        value = cond.get("value")
        if op in ("is_null", "not_null"):
            value = None
        elif op == "contains":
            if not isinstance(value, str) or not value:
                raise Refused(f"where[{i}]: contains takes a non-empty string")
        elif value is None or not _value_fits(value, classes[column]):
            raise Refused(f"where[{i}]: {op} on {column!r} takes a "
                          f"{classes[column] if classes[column] != 'other' else 'literal'} value")
        out.append({"column": column, "op": op, "value": value})
    return out


def _like(text: str) -> str:
    """A case-insensitive substring pattern for ``LIKE … ESCAPE '\\'``."""
    escaped = text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def build_filter(reader: "_Reader", where: list[dict], q: Optional[str],
                 sort: Optional[str], desc: bool) -> tuple[str, str, list]:
    """``(where_sql, order_sql, params)`` from parts :func:`parse_where` and
    the column check already admitted: quoted identifiers, bound values."""
    params: list = []

    def bind(value: Any) -> str:
        params.append(value)
        return reader.mark(len(params) - 1)

    clauses = []
    for cond in where:
        col, op = quote(cond["column"]), cond["op"]
        if op == "is_null":
            clauses.append(f"{col} IS NULL")
        elif op == "not_null":
            clauses.append(f"{col} IS NOT NULL")
        elif op == "contains":
            clauses.append(f"LOWER(CAST({col} AS VARCHAR)) LIKE {bind(_like(cond['value']))} ESCAPE '\\'")
        else:
            clauses.append(f"{col} {_COMPARE[op]} {bind(cond['value'])}")
    if q:
        texts = [name for name, cls in reader.classes.items() if cls == "text"]
        # A search matches text columns only; a table with none matches nothing.
        clauses.append("(" + " OR ".join(
            f"LOWER({quote(name)}) LIKE {bind(_like(q))} ESCAPE '\\'" for name in texts) + ")"
            if texts else "1 = 0")
    where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    order_sql = ""
    if sort is not None:
        if sort not in reader.classes:
            raise Refused(f"unknown sort column {sort!r}")
        order_sql = f" ORDER BY {quote(sort)} {'DESC' if desc else 'ASC'} NULLS LAST"
    return where_sql, order_sql, params


# ── Values out ──────────────────────────────────────────────────────────────


def _cell(value: Any) -> Any:
    """A value for JSON: numbers as numbers (NaN and infinity, which JSON
    lacks, as null), dates and timestamps as ISO strings, anything else the
    driver hands back as text."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, (float, Decimal)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, (list, tuple)):
        return [_cell(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _cell(v) for k, v in value.items()}
    return str(value)


# ── Readers ─────────────────────────────────────────────────────────────────


class _Reader:
    """A table opened for reading: its relation, its columns, and how a value
    is bound on this engine."""

    kind: str
    relation: str
    columns: list[dict]
    classes: dict[str, str]

    def mark(self, i: int) -> str:
        raise NotImplementedError

    def execute(self, sql: str, params: list):
        raise NotImplementedError

    def catalog_rows(self) -> tuple[Optional[int], bool]:
        """``(rows, exact)`` for the whole table, by the row-count rule."""
        raise NotImplementedError

    def unfiltered_total(self) -> tuple[Optional[int], bool]:
        """The total a page reports with no filter."""
        raise NotImplementedError


def _duck_class(dtype: str) -> str:
    from tracebi.workbench import _NUMERIC_SQL

    upper = dtype.upper()
    if any(upper.startswith(t) for t in _NUMERIC_SQL):
        return "number"
    if upper.startswith(_TIME_SQL):
        return "time"
    if upper.startswith("VARCHAR"):
        return "text"
    if upper == "BOOLEAN":
        return "bool"
    return "other"


class _DuckReader(_Reader):
    def __init__(self, con, relation: str, kind: str) -> None:
        self.con, self.relation, self.kind = con, relation, kind
        self.columns = [{"name": str(r[0]), "type": str(r[1])} for r in
                        con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()]
        self.classes = {c["name"]: _duck_class(c["type"]) for c in self.columns}

    def mark(self, i: int) -> str:
        return "?"

    def execute(self, sql: str, params: list):
        return self.con.execute(sql, params)

    def catalog_rows(self) -> tuple[Optional[int], bool]:
        return int(self.con.execute(f"SELECT count(*) FROM {self.relation}").fetchone()[0]), True

    unfiltered_total = catalog_rows


def _sql_class(sqltype) -> str:
    import sqlalchemy as sa

    if isinstance(sqltype, sa.Boolean):
        return "bool"
    if isinstance(sqltype, (sa.Integer, sa.Numeric)):
        return "number"
    if isinstance(sqltype, (sa.Date, sa.DateTime, sa.Time)):
        return "time"
    if isinstance(sqltype, sa.String):
        return "text"
    return "other"


def _sql_type(sqltype) -> str:
    try:
        return str(sqltype)
    except Exception:  # noqa: BLE001 — a type the dialect cannot spell
        return type(sqltype).__name__.upper()


class _SQLReader(_Reader):
    kind = "connection"

    def __init__(self, conn, table: str, reflected: list[dict]) -> None:
        self.conn, self.table, self.relation = conn, table, quote(table)
        self.columns = [{"name": str(c["name"]), "type": _sql_type(c["type"])} for c in reflected]
        self.classes = {str(c["name"]): _sql_class(c["type"]) for c in reflected}

    def mark(self, i: int) -> str:
        return f":p{i}"

    def execute(self, sql: str, params: list):
        from sqlalchemy import text

        return self.conn.execution_options(stream_results=True).execute(
            text(sql), {f"p{i}": v for i, v in enumerate(params)})

    def catalog_rows(self) -> tuple[Optional[int], bool]:
        from tracebi.sources import sql_row_estimates

        return sql_row_estimates(self.conn).get(self.table), False

    def unfiltered_total(self) -> tuple[Optional[int], bool]:
        # The catalog's estimate where there is one: an unfiltered count(*)
        # is the slow query on a large table. Else one exact count, under the
        # statement timeout.
        rows, exact = self.catalog_rows()
        if rows is not None:
            return rows, exact
        return int(self.execute(f"SELECT count(*) FROM {self.relation}", []).fetchone()[0]), True


class _InputFile:
    """One file under ``inputs/`` as a query connection sees it: a view over
    DuckDB's own reader, defined before the lock, and the one path the lock
    still allows (the shape :meth:`tracebi.warehouse.Warehouse.attach` has)."""

    def __init__(self, path: Path) -> None:
        self.path = str(path)
        self.reader = _FILE_READERS[path.suffix.lower()]

    def attach(self, con, alias: str) -> list[str]:
        literal = "'" + self.path.replace("'", "''") + "'"
        con.execute(f"CREATE VIEW {quote(alias)} AS SELECT * FROM {self.reader}({literal})")
        return [self.path]


def _input_path(table: str) -> Path:
    """The file *table* names under ``inputs/``, confined to that folder: no
    ``..``, no hidden file, nothing a link resolves to outside it."""
    from tracebi.sources import inputs_dir

    parts = table.split("/")
    if "\\" in table or any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        raise NotInCatalog(table)
    root = inputs_dir().resolve()
    path = (root / table).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise NotInCatalog(table)
    if path.suffix.lower() not in _FILE_READERS:
        raise Refused(f"inputs/{table} is not a file DuckDB reads as a table "
                      f"({', '.join(sorted(_FILE_READERS))})")
    return path


def _reason(exc: BaseException) -> str:
    from tracebi.sources import _reason as reason

    return reason(exc)


def _unreachable(exc: BaseException) -> NotConnected:
    from tracebi.connections import ConnectionConfigError

    if isinstance(exc, ConnectionConfigError) and getattr(exc, "variable", None):
        return NotConnected({"connected": False, "variable": exc.variable,
                             "reason": f"{exc.variable} is not set"})
    return NotConnected({"connected": False, "reason": _reason(exc)})


@contextlib.contextmanager
def _sql_timeout(conn) -> Iterator[None]:
    """The project's statement timeout on a SQL connection: a timer cancels
    the running statement (``cancel()`` on Postgres, ``interrupt()`` on
    SQLite), and the interrupted statement surfaces as QueryTimeout."""
    from tracebi.model.engine import QueryTimeout
    from tracebi.project_config import engine_settings

    limit = float(engine_settings()["query_timeout_s"])
    raw = conn.connection.dbapi_connection
    stop = getattr(raw, "cancel", None) or getattr(raw, "interrupt", None)
    fired = threading.Event()
    timer: Optional[threading.Timer] = None
    if stop is not None and limit > 0:
        def _stop() -> None:
            fired.set()
            stop()
        timer = threading.Timer(limit, _stop)
        timer.daemon = True
        timer.start()
    try:
        yield
    except Exception as exc:
        if fired.is_set():
            raise QueryTimeout(
                f"The read ran past the {limit:g} s limit and was stopped "
                f"(engine.query_timeout_s in tracebi.yaml).") from exc
        raise
    finally:
        if timer is not None:
            timer.cancel()


@contextlib.contextmanager
def _sql_reader(connector, table: str) -> Iterator[_SQLReader]:
    """A short-lived engine of the connection's own URL, for this request
    only: the connector's pooled engine is never borrowed, so nothing is held
    after the response."""
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.engine import make_url
    from sqlalchemy.pool import NullPool

    try:
        url = connector.url
        options: dict = {"poolclass": NullPool}
        if make_url(url).get_backend_name() == "sqlite":
            # An export streams across the server's worker threads.
            options["connect_args"] = {"check_same_thread": False}
        engine = create_engine(url, **options)
    except Exception as exc:  # noqa: BLE001 — an unresolvable URL is an answer
        raise _unreachable(exc)
    try:
        try:
            catalog = inspect(engine)
            names = catalog.get_table_names()
            reflected = catalog.get_columns(table) if table in names else None
            conn = engine.connect()
        except Exception as exc:  # noqa: BLE001 — an unreachable database is an answer
            raise _unreachable(exc)
        try:
            if reflected is None:
                raise NotInCatalog(table)
            with _sql_timeout(conn):
                yield _SQLReader(conn, table, reflected)
        finally:
            conn.close()
    finally:
        engine.dispose()


def _warehouse_target(connector):
    wh = getattr(connector, "warehouse", None)
    return wh.sink if wh is not None else str(connector.describe()["database"])


@contextlib.contextmanager
def open_table(connector, table: str) -> Iterator[_Reader]:
    """Open *table* of *connector* for reading. Raises :class:`NotConnected`
    (answer 200 with it), :class:`NotInCatalog` (404), :class:`Unsupported`
    (a kind of source these routes do not read)."""
    from tracebi.connectors.memory_connector import MemoryConnector
    from tracebi.connectors.sql_connector import SQLConnector
    from tracebi.model.engine import query_connection, statement_timeout
    from tracebi.sources import is_framework_table, is_warehouse

    if is_framework_table(table):
        raise NotInCatalog(table)
    if is_warehouse(connector.describe()):
        from tracebi.warehouse import as_warehouse

        warehouse = as_warehouse(_warehouse_target(connector))
        try:
            built = warehouse.exists()
        except Exception as exc:  # noqa: BLE001 — an unresolvable address is an answer
            raise _unreachable(exc)
        if not built:
            raise NotConnected({"connected": False, "reason": "Nothing is built here yet."})
        with statement_timeout(), query_connection({"wh": warehouse}, default="wh") as con:
            if "wh" not in con.attached:
                raise NotConnected({"connected": False,
                                    "reason": _reason(RuntimeError(con.attach_errors.get("wh", "")))})
            names = dict(con.execute(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_catalog = 'wh' AND table_schema = 'main'").fetchall())
            if table not in names:
                raise NotInCatalog(table)
            reader = _DuckReader(con, f'"wh"."main".{quote(table)}', "warehouse")
            # On the object tier every table is a view over its Parquet file:
            # the reader's mechanics, not a sink view.
            reader.table_kind = ("view" if warehouse.tier != "object" and names[table] == "VIEW"
                                 else "table")
            yield reader
        return
    if isinstance(connector, MemoryConnector):
        if table not in connector.list_tables():
            raise NotInCatalog(table)
        frame = connector.load(table)
        with statement_timeout(), query_connection() as con:
            con.register("t", frame)
            yield _DuckReader(con, '"t"', "connection")
        return
    if isinstance(connector, SQLConnector):
        with _sql_reader(connector, table) as reader:
            yield reader
        return
    raise Unsupported(type(connector).__name__)


@contextlib.contextmanager
def open_source(source: str, table: str) -> Iterator[_Reader]:
    """:func:`open_table` by address: a registered connector's name, or
    ``inputs`` for a file under the project's ``inputs/`` folder."""
    from tracebi.model.engine import query_connection, statement_timeout

    if source == "inputs":
        path = _input_path(table)
        with statement_timeout(), query_connection({"src": _InputFile(path)}) as con:
            if "src" not in con.attached:
                raise NotConnected({"connected": False,
                                    "reason": _reason(RuntimeError(con.attach_errors.get("src", "")))})
            yield _DuckReader(con, '"src"', "file")
        return
    connector = registry.get_connector(source)
    if connector is None:
        raise NotInCatalog(source)
    with open_table(connector, table) as reader:
        yield reader


# ── What a page asks for ────────────────────────────────────────────────────


def read_rows(reader: _Reader, *, offset: int = 0, limit: int = 100,
              sort: Optional[str] = None, desc: bool = False,
              q: Optional[str] = None, where: Any = None) -> dict:
    """One page of rows: ``{columns, rows, offset, limit, total, total_exact,
    elapsed_ms}``. The total is exact for DuckDB and for any filtered read;
    an unfiltered SQL connection reports its catalog estimate where it keeps
    one (``total_exact: false``)."""
    started = time.perf_counter()
    conditions = parse_where(where, reader.classes)
    where_sql, order_sql, params = build_filter(reader, conditions, q, sort, desc)
    rows = reader.execute(
        f"SELECT * FROM {reader.relation}{where_sql}{order_sql} "
        f"LIMIT {int(limit)} OFFSET {int(offset)}", params).fetchall()
    if where_sql:
        total, exact = int(reader.execute(
            f"SELECT count(*) FROM {reader.relation}{where_sql}", params).fetchone()[0]), True
    else:
        total, exact = reader.unfiltered_total()
    return {
        "columns": reader.columns,
        "rows": [[_cell(v) for v in row] for row in rows],
        "offset": offset,
        "limit": limit,
        "total": total,
        "total_exact": exact,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def profile_table(reader: _Reader) -> dict:
    """``{rows, columns: {name: {type, nulls, null_share, distinct, min, max,
    mean?, top}}}``, by read-only aggregates. ``min``/``max`` are given for
    numbers and times (null otherwise), ``mean`` for numbers only, ``top``
    (the five commonest values with their counts) for text and booleans
    (empty otherwise). Past :data:`~tracebi.workbench.PROFILE_COLUMN_CAP`
    columns nothing is profiled, and ``note`` says why."""
    from tracebi.workbench import PROFILE_COLUMN_CAP

    rel = reader.relation
    rows = int(reader.execute(f"SELECT count(*) FROM {rel}", []).fetchone()[0])
    if len(reader.columns) > PROFILE_COLUMN_CAP:
        return {"rows": rows, "columns": {},
                "note": f"profile skipped — {len(reader.columns)} columns (cap {PROFILE_COLUMN_CAP})"}
    out: dict = {}
    for column in reader.columns:
        name, cls = column["name"], reader.classes[column["name"]]
        col = quote(name)
        aggregates = f"COUNT({col}), COUNT(DISTINCT {col})"
        if cls in ("number", "time"):
            aggregates += f", MIN({col}), MAX({col})"
        if cls == "number":
            aggregates += f", AVG({col})"
        got = reader.execute(f"SELECT {aggregates} FROM {rel}", []).fetchone()
        nulls = rows - int(got[0])
        stats: dict = {"type": column["type"], "nulls": nulls,
                       "null_share": (nulls / rows) if rows else 0.0,
                       "distinct": int(got[1]),
                       "min": _cell(got[2]) if cls in ("number", "time") else None,
                       "max": _cell(got[3]) if cls in ("number", "time") else None,
                       "top": []}
        if cls == "number":
            stats["mean"] = _cell(got[4])
        if cls in ("text", "bool"):
            stats["top"] = [{"value": _cell(v), "count": int(n)} for v, n in reader.execute(
                f"SELECT {col}, COUNT(*) AS n FROM {rel} WHERE {col} IS NOT NULL "
                f"GROUP BY {col} ORDER BY n DESC, {col} LIMIT 5", []).fetchall()]
        out[name] = stats
    return {"rows": rows, "columns": out}


def _csv_text(value: Any) -> Any:
    value = _cell(value)
    return "" if value is None else value


def csv_lines(reader: _Reader, *, sort: Optional[str] = None, desc: bool = False,
              q: Optional[str] = None, where: Any = None) -> Iterator[str]:
    """The cut as CSV text, a batch at a time, straight from the engine's
    cursor: no frame is built."""
    conditions = parse_where(where, reader.classes)
    where_sql, order_sql, params = build_filter(reader, conditions, q, sort, desc)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([c["name"] for c in reader.columns])
    cursor = reader.execute(f"SELECT * FROM {reader.relation}{where_sql}{order_sql}", params)
    while True:
        batch = cursor.fetchmany(_EXPORT_BATCH)
        if not batch:
            break
        writer.writerows([_csv_text(v) for v in row] for row in batch)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
    if buf.tell():
        yield buf.getvalue()


def stream_csv(opener, filename: str, **cut) -> StreamingResponse:
    """A CSV download of the cut. *opener* is a zero-argument context manager
    factory opening the table: the stream opens its own reader, because the
    response is iterated after the route returns, on the server's worker
    threads; the statement timeout is set inside it for the same reason."""
    def chunks() -> Iterator[str]:
        with opener() as reader:
            yield from csv_lines(reader, **cut)

    def in_one_context(gen: Iterator[str]) -> Iterator[str]:
        # The server steps the stream on whichever worker thread is free, each
        # step in a fresh copy of the context; the timeout's context variable
        # must be set and reset in one, so every step runs in this one.
        ctx = contextvars.copy_context()
        try:
            while True:
                try:
                    chunk = ctx.run(next, gen)
                except StopIteration:
                    return
                yield chunk
        finally:
            ctx.run(gen.close)

    safe = "".join(c for c in filename if c.isalnum() or c in "._- ") or "export"
    return StreamingResponse(in_one_context(chunks()), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{safe}.csv"'})


# ── What else is known about a table ────────────────────────────────────────


def _models_reading(source: str, table: str) -> list[str]:
    out = []
    for info in registry.list_models():
        model = registry.get_model(info["name"])
        if model is None:
            continue
        if any(t["connector"] == source and t["source"] == table
               for t in model.info().get("tables", [])):
            out.append(model.name)
    return out


def _used_by(models: list[str]) -> list[dict]:
    """The reports, of those the caller may view, whose bindings read one of
    *models*."""
    if not models:
        return []
    from tracebi.web.api.routers.reports import _can_view, _library_package

    out = []
    for item in registry.list_reports():
        if not _can_view(item["name"]):
            continue
        try:
            read = _library_package(item["name"])[2]
        except Exception:  # noqa: BLE001 — an unreadable report reads nothing
            continue
        if set(read) & set(models):
            out.append({"report": item["name"], "display_name": item["display_name"]})
    return out


def _shown(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return os.path.relpath(path, os.getcwd()).replace(os.sep, "/")
    except ValueError:
        return str(path)


def _warehouse_facts(connector, table: str, view: bool = False) -> dict:
    """Who wrote a warehouse table, its sink contract judged now, and what the
    run that wrote it read from outside the warehouse: the certificate's
    record, as the Warehouse page reads it. For a sink view (*view*), also
    the transform that defined it and the tables it reads, which the
    certificate records whether or not a check touches the view."""
    from tracebi.contracts import columns_from, read_contracts, table_statuses, view_record
    from tracebi.sources import _contract_owners
    from tracebi.transforms import contract_file, find_transform

    target = _warehouse_target(connector)
    status = table_statuses(target, [table])[table]
    record = status.get("transform")
    at = status.get("checked_at")
    owners = _contract_owners()
    certs = read_contracts(target)
    defined = view_record(certs, table) if view else None
    if not record and defined:
        record, at = defined["contract"], defined["checked_at"]
    transform = owners.get(record) if record else None
    # The file declaring checks, only where a check covers this table.
    path = find_transform(transform) if transform and status.get("transform") else None
    file = (contract_file(path) or path) if path else None
    extra = {}
    if view:
        extra["view"] = {"transform": owners.get(defined["contract"]) if defined else None,
                         "bases": defined["bases"] if defined else []}
    return {
        **extra,
        # Each column's bases, as DuckDB's parse of a SQL transform proved
        # them; null for a pandas transform or a table written outside one.
        "columns_from": columns_from(certs, table),
        "written_by": ({"transform": transform, "contract": record,
                        "at": at} if record else None),
        "contract": {"status": status["status"], "file": _shown(file),
                     "checks": status.get("checks"), "note": status.get("note"),
                     "checked_at": status.get("checked_at")},
        "transform_read": [
            {"ref": ref,
             # The committed snapshot stood in for the connection on that run.
             "snapshot": src.get("fallback") if src.get("source_fallback") else None,
             "fingerprint": src.get("fingerprint")}
            for ref, src in (status.get("sources") or {}).items()],
    }


# ── Routes ──────────────────────────────────────────────────────────────────
#
# The suffixed routes come first: ``{table:path}`` would otherwise take
# ``fact_holdings/rows`` as the table's name.


def _answer(source: str, table: str, read):
    """Run *read* on the opened table, mapping what can go wrong to the
    answer each case gets."""
    from tracebi.model.engine import QueryTimeout

    try:
        with open_source(source, table) as reader:
            return read(reader)
    except NotConnected as exc:
        return exc.answer
    except NotInCatalog:
        raise HTTPException(status_code=404, detail=f"No table '{table}' in '{source}'")
    except Unsupported as exc:
        return {"connected": False,
                "reason": f"A {exc} source cannot list its tables, so they are not read here."}
    except Refused as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except QueryTimeout as exc:
        raise HTTPException(status_code=504, detail=error_detail("Read stopped", exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=error_detail("Read failed", exc))


@router.get("/{source}/{table:path}/rows")
def table_rows(source: str, table: str,
               offset: int = Query(0, ge=0),
               limit: int = Query(100, ge=1, le=MAX_LIMIT),
               sort: Optional[str] = None, desc: bool = False,
               q: Optional[str] = None, where: Optional[str] = None):
    """A page of rows: ``{columns: [{name, type}], rows: [[…]], offset,
    limit, total, total_exact, elapsed_ms}``. ``sort`` names a column
    (``desc=1`` reverses it); ``q`` matches text columns, case-insensitively;
    ``where`` is a JSON list of ``{column, op, value}``, op one of
    eq, ne, lt, le, gt, ge, contains, is_null, not_null."""
    return _answer(source, table, lambda r: read_rows(
        r, offset=offset, limit=limit, sort=sort, desc=desc, q=q, where=where))


@router.get("/{source}/{table:path}/profile")
def table_profile(source: str, table: str):
    """Each column's type, nulls (count and share), distinct values, range
    (numbers and dates), mean (numbers) and commonest values with counts
    (text): one table, read on request."""
    return _answer(source, table, profile_table)


@router.get("/{source}/{table:path}/export.csv")
def table_export(source: str, table: str, sort: Optional[str] = None,
                 desc: bool = False, q: Optional[str] = None,
                 where: Optional[str] = None):
    """The cut (``sort``, ``q``, ``where`` as for ``/rows``) as CSV, streamed
    from the engine. A request the grammar refuses is refused before the
    download starts."""
    cut = {"sort": sort, "desc": desc, "q": q, "where": where}

    def check(reader):
        build_filter(reader, parse_where(where, reader.classes), q, sort, desc)

    answer = _answer(source, table, check)
    if answer is not None:
        return answer           # not connected, or not a source read here
    return stream_csv(lambda: open_source(source, table), table.rsplit("/", 1)[-1], **cut)


class ExportBody(BaseModel):
    to: str


@router.post("/{source}/{table:path}/export")
def table_export_to(source: str, table: str, body: ExportBody):
    """Write a warehouse table or view to ``to``: a connection's name (the
    table replaced there, through its connector) or an object prefix
    (``s3://…``, ``gs://…``, or a folder in the project) as
    ``<table>.parquet``. Admin (``_required_role``); recorded as a run,
    ``kind: export``. Answers ``{table, to, kind, rows, path?}``."""
    from tracebi.connections import ConnectionConfigError
    from tracebi.project_config import warehouse as project_warehouse
    from tracebi.sources import is_warehouse
    from tracebi.warehouse import ExportError, WarehouseConfigError, as_warehouse, export_table

    connector = registry.get_connector(source)
    if connector is None:
        raise HTTPException(status_code=404, detail=f"No source '{source}'")
    if not is_warehouse(connector.describe()) or (
            as_warehouse(_warehouse_target(connector)).address != project_warehouse().address):
        raise HTTPException(status_code=422, detail=(
            f"'{source}' is not the workspace's warehouse; only its tables and views "
            f"are exported from here"))
    try:
        return export_table(table, body.to)
    except (ExportError, ConnectionConfigError, WarehouseConfigError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=error_detail("Export failed", exc))


@router.get("/{source}/{table:path}")
def table_detail(source: str, table: str):
    """What the table is: ``{source, table, kind, rows, rows_exact, columns,
    written_by, contract, columns_from, read_by, used_by, transform_read}``. ``rows`` is
    exact for DuckDB and files, the catalog's estimate for a SQL connection
    that keeps one (``rows_exact: false``), else null. A warehouse table also
    says ``table_kind`` (``table`` or ``view``; ``kind`` names the kind of
    source), and a sink view ``view: {transform, bases}`` from the
    certificate. ``columns_from`` is a SQL transform's column lineage
    (``{column: {from, via} | {from: null, reason}}``), else null."""
    def describe(reader):
        rows, exact = reader.catalog_rows()
        out = {"kind": reader.kind, "rows": rows, "rows_exact": exact,
               "columns": reader.columns}
        if reader.kind == "warehouse":
            out["table_kind"] = reader.table_kind
        return out

    got = _answer(source, table, describe)
    if "connected" in got:
        return got
    models = [] if source == "inputs" else _models_reading(source, table)
    facts: dict = {"written_by": None, "contract": None, "columns_from": None,
                   "transform_read": []}
    if got["kind"] == "warehouse":
        # After the reader has closed: the contract join opens the file itself.
        facts = _warehouse_facts(registry.get_connector(source), table,
                                 view=got["table_kind"] == "view")
    return {"source": source, "table": table, **got, **facts,
            "read_by": models, "used_by": _used_by(models)}
