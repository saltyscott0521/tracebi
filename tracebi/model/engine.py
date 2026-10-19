"""The query connection: one locked, read-only DuckDB per model query.

Every model query (``DataModel.execute``), every SQL calculation and every
page replay the server runs goes through :func:`query_connection`. It opens a
fresh in-memory DuckDB, applies the project's limits (``tracebi.yaml``
``engine``: ``memory_limit``, ``threads``, ``temp_directory``), attaches each
warehouse file READ_ONLY, and then switches external access off and locks the
configuration. From that point the connection can read the attached tables
and the frames the caller registers, and nothing else: no other file, no
URL (``read_csv('http://…')`` is a read), no ``ATTACH``, ``COPY``,
``INSTALL`` or ``LOAD``, and no ``SET`` that would switch any of it back on.
DuckDB enforces it, not a parser of ours.

The transform side is deliberately NOT built on this. ``run-transform``,
``DuckDBConnector.write`` and the sink contracts open their own connections:
a transform is reviewed code that pulls from the outside world (files, URLs,
extensions) and writes the warehouse, and it runs only from the CLI, the
scheduler or an approved code request. A query connection answers a reader.

A statement timeout is opt-in per call site, through :func:`statement_timeout`
(the web query route, the selection endpoint and the agent gateway's query
tool use it): a timer calls ``con.interrupt()`` when it runs out, and the
interrupted query surfaces as :class:`QueryTimeout`, naming the limit.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import threading
from typing import Iterator, Optional

#: The timeout, in seconds, the current context's queries run under; None is
#: no limit (a build, ``verify``, a notebook).
_timeout: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar(
    "tracebi_query_timeout", default=None)


class QueryTimeout(TimeoutError):
    """A query ran past the statement timeout and was interrupted."""


@contextlib.contextmanager
def statement_timeout(seconds: Optional[float] = None) -> Iterator[float]:
    """Run the queries in this block under a timeout (default: the project's
    ``engine.query_timeout_s``, 30 s)."""
    if seconds is None:
        from tracebi.project_config import engine_settings
        seconds = engine_settings()["query_timeout_s"]
    token = _timeout.set(float(seconds))
    try:
        yield float(seconds)
    finally:
        _timeout.reset(token)


def _sql_str(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@contextlib.contextmanager
def query_connection(warehouses: "Optional[dict[str, str]]" = None,
                     default: Optional[str] = None):
    """A locked in-memory DuckDB with each of *warehouses* (``{alias: path}``)
    attached READ_ONLY. *default* is the alias ``USE``d, so an unqualified
    table name in a model's ``SELECT`` source resolves in that warehouse.

    A file that cannot be attached (missing, or held read-write by a writer)
    is left out rather than failing the connection; its tables then fail by
    name when a query reads them. ``con.attached`` lists the aliases that
    made it, ``con.attach_errors`` why any other did not.
    """
    import duckdb
    from tracebi.project_config import engine_settings

    settings = engine_settings()
    con = duckdb.connect(":memory:")
    timer: Optional[threading.Timer] = None
    fired = threading.Event()
    limit = _timeout.get()
    try:
        con.execute(f"SET memory_limit = {_sql_str(settings['memory_limit'])}")
        con.execute(f"SET threads = {int(settings['threads'])}")
        con.execute(f"SET temp_directory = {_sql_str(settings['temp_directory'])}")
        attached: list[str] = []
        errors: dict[str, str] = {}
        for alias, path in (warehouses or {}).items():
            try:
                con.execute(f"ATTACH {_sql_str(os.path.abspath(path))} "
                            f'AS "{alias}" (READ_ONLY)')
            except duckdb.Error as exc:
                errors[alias] = str(exc)
                continue
            attached.append(alias)
        if default in attached:
            con.execute(f'USE "{default}"')
        # Locked before any query runs: no file, extension, or network access,
        # and no way to switch it back on from SQL.
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")
        if limit is not None:
            def _stop() -> None:
                fired.set()
                con.interrupt()
            timer = threading.Timer(limit, _stop)
            timer.daemon = True
            timer.start()
        yield _Connection(con, attached, errors)
        if fired.is_set():
            raise _timed_out(limit)
    except duckdb.InterruptException as exc:
        if fired.is_set():
            raise _timed_out(limit) from exc
        raise
    finally:
        if timer is not None:
            timer.cancel()
        con.close()


def _timed_out(limit: Optional[float]) -> QueryTimeout:
    return QueryTimeout(
        f"The query ran past the {limit:g} s limit and was stopped "
        f"(engine.query_timeout_s in tracebi.yaml). Narrow it with filters, "
        f"fewer dimensions or a limit, or raise the limit.")


class _Connection:
    """The DuckDB connection, plus which warehouses it attached (and why
    any it could not)."""

    def __init__(self, con, attached: list[str], errors: dict[str, str]) -> None:
        self._con = con
        self.attached = attached
        self.attach_errors = errors

    def __getattr__(self, name):
        return getattr(self._con, name)


# ── Warehouse table fingerprints ────────────────────────────────────────────
#
# A query that reads the warehouse through views loads nothing into pandas,
# but its lineage still records each table's fingerprint the way it always
# has: the frame the connector's load() returns (filtered when the load was
# pushed down), hashed with frame_fingerprint. That is the join contracts and
# verify rely on, so it is computed exactly that way, through the connector,
# and remembered against the warehouse file's size and modification time:
# one build (dozens of figures over the same tables) hashes each table once,
# and a rewrite of the file is a new key.

_FP_CACHE: dict[tuple, tuple[str, int]] = {}
_FP_CACHE_MAX = 256
_fp_lock = threading.Lock()


def _file_stamp(path: str) -> tuple:
    out = []
    for p in (path, path + ".wal"):
        try:
            st = os.stat(p)
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


def warehouse_table_fingerprint(connector, source: str,
                                filter: Optional[dict] = None) -> tuple[str, int]:
    """``(fingerprint, rows)`` of ``connector.load(source, filter=filter)``."""
    from tracebi.model.dataset import frame_fingerprint

    path = os.path.abspath(connector.database)
    key = (path, _file_stamp(path), connector.directory, source,
           tuple(sorted((str(k), type(v).__name__, repr(v))
                        for k, v in (filter or {}).items())))
    with _fp_lock:
        hit = _FP_CACHE.get(key)
    if hit is not None:
        return hit
    df = connector.load(source, filter=filter or None)
    value = (frame_fingerprint(df), len(df))
    with _fp_lock:
        if len(_FP_CACHE) >= _FP_CACHE_MAX:
            _FP_CACHE.pop(next(iter(_FP_CACHE)))
        _FP_CACHE[key] = value
    return value
