"""A proposed SQL transform, run once against a throwaway copy.

An agent's ``propose_transform`` (new or a change) is run at proposal time,
before anyone approves it, so the agent and the reviewer see what it would
make. Nothing it does reaches anything real:

- a fresh scratch DuckDB under ``.tracebi/dryrun/<request id>/``, removed
  afterwards, is the default catalog: every table and view the SQL creates
  lands there;
- the project's warehouse is attached READ_ONLY (the object tier as views
  over its Parquet files, as a query connection reads it), so a warehouse
  table the SQL reads resolves by its bare name, and a write to it fails;
- each ``-- source:`` table is loaded by the same loader, with the same
  fallback rules, the real run uses (:func:`tracebi.transforms._attach_sources`);
  a table read through DuckDB's scanner is then copied into its in-memory
  catalog and the scanned database detached, its secret dropped, so no
  statement can reach the rest of that database;
- then external access is switched off and the configuration locked, as on a
  model's query connection (:mod:`tracebi.model.engine`): no file outside the
  workspace's ``inputs/`` (and there no database file, and no uploaded file a
  connection's allowlist does not admit), no URL, no extension, no ``SET``
  that would undo it. DuckDB enforces it;
- statement by statement, ``ATTACH``, ``DETACH``, ``EXPORT``, ``LOAD`` /
  ``INSTALL``, a scanner's own functions and ``query()`` / ``query_table()``
  (SQL held in a string) are refused, a ``COPY`` is not
  executed (it moves rows to or from a file), and a ``-- sink:`` line sends
  nothing; the result names each;
- the whole run is bounded by the workspace's statement timeout
  (``engine.query_timeout_s``) and runs under its engine limits.

Then the contract's checks run, read-only, against what the run created
(:func:`tracebi.contracts.observe`), and nothing is written: no certificate,
no warehouse table, no connection. The result says, per created table, its
columns, rows and first rows; per check, whether it passed and how many rows
failed it; the column lineage DuckDB's parse proves; the elapsed time; and
any error with the statement it failed on.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

#: Rows kept per created table.
SAMPLE_ROWS = 20

#: The warehouse's catalog name in a dry run; a bare table name finds it
#: through the search path when the scratch catalog has no table of that name.
_WAREHOUSE = "__tracebi_warehouse"
_SCRATCH = "dryrun"

#: Statement types a dry run never executes, by DuckDB's own parse.
_REFUSED = {"ATTACH": "opens another database", "DETACH": "closes a database",
            "EXPORT": "writes files", "COPY_DATABASE": "copies a database",
            "LOAD": "loads or installs an extension", "UPDATE_EXTENSIONS": "updates extensions",
            "???": "is not a statement a transform runs"}
#: Table functions of DuckDB's scanners: they read a database the allowlist
#: does not govern.
_SCANNER_PREFIXES = ("postgres_", "mysql_", "sqlite_", "pg_")
#: Table functions that run SQL held in a string, out of the reach of the
#: statement checks above.
_STRING_SQL = frozenset({"query", "query_table"})

_DB_MAGIC = (b"SQLite format 3\x00",)


def dryrun_dir(request_id: str) -> Path:
    return Path(".tracebi") / "dryrun" / request_id


def run(sql: str, contract_yaml: str, name: str, scratch: "str | os.PathLike[str]",
        root: Optional[str] = None) -> dict:
    """Dry-run ``transforms/<name>.sql`` (text *sql*) and its contract in a
    throwaway DuckDB at *scratch*, removed afterwards. Returns the result
    (see the module docstring); ``ok`` is true when every statement ran and
    every check passed."""
    root = os.path.abspath(root or os.getcwd())
    scratch = Path(scratch)
    started = time.perf_counter()
    out: dict = {"ok": False, "ran_at": datetime.now(timezone.utc).isoformat(),
                 "tables": [], "checks": [], "sources": {}, "not_executed": [],
                 "notes": [], "lineage": None, "error": None}
    try:
        _run(sql, contract_yaml, name, scratch, root, out)
    except Exception as exc:  # noqa: BLE001 — the result says why; nothing real was touched
        if out["error"] is None:
            out["error"] = {"message": _one_line(exc)}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        try:
            scratch.parent.rmdir()     # .tracebi/dryrun/, once nothing else runs there
        except OSError:
            pass
    out["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    passed = sum(1 for c in out["checks"] if c["passed"])
    out["checks_passed"], out["checks_total"] = passed, len(out["checks"])
    out["ok"] = out["error"] is None and passed == len(out["checks"]) and bool(out["checks"])
    out["summary"] = summary(out)
    return out


def summary(result: dict) -> str:
    """``Dry run: 3 tables, checks 4 of 4 passed`` — or what failed."""
    if result.get("error"):
        return f"Dry run failed: {result['error']['message']}"
    n = len(result.get("tables") or [])
    said = (f"Dry run: {n} table{'s' if n != 1 else ''}, checks "
            f"{result.get('checks_passed', 0)} of {result.get('checks_total', 0)} passed")
    return said


def _one_line(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _lit(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _ident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _run(sql: str, contract_yaml: str, name: str, scratch: Path, root: str, out: dict) -> None:
    import duckdb

    from tracebi.contracts import observe, read_contract_file
    from tracebi.model.engine import _timed_out
    from tracebi.project_config import engine_settings, sink_target
    from tracebi.transforms import (
        TransformError, _attach_sources, _line_of, _previous_line, _sink_lines, _sink_of,
        _sink_views, _view_oids, render_sql, source_directives,
    )

    where = f"transforms/{name}.sql"
    scratch.mkdir(parents=True, exist_ok=True)
    contract_path = scratch / f"{name}.contract.yaml"
    contract_path.write_text(contract_yaml or "", encoding="utf-8")
    spec = read_contract_file(contract_path, name)
    directives = source_directives(sql, where)
    for src in directives:
        if not _may_read(src["connection"], src["table"], root):
            raise TransformError(f"{where}: -- source: {src['ref']} is not a table agents may "
                                 f"read, so a dry run does not load it")
    text = render_sql(sql, root, where)
    try:
        statements = duckdb.extract_statements(text)
    except duckdb.Error as exc:
        raise TransformError(f"{where}: {exc}") from exc
    marks = _sink_lines(text, where)
    settings = engine_settings(root)
    sink = sink_target(root)
    tier = sink.warehouse.tier

    con = duckdb.connect(str(scratch / f"{_SCRATCH}.duckdb"))
    fired = threading.Event()

    def _stop() -> None:
        fired.set()
        con.interrupt()

    timer = threading.Timer(settings["query_timeout_s"], _stop)
    timer.daemon = True
    timer.start()
    try:
        # Before anything touches the secret manager: a dry run keeps no secret.
        con.execute("SET allow_persistent_secrets = false")
        con.execute(f"SET memory_limit = {_lit(settings['memory_limit'])}")
        con.execute(f"SET threads = {int(settings['threads'])}")
        (scratch / "tmp").mkdir(exist_ok=True)
        con.execute(f"SET temp_directory = {_lit(str(scratch / 'tmp'))}")
        con.execute(f"SET file_search_path = {_lit(root)}")
        allowed = _attach_warehouse(con, sink.warehouse, out)
        loaded = _attach_sources(con, directives, root, where)
        out["sources"] = {ref: {k: rec.get(k) for k in (
            "connection", "table", "method", "rows", "fingerprint", "loaded_at")}
            | {"snapshot": rec.get("fallback") if rec.get("source_fallback") else None}
            for ref, rec in loaded.items()}
        _seal_sources(con, loaded)
        allowed += _input_files(root)
        if allowed:
            con.execute("SET allowed_paths = [" + ", ".join(_lit(p) for p in allowed) + "]")
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")

        before = _view_oids(con)
        tracer = _tracer(con, [d["connection"] for d in directives], root,
                         _WAREHOUSE in _databases(con))
        cursor = 0
        for i, statement in enumerate(statements, 1):
            start = text.find(statement.query, cursor)
            cursor = start + len(statement.query) if start >= 0 else cursor
            line = _line_of(text, max(start, 0), statement.query)
            mark = _previous_line(text, line, marks)
            if mark is not None:
                send = _sink_of(mark, statement.query, where)
                out["not_executed"].append({
                    "line": mark["line"], "what": f"-- sink: {send['connection']}"
                    + (" only" if send["only"] else ""), "table": send["table"],
                    "reason": f"a dry run sends nothing to a connection: on approval, "
                              f"{send['table']} goes to {send['connection']} after the run"})
            kind = statement.type.name
            shown = " ".join(statement.query.split())[:400]
            if kind == "COPY":
                out["not_executed"].append({
                    "line": line, "statement": i, "what": "COPY",
                    "reason": "a dry run writes and reads no file through COPY; on approval "
                              "it runs as written"})
                continue
            refusal = _refused(kind, statement.query)
            if refusal:
                out["error"] = {"statement": i, "line": line, "sql": shown,
                                "message": f"{where}: statement {i} (line {line}) {refusal}"}
                return
            tracer.before(statement.query)
            try:
                con.execute(statement.query)
            except duckdb.InterruptException:
                raise
            except duckdb.Error as exc:
                out["error"] = {"statement": i, "line": line, "sql": shown,
                                "message": f"{where}: statement {i} (line {line}) failed: "
                                           f"{' '.join(str(exc).split())}"}
                return
            tracer.after()
        if marks:
            raise TransformError(
                f"{where}: line {min(marks)}: a -- sink: line belongs on the line just "
                f"above the CREATE OR REPLACE TABLE whose table it sends")
        _sink_views(con, before, directives, where, tier, also=_warehouse_names(con))
        out["lineage"] = tracer.result()
        out["tables"] = _created(con)
        out["checks"] = [_check_entry(c) for c in observe(con, spec["checks"])]
    except duckdb.InterruptException as exc:
        if fired.is_set():
            out["error"] = {"message": str(_timed_out(settings["query_timeout_s"]))}
            return
        raise exc
    finally:
        timer.cancel()
        con.close()
    if fired.is_set() and out["error"] is None:
        out["error"] = {"message": str(_timed_out(settings["query_timeout_s"]))}


def _may_read(connection: str, table: str, root: str) -> bool:
    """The allowlist (:func:`tracebi.connections.agent_may_read`) of the
    connection file under *root*."""
    from tracebi.connections import agent_may_read, connection_file, load_connection

    path = connection_file(connection, root)
    try:
        return path is not None and agent_may_read(load_connection(path, root=root), table)
    except Exception:  # noqa: BLE001 — a connection that will not load admits nothing
        return False


def _databases(con) -> set:
    return {r[0] for r in con.execute("SELECT database_name FROM duckdb_databases()").fetchall()}


def _attach_warehouse(con, wh, out: dict) -> list[str]:
    """The project's warehouse, READ_ONLY, behind the scratch catalog in the
    search path. A warehouse not there yet (a first transform) is no error:
    the SQL then reads none of its tables."""
    import duckdb

    if wh.tier == "file" and not os.path.isfile(wh.address):
        out["notes"].append("The warehouse has no file yet, so the SQL reads none of its tables.")
        return []
    try:
        allowed = wh.attach(con, _WAREHOUSE)
    except (duckdb.Error, ValueError) as exc:
        out["notes"].append(f"The warehouse could not be attached ({' '.join(str(exc).split())}); "
                            f"the SQL reads none of its tables here.")
        return []
    con.execute(f"SET search_path = {_lit(f'{_SCRATCH}.main,{_WAREHOUSE}.main')}")
    return list(allowed)


def _seal_sources(con, loaded: dict) -> None:
    """A table read through DuckDB's scanner is a view over the whole scanned
    database: copy it into its catalog, then detach that database and drop
    its secret, so only the allowlisted table remains. Fails closed: if a
    scanned database is still attached, nothing runs."""
    from tracebi.connectors.scan import HIDDEN

    for rec in loaded.values():
        if rec.get("method") != "scanner":
            continue
        cat, table = _ident(rec["connection"]), _ident(rec["table"])
        copy = _ident(f"{rec['table']}__tracebi_copy")
        con.execute(f"CREATE TABLE {cat}.main.{copy} AS SELECT * FROM {cat}.main.{table}")
        con.execute(f"DROP VIEW {cat}.main.{table}")
        con.execute(f"ALTER TABLE {cat}.main.{copy} RENAME TO {table}")
    for name in sorted(_databases(con)):
        if name.lower().startswith(HIDDEN):
            con.execute(f"DETACH {_ident(name)}")
    for (secret,) in con.execute("SELECT name FROM duckdb_secrets()").fetchall():
        if secret.lower().startswith(HIDDEN):
            con.execute(f"DROP TEMPORARY SECRET IF EXISTS {_ident(secret)}")
    if any(n.lower().startswith(HIDDEN) for n in _databases(con)):
        raise RuntimeError("a scanned source database is still attached; the dry run did not run")


def _input_files(root: str) -> list[str]:
    """The files under ``inputs/`` a dry run may read: not a database file,
    and not an uploaded file whose connection's allowlist leaves it out."""
    from tracebi.sources import inputs_dir

    base = Path(root) / inputs_dir()
    if not base.is_dir():
        return []
    shut = _uploads_not_admitted(root)
    out = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.resolve() in shut or len(out) >= 5000:
            continue
        try:
            with open(path, "rb") as fh:
                head = fh.read(16)
        except OSError:
            continue
        if head.startswith(_DB_MAGIC) or head[8:12] == b"DUCK":
            continue
        out.append(str(path.resolve()))
    return out


def _uploads_not_admitted(root: str) -> set:
    """Files an ``upload`` connection declares whose one table agents may not read."""
    from tracebi.connections import SUFFIXES, agent_may_read, connections_dir, load_connection

    shut: set = set()
    d = connections_dir(root)
    for path in sorted(d.iterdir()) if d.is_dir() else []:
        if path.suffix not in SUFFIXES:
            continue
        try:
            conn = load_connection(path, root=root)
        except Exception:  # noqa: BLE001 — a file that will not load admits nothing
            continue
        file = getattr(conn, "file", None)
        if isinstance(file, str) and not agent_may_read(conn, Path(file).stem):
            shut.add((Path(root) / file).resolve())
    return shut


def _refused(kind: str, sql: str) -> Optional[str]:
    """Why a statement is not run in a dry run, or None."""
    from tracebi.connectors.scan import HIDDEN

    if kind in _REFUSED:
        return f"is {kind.replace('_', ' ')}, which a dry run does not run: it {_REFUSED[kind]}"
    if HIDDEN in sql.lower():
        return "names a scanned database, which a transform reads only by its connection's name"
    import duckdb
    tokens = duckdb.tokenize(sql)
    for n, (pos, kind_) in enumerate(tokens):
        if kind_ not in (duckdb.token_type.identifier, duckdb.token_type.keyword):
            continue
        end = tokens[n + 1][0] if n + 1 < len(tokens) else len(sql)
        word = sql[pos:end].strip().strip('"').lower()
        rest = sql[end:].lstrip() if n + 1 < len(tokens) else ""
        if word.startswith(_SCANNER_PREFIXES) and rest.startswith("("):
            return (f"calls {word}(…), a scanner's own function; read a connection's table "
                    f"with a -- source: line")
        if word in _STRING_SQL and rest.startswith("("):
            return (f"calls {word}(…), which runs SQL from a string; a dry run runs only "
                    f"the statements as written")
    return None


def _tracer(con, sources: list, root: str, warehouse: bool):
    from tracebi.lineage_sql import Tracer

    class _DryTracer(Tracer):
        """The real run's tracer; a table of the attached warehouse counts as
        the warehouse's own, as it does when the run writes there."""

        def _in_warehouse(self, name: str) -> bool:
            if super()._in_warehouse(name):
                return True
            return warehouse and self.con.execute(
                "SELECT count(*) FROM (SELECT table_name AS n FROM duckdb_tables() "
                "WHERE database_name = ? AND schema_name = 'main' "
                "UNION ALL SELECT view_name FROM duckdb_views() WHERE database_name = ? "
                "AND schema_name = 'main' AND NOT internal) WHERE lower(n) = ?",
                [_WAREHOUSE, _WAREHOUSE, name.lower()]).fetchone()[0] > 0

    return _DryTracer(con, sources, root)


def _warehouse_names(con) -> set:
    return {r[0].lower() for r in con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = ? AND schema_name = 'main' "
        "UNION SELECT view_name FROM duckdb_views() WHERE database_name = ? "
        "AND schema_name = 'main' AND NOT internal", [_WAREHOUSE, _WAREHOUSE]).fetchall()}


def _created(con) -> list[dict]:
    """Each table and view the run created: columns, rows, the first rows."""
    from tracebi.workbench import _json_safe

    rows = con.execute(
        "SELECT table_name, 'table' FROM duckdb_tables() WHERE database_name = current_database() "
        "AND schema_name = 'main' AND NOT temporary "
        "UNION ALL SELECT view_name, 'view' FROM duckdb_views() WHERE database_name = current_database() "
        "AND schema_name = 'main' AND NOT internal AND NOT temporary ORDER BY 1").fetchall()
    out = []
    for name, kind in rows:
        rel = f"main.{_ident(name)}"
        columns = [{"name": r[0], "type": r[1]} for r in con.execute(f"DESCRIBE {rel}").fetchall()]
        count = int(con.execute(f"SELECT count(*) FROM {rel}").fetchone()[0])
        result = con.execute(f"SELECT * FROM {rel} LIMIT {SAMPLE_ROWS}")
        names = [d[0] for d in result.description]
        sample = [{c: _json_safe(v) for c, v in zip(names, row)} for row in result.fetchall()]
        out.append({"name": name, "kind": kind, "columns": columns, "rows": count,
                    "sample": sample})
    return out


#: Per check, the observed count that is the number of failing rows (or keys).
_FAILING = {"unique": None, "not_null": None, "foreign_key": None, "values": None,
            "reconcile": "mismatched_keys"}


def _check_entry(check: dict) -> dict:
    entry = {k: check.get(k) for k in ("check", "table", "params", "passed", "observed", "note")
             if k in check}
    if "error" in check:
        entry["error"] = check["error"]
    if check["check"] in _FAILING:
        key = _FAILING[check["check"]]
        observed = check.get("observed")
        entry["failing_rows"] = (observed.get(key) if key and isinstance(observed, dict)
                                 else observed if isinstance(observed, int) else None)
    return entry
