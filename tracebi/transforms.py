"""Phase ① transforms: find one, say which form it is, run it.

A transform is one file in ``transforms/`` (``TRACEBI_TRANSFORMS_DIR``), in
one of three forms:

- **sql** (the default, ``<name>.sql``): DuckDB SQL, statements in order, run
  top to bottom in ONE fresh connection to the project's warehouse
  (``tracebi.yaml``; :mod:`tracebi.warehouse`). A table the script creates
  (``CREATE OR REPLACE TABLE x AS …``, not ``TEMP``) is a sink table: on the
  file and remote tiers it lands in the warehouse itself, and on the object
  tier the runner writes it to ``<location>/x.parquet`` after the script, as
  ``write()`` would. A script may instead ``COPY (…) TO '{{ sink }}/x.parquet'``
  itself. ``TEMP`` tables and ``TEMP MACRO``\\ s are scratch and vanish with
  the connection.
- **python** (``<name>.py``) and **notebook** (``<name>.ipynb``): the escape
  hatch, run top to bottom in a fresh namespace, ending by writing frames
  (pandas, or anything DuckDB reads as Arrow) with
  ``DuckDBConnector(...).write(df, table)``.

**Templating** (SQL only) is exactly two placeholders, substituted as text
with any single quote doubled, so each belongs inside a ``'…'`` literal:
``{{ sink }}`` is ``str(sink_target(root))`` (the ``.duckdb`` path, the
object prefix, or the attach string) and ``{{ root }}`` the project root,
absolute. Anything else between ``{{`` and ``}}`` is an error naming it.

**Relative paths** in a SQL transform's reads (``read_csv('inputs/x.csv')``)
resolve against the project root: the connection's ``file_search_path`` is
set to it. A write names its destination with ``{{ sink }}`` or ``{{ root }}``.

**Sources** (SQL only): a header line ``-- source: crm.issuer_ratings`` names
one table of a declared connection (``connections/crm.yaml``). Before the
statements run, the runner loads it through that connection's connector, as a
model would (the whole table, nothing pushed down), and the SQL reads it as
``crm.issuer_ratings``: an in-memory database named after the connection,
attached for the run, so nothing of it lands in the warehouse. The line may
end ``fallback: inputs/issuer_ratings.csv``, a committed snapshot read only
when the connection's ``${VAR}`` is unset; any other failure to reach the
source stops the run. Each load is recorded (:func:`load_source`) and, when a
contract sits beside the transform, written into its certificate under
``sources``, so the certificate says which inputs the sink satisfied its
contract against, and whether the snapshot stood in for the connection.

**The contract beside it.** ``<name>.contract.yaml`` (:mod:`tracebi.contracts`,
the same closed vocabulary as ``with contract(...)``) runs after the
transform, of any form, and writes the same certificate. Its checks read what
landed through the warehouse's own reader once the transform's connection is
closed: on the object tier the transform's connection holds in-memory tables
that are not the sink, and the certificate's fingerprints read through the
connector load path, which cannot open a file the transform still holds.

Two files of one name (``x.sql`` and ``x.py``) are refused, naming both, as
two models of one name are. Nothing is converted: a pandas transform keeps
running until its author rewrites it.
"""

from __future__ import annotations

import os
import re
import runpy
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import pandas as pd

#: Suffix → the form ``run-transform`` reports and a pipeline run records.
FORMS = {".sql": "sql", ".py": "python", ".ipynb": "notebook"}

_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.S)

# ``-- source: <connection>.<table> [fallback: <path>.csv]``, one per line.
_DIRECTIVE = re.compile(r"^\s*--\s*source:(.*)$")
_SOURCE = re.compile(r"\s*(?P<connection>[A-Za-z_]\w*)(?:\.(?P<table>[A-Za-z_]\w*))?"
                     r"(?:\s+fallback:\s*(?P<fallback>\S+))?\s*")


class TransformError(ValueError):
    """A transform that cannot be found unambiguously, or SQL that cannot run.
    The message names the file (and the statement)."""


def transforms_dir() -> Path:
    return Path(os.environ.get("TRACEBI_TRANSFORMS_DIR", "transforms"))


def find_transform(name: str) -> Optional[Path]:
    """The file ``tracebi run-transform <name>`` runs: ``transforms/<name>`` as
    given, or with ``.sql``, ``.py`` or ``.ipynb`` added. Raises
    :class:`TransformError` when two forms of one name exist."""
    tdir = transforms_dir()
    given = Path(name).suffix if Path(name).suffix in FORMS else ""
    stem = name[: -len(given)] if given else name
    found = [tdir / f"{stem}{suffix}" for suffix in FORMS if (tdir / f"{stem}{suffix}").is_file()]
    if len(found) > 1:
        raise TransformError(
            f"{' and '.join(str(p) for p in found)} are one transform in two "
            f"forms; a transform is one file, so delete one")
    if found and not given:
        return found[0]
    plain = tdir / name
    return plain if plain.is_file() else None


def transform_form(path: "str | os.PathLike[str]") -> str:
    """``sql``, ``python`` or ``notebook``, from the file's suffix."""
    return FORMS.get(Path(path).suffix, "python")


def contract_file(path: "str | os.PathLike[str]") -> Optional[Path]:
    """The ``<name>.contract.yaml`` beside a transform, if there is one."""
    from tracebi.contracts import CONTRACT_FILE_SUFFIX

    path = Path(path)
    beside = path.with_name(path.stem + CONTRACT_FILE_SUFFIX)
    return beside if beside.is_file() else None


def render_sql(text: str, root: str, where: str = "the transform") -> str:
    """Substitute ``{{ sink }}`` and ``{{ root }}``; refuse any other placeholder."""
    from tracebi.project_config import sink_target

    values = {"sink": str(sink_target(root)), "root": os.path.abspath(root)}

    def sub(match: "re.Match[str]") -> str:
        key = match.group(1).strip()
        if key not in values:
            raise TransformError(
                f"{where}: {{{{ {key} }}}} is not a placeholder; a SQL transform "
                f"has two, {{{{ sink }}}} and {{{{ root }}}}")
        return values[key].replace("'", "''")

    return _PLACEHOLDER.sub(sub, text)


def source_directives(text: str, where: str = "the transform") -> list[dict]:
    """The ``-- source:`` lines of a SQL transform's header (the comment lines
    above its first statement), each as ``{ref, connection, table, fallback}``.
    A connection with no table, a repeated source, or a ``-- source:`` line
    below the header is an error naming the line: a directive the runner
    would skip must not read as one it obeys."""
    found: list[dict] = []
    in_header = True
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if in_header and stripped and not stripped.startswith("--"):
            in_header = False
        directive = _DIRECTIVE.match(line)
        if directive is None:
            continue
        if not in_header:
            raise TransformError(
                f"{where}: line {number}: a -- source: line belongs in the header, "
                f"above the first statement")
        parsed = _SOURCE.fullmatch(directive.group(1))
        if parsed is None:
            raise TransformError(
                f"{where}: line {number}: expected -- source: <connection>.<table>"
                f" [fallback: <path>.csv], got {stripped!r}")
        if parsed.group("table") is None:
            raise TransformError(
                f"{where}: line {number}: -- source: {parsed.group('connection')} "
                f"names no table; name each one, as -- source: "
                f"{parsed.group('connection')}.<table>")
        ref = f"{parsed.group('connection')}.{parsed.group('table')}"
        if any(s["ref"] == ref for s in found):
            raise TransformError(f"{where}: line {number}: {ref} is named twice")
        found.append({"ref": ref, "connection": parsed.group("connection"),
                      "table": parsed.group("table"),
                      "fallback": parsed.group("fallback")})
    return found


def load_source(ref: str, root: Optional[str] = None,
                fallback: Optional[str] = None,
                force_fallback: bool = False) -> "tuple[pd.DataFrame, dict]":
    """Load ``<connection>.<table>`` through the declared connection's
    connector, the whole table with nothing pushed down, and return
    ``(frame, record)``. The record is what a certificate keeps:
    ``{connection, table, rows, fingerprint, loaded_at}``, plus
    ``source_fallback: csv`` and ``fallback`` when *fallback* (a ``.csv``
    path inside the project) stood in because the connection's ``${VAR}`` is
    unset. Any other failure (the server down, the table missing) raises: a
    snapshot never covers for a source that is set but unreachable.

    A relational table has no row order, so the frame is sorted by every
    column: its fingerprint names the rows, not the order a server happened
    to return them in. The SQL runner calls this for each ``-- source:``
    line; a Python transform calls it to get the same frame and record.
    *force_fallback* reads the snapshot without trying the connection: how
    ``verify --contracts`` re-reads a load the snapshot served."""
    from datetime import datetime, timezone

    from tracebi.connections import ConnectionConfigError, connection_file, load_connection
    from tracebi.model.dataset import frame_fingerprint

    root = os.path.abspath(root or os.getcwd())
    connection, _, table = ref.partition(".")
    if not table:
        raise TransformError(f"source {ref!r}: name the table, as {connection}.<table>")
    path = connection_file(connection, root)
    if path is None:
        raise TransformError(f"source {ref}: there is no connections/{connection}.yaml")
    connector = load_connection(path, root=root)
    record: dict = {"connection": connection, "table": table}
    unset = "the snapshot is read again, as the certificate recorded it" if force_fallback else None
    if unset is None:
        try:
            frame = connector.load(table)
        except ConnectionConfigError as exc:
            if fallback is None:
                raise TransformError(f"source {ref}: {exc}") from exc
            unset = str(exc)
        finally:
            engine = connector.__dict__.get("_engine")
            if engine is not None:
                engine.dispose()    # the source is read once; hold no connection to it
    if unset is not None:
        frame = _read_fallback(ref, fallback, root)
        record.update(source_fallback="csv", fallback=fallback, reason=unset)
    frame = frame.sort_values(
        list(frame.columns), key=lambda col: col.astype(str) if col.dtype == object else col,
        kind="stable").reset_index(drop=True)
    record.update(rows=len(frame), fingerprint=frame_fingerprint(frame),
                  loaded_at=datetime.now(timezone.utc).isoformat())
    return frame, record


def _read_fallback(ref: str, fallback: str, root: str) -> "pd.DataFrame":
    """The CSV snapshot that stands in for an unset connection, read through
    the CSV connector: only a ``.csv`` inside the project."""
    from tracebi.connectors.csv_connector import CSVConnector
    from tracebi.model.model_spec import _escapes

    if not fallback.endswith(".csv") or _escapes(fallback):
        raise TransformError(f"source {ref}: fallback {fallback!r} must be a .csv "
                             f"path inside the project (no absolute path, no '..')")
    path = Path(root) / fallback
    if not path.is_file():
        raise TransformError(f"source {ref}: fallback {fallback} does not exist")
    return CSVConnector("fallback", directory=str(path.parent)).load(path.name)


def _attach_sources(con, sources: list[dict], root: str, where: str) -> dict:
    """Load each ``-- source:`` table and make it ``<connection>.<table>`` in
    *con*: one in-memory database per connection, attached for this run only,
    so a source never lands in the warehouse. Returns ``{ref: record}``."""
    from tracebi.model.data_model import _register_frame

    records: dict = {}
    for src in sources:
        try:
            frame, records[src["ref"]] = load_source(src["ref"], root, src["fallback"])
        except TransformError as exc:
            raise TransformError(f"{where}: {exc}") from exc
        catalog, table = (f'"{src[k]}"' for k in ("connection", "table"))
        attached = {r[0] for r in con.execute(
            "SELECT database_name FROM duckdb_databases()").fetchall()}
        if src["connection"] not in attached:
            con.execute(f"ATTACH ':memory:' AS {catalog}")
        _register_frame(con, "__tracebi_source", frame)
        con.execute(f"CREATE TABLE {catalog}.main.{table} AS SELECT * FROM __tracebi_source")
        con.unregister("__tracebi_source")
    return records


def _line_of(text: str, start: int, statement: str) -> int:
    """The line of a statement's first character of SQL (past leading blank
    lines and ``--`` comments), for an error message."""
    offset = 0
    for line in statement.splitlines(keepends=True):
        if line.strip() and not line.strip().startswith("--"):
            offset += len(line) - len(line.lstrip())
            break
        offset += len(line)
    return text.count("\n", 0, start + offset) + 1


def run_sql(path: "str | os.PathLike[str]", root: Optional[str] = None,
            sources: Optional[dict] = None) -> int:
    """Run a SQL transform in one fresh write connection to the project's
    warehouse; on the object tier, land the tables it created as Parquet.
    Returns the number of statements run. Each ``-- source:`` load's record
    goes into *sources* (``{ref: record}``) when a dict is passed."""
    import duckdb

    from tracebi.connectors.duckdb_connector import DuckDBConnector
    from tracebi.project_config import sink_target

    root = os.path.abspath(root or os.getcwd())
    where = os.path.relpath(path, root) if os.path.abspath(path).startswith(root + os.sep) else str(path)
    raw = Path(path).read_text(encoding="utf-8")
    directives = source_directives(raw, where)
    text = render_sql(raw, root, where)
    try:
        statements = duckdb.extract_statements(text)
    except duckdb.Error as exc:
        raise TransformError(f"{where}: {exc}") from exc
    sink = sink_target(root)
    # The connection write() takes: on the file tier it waits a moment for a
    # reader to let go, and every tier gets the project's engine limits.
    with DuckDBConnector("transform", database=sink).write_connection() as con:
        con.execute(f"SET file_search_path = '{root.replace(chr(39), chr(39) * 2)}'")
        loaded = _attach_sources(con, directives, root, where)
        if sources is not None:
            sources.update(loaded)
        cursor = 0
        for i, statement in enumerate(statements, 1):
            start = text.find(statement.query, cursor)
            cursor = start + len(statement.query) if start >= 0 else cursor
            try:
                con.execute(statement)
            except duckdb.Error as exc:
                line = _line_of(text, max(start, 0), statement.query)
                raise TransformError(f"{where}: statement {i} (line {line}) failed: "
                                     f"{' '.join(str(exc).split())}") from exc
        if sink.warehouse.tier == "object":
            _land_tables(con, sink.warehouse)
    return len(statements)


def _land_tables(con, wh) -> None:
    """Object tier: each table the script created in the connection's own
    catalog becomes ``<location>/<table>.parquet``, written under a temporary
    name and renamed into place in a local directory (as ``write()`` does),
    so a reader never opens half a file."""
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM duckdb_tables() WHERE database_name = current_database() "
        "AND schema_name = 'main' AND NOT temporary ORDER BY table_name").fetchall()]
    for table in tables:
        path = wh.table_path(table)
        target = path if wh.is_url else f"{path}.tmp-{os.getpid()}"
        ident = '"' + table.replace('"', '""') + '"'
        lit = "'" + target.replace("'", "''") + "'"
        con.execute(f"COPY {ident} TO {lit} (FORMAT PARQUET)")
        if not wh.is_url:
            os.replace(target, path)


def run_transform(path: "str | os.PathLike[str]", root: Optional[str] = None) -> str:
    """Run a transform of any form top to bottom, fresh, then the
    ``.contract.yaml`` beside it if there is one. Returns the form."""
    from tracebi.contracts import run_contract_file
    from tracebi.project_config import sink_target

    path = Path(path)
    form = transform_form(path)
    sources: dict = {}
    if form == "sql":
        run_sql(path, root, sources)
    elif form == "notebook":
        from tracebi._notebook import notebook_to_source
        source = notebook_to_source(path)
        ns: dict = {"__name__": "__main__", "__file__": str(path)}
        exec(compile(source, str(path), "exec"), ns)
    else:
        runpy.run_path(str(path), run_name="__main__")
    beside = contract_file(path)
    if beside is not None:
        run_contract_file(beside, sink_target(root), default_name=path.stem,
                          sources=sources or None)
    return form
