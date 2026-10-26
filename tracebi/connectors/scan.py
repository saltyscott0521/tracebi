"""Reading a source where it lives: DuckDB's own scanners, else Arrow.

A ``-- source:`` line in a transform, and a model table over a declared
connection, read a table of a database outside the warehouse. The way the
field settled on is to query where the data lives when you can, and when you
copy, to copy in bulk and columnar:

- **scanner**: a Postgres, MySQL or SQLite connection is attached into the
  DuckDB connection itself through DuckDB's ``postgres``, ``mysql`` or
  ``sqlite`` extension, READ_ONLY. DuckDB pushes projections and filters down
  and moves rows as Arrow, with no pandas in between.
- **arrow**: Snowflake and BigQuery hand back Arrow from their own result
  APIs, and any other SQLAlchemy URL goes through ADBC when its driver
  imports (:meth:`BaseConnector.load_arrow`).
- **pandas**: the floor, the connector's ``load()``, as every source was read
  before.

The database is attached under a hidden name (``__tracebi_src_<name>``) and
each table a caller names becomes a view ``<name>.main.<table>`` in an
in-memory catalog named after the connection. So the SQL reads
``crm.issuer_ratings`` whichever way the rows arrive, and only the tables a
transform declared, or a connection's allowlist admits, have a name there.

The connection's credentials are resolved through the connection (and so
through :mod:`tracebi.project_credentials`) when it is attached, passed to
DuckDB as a temporary secret held by that one connection, and never written
anywhere; a driver's error that echoes them is redacted before it is raised.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    import pyarrow as pa

#: The DuckDB extension that reads each SQLAlchemy dialect in place.
SCANNERS = {"sqlite": "sqlite", "postgresql": "postgres",
            "mysql": "mysql", "mariadb": "mysql"}
#: The catalog a scanned database is attached under: never a name an author
#: writes, and refused on a query connection (:mod:`tracebi.model.engine`).
HIDDEN = "__tracebi_src_"

#: Extensions that could not be loaded or installed in this process, with the
#: reason, so a machine without them asks once rather than on every read.
_unavailable: dict[str, str] = {}

#: The allowlist check, when the connections module does not provide one.
#: ``None`` reads ``tracebi.connections.agent_may_read``; a test, or a build
#: without the allowlist, may set a ``(connection, table) -> bool`` here.
agent_may_read_hook: Optional[Callable[[str, str], bool]] = None


class ScannerUnavailable(RuntimeError):
    """The scanner for a source cannot be used here (its extension is not
    installed and could not be). The caller reads the source another way."""


class ScanError(RuntimeError):
    """Attaching a source failed (the server down, a table missing). The
    message carries no credential."""


def agent_may_read(connection: str, table: str) -> bool:
    """Whether *table* of *connection* is on the connection's allowlist
    (``agents: {tables: …}`` in ``connections/<name>.yaml``): what the
    model's live attach, and a sink view over a source, may read."""
    if agent_may_read_hook is not None:
        return bool(agent_may_read_hook(connection, table))
    try:
        from tracebi.connections import agent_may_read as check
    except ImportError:
        return True     # no allowlist in this build: every table, as before it
    return bool(check(connection, table))


def _lit(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _ident(name) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def scanner(connector) -> Optional[str]:
    """The DuckDB extension that reads *connector*'s database in place
    (``postgres``, ``mysql``, ``sqlite``), or None. Reads the connection's URL,
    so an unset ``${VAR}`` raises :class:`ConnectionConfigError` here."""
    from tracebi.connectors.sql_connector import SQLConnector, url_dialect

    if not isinstance(connector, SQLConnector):
        return None
    return SCANNERS.get(url_dialect(connector.url) or "")


def is_live(connector) -> bool:
    """A declared SQL connection (``connections/<name>.yaml`` of type sql,
    postgres or mysql): what a model reads live, through its allowlist."""
    from tracebi.connectors.sql_connector import SQLConnector

    return isinstance(connector, SQLConnector) and "_decl" in connector.__dict__


def load_extension(con, name: str, install: bool = True) -> None:
    """``LOAD`` *name* into *con*, installing it once when *install* and it is
    missing. Raises :class:`ScannerUnavailable` naming the one command that
    installs it."""
    import duckdb

    if name in _unavailable:
        raise ScannerUnavailable(_unavailable[name])
    try:
        con.execute(f"LOAD {name}")
        return
    except duckdb.Error:
        pass
    if install:
        try:
            con.execute(f"INSTALL {name}")
            con.execute(f"LOAD {name}")
            return
        except duckdb.Error:
            pass
    message = (f"DuckDB's {name} extension is not installed here"
               f"{' and could not be downloaded' if install else ''}; install it once "
               f"with: python -c \"import duckdb; duckdb.connect().execute('INSTALL {name}')\"")
    if install:
        _unavailable[name] = message
    raise ScannerUnavailable(message)


def attach_tables(con, connector, catalog: str, tables: list[str],
                  install: bool = True) -> list[str]:
    """Attach *connector*'s database READ_ONLY into *con* and make each of
    *tables* the view ``<catalog>.main.<table>``. Returns the files a locked
    connection must still allow (a SQLite database), else nothing.

    Raises :class:`ScannerUnavailable` when there is no scanner for it here,
    and :class:`ScanError`, with any credential redacted, when the database or
    a table cannot be reached."""
    import duckdb
    from sqlalchemy.engine import make_url

    extension = scanner(connector)
    if extension is None:
        raise ScannerUnavailable(f"{type(connector).__name__} has no DuckDB scanner")
    load_extension(con, extension, install)
    url = make_url(connector.url)
    hidden = _ident(HIDDEN + catalog)
    allowed: list[str] = []
    attached = {r[0] for r in con.execute(
        "SELECT database_name FROM duckdb_databases()").fetchall()}
    try:
        if extension == "sqlite":
            path = os.path.abspath(url.database or "")
            if not os.path.isfile(path):
                raise ScanError(f"connection '{connector.name}': the SQLite file "
                                f"{url.database} does not exist")
            if HIDDEN + catalog not in attached:     # one attach per connection
                con.execute(f"ATTACH {_lit(path)} AS {hidden} (TYPE sqlite, READ_ONLY)")
            schema, allowed = "main", [path]
        elif HIDDEN + catalog in attached:
            schema = "public" if extension == "postgres" else (url.database or "")
        else:
            # The credential goes in a temporary secret this connection alone
            # holds; the attach string carries only the URL's other options.
            # The name is an identifier as written: HIDDEN plus a connection
            # name, which is letters, digits and underscores.
            secret = (HIDDEN + catalog).lower()
            parts = [f"TYPE {extension}"]
            for key, value in (("HOST", url.host), ("DATABASE", url.database),
                               ("USER", url.username), ("PASSWORD", url.password)):
                if value not in (None, ""):
                    parts.append(f"{key} {_lit(value)}")
            if url.port is not None:
                parts.append(f"PORT {int(url.port)}")
            con.execute(f"CREATE OR REPLACE TEMPORARY SECRET {secret} ({', '.join(parts)})")
            options = " ".join(f"{k}={v}" for k, v in url.query.items()
                               if isinstance(v, str))
            con.execute(f"ATTACH {_lit(options)} AS {hidden} "
                        f"(TYPE {extension}, SECRET {secret}, READ_ONLY)")
            schema = "public" if extension == "postgres" else (url.database or "")
        if catalog not in attached:
            con.execute(f"ATTACH ':memory:' AS {_ident(catalog)}")
        for table in tables:
            con.execute(f"CREATE OR REPLACE VIEW {_ident(catalog)}.main.{_ident(table)} AS "
                        f"SELECT * FROM {hidden}.{_ident(schema)}.{_ident(table)}")
            # A view binds lazily: read it once so a missing table fails here,
            # by name, rather than in the middle of someone's SQL.
            con.execute(f"SELECT * FROM {_ident(catalog)}.main.{_ident(table)} LIMIT 0").fetchall()
    except duckdb.Error as exc:
        raise ScanError(redacted(connector, f"connection '{connector.name}': "
                                            f"{' '.join(str(exc).split())}")) from None
    return allowed


def redacted(connector, text: str) -> str:
    """*text* with the connection's password (and its whole URL) replaced by
    ``***``: a driver's error can echo what it was given."""
    try:
        from sqlalchemy.engine import make_url

        url = make_url(connector.url)
        for secret in (connector.url, url.password):
            if secret and len(str(secret)) >= 4:
                text = text.replace(str(secret), "***")
    except Exception:  # noqa: BLE001 — nothing resolvable, nothing to hide
        pass
    return text


def arrow_rows(con, relation: str) -> "pa.Table":
    """Every row of *relation* in *con*, as an Arrow table."""
    return con.execute(f"SELECT * FROM {relation}").to_arrow_table()


class LiveSource:
    """A declared connection's tables, read live by a model's query
    connection (:func:`tracebi.model.engine.query_connection`, ``sources``).

    Only the tables the connection's allowlist admits are given a name; the
    rest are not there to read. The database is attached through its scanner
    before the connection is locked; where there is no scanner here, each
    table is read through the connector (Arrow, else pandas) into the
    catalog, still before the lock."""

    def __init__(self, connector, tables: list[str]) -> None:
        self.connector = connector
        self.tables = sorted(set(tables))

    def admitted(self) -> list[str]:
        return [t for t in self.tables if agent_may_read(self.connector.name, t)]

    def attach(self, con, alias: str) -> list[str]:
        tables = self.admitted()
        if not tables:
            # Nothing it may read: no reason to open a connection to it.
            raise ValueError(f"connection '{self.connector.name}' has no table on its "
                             f"allowlist among {', '.join(self.tables)}")
        try:
            try:
                return attach_tables(con, self.connector, alias, tables, install=False)
            except ScannerUnavailable:
                pass
            import pyarrow as pa

            attached = {r[0] for r in con.execute(
                "SELECT database_name FROM duckdb_databases()").fetchall()}
            if alias not in attached:
                con.execute(f"ATTACH ':memory:' AS {_ident(alias)}")
            for table in tables:
                arrow = self.connector.load_arrow(table)
                if arrow is None:
                    arrow = pa.Table.from_pandas(self.connector.load(table), preserve_index=False)
                con.register("__tracebi_live", arrow)
                con.execute(f"CREATE TABLE {_ident(alias)}.main.{_ident(table)} AS "
                            f"SELECT * FROM __tracebi_live")
                con.unregister("__tracebi_live")
            return []
        finally:
            engine = self.connector.__dict__.get("_engine")
            if engine is not None:
                engine.dispose()


def view_sources(con, catalogs: list[str],
                 root: Optional[str] = None) -> dict[str, list[str]]:
    """``{connection: [table]}`` that the views of *catalogs* in *con* read
    from a declared connection (a sink view over an allowlisted source
    table), so a query connection can attach them before it is locked."""
    from tracebi.connections import connections_dir

    folder = connections_dir(root)
    if not catalogs or not folder.is_dir():
        return {}
    names = {p.stem.lower(): p.stem for p in folder.iterdir()
             if p.suffix in (".yaml", ".yml")}
    if not names:
        return {}
    marks = ", ".join(_lit(c) for c in catalogs)
    rows = con.execute("SELECT sql FROM duckdb_views() WHERE NOT internal "
                       f"AND database_name IN ({marks})").fetchall()
    found: dict[str, set[str]] = {}
    for (sql,) in rows:
        text = (sql or "").lower()
        if not any(f"{n}." in text or f'"{n}".' in text for n in names):
            continue
        from tracebi.transforms import TransformError, _view_refs

        try:
            refs, _ = _view_refs(con, sql)
        except TransformError:
            continue
        for catalog, schema, table in refs:
            qualifier = (catalog or (schema if schema.lower() != "main" else "")).lower()
            if qualifier in names:
                found.setdefault(names[qualifier], set()).add(table)
    return {k: sorted(v) for k, v in found.items()}


def follow_views(con, catalogs: list[str],
                 root: Optional[str] = None) -> "dict[str, LiveSource]":
    """A :class:`LiveSource` for each connection the views of *catalogs*
    read (:func:`view_sources`), keyed by the connection's name: the catalog
    those views name it by."""
    from tracebi.connections import connection_file, load_connection

    out: dict[str, LiveSource] = {}
    for name, tables in view_sources(con, catalogs, root).items():
        path = connection_file(name, root)
        if path is None:
            continue
        try:
            out[name] = LiveSource(load_connection(path, root), tables)
        except Exception:  # noqa: BLE001 — a broken file: the view then fails by name
            continue
    return out
