"""
StarSchema — join-free analytic query engine over a DataModel.

Dimensions and facts are registered by name; ``query()`` auto-resolves
all necessary joins, applies filters, aggregates, and returns a
fully lineage-tracked DataSet.

Dimension references use dot notation: ``"dim_customer.region"``.
Measures use a dict: ``{"revenue": "sum", "order_id": "count"}``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from tracebi.model.dataset import DataSet, LineageNode
from tracebi.model.data_model import DataModel


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
        """
        Register a dimension table.

        Args:
            name:       Logical dimension name (e.g. ``"dim_customer"``).
            table_name: Table name as registered in the DataModel.
            key_col:    Primary key column used to join to fact tables.
            attributes: Columns available for grouping/display. If omitted,
                        all columns except ``key_col`` are considered attributes.
        """
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
        """
        Register a fact table.

        Args:
            name:         Logical fact name (e.g. ``"fact_orders"``).
            table_name:   Table name as registered in the DataModel.
            measures:     Numeric columns that can be aggregated.
            foreign_keys: Mapping of ``{dim_name: fk_column}`` — the column
                          in the fact table that joins to the dimension's key.
                          If a dimension name maps to the same column as the
                          dimension's ``key_col``, you may omit it and the
                          key_col will be used by default.
        """
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
        parsed_dims: list[tuple[str, str]] = []  # (dim_name, attribute)
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

        # ── Load fact table ────────────────────────────────────
        lineage: list[LineageNode] = []
        fact_ds = self._model.load(fact_def.table_name)
        lineage.extend(fact_ds.lineage)
        df = fact_ds.to_pandas()

        # ── Apply filters ──────────────────────────────────────
        for col, val in filters.items():
            rows_before = len(df)
            df = df[df[col] == val]
            lineage.append(LineageNode(
                operation="filter",
                description=f"Filter: {col} == {val!r}",
                metadata={
                    "column":       col,
                    "value":        val,
                    "rows_before":  rows_before,
                    "rows_after":   len(df),
                    "rows_removed": rows_before - len(df),
                },
            ))

        # ── Join required dimensions ───────────────────────────
        needed_dims = {dim_name for dim_name, _ in parsed_dims}
        for dim_name in needed_dims:
            dim_def = self._dimensions[dim_name]
            dim_ds = self._model.load(dim_def.table_name)
            lineage.extend(dim_ds.lineage)

            fk_col = fact_def.foreign_keys.get(dim_name, dim_def.key_col)
            dim_df = dim_ds.to_pandas()

            # prefix dim attribute columns to avoid collisions
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
                    f"Joined fact '{fact_def.table_name}' → dim '{dim_def.table_name}' "
                    f"on {fk_col} = {dim_def.key_col} (left)"
                ),
                metadata={
                    "fact":       fact_def.table_name,
                    "dimension":  dim_def.table_name,
                    "fact_key":   fk_col,
                    "dim_key":    dim_def.key_col,
                },
            ))

        # ── Build group-by columns (prefixed) ─────────────────
        groupby_cols = [f"{dim_name}.{attr}" for dim_name, attr in parsed_dims]

        # ── Aggregate or select ────────────────────────────────
        if aggregate and groupby_cols:
            agg_spec = {col: func for col, func in measures.items()}
            result_df = df.groupby(groupby_cols, as_index=False).agg(agg_spec)
            lineage.append(LineageNode(
                operation="transform",
                description=(
                    f"Aggregated [{', '.join(f'{c}:{f}' for c, f in measures.items())}] "
                    f"grouped by [{', '.join(groupby_cols)}]"
                ),
                metadata={
                    "measures":    measures,
                    "group_by":    groupby_cols,
                    "rows_out":    len(result_df),
                },
            ))
        elif aggregate and not groupby_cols:
            # Total aggregates — no groupby
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
            result_df = pd.DataFrame([row])
            lineage.append(LineageNode(
                operation="transform",
                description=f"Grand total aggregation: {measures}",
                metadata={"measures": measures},
            ))
        else:
            # No aggregation — select relevant columns
            select_cols = groupby_cols + list(measures.keys())
            select_cols = [c for c in select_cols if c in df.columns]
            result_df = df[select_cols].copy()

        result_name = f"{fact}_result"
        return DataSet(df=result_df, name=result_name, lineage=lineage)

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
