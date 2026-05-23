"""
StarSchema — join-free analytic query engine over a DataModel.

Dimensions and facts are registered by name; ``query()`` auto-resolves
all necessary joins, applies filters, aggregates, and returns a
fully lineage-tracked DataSet.

Dimension references use dot notation: ``"dim_customer.region"``.
Measures use a dict: ``{"revenue": "sum", "order_id": "count"}``.

Internally the query is executed in DuckDB when available: each input
table is registered as a DuckDB view (zero-copy from pandas) and the
join + filter + aggregate runs as a single SQL statement. The result
is materialised back to a pandas DataFrame so the user-facing API is
unchanged. When ``duckdb`` is not installed, falls back to pandas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from tracebi.model.dataset import DataSet, LineageNode
from tracebi.model.data_model import DataModel


_AGG_FUNCS = {"sum", "count", "mean", "avg", "min", "max", "nunique"}


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


class StarSchema:
    """
    Declarative star schema over a DataModel.

    Usage::

        schema = StarSchema("Sales", model=model)

        schema.add_dimension(
            name="dim_customer",
            table_name="customers",
            key_col="customer_id",
            attributes=["region", "segment"],
        )
        schema.add_fact(
            name="fact_orders",
            table_name="orders",
            measures=["revenue", "qty"],
            foreign_keys={"dim_customer": "customer_id"},
        )

        ds = schema.query(
            fact="fact_orders",
            measures={"revenue": "sum", "qty": "sum"},
            dimensions=["dim_customer.region"],
            filters={"status": "shipped"},
            aggregate=True,
        )
    """

    def __init__(self, name: str, model: DataModel) -> None:
        self.name = name
        self._model = model
        self._dimensions: dict[str, _DimensionDef] = {}
        self._facts: dict[str, _FactDef] = {}

    # ── Registration ───────────────────────────────────────────

    def add_dimension(
        self,
        name: str,
        table_name: str,
        key_col: str,
        attributes: Optional[list[str]] = None,
    ) -> "StarSchema":
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
    ) -> "StarSchema":
        self._facts[name] = _FactDef(
            name=name,
            table_name=table_name,
            measures=list(measures),
            foreign_keys=dict(foreign_keys) if foreign_keys else {},
        )
        return self

    # ── Query ──────────────────────────────────────────────────

    def query(
        self,
        fact: str,
        measures: dict[str, str],
        dimensions: Optional[list[str]] = None,
        filters: Optional[dict[str, Any]] = None,
        aggregate: bool = True,
    ) -> DataSet:
        """
        Run an analytic query and return a lineage-tracked DataSet.

        Args:
            fact:       Fact name registered via ``add_fact()``.
            measures:   ``{column: agg_func}`` — e.g.
                        ``{"revenue": "sum", "order_id": "count"}``.
                        Supported agg funcs: ``sum``, ``count``, ``mean``,
                        ``min``, ``max``, ``nunique``.
            dimensions: List of ``"dim_name.attribute"`` references for
                        grouping and selection.  May be ``None`` or ``[]``
                        to return aggregate totals only.
            filters:    ``{column: value}`` equality filters applied to the
                        fact table before joining/aggregating.
            aggregate:  When ``True`` (default), group by dimension attributes
                        and aggregate measures.  When ``False``, return the
                        flat joined rows with measures selected.

        Returns:
            A DataSet with full lineage covering load → join → filter →
            aggregate steps.
        """
        if fact not in self._facts:
            raise ValueError(
                f"Fact '{fact}' is not registered in StarSchema '{self.name}'. "
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
                    f"Dimension '{dim_name}' is not registered in StarSchema "
                    f"'{self.name}'. Available: {list(self._dimensions.keys())}"
                )
            parsed_dims.append((dim_name, attribute))

        # ── Load fact + needed dimension tables ───────────────
        lineage: list[LineageNode] = []
        # Push fact-table filters down via the connector when columns match
        fact_ds = self._model.load(fact_def.table_name, filter=filters or None)
        lineage.extend(fact_ds.lineage)
        fact_df = fact_ds.to_pandas()

        needed_dims = {dim_name for dim_name, _ in parsed_dims}
        dim_dfs: dict[str, pd.DataFrame] = {}
        for dim_name in needed_dims:
            dim_def = self._dimensions[dim_name]
            dim_ds = self._model.load(dim_def.table_name)
            lineage.extend(dim_ds.lineage)
            dim_dfs[dim_name] = dim_ds.to_pandas()

        # ── Note any remaining filters not pushed at source ───
        # (the connector applies what it can; we re-apply in DuckDB/pandas
        # to be safe across connector implementations)
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
            description=f"StarSchema query executed via {engine}",
            metadata={"engine": engine, "rows_out": len(result_df)},
        ))

        return DataSet(df=result_df, name=f"{fact}_result", lineage=lineage)

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

            # SELECT list
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

            # FROM + joins
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

            # WHERE — re-apply filters that may not have been pushed down
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

    def describe(self) -> None:
        sep = "=" * 55
        print(f"\n{sep}")
        print(f"  StarSchema: '{self.name}'")
        print(f"  Facts ({len(self._facts)}):")
        for f in self._facts.values():
            print(f"    {f.name} → {f.table_name}  measures={f.measures}")
        print(f"  Dimensions ({len(self._dimensions)}):")
        for d in self._dimensions.values():
            print(f"    {d.name} → {d.table_name}  key={d.key_col}  attrs={d.attributes}")
        print(f"{sep}\n")

    def __repr__(self) -> str:
        return (
            f"<StarSchema name={self.name!r} "
            f"facts={list(self._facts.keys())} "
            f"dimensions={list(self._dimensions.keys())}>"
        )
