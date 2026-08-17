"""DuckDB connector — fast, file- or memory-backed analytic database."""

from __future__ import annotations

import decimal
import os
from typing import Any, Optional

import pandas as pd

from tracebi.connectors.base import BaseConnector


class DuckDBConnector(BaseConnector):
    """
    Connector backed by an embedded DuckDB instance.

    DuckDB can read Parquet, CSV, JSON, and its own native database files
    with a single SQL query, and push column projection / filters down at
    source. The connector exposes the same ``load(source, filter, columns)``
    contract as every other connector and returns a pandas DataFrame for
    the user-facing API.

    Concurrency: for a file-backed database the persistent connection is
    opened READ-ONLY — DuckDB allows unlimited concurrent read-only
    processes, so dev, ``report build``, and ``serve`` coexist against one
    warehouse. ``write()`` releases that handle, opens a short-lived
    read-write connection just for the write, and closes it again.
    ``":memory:"`` keeps a persistent read-write connection: an in-memory
    database lives on its connection.

    Usage::

        # In-memory analytics
        conn = DuckDBConnector("warehouse")
        conn.register_df("orders", orders_df)

        # Persistent DuckDB file
        conn = DuckDBConnector("warehouse", database="data/analytics.duckdb")

        # Parquet / CSV on disk — source is the file path
        conn = DuckDBConnector("files", directory="data/")

    Args:
        name:      Logical name used to reference this connector in a DataModel.
        database:  Optional path to a DuckDB database file. ``":memory:"`` by default.
        directory: Optional base directory for resolving relative file sources.
    """

    def __init__(
        self,
        name: str,
        database: str = ":memory:",
        directory: Optional[str] = None,
    ) -> None:
        super().__init__(name)
        self.database = database
        self.directory = directory
        self._conn = None
        self._views: dict[str, pd.DataFrame] = {}

    def supports_pushdown(self) -> bool:
        return True

    def describe(self) -> dict:
        out = {**super().describe(), "database": self.database}
        if self.directory:
            out["directory"] = self.directory
        return out

    @staticmethod
    def _duckdb():
        try:
            import duckdb
        except ImportError:
            raise ImportError(
                "duckdb is required for DuckDBConnector.\n"
                "Install with: pip install 'tracebi[duckdb]'"
            )
        return duckdb

    @staticmethod
    def _is_lock_conflict(exc: Exception) -> bool:
        # Cross-process conflicts are IOExceptions mentioning the file lock;
        # same-process conflicts are ConnectionExceptions about opening the
        # same file with a different configuration (read-only vs read-write).
        msg = str(exc).lower()
        return "lock" in msg or "different configuration" in msg

    def connect(self) -> None:
        duckdb = self._duckdb()
        if self._conn is not None:
            return
        if self.database == ":memory:":
            # An in-memory database lives on its connection — keep one
            # persistent read-write connection.
            self._conn = duckdb.connect(self.database)
        else:
            if not os.path.exists(self.database):
                raise FileNotFoundError(
                    f"DuckDB database file '{self.database}' does not exist. "
                    "The first write() creates it — run the transform that "
                    "sinks this warehouse first."
                )
            try:
                self._conn = duckdb.connect(self.database, read_only=True)
            except duckdb.Error as exc:
                if self._is_lock_conflict(exc):
                    raise RuntimeError(
                        f"Cannot open '{self.database}' read-only: another "
                        "process holds it read-write — finish the transform "
                        "(or its write()) first."
                    ) from exc
                raise
        for view_name, view_df in self._views.items():
            self._conn.register(view_name, view_df)

    @property
    def connection(self):
        """Underlying DuckDB connection (for advanced use)."""
        if self._conn is None:
            self.connect()
        return self._conn

    def disconnect(self) -> None:
        """Release the persistent handle; the next load reconnects lazily.

        DuckDB refuses to open one file with two configurations in the same
        process, so short-lived readers (contract fingerprints, tests) must
        release deterministically rather than waiting on garbage collection.
        A :memory: database lives on its connection — disconnecting one
        discards its tables, so it is refused loudly instead of obeyed.
        """
        if self.database == ":memory:":
            raise RuntimeError(
                "disconnect() would discard an in-memory database's tables; "
                "it is only meaningful for file-backed connectors."
            )
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def register_df(self, name: str, df: pd.DataFrame) -> "DuckDBConnector":
        """Register a pandas DataFrame as a DuckDB view named *name*."""
        if self._conn is None:
            self.connect()
        self._conn.register(name, df)
        # Remembered so the view survives write()'s release/reopen cycle.
        self._views[name] = df
        return self

    def _resolve_source(self, source: str) -> str:
        """Return a SQL reference for *source* — a file, query, or table name."""
        s = source.strip()
        if s.upper().startswith("SELECT"):
            return f"({s})"
        ext = os.path.splitext(s)[1].lower()
        if ext in (".parquet", ".csv", ".json", ".jsonl", ".ndjson"):
            path = s
            if self.directory and not os.path.isabs(path):
                path = os.path.join(self.directory, path)
            path_lit = path.replace("'", "''")
            if ext == ".parquet":
                return f"read_parquet('{path_lit}')"
            if ext == ".csv":
                return f"read_csv_auto('{path_lit}')"
            return f"read_json_auto('{path_lit}')"
        # Plain table or view name
        if '"' in s:
            raise ValueError(f"Invalid identifier: {source!r}")
        return f'"{s}"'

    def load(
        self,
        source: str,
        filter: Optional[dict[str, Any]] = None,
        columns: Optional[list[str]] = None,
    ) -> pd.DataFrame:
        if self._conn is None:
            self.connect()

        from_clause = self._resolve_source(source)
        select_cols = ", ".join(f'"{c}"' for c in columns) if columns else "*"
        query = f"SELECT {select_cols} FROM {from_clause}"
        params: list[Any] = []
        if filter:
            clauses = []
            for col, val in filter.items():
                clauses.append(f'"{col}" = ?')
                params.append(val)
            query += " WHERE " + " AND ".join(clauses)
        return self._conn.execute(query, params).df()

    def write(
        self,
        df: pd.DataFrame,
        table: str,
        if_exists: str = "replace",
    ) -> None:
        """Persist *df* into a DuckDB table named *table*.

        Object columns whose non-null values are all ``decimal.Decimal``
        land as ``DECIMAL(38,12)``, preserving the exact digits instead of
        a too-narrow inferred type or a lossy float64 conversion.
        ``DECIMAL(38,12)`` holds up to 26 integer digits and 12 decimal
        places; values with deeper scale are rounded to 12 decimal places
        at write. A column mixing ``Decimal`` with other types (e.g. a
        stray float) is not promoted — it falls through to DuckDB's own
        inference (typically ``DOUBLE``), having already lost exactness.
        Appending a Decimal column into an existing table whose column is
        not ``DECIMAL(38,12)`` raises rather than silently coercing.
        """
        if self.database == ":memory:":
            if self._conn is None:
                self.connect()
            self._write_into(self._conn, df, table, if_exists)
            return
        # File-backed: release the read-only handle, write through a
        # short-lived read-write connection, and leave the connector lazy —
        # the next load reopens read-only.
        duckdb = self._duckdb()
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        try:
            write_conn = duckdb.connect(self.database)
        except duckdb.Error as exc:
            if self._is_lock_conflict(exc):
                raise RuntimeError(
                    f"Cannot open '{self.database}' read-write: another "
                    "tracebi process holds the warehouse open — stop "
                    "`tracebi serve` / `tracebi dev` first."
                ) from exc
            raise
        try:
            self._write_into(write_conn, df, table, if_exists)
        finally:
            write_conn.close()

    @staticmethod
    def _decimal_columns(df: pd.DataFrame) -> set:
        """Columns this write treats as Decimal: object dtype, at least one
        non-null value, and every non-null value a ``decimal.Decimal``."""
        decimal_cols = set()
        for col in df.columns:
            if df[col].dtype != object:
                continue
            values = df[col].dropna()
            if len(values) and all(isinstance(v, decimal.Decimal) for v in values):
                decimal_cols.add(col)
        return decimal_cols

    @classmethod
    def _decimal_select(cls, df: pd.DataFrame) -> str:
        """SELECT list for the staged frame, casting Decimal columns wide.

        Object columns whose non-null values are all ``decimal.Decimal``
        (at least one non-null) are CAST to ``DECIMAL(38,12)`` — DuckDB's
        ``register()`` otherwise infers a precision/scale from the values
        it samples, which can be too narrow for later rows (and older
        versions degrade to a lossy float64). Every other column passes
        through unchanged; with no Decimal columns this is plain ``*``.
        """
        decimal_cols = cls._decimal_columns(df)
        if not decimal_cols:
            return "*"
        parts = []
        for c in df.columns:
            ident = str(c).replace('"', '""')
            if c in decimal_cols:
                parts.append(f'CAST("{ident}" AS DECIMAL(38,12)) AS "{ident}"')
            else:
                parts.append(f'"{ident}"')
        return ", ".join(parts)

    def _check_append_decimal_types(self, conn, df: pd.DataFrame, table: str) -> None:
        """Refuse an append that would coerce a Decimal column into a
        non-DECIMAL(38,12) column of the existing table.

        DuckDB's INSERT casts to the target column's type, so appending
        exact Decimals into e.g. an INTEGER or DOUBLE column would silently
        change the numbers. A sink must never do that — raise instead.
        Non-Decimal columns are not checked and keep DuckDB's behavior.
        """
        decimal_cols = self._decimal_columns(df)
        if not decimal_cols:
            return
        existing = dict(conn.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ?",
            [table],
        ).fetchall())
        for col in df.columns:
            if col not in decimal_cols or col not in existing:
                continue
            if existing[col] != "DECIMAL(38,12)":
                raise ValueError(
                    f"Cannot append Decimal column '{col}' into table "
                    f"'{table}': the existing column is {existing[col]}, and "
                    "inserting would silently coerce the values. Rewrite the "
                    "table with if_exists=\"replace\" to retype it as "
                    "DECIMAL(38,12), or align the frame's column with the "
                    "table's existing type."
                )

    def _write_into(self, conn, df: pd.DataFrame, table: str, if_exists: str) -> None:
        select = self._decimal_select(df)
        conn.register("__tracebi_tmp__", df)
        try:
            if if_exists == "replace":
                conn.execute(f'DROP TABLE IF EXISTS "{table}"')
                conn.execute(f'CREATE TABLE "{table}" AS SELECT {select} FROM __tracebi_tmp__')
            elif if_exists == "append":
                exists = conn.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = ?",
                    [table],
                ).fetchone()
                if exists:
                    self._check_append_decimal_types(conn, df, table)
                    conn.execute(f'INSERT INTO "{table}" SELECT {select} FROM __tracebi_tmp__')
                else:
                    conn.execute(f'CREATE TABLE "{table}" AS SELECT {select} FROM __tracebi_tmp__')
            elif if_exists == "fail":
                exists = conn.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = ?",
                    [table],
                ).fetchone()
                if exists:
                    raise ValueError(
                        f"Table '{table}' already exists in DuckDBConnector '{self.name}'."
                    )
                conn.execute(f'CREATE TABLE "{table}" AS SELECT {select} FROM __tracebi_tmp__')
            else:
                raise ValueError(
                    f"Invalid if_exists={if_exists!r}; expected replace, append, or fail."
                )
        finally:
            conn.unregister("__tracebi_tmp__")
