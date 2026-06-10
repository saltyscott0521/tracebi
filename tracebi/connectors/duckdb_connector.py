"""DuckDB connector — fast, file- or memory-backed analytic database."""

from __future__ import annotations

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

    def supports_pushdown(self) -> bool:
        return True

    def describe(self) -> dict:
        out = {**super().describe(), "database": self.database}
        if self.directory:
            out["directory"] = self.directory
        return out

    def connect(self) -> None:
        try:
            import duckdb
        except ImportError:
            raise ImportError(
                "duckdb is required for DuckDBConnector.\n"
                "Install with: pip install 'tracebi[duckdb]'"
            )
        if self._conn is None:
            self._conn = duckdb.connect(self.database)

    @property
    def connection(self):
        """Underlying DuckDB connection (for advanced use)."""
        if self._conn is None:
            self.connect()
        return self._conn

    def register_df(self, name: str, df: pd.DataFrame) -> "DuckDBConnector":
        """Register a pandas DataFrame as a DuckDB view named *name*."""
        if self._conn is None:
            self.connect()
        self._conn.register(name, df)
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
        """Persist *df* into a DuckDB table named *table*."""
        if self._conn is None:
            self.connect()
        self._conn.register("__tracebi_tmp__", df)
        try:
            if if_exists == "replace":
                self._conn.execute(f'DROP TABLE IF EXISTS "{table}"')
                self._conn.execute(f'CREATE TABLE "{table}" AS SELECT * FROM __tracebi_tmp__')
            elif if_exists == "append":
                exists = self._conn.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = ?",
                    [table],
                ).fetchone()
                if exists:
                    self._conn.execute(f'INSERT INTO "{table}" SELECT * FROM __tracebi_tmp__')
                else:
                    self._conn.execute(f'CREATE TABLE "{table}" AS SELECT * FROM __tracebi_tmp__')
            elif if_exists == "fail":
                exists = self._conn.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = ?",
                    [table],
                ).fetchone()
                if exists:
                    raise ValueError(
                        f"Table '{table}' already exists in DuckDBConnector '{self.name}'."
                    )
                self._conn.execute(f'CREATE TABLE "{table}" AS SELECT * FROM __tracebi_tmp__')
            else:
                raise ValueError(
                    f"Invalid if_exists={if_exists!r}; expected replace, append, or fail."
                )
        finally:
            self._conn.unregister("__tracebi_tmp__")
