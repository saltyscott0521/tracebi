"""
DataModel — Qlik-style relational graph of connectors and tables.

Register connectors and tables, declare named relationships (joins),
then call ``model.load()``, ``model.resolve()``, or ``model.resolve_chain()``
to get fully lineage-tracked DataSets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode


# Threshold (rows) at which an unfiltered, full-table load triggers a
# lineage warning. Visible in the lineage chain, non-blocking.
LARGE_LOAD_WARN_ROWS = 100_000


# ─────────────────────────────────────────────────────────────
# Internal config dataclasses
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _TableDef:
    name: str
    connector_name: str
    source: str


@dataclass(frozen=True)
class _RelationshipDef:
    name: str
    left_table: str
    right_table: str
    left_key: str
    right_key: str
    how: str  # left | inner | right | outer


# ─────────────────────────────────────────────────────────────
# DataModel
# ─────────────────────────────────────────────────────────────

class DataModel:
    """
    A code-defined, Qlik-style relational data model.

    Usage:
        from tracebi import DataModel, CSVConnector, SQLConnector

        model = DataModel("SalesModel")
        model.add_connector(SQLConnector("sales_db", url="sqlite:///sales.db"))
        model.add_connector(CSVConnector("lookups", directory="data/"))

        model.add_table("orders",    connector="sales_db", source="orders")
        model.add_table("customers", connector="sales_db", source="customers")
        model.add_table("regions",   connector="lookups",  source="regions.csv")

        model.add_relationship(
            name="orders_customers",
            left_table="orders",
            right_table="customers",
            left_key="customer_id",
            how="left",
        )

        model.connect()
        orders_ds = model.load("orders")
        joined_ds = model.resolve("orders_customers")
        full_ds   = model.resolve_chain(["orders_customers", "customers_regions"])
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._connectors: dict[str, BaseConnector] = {}
        self._tables: dict[str, _TableDef] = {}
        self._relationships: dict[str, _RelationshipDef] = {}

    # ── Fluent builder ─────────────────────────────────────────

    def add_connector(self, connector: BaseConnector) -> "DataModel":
        """Register a connector by its ``name`` attribute."""
        self._connectors[connector.name] = connector
        return self

    def add_table(
        self,
        name: str,
        connector: str,
        source: str,
    ) -> "DataModel":
        """
        Register a table.

        Args:
            name:      Logical table name used in relationships and ``load()``.
            connector: Name of a previously registered connector.
            source:    Source identifier passed to the connector's ``load()``
                       (e.g. table name, file name, SQL query).
        """
        if connector not in self._connectors:
            raise ValueError(
                f"Connector '{connector}' is not registered in model '{self.name}'. "
                f"Call add_connector() first."
            )
        self._tables[name] = _TableDef(name=name, connector_name=connector, source=source)
        return self

    def add_relationship(
        self,
        name: str,
        left_table: str,
        right_table: str,
        left_key: str,
        right_key: Optional[str] = None,
        how: str = "left",
    ) -> "DataModel":
        """
        Declare a named join relationship between two tables.

        Args:
            name:        Unique relationship name; used in ``resolve()`` and
                         ``resolve_chain()``.
            left_table:  Name of the left-hand table.
            right_table: Name of the right-hand table.
            left_key:    Column in the left table to join on.
            right_key:   Column in the right table to join on.
                         Defaults to ``left_key`` when omitted.
            how:         Pandas merge type: ``'left'``, ``'inner'``,
                         ``'right'``, ``'outer'``. Default ``'left'``.
        """
        for tbl in (left_table, right_table):
            if tbl not in self._tables:
                raise ValueError(
                    f"Table '{tbl}' is not registered in model '{self.name}'. "
                    f"Call add_table() first."
                )
        self._relationships[name] = _RelationshipDef(
            name=name,
            left_table=left_table,
            right_table=right_table,
            left_key=left_key,
            right_key=right_key or left_key,
            how=how,
        )
        return self

    # ── Connection ─────────────────────────────────────────────

    def connect(self) -> None:
        """Call ``connect()`` on every registered connector."""
        for connector in self._connectors.values():
            connector.connect()

    # ── Data loading ───────────────────────────────────────────

    def load(
        self,
        table_name: str,
        filter: Optional[dict[str, Any]] = None,
        columns: Optional[list[str]] = None,
    ) -> DataSet:
        """
        Load a registered table and return a lineage-tracked DataSet.

        Every call to ``load()`` re-reads from the source (no caching),
        so lineage is always fresh.

        Args:
            table_name: Registered table name.
            filter:     Optional ``{column: value}`` equality filters pushed
                        down to the connector where possible (SQL WHERE,
                        DuckDB predicate), applied in pandas otherwise.
            columns:    Optional list of columns to project at source.

        Lineage: emits one ``operation="load"`` node, plus a non-blocking
        ``operation="warning"`` node when the load is unfiltered, unprojected,
        and returns more than ``LARGE_LOAD_WARN_ROWS`` rows.
        """
        if table_name not in self._tables:
            raise ValueError(
                f"Table '{table_name}' is not registered in model '{self.name}'. "
                f"Available tables: {list(self._tables.keys())}"
            )
        tdef = self._tables[table_name]
        connector = self._connectors[tdef.connector_name]
        df = connector.load(tdef.source, filter=filter, columns=columns)
        pushdown = connector.supports_pushdown() and (filter or columns)
        load_node = LineageNode(
            operation="load",
            description=f"Loaded '{table_name}' from connector '{tdef.connector_name}'",
            connector={
                "connector_name": tdef.connector_name,
                "connector_type": type(connector).__name__,
            },
            source=tdef.source,
            metadata={
                "rows_loaded": len(df),
                "filter":      filter,
                "columns":     columns,
                "pushdown":    bool(pushdown),
            },
        )
        nodes = [load_node]
        if not filter and not columns and len(df) > LARGE_LOAD_WARN_ROWS:
            nodes.append(LineageNode(
                operation="warning",
                description=(
                    f"Large unfiltered load: {len(df):,} rows from "
                    f"'{table_name}'. Consider passing filter= or columns= "
                    "to push the predicate to the source."
                ),
                metadata={
                    "rows_loaded": len(df),
                    "threshold":   LARGE_LOAD_WARN_ROWS,
                    "table":       table_name,
                },
            ))
        return DataSet(df=df, name=table_name, lineage=nodes)

    def resolve(self, relationship_name: str) -> DataSet:
        """
        Load and join two tables according to a named relationship.

        Returns a DataSet whose lineage includes load steps for both tables
        and a join step.
        """
        if relationship_name not in self._relationships:
            raise ValueError(
                f"Relationship '{relationship_name}' is not registered in model '{self.name}'. "
                f"Available: {list(self._relationships.keys())}"
            )
        rel = self._relationships[relationship_name]
        left_ds = self.load(rel.left_table)
        right_ds = self.load(rel.right_table)

        merged = left_ds.to_pandas().merge(
            right_ds.to_pandas(),
            left_on=rel.left_key,
            right_on=rel.right_key,
            how=rel.how,
            suffixes=("", f"_{rel.right_table}"),
        )
        join_node = LineageNode(
            operation="join",
            description=(
                f"Joined '{rel.left_table}' → '{rel.right_table}' "
                f"on {rel.left_key}={rel.right_key} ({rel.how})"
            ),
            metadata={
                "relationship": relationship_name,
                "left_key":     rel.left_key,
                "right_key":    rel.right_key,
                "how":          rel.how,
            },
        )
        combined_lineage = left_ds.lineage + right_ds.lineage + [join_node]
        return DataSet(
            df=merged,
            name=f"{rel.left_table}_{rel.right_table}",
            lineage=combined_lineage,
        )

    def resolve_chain(self, relationship_names: list[str]) -> DataSet:
        """
        Resolve a chain of relationships left-to-right.

        Equivalent to calling ``resolve()`` iteratively, accumulating all
        lineage steps.

        Example:
            full = model.resolve_chain(["orders_customers", "customers_regions"])
        """
        if not relationship_names:
            raise ValueError("resolve_chain() requires at least one relationship name.")

        ds = self.resolve(relationship_names[0])

        for rel_name in relationship_names[1:]:
            if rel_name not in self._relationships:
                raise ValueError(
                    f"Relationship '{rel_name}' is not registered in model '{self.name}'."
                )
            rel = self._relationships[rel_name]
            right_ds = self.load(rel.right_table)
            merged = ds.to_pandas().merge(
                right_ds.to_pandas(),
                left_on=rel.left_key,
                right_on=rel.right_key,
                how=rel.how,
                suffixes=("", f"_{rel.right_table}"),
            )
            join_node = LineageNode(
                operation="join",
                description=(
                    f"Joined → '{rel.right_table}' "
                    f"on {rel.left_key}={rel.right_key} ({rel.how})"
                ),
                metadata={
                    "relationship": rel_name,
                    "left_key":     rel.left_key,
                    "right_key":    rel.right_key,
                    "how":          rel.how,
                },
            )
            ds = DataSet(
                df=merged,
                name=f"{ds.name}_{rel.right_table}",
                lineage=ds.lineage + right_ds.lineage + [join_node],
            )

        return ds

    # ── Inspection ─────────────────────────────────────────────

    def describe(self) -> None:
        """Print a summary of the model's connectors, tables, and relationships."""
        sep = "=" * 55
        print(f"\n{sep}")
        print(f"  DataModel: '{self.name}'")
        print(f"  Connectors ({len(self._connectors)}): {list(self._connectors.keys())}")
        print(f"  Tables ({len(self._tables)}): {list(self._tables.keys())}")
        print(f"  Relationships ({len(self._relationships)}): {list(self._relationships.keys())}")
        print(f"{sep}\n")

    def __repr__(self) -> str:
        return (
            f"<DataModel name={self.name!r} "
            f"tables={list(self._tables.keys())} "
            f"relationships={list(self._relationships.keys())}>"
        )
