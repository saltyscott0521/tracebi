"""
DataModel — Qlik-style relational graph with built-in star-schema query.

A DataModel registers connectors and tables, then exposes two layered query
surfaces over them:

* **Ad-hoc navigation** — declare named relationships with
  ``add_relationship()`` and resolve them via ``resolve()`` /
  ``resolve_chain()`` to get a flat, lineage-tracked DataSet.

* **Analytic queries** — tag tables as dimensions and facts with
  ``add_dimension()`` / ``add_fact()`` and call ``query()`` for filtered,
  aggregated OLAP-style results. Joins are auto-resolved from the fact's
  foreign keys; execution uses DuckDB when available with a pandas fallback.

Both surfaces share the connector/table registry and produce DataSets with
full lineage chains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode


# Threshold (rows) at which an unfiltered, full-table load triggers a
# lineage warning. Visible in the lineage chain, non-blocking.
LARGE_LOAD_WARN_ROWS = 100_000

_AGG_FUNCS = {"sum", "count", "mean", "avg", "min", "max", "nunique"}


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


@dataclass
class _DimensionDef:
    name: str
    table_name: str
    key_col: str
    attributes: list[str] = field(default_factory=list)


@dataclass
class _FactDef:
    name: str
    table_name: str
    measures: list[str]
    foreign_keys: dict[str, str] = field(default_factory=dict)  # dim_name -> fk_col


# ─────────────────────────────────────────────────────────────
# DataModel
# ─────────────────────────────────────────────────────────────

class DataModel:
    """
    A code-defined relational data model with optional star-schema semantics.

    Ad-hoc navigation::

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

    Analytic queries::

        model.add_dimension(
            name="dim_customer",
            table_name="customers",
            key_col="customer_id",
            attributes=["region", "segment"],
        )
        model.add_fact(
            name="fact_orders",
            table_name="orders",
            measures=["revenue", "qty"],
            foreign_keys={"dim_customer": "customer_id"},
        )

        ds = model.query(
            fact="fact_orders",
            measures={"revenue": "sum", "qty": "sum"},
            dimensions=["dim_customer.region"],
            filters={"status": "shipped"},
            aggregate=True,
        )
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._connectors: dict[str, BaseConnector] = {}
        self._tables: dict[str, _TableDef] = {}
        self._relationships: dict[str, _RelationshipDef] = {}
        self._dimensions: dict[str, _DimensionDef] = {}
        self._facts: dict[str, _FactDef] = {}

    # ── Fluent builder ─────────────────────────────────────────

    def add_connector(self, connector: BaseConnector) -> "DataModel":
        """Register a connector by its ``name`` attribute."""
        self._connectors[connector.name] = connector
        return self

    def connectors(self) -> list[BaseConnector]:
        """Return the connector objects registered on this model."""
        return list(self._connectors.values())

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

    def add_dimension(
        self,
        name: str,
        table_name: str,
        key_col: str,
        attributes: Optional[list[str]] = None,
    ) -> "DataModel":
        """Tag a registered table as a dimension with a key column and exposed attributes."""
        if table_name not in self._tables:
            raise ValueError(
                f"Table '{table_name}' is not registered in model '{self.name}'. "
                f"Call add_table() first."
            )
        self._dimensions[name] = _DimensionDef(
            name=name,
            table_name=table_name,
            key_col=key_col,
            attributes=list(attributes) if attributes else [],
        )
        return self

    def add_fact(
        self,
        name: str,
        table_name: str,
        measures: list[str],
        foreign_keys: Optional[dict[str, str]] = None,
    ) -> "DataModel":
        """Tag a registered table as a fact with measure columns and FK mapping to dimensions."""
        if table_name not in self._tables:
            raise ValueError(
                f"Table '{table_name}' is not registered in model '{self.name}'. "
                f"Call add_table() first."
            )
        self._facts[name] = _FactDef(
            name=name,
            table_name=table_name,
            measures=list(measures),
            foreign_keys=dict(foreign_keys) if foreign_keys else {},
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
                "rows_left":    len(left_ds),
                "rows_right":   len(right_ds),
                "rows_after":   len(merged),
                "right_chain_len": len(right_ds.lineage),
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
                    "rows_left":    len(ds),
                    "rows_right":   len(right_ds),
                    "rows_after":   len(merged),
                    "right_chain_len": len(right_ds.lineage),
                },
            )
            ds = DataSet(
                df=merged,
                name=f"{ds.name}_{rel.right_table}",
                lineage=ds.lineage + right_ds.lineage + [join_node],
            )

        return ds

    # ── Analytic query (star-schema) ───────────────────────────

    def query(
        self,
        fact: str,
        measures: dict[str, str],
        dimensions: Optional[list[str]] = None,
        filters: Optional[dict[str, Any]] = None,
        aggregate: bool = True,
    ) -> DataSet:
        """
        Run a star-schema analytic query and return a lineage-tracked DataSet.

        Args:
            fact:       Fact name registered via ``add_fact()``.
            measures:   ``{column: agg_func}`` — e.g.
                        ``{"revenue": "sum", "order_id": "count"}``.
                        Supported agg funcs: ``sum``, ``count``, ``mean``,
                        ``min``, ``max``, ``nunique``.
            dimensions: List of ``"dim_name.attribute"`` references for
                        grouping and selection. May be ``None`` or ``[]``
                        to return aggregate totals only.
            filters:    ``{column: value}`` equality filters applied to the
                        fact table before joining/aggregating.
            aggregate:  When ``True`` (default), group by dimension attributes
                        and aggregate measures. When ``False``, return the
                        flat joined rows with measures selected.

        Returns:
            A DataSet with full lineage covering load → join → filter →
            aggregate steps.
        """
        if fact not in self._facts:
            raise ValueError(
                f"Fact '{fact}' is not registered in model '{self.name}'. "
                f"Available facts: {list(self._facts.keys())}"
            )
        fact_def = self._facts[fact]
        dimensions = list(dimensions or [])
        filters = dict(filters or {})

        # ── Parse dimension references ─────────────────────────
        parsed_dims: list[tuple[str, str]] = []
        for ref in dimensions:
            if "." not in ref:
                raise ValueError(
                    f"Dimension reference '{ref}' must use dot notation: "
                    f"'dim_name.attribute'"
                )
            dim_name, attribute = ref.split(".", 1)
            if dim_name not in self._dimensions:
                raise ValueError(
                    f"Dimension '{dim_name}' is not registered in model "
                    f"'{self.name}'. Available: {list(self._dimensions.keys())}"
                )
            parsed_dims.append((dim_name, attribute))

        # ── Load fact + needed dimension tables ───────────────
        lineage: list[LineageNode] = []
        fact_ds = self.load(fact_def.table_name, filter=filters or None)
        lineage.extend(fact_ds.lineage)
        fact_df = fact_ds.to_pandas()

        needed_dims = {dim_name for dim_name, _ in parsed_dims}
        dim_dfs: dict[str, pd.DataFrame] = {}
        for dim_name in needed_dims:
            dim_def = self._dimensions[dim_name]
            dim_ds = self.load(dim_def.table_name)
            lineage.extend(dim_ds.lineage)
            dim_dfs[dim_name] = dim_ds.to_pandas()

        # A typo'd column must never produce a silently wrong result.
        self._validate_query_columns(
            fact_def, fact_df, dim_dfs, parsed_dims, measures, filters
        )

        for col, val in filters.items():
            lineage.append(LineageNode(
                operation="filter",
                description=f"Filter: {col} == {val!r}",
                metadata={"column": col, "value": val},
            ))

        # ── Try DuckDB engine first; fall back to pandas ──────
        try:
            result_df = self._execute_duckdb(
                fact_df=fact_df,
                fact_def=fact_def,
                dim_dfs=dim_dfs,
                parsed_dims=parsed_dims,
                measures=measures,
                filters=filters,
                aggregate=aggregate,
                lineage=lineage,
            )
            engine = "duckdb"
        except ImportError:
            result_df = self._execute_pandas(
                fact_df=fact_df,
                fact_def=fact_def,
                dim_dfs=dim_dfs,
                parsed_dims=parsed_dims,
                measures=measures,
                filters=filters,
                aggregate=aggregate,
                lineage=lineage,
            )
            engine = "pandas"

        lineage.append(LineageNode(
            operation="transform",
            description=f"Star-schema query executed via {engine}",
            metadata={"engine": engine, "rows_out": len(result_df)},
        ))

        return DataSet(df=result_df, name=f"{fact}_result", lineage=lineage)

    @staticmethod
    def _hint(name: str, options) -> str:
        import difflib
        close = difflib.get_close_matches(name, [str(o) for o in options], n=1)
        return f" Did you mean '{close[0]}'?" if close else ""

    def _validate_query_columns(
        self,
        fact_def,
        fact_df: pd.DataFrame,
        dim_dfs: dict[str, pd.DataFrame],
        parsed_dims: list[tuple[str, str]],
        measures: dict[str, str],
        filters: dict[str, Any],
    ) -> None:
        """Raise ValueError for any measure, filter, or dimension-attribute
        reference that doesn't exist. Both query engines rely on this —
        a typo must fail loudly, never return a silently wrong result."""
        fact_cols = set(fact_df.columns)
        for col in measures:
            if col not in fact_cols:
                raise ValueError(
                    f"Measure column '{col}' not found on fact table "
                    f"'{fact_def.table_name}'.{self._hint(col, fact_cols)} "
                    f"Available columns: {sorted(fact_cols)}"
                )
        for col in filters:
            if col not in fact_cols:
                raise ValueError(
                    f"Filter column '{col}' not found on fact table "
                    f"'{fact_def.table_name}'.{self._hint(col, fact_cols)} "
                    f"Available columns: {sorted(fact_cols)}"
                )
        for dim_name, attribute in parsed_dims:
            dim_def = self._dimensions[dim_name]
            declared = dim_def.attributes
            if declared and attribute not in declared and attribute != dim_def.key_col:
                raise ValueError(
                    f"Attribute '{attribute}' is not declared on dimension "
                    f"'{dim_name}'.{self._hint(attribute, declared)} "
                    f"Declared attributes: {declared}"
                )
            dim_cols = set(dim_dfs[dim_name].columns)
            if attribute not in dim_cols:
                raise ValueError(
                    f"Attribute '{attribute}' not found on dimension table "
                    f"'{dim_def.table_name}'.{self._hint(attribute, dim_cols)} "
                    f"Available columns: {sorted(dim_cols)}"
                )

    # ── DuckDB engine ──────────────────────────────────────────

    def _execute_duckdb(
        self,
        *,
        fact_df: pd.DataFrame,
        fact_def: _FactDef,
        dim_dfs: dict[str, pd.DataFrame],
        parsed_dims: list[tuple[str, str]],
        measures: dict[str, str],
        filters: dict[str, Any],
        aggregate: bool,
        lineage: list[LineageNode],
    ) -> pd.DataFrame:
        import duckdb

        con = duckdb.connect(":memory:")
        try:
            con.register("fact", fact_df)
            for dim_name, dim_df in dim_dfs.items():
                con.register(f"dim_{dim_name}", dim_df)

            group_cols_sql: list[str] = []
            select_cols_sql: list[str] = []
            for dim_name, attribute in parsed_dims:
                alias = f'"{dim_name}.{attribute}"'
                expr = f'dim_{dim_name}."{attribute}" AS {alias}'
                select_cols_sql.append(expr)
                group_cols_sql.append(alias)

            if aggregate:
                for col, func in measures.items():
                    func_l = func.lower()
                    if func_l not in _AGG_FUNCS:
                        raise ValueError(
                            f"Unsupported aggregation '{func}' for measure '{col}'"
                        )
                    sql_func = "AVG" if func_l == "mean" else (
                        "COUNT(DISTINCT" if func_l == "nunique" else func_l.upper()
                    )
                    if func_l == "nunique":
                        select_cols_sql.append(
                            f'COUNT(DISTINCT fact."{col}") AS "{col}"'
                        )
                    else:
                        select_cols_sql.append(
                            f'{sql_func}(fact."{col}") AS "{col}"'
                        )
            else:
                for col in measures.keys():
                    select_cols_sql.append(f'fact."{col}" AS "{col}"')

            from_clause = "fact"
            for dim_name in {d for d, _ in parsed_dims}:
                dim_def = self._dimensions[dim_name]
                fk_col = fact_def.foreign_keys.get(dim_name, dim_def.key_col)
                from_clause += (
                    f' LEFT JOIN dim_{dim_name} '
                    f'ON fact."{fk_col}" = dim_{dim_name}."{dim_def.key_col}"'
                )
                lineage.append(LineageNode(
                    operation="join",
                    description=(
                        f"Joined fact '{fact_def.table_name}' → dim "
                        f"'{dim_def.table_name}' on {fk_col} = "
                        f"{dim_def.key_col} (left)"
                    ),
                    metadata={
                        "fact":      fact_def.table_name,
                        "dimension": dim_def.table_name,
                        "fact_key":  fk_col,
                        "dim_key":   dim_def.key_col,
                        "engine":    "duckdb",
                    },
                ))

            where_clauses: list[str] = []
            params: list[Any] = []
            for col, val in filters.items():
                where_clauses.append(f'fact."{col}" = ?')
                params.append(val)

            sql = "SELECT " + ", ".join(select_cols_sql) + f" FROM {from_clause}"
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            if aggregate and group_cols_sql:
                sql += " GROUP BY " + ", ".join(group_cols_sql)

            return con.execute(sql, params).df()
        finally:
            con.close()

    # ── Pandas fallback engine ────────────────────────────────

    def _execute_pandas(
        self,
        *,
        fact_df: pd.DataFrame,
        fact_def: _FactDef,
        dim_dfs: dict[str, pd.DataFrame],
        parsed_dims: list[tuple[str, str]],
        measures: dict[str, str],
        filters: dict[str, Any],
        aggregate: bool,
        lineage: list[LineageNode],
    ) -> pd.DataFrame:
        df = fact_df
        for col, val in filters.items():
            if col in df.columns:
                df = df[df[col] == val]

        for dim_name in {d for d, _ in parsed_dims}:
            dim_def = self._dimensions[dim_name]
            fk_col = fact_def.foreign_keys.get(dim_name, dim_def.key_col)
            dim_df = dim_dfs[dim_name]
            attr_cols = [dim_def.key_col] + (
                dim_def.attributes if dim_def.attributes
                else [c for c in dim_df.columns if c != dim_def.key_col]
            )
            dim_df = dim_df[attr_cols].rename(
                columns={c: f"{dim_name}.{c}" for c in attr_cols if c != dim_def.key_col}
            )
            df = df.merge(
                dim_df,
                left_on=fk_col,
                right_on=dim_def.key_col,
                how="left",
                suffixes=("", f"_{dim_name}"),
            )
            lineage.append(LineageNode(
                operation="join",
                description=(
                    f"Joined fact '{fact_def.table_name}' → dim "
                    f"'{dim_def.table_name}' on {fk_col} = "
                    f"{dim_def.key_col} (left)"
                ),
                metadata={
                    "fact":      fact_def.table_name,
                    "dimension": dim_def.table_name,
                    "fact_key":  fk_col,
                    "dim_key":   dim_def.key_col,
                    "engine":    "pandas",
                },
            ))

        groupby_cols = [f"{d}.{a}" for d, a in parsed_dims]

        if aggregate and groupby_cols:
            return df.groupby(groupby_cols, as_index=False).agg(
                {col: func for col, func in measures.items()}
            )
        if aggregate and not groupby_cols:
            row: dict[str, Any] = {}
            for col, func in measures.items():
                s = df[col] if col in df.columns else pd.Series(dtype=float)
                if func == "sum":
                    row[col] = s.sum()
                elif func == "count":
                    row[col] = s.count()
                elif func == "mean":
                    row[col] = s.mean()
                elif func == "min":
                    row[col] = s.min()
                elif func == "max":
                    row[col] = s.max()
                elif func == "nunique":
                    row[col] = s.nunique()
                else:
                    row[col] = s.agg(func)
            return pd.DataFrame([row])

        select_cols = groupby_cols + list(measures.keys())
        select_cols = [c for c in select_cols if c in df.columns]
        return df[select_cols].copy()

    # ── Inspection ─────────────────────────────────────────────

    def info(self) -> dict:
        """
        The model's structure as a plain dict (tables, relationships,
        facts, dimensions). This is the stable surface the web layer reads —
        prefer it over touching private attributes.
        """
        return {
            "name": self.name,
            "connectors": list(self._connectors.keys()),
            "tables": [
                {"name": t.name, "connector": t.connector_name, "source": t.source}
                for t in self._tables.values()
            ],
            "relationships": [
                {
                    "name": r.name,
                    "left_table": r.left_table,
                    "right_table": r.right_table,
                    "left_key": r.left_key,
                    "right_key": r.right_key,
                    "how": r.how,
                }
                for r in self._relationships.values()
            ],
            "facts": [
                {
                    "name": f.name,
                    "table": f.table_name,
                    "measures": list(f.measures),
                    "foreign_keys": dict(f.foreign_keys),
                }
                for f in self._facts.values()
            ],
            "dimensions": [
                {
                    "name": d.name,
                    "table": d.table_name,
                    "key": d.key_col,
                    "attributes": list(d.attributes),
                }
                for d in self._dimensions.values()
            ],
        }

    def describe(self) -> None:
        """Print a summary of the model's connectors, tables, relationships, facts, and dimensions."""
        sep = "=" * 55
        print(f"\n{sep}")
        print(f"  DataModel: '{self.name}'")
        print(f"  Connectors ({len(self._connectors)}): {list(self._connectors.keys())}")
        print(f"  Tables ({len(self._tables)}): {list(self._tables.keys())}")
        print(f"  Relationships ({len(self._relationships)}): {list(self._relationships.keys())}")
        if self._facts:
            print(f"  Facts ({len(self._facts)}):")
            for f in self._facts.values():
                print(f"    {f.name} → {f.table_name}  measures={f.measures}")
        if self._dimensions:
            print(f"  Dimensions ({len(self._dimensions)}):")
            for d in self._dimensions.values():
                print(f"    {d.name} → {d.table_name}  key={d.key_col}  attrs={d.attributes}")
        print(f"{sep}\n")

    def help(self) -> None:
        """Print a cheat sheet of the DataModel API."""
        print(
            "\nDataModel — associative model linking DataSets by key.\n"
            "\n"
            "Building:\n"
            "  .add_connector(connector)                Register a data source\n"
            '  .add_table(name, connector=, source=)    Declare a table\n'
            "  .add_relationship(name, left_table=, right_table=, left_key=, right_key=)\n"
            "  .add_fact(name, table=, measures=[...])  Star-schema fact\n"
            "  .add_dimension(name, table=, key=, attributes=[...])\n"
            "\n"
            "Loading & querying (all return a DataSet with lineage):\n"
            "  .load(table_name)                        Load one table\n"
            "  .resolve(relationship_name)              Join two tables\n"
            "  .resolve_chain([rel1, rel2, ...])        Chain multiple joins\n"
            "  .query(fact=, dimensions=[...], measures={...}, filters={...})\n"
            "\n"
            "Inspection:\n"
            "  .info()        Structure as a dict\n"
            "  .describe()    Print a text summary\n"
        )

    def _repr_html_(self) -> str:
        """Rich notebook display: tables, relationships, facts, dimensions."""
        import html as _h

        info = self.info()
        h_css = "font-weight:700;color:#1F3864;font-size:12px;margin:8px 0 4px 0"
        item_css = "font-size:11px;color:#333;padding:1px 0"

        def block(title: str, lines: list[str]) -> str:
            if not lines:
                return ""
            items = "".join(f'<div style="{item_css}">{line}</div>' for line in lines)
            return f'<div style="{h_css}">{title}</div>{items}'

        tables = [
            f'<b>{_h.escape(t["name"])}</b> '
            f'<span style="color:#999">← {_h.escape(t["connector"])} / {_h.escape(t["source"])}</span>'
            for t in info["tables"]
        ]
        rels = [
            f'<b>{_h.escape(r["name"])}</b> '
            f'<span style="color:#999">{_h.escape(r["left_table"])}.{_h.escape(r["left_key"])} '
            f'{_h.escape(r["how"])}-join {_h.escape(r["right_table"])}.{_h.escape(r["right_key"])}</span>'
            for r in info["relationships"]
        ]
        facts = [
            f'<b>{_h.escape(f["name"])}</b> '
            f'<span style="color:#999">→ {_h.escape(f["table"])} measures={f["measures"]}</span>'
            for f in info["facts"]
        ]
        dims = [
            f'<b>{_h.escape(d["name"])}</b> '
            f'<span style="color:#999">→ {_h.escape(d["table"])} key={_h.escape(d["key"])} '
            f'attrs={d["attributes"]}</span>'
            for d in info["dimensions"]
        ]

        return f"""
<div style="font-family:'Segoe UI',Calibri,Arial,sans-serif;border:1px solid #dde4ef;border-radius:6px;padding:12px 16px;display:inline-block;max-width:100%">
  <div>
    <span style="font-weight:700;color:#1F3864;font-size:14px">DataModel: {_h.escape(self.name)}</span>
    <span style="color:#666;font-size:11px;margin-left:8px">connectors: {", ".join(_h.escape(c) for c in info["connectors"]) or "—"}</span>
  </div>
  {block("Tables", tables)}
  {block("Relationships", rels)}
  {block("Facts", facts)}
  {block("Dimensions", dims)}
</div>"""

    def __repr__(self) -> str:
        return (
            f"<DataModel name={self.name!r} "
            f"tables={list(self._tables.keys())} "
            f"relationships={list(self._relationships.keys())} "
            f"facts={list(self._facts.keys())} "
            f"dimensions={list(self._dimensions.keys())}>"
        )
