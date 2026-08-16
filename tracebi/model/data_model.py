"""
DataModel — governed semantic model: tables, relationships, declared
facts/dimensions/measures, and a star-schema query surface.

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

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode, frame_fingerprint


# Threshold (rows) at which an unfiltered, full-table load triggers a
# lineage warning. Visible in the lineage chain, non-blocking.
LARGE_LOAD_WARN_ROWS = 100_000

_AGG_FUNCS = {"sum", "count", "mean", "avg", "min", "max", "nunique"}

# Filter operators. A closed set rather than free SQL: free SQL cannot be
# validated, cannot be executed by the pandas engine, and is an injection
# surface. Every operator below is implemented in both engines and is
# parameterised in the DuckDB path.
#   {"region": "NE"}                        → eq  (scalar shorthand)
#   {"region": ["NE", "SE"]}                → in  (list shorthand)
#   {"revenue": {"gte": 1000}}              → explicit operator
#   {"dim_customer.region": "NE"}           → filter on a dimension attribute
FILTER_OPS = (
    "eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte",
    "between", "is_null", "not_null", "contains",
)

# Operators whose value is not a plain scalar.
_LIST_OPS = ("in", "not_in")
_NULL_OPS = ("is_null", "not_null")


# ─────────────────────────────────────────────────────────────
# Internal config dataclasses
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Predicate:
    """
    One parsed filter condition.

    ``target`` is either a fact column name or a ``"dim_name.attribute"``
    reference. Dimension predicates require the dimension to be joined, so
    they are applied after the join; fact predicates can be pushed down.
    """
    target: str
    op: str
    value: Any
    dim_name: Optional[str] = None      # set for dimension predicates
    attribute: Optional[str] = None

    @property
    def is_dim(self) -> bool:
        return self.dim_name is not None

    def describe(self) -> str:
        if self.op in _NULL_OPS:
            return f"{self.target} {self.op.replace('_', ' ')}"
        return f"{self.target} {self.op} {self.value!r}"


@dataclass(frozen=True)
class MeasureDef:
    """
    A named, governed measure declared on the model.

    Defined once in ``models/<name>.py``, reviewed in a pull request,
    versioned in git, and referenced by name from every report — this is
    what makes the model a shared vocabulary rather than a pile of ad-hoc
    groupbys.

    Exactly three kinds, deliberately closed:

    * **simple** — an aggregation of one column::

          add_measure("revenue", column="revenue", agg="sum")

    * **expression** — an aggregation of a row-level arithmetic expression::

          add_measure("gross_margin", expr="revenue - cost", agg="sum")

    * **ratio** — one measure divided by another, computed after
      aggregation so the result is a true ratio of totals, not a mean of
      per-row ratios::

          add_measure("margin_pct", ratio=("gross_margin", "revenue"))

    These three cover the large majority of real usage, run on both
    engines, and need no expression parser. A richer grammar can arrive
    later as sugar that compiles down to these same structures.

    Measures are **data, never callables.** A lambda cannot be serialized,
    diffed, reviewed as data, validated before execution, or sent over the
    wire — accepting one would forfeit reproducibility at the root.
    """
    name: str
    kind: str                                  # simple | expression | ratio
    agg: Optional[str] = None
    column: Optional[str] = None
    expr: Optional[str] = None
    ratio: Optional[tuple[str, str]] = None    # (numerator, denominator)
    description: str = ""
    format: Optional[str] = None               # presentation hint, e.g. "percent"

    def to_dict(self) -> dict:
        d = {"name": self.name, "kind": self.kind}
        for key in ("agg", "column", "expr", "description", "format"):
            val = getattr(self, key)
            if val:
                d[key] = val
        if self.ratio:
            d["ratio"] = list(self.ratio)
        return d


# Characters permitted in a row-level measure expression. Restricted to
# arithmetic over bare column names and numeric literals: no function calls,
# no quotes, no subqueries. The expression is validated against the fact's
# actual columns before it ever reaches an engine.
_EXPR_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXPR_ALLOWED = re.compile(r"^[A-Za-z0-9_+\-*/(). ]+$")
# An identifier immediately followed by "(" is a function call. Row
# expressions are arithmetic only — aggregation is declared via agg=.
_EXPR_CALL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\(")


def _normalize_order_by(raw: Any) -> tuple[dict, ...]:
    """
    Normalize ``order_by`` to the canonical tuple-of-dicts form.

    Accepts ``{"column": str, "desc": bool}`` dicts and the ``"col"`` /
    ``"-col"`` string shorthand. The stamped resolved spec always carries
    the dict form, so replay compares like with like.
    """
    if not raw:
        return ()
    out: list[dict] = []
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            desc = entry.startswith("-")
            out.append({"column": entry.lstrip("-"), "desc": desc})
            continue
        if isinstance(entry, dict):
            unknown = set(entry) - {"column", "desc"}
            if unknown:
                raise ValueError(
                    f"order_by[{i}]: unknown key(s) {sorted(unknown)}. "
                    f"Each entry is {{'column': str, 'desc': bool}} or the "
                    f"'col' / '-col' string shorthand."
                )
            col = entry.get("column")
            if not col or not isinstance(col, str):
                raise ValueError(f"order_by[{i}]: each entry needs a 'column' (string).")
            out.append({"column": col, "desc": bool(entry.get("desc", False))})
            continue
        raise ValueError(
            f"order_by[{i}]: expected a dict or string, got {type(entry).__name__}."
        )
    return tuple(out)


@dataclass(frozen=True)
class QuerySpec:
    """
    A star-schema query as data.

    Everything needed to run a query, in a form that can be serialized,
    diffed, code-reviewed, committed, and replayed. ``DataModel.execute()``
    takes one of these; ``DataModel.query()`` is sugar that builds one.

    The resolved spec is stamped into the query's lineage, so an audit trail
    records not merely "a query ran" but exactly which query — and combined
    with ``DataSet.fingerprint()`` that is end-to-end reproducibility.

    Deliberately contains no callables and no free-form SQL: a spec that
    cannot be validated before execution is not a spec.
    """
    fact: str
    measures: Any                                   # {col: agg} or [names]
    dimensions: tuple[str, ...] = ()
    filters: Any = None                             # see DataModel.query()
    aggregate: bool = True
    allow_fanout: bool = False
    order_by: tuple = ()                            # ({"column": str, "desc": bool}, ...)
    limit: Optional[int] = None

    def to_dict(self) -> dict:
        d = {
            "fact": self.fact,
            "measures": (list(self.measures) if isinstance(self.measures, (list, tuple))
                         else dict(self.measures)),
            "dimensions": list(self.dimensions),
            "filters": dict(self.filters) if self.filters else {},
            "aggregate": self.aggregate,
            "allow_fanout": self.allow_fanout,
        }
        # Only when present: a spec without ordering serializes byte-for-byte
        # as it did before order_by/limit existed, so recorded specs in
        # existing manifests and lineage stay stable.
        if self.order_by:
            d["order_by"] = [dict(o) for o in self.order_by]
        if self.limit is not None:
            d["limit"] = int(self.limit)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "QuerySpec":
        if "fact" not in d:
            raise ValueError("QuerySpec requires a 'fact'.")
        if "measures" not in d:
            raise ValueError("QuerySpec requires 'measures'.")
        unknown = set(d) - {
            "fact", "measures", "dimensions", "filters", "aggregate",
            "allow_fanout", "order_by", "limit",
        }
        if unknown:
            raise ValueError(
                f"Unknown QuerySpec field(s): {sorted(unknown)}. "
                f"Allowed: fact, measures, dimensions, filters, aggregate, "
                f"allow_fanout, order_by, limit."
            )
        measures = d["measures"]
        limit = d.get("limit")
        if limit is not None:
            limit = int(limit)
            if limit < 1:
                raise ValueError(f"limit must be a positive integer, got {limit}.")
        return cls(
            fact=d["fact"],
            measures=list(measures) if isinstance(measures, list) else dict(measures),
            dimensions=tuple(d.get("dimensions") or ()),
            filters=dict(d.get("filters") or {}) or None,
            aggregate=bool(d.get("aggregate", True)),
            allow_fanout=bool(d.get("allow_fanout", False)),
            order_by=_normalize_order_by(d.get("order_by")),
            limit=limit,
        )


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
        self._measures: dict[str, MeasureDef] = {}

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

    def add_measure(
        self,
        name: str,
        *,
        column: Optional[str] = None,
        agg: Optional[str] = None,
        expr: Optional[str] = None,
        ratio: Optional[tuple[str, str]] = None,
        description: str = "",
        format: Optional[str] = None,
    ) -> "DataModel":
        """
        Declare a named measure on the model.

        Define the calculation once, review it in a pull request, and
        reference it by name from every report and query::

            model.add_measure("revenue", column="revenue", agg="sum")
            model.add_measure("orders", column="order_id", agg="nunique")
            model.add_measure("gross_margin", expr="revenue - cost", agg="sum")
            model.add_measure("margin_pct", ratio=("gross_margin", "revenue"),
                              format="percent")

            model.query(fact="fact_orders",
                        measures=["revenue", "margin_pct"],
                        dimensions=["dim_customer.region"])

        Exactly one of ``column``, ``expr``, or ``ratio`` must be given.
        ``agg`` is required for the first two. Ratios are computed after
        aggregation, so they are a ratio of totals rather than a mean of
        per-row ratios.

        Everything here is declarative data — callables are rejected, since
        a lambda cannot be serialized, diffed, reviewed, or validated
        before it runs.
        """
        for label, value in (("column", column), ("expr", expr), ("agg", agg)):
            if callable(value):
                raise TypeError(
                    f"Measure '{name}': {label} must be declarative data, not a "
                    f"callable. A function cannot be serialized, diffed, or "
                    f"validated before execution. Use expr='a - b' instead of "
                    f"a lambda."
                )

        given = [k for k, v in (("column", column), ("expr", expr), ("ratio", ratio))
                 if v is not None]
        if len(given) != 1:
            raise ValueError(
                f"Measure '{name}' must specify exactly one of column=, expr=, "
                f"or ratio=, got {given or 'none'}."
            )

        kind = {"column": "simple", "expr": "expression", "ratio": "ratio"}[given[0]]

        if kind == "ratio":
            if not (isinstance(ratio, (tuple, list)) and len(ratio) == 2):
                raise ValueError(
                    f"Measure '{name}': ratio must be a (numerator, denominator) "
                    f"pair of measure names, got {ratio!r}."
                )
            if agg is not None:
                raise ValueError(
                    f"Measure '{name}': ratio measures take no agg — the ratio "
                    f"is computed from the aggregated numerator and denominator."
                )
            ratio = (str(ratio[0]), str(ratio[1]))
        else:
            if agg is None:
                raise ValueError(
                    f"Measure '{name}' needs an agg (one of "
                    f"{', '.join(sorted(_AGG_FUNCS))})."
                )
            if agg.lower() not in _AGG_FUNCS:
                raise ValueError(
                    f"Measure '{name}': unsupported aggregation '{agg}'."
                    f"{self._hint(agg, sorted(_AGG_FUNCS))} "
                    f"Supported: {', '.join(sorted(_AGG_FUNCS))}"
                )
            agg = agg.lower()

        if kind == "expression":
            if not _EXPR_ALLOWED.match(expr or ""):
                raise ValueError(
                    f"Measure '{name}': expression {expr!r} may only contain "
                    f"column names, numbers, and + - * / ( ). Function calls, "
                    f"quotes, and SQL fragments are not allowed."
                )
            if _EXPR_CALL.search(expr or ""):
                raise ValueError(
                    f"Measure '{name}': expression {expr!r} looks like a "
                    f"function call. Row expressions are arithmetic only — "
                    f"declare the aggregation separately, e.g. "
                    f"expr='revenue - cost', agg='sum'."
                )

        self._measures[name] = MeasureDef(
            name=name, kind=kind, agg=agg, column=column, expr=expr,
            ratio=tuple(ratio) if ratio else None,
            description=description, format=format,
        )
        return self

    def measures(self) -> dict[str, MeasureDef]:
        """Declared measures, by name."""
        return dict(self._measures)

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
                # The frame is already in memory here, so fingerprint it now.
                # Every stamped query — and every manifest section built from
                # one — then records exactly which inputs produced it, which
                # is what lets `tracebi verify` tell source drift apart from
                # an unexplained mismatch.
                "input": {
                    "table":       table_name,
                    "fingerprint": frame_fingerprint(df),
                    "rows":        len(df),
                },
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
        measures: "dict[str, str] | list[str]",
        dimensions: Optional[list[str]] = None,
        filters: Optional[dict[str, Any]] = None,
        aggregate: bool = True,
        allow_fanout: bool = False,
        order_by: Optional[list] = None,
        limit: Optional[int] = None,
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
            filters:    Predicates on fact columns **or dimension
                        attributes**. Three spellings per entry::

                            {"status": "shipped"}              # equality
                            {"region": ["NE", "SE"]}           # IN
                            {"revenue": {"gte": 1000}}         # operator
                            {"dim_customer.region": "West"}    # dimension

                        Operators: eq, ne, in, not_in, gt, gte, lt, lte,
                        between, is_null, not_null, contains. A dimension
                        referenced only by a filter is still joined.
                        Equality filters on fact columns are pushed down to
                        the connector where it supports it.
            aggregate:  When ``True`` (default), group by dimension attributes
                        and aggregate measures. When ``False``, return the
                        flat joined rows with measures selected.
            allow_fanout: Permit joining a dimension whose key is not unique.
                        Off by default: a repeated key multiplies fact rows
                        and silently inflates additive measures. Set ``True``
                        only when the multiplication is intended — the opt-in
                        is then recorded as a warning node in the lineage.
            order_by:   Result ordering: ``[{"column": ..., "desc": bool}]``
                        dicts or ``"col"`` / ``"-col"`` shorthand, over result
                        columns (dimension refs, measure names — ratios
                        included). Remaining dimension columns are appended
                        as an ascending tie-break so the order is total, and
                        the fully resolved ordering is stamped in the spec.
            limit:      Keep the first N rows after sorting. Refused without
                        ``order_by`` — "first N" must never masquerade as
                        "top N".

        Returns:
            A DataSet with full lineage covering load → join → filter →
            aggregate steps.

        Raises:
            ValueError: if a referenced column does not exist, or if a joined
                dimension has a non-unique key and ``allow_fanout`` is False.
        """
        return self.execute(QuerySpec(
            fact=fact,
            measures=measures,
            dimensions=tuple(dimensions or ()),
            filters=filters,
            aggregate=aggregate,
            allow_fanout=allow_fanout,
            order_by=_normalize_order_by(order_by),
            limit=limit,
        ))

    def execute(self, spec: QuerySpec) -> DataSet:
        """
        Run a :class:`QuerySpec` and return a lineage-tracked DataSet.

        This is the primitive; :meth:`query` is keyword sugar over it. Taking
        a spec means a query can be built as data — validated, serialized,
        committed, reviewed, and replayed — rather than only ever existing as
        a function call.
        """
        fact = spec.fact
        measures = spec.measures
        dimensions = list(spec.dimensions or [])
        filters = spec.filters
        aggregate = spec.aggregate
        allow_fanout = spec.allow_fanout

        if fact not in self._facts:
            raise ValueError(
                f"Fact '{fact}' is not registered in model '{self.name}'. "
                f"Available facts: {list(self._facts.keys())}"
            )
        fact_def = self._facts[fact]
        dimensions = list(dimensions or [])
        filters = dict(filters or {})
        measures, derived, ratios = self._resolve_measures(measures, fact_def)

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

        # ── Load fact ─────────────────────────────────────────
        lineage: list[LineageNode] = []

        # Parse filters before loading so equality predicates on fact columns
        # can still be pushed down to the connector. A first load without a
        # filter is needed to know the fact's columns; use the declared
        # measures/foreign keys to avoid it where possible.
        probe_cols = set(fact_def.measures) | set(fact_def.foreign_keys.values())
        pushdown: dict[str, Any] = {}
        deferred: dict[str, Any] = {}
        for key, raw in (filters or {}).items():
            simple = (
                "." not in key
                and not isinstance(raw, (dict, list, tuple, set))
            )
            (pushdown if simple else deferred)[key] = raw

        fact_ds = self.load(fact_def.table_name, filter=pushdown or None)
        lineage.extend(fact_ds.lineage)
        fact_df = fact_ds.to_pandas()
        # Materialise row-level measure expressions before validation, so
        # derived columns are visible to everything downstream.
        if derived:
            fact_df = self._apply_derived(fact_df, derived, fact_def)
            lineage.append(LineageNode(
                operation="assign",
                description=(
                    "Derived measure column(s): "
                    + ", ".join(f"{k} = {v}" for k, v in derived.items())
                ),
                metadata={"derived": dict(derived)},
            ))
        fact_cols = set(fact_df.columns) | probe_cols

        predicates = self._parse_filters(filters, fact_def, fact_cols)
        # Predicates already satisfied by pushdown must not be re-applied
        # against a frame the connector has already filtered — but re-applying
        # an equality filter is idempotent, so keep them for the engine too
        # when the connector could not push down.
        pushed = set(pushdown) if fact_ds.lineage and pushdown else set()

        # ── Load dimensions: those grouped by AND those filtered on ───
        needed_dims = {dim_name for dim_name, _ in parsed_dims}
        needed_dims |= {p.dim_name for p in predicates if p.is_dim}
        dim_dfs: dict[str, pd.DataFrame] = {}
        for dim_name in needed_dims:
            dim_def = self._dimensions[dim_name]
            dim_ds = self.load(dim_def.table_name)
            lineage.extend(dim_ds.lineage)
            dim_dfs[dim_name] = dim_ds.to_pandas()

        # A typo'd column must never produce a silently wrong result.
        self._validate_query_columns(
            fact_def, fact_df, dim_dfs, parsed_dims, measures, {}
        )
        self._validate_dim_predicates(predicates, dim_dfs)
        # Neither must a non-unique dimension key. Every joined dimension is
        # checked, including ones joined only to satisfy a filter.
        join_dims = [(d, "") for d in needed_dims]
        self._check_dimension_keys(
            dim_dfs, join_dims, fact_df, fact_def, allow_fanout, lineage
        )

        for p in predicates:
            lineage.append(LineageNode(
                operation="filter",
                description=f"Filter: {p.describe()}",
                metadata={
                    "target": p.target,
                    "operator": p.op,
                    "value": p.value,
                    "on": "dimension" if p.is_dim else "fact",
                    "pushed_down": p.target in pushed,
                },
            ))

        # ── Try DuckDB engine first; fall back to pandas ──────
        try:
            result_df = self._execute_duckdb(
                fact_df=fact_df,
                fact_def=fact_def,
                dim_dfs=dim_dfs,
                parsed_dims=parsed_dims,
                measures=measures,
                predicates=predicates,
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
                predicates=predicates,
                aggregate=aggregate,
                lineage=lineage,
            )
            engine = "pandas"

        # Ratios divide the aggregated totals, so they must run after the
        # engine — sum(margin)/sum(revenue), not the mean of row ratios.
        if ratios:
            result_df = self._apply_ratios(result_df, ratios)
            lineage.append(LineageNode(
                operation="assign",
                description=(
                    "Ratio measure(s): "
                    + ", ".join(f"{k} = {n} / {d}" for k, (n, d) in ratios.items())
                ),
                metadata={"ratios": {k: list(v) for k, v in ratios.items()}},
            ))

        # ── Ordering (after ratios, so a ratio measure is sortable) ────
        # limit without order_by is refused: "first N rows" in engine order
        # silently masquerades as "top N" — the grammar will not express it.
        if spec.limit is not None and not spec.order_by:
            raise ValueError(
                "limit without order_by is refused: without a stated ordering, "
                "'first N rows' silently masquerades as 'top N'. Add order_by "
                "to state the ranking."
            )
        stamped_spec = spec.to_dict()
        if spec.order_by:
            resolved = [dict(o) for o in spec.order_by]
            result_cols = list(result_df.columns)
            for o in resolved:
                if o["column"] not in result_df.columns:
                    raise ValueError(
                        f"order_by column '{o['column']}' is not a result "
                        f"column of this query."
                        f"{self._hint(o['column'], result_cols)} "
                        f"Result columns: {result_cols}"
                    )
            # Deterministic on ties: append the remaining grouped dimension
            # columns as an implicit ascending tie-break, and stamp the FULLY
            # resolved ordering so replay reproduces it exactly. Applied only
            # when order_by/limit is present — a spec without them keeps
            # today's byte-for-byte output (the engines already ORDER BY the
            # group columns), so no existing fingerprint can move.
            named = {o["column"] for o in resolved}
            for dim_name, attribute in parsed_dims:
                ref = f"{dim_name}.{attribute}"
                if ref in result_df.columns and ref not in named:
                    resolved.append({"column": ref, "desc": False})
                    named.add(ref)
            result_df = result_df.sort_values(
                by=[o["column"] for o in resolved],
                ascending=[not o["desc"] for o in resolved],
                kind="mergesort",   # stable — the tie-break is total anyway
            ).reset_index(drop=True)
            stamped_spec["order_by"] = [dict(o) for o in resolved]
            if spec.limit is not None:
                result_df = result_df.head(int(spec.limit)).reset_index(drop=True)
            lineage.append(LineageNode(
                operation="sort",
                description=(
                    "Ordered by "
                    + ", ".join(
                        f"{o['column']}{' desc' if o['desc'] else ''}"
                        for o in resolved
                    )
                    + (f", limit {spec.limit}" if spec.limit is not None else "")
                ),
                metadata={"order_by": [dict(o) for o in resolved],
                          "limit": spec.limit},
            ))

        lineage.append(LineageNode(
            operation="transform",
            description=f"Star-schema query executed via {engine}",
            metadata={
                "engine": engine,
                "rows_out": len(result_df),
                "measures": dict(measures),
                # The model and the exact spec that produced this frame —
                # with the fully resolved ordering, so replay compares like
                # with like. With DataSet.fingerprint() that makes the run
                # reproducible, and it lets a report recover a declarative
                # data reference for its own sections (see tracebi.spec).
                "model": self.name,
                "query_spec": stamped_spec,
            },
        ))

        return DataSet(df=result_df, name=f"{fact}_result", lineage=lineage)

    @staticmethod
    def _hint(name: str, options) -> str:
        import difflib
        close = difflib.get_close_matches(name, [str(o) for o in options], n=1)
        return f" Did you mean '{close[0]}'?" if close else ""

    def _resolve_measures(
        self,
        measures: "dict[str, str] | list[str]",
        fact_def: "_FactDef",
    ) -> tuple[dict[str, str], dict[str, str], dict[str, tuple[str, str]]]:
        """
        Expand the ``measures`` argument into what the engines understand.

        Accepts either the legacy ``{column: agg}`` mapping or a list of
        declared measure names, and returns:

        * ``agg_map``  — ``{output_column: agg_func}`` for the engine
        * ``derived``  — ``{output_column: row_expression}`` to materialise
                          on the fact before aggregating
        * ``ratios``   — ``{output_column: (numerator, denominator)}`` to
                          compute after aggregation

        Ad-hoc ``{column: agg}`` still works unchanged, so existing callers
        and the Explore UI are unaffected.
        """
        agg_map: dict[str, str] = {}
        derived: dict[str, str] = {}
        ratios: dict[str, tuple[str, str]] = {}

        if isinstance(measures, dict):
            if not measures:
                raise ValueError("query() requires at least one measure.")
            # Legacy/ad-hoc form. Values may be an agg name, or a
            # (source_column, agg) tuple mirroring DataSet.aggregate().
            for out_col, spec in measures.items():
                if isinstance(spec, (tuple, list)) and len(spec) == 2:
                    src, func = spec
                    derived[out_col] = str(src)   # rename, not arithmetic
                    agg_map[out_col] = str(func).lower()
                else:
                    agg_map[out_col] = str(spec).lower()
            return agg_map, derived, ratios

        names = list(measures or [])
        if not names:
            raise ValueError("query() requires at least one measure.")

        def _expand(mname: str, seen: tuple) -> None:
            if mname in agg_map or mname in ratios:
                return
            if mname not in self._measures:
                raise ValueError(
                    f"Measure '{mname}' is not declared on model '{self.name}'."
                    f"{self._hint(mname, self._measures)} "
                    f"Declared measures: {sorted(self._measures)}. "
                    f"Pass {{'{mname}': 'sum'}} for an ad-hoc measure, or "
                    f"declare it with add_measure()."
                )
            if mname in seen:
                raise ValueError(
                    f"Measure '{mname}' is defined in terms of itself "
                    f"({' → '.join(seen + (mname,))})."
                )
            m = self._measures[mname]
            if m.kind == "simple":
                agg_map[m.name] = m.agg
                if m.column != m.name:
                    derived[m.name] = m.column
            elif m.kind == "expression":
                agg_map[m.name] = m.agg
                derived[m.name] = m.expr
            else:  # ratio
                num, den = m.ratio
                _expand(num, seen + (mname,))
                _expand(den, seen + (mname,))
                ratios[m.name] = (num, den)

        for n in names:
            _expand(n, ())
        return agg_map, derived, ratios

    def _apply_derived(
        self,
        df: pd.DataFrame,
        derived: dict[str, str],
        fact_def: "_FactDef",
    ) -> pd.DataFrame:
        """
        Materialise row-level measure expressions onto the fact frame.

        Validates every referenced name against the frame's actual columns
        first — an unknown column must fail loudly, never evaluate to NaN
        and quietly poison a total.
        """
        if not derived:
            return df
        cols = set(df.columns)
        out = df.copy()
        for out_col, expression in derived.items():
            if expression in cols:            # plain rename/alias
                out[out_col] = out[expression]
                continue
            referenced = [
                t for t in _EXPR_TOKEN.findall(expression)
                if not t.isdigit()
            ]
            for token in referenced:
                if token not in cols:
                    raise ValueError(
                        f"Measure '{out_col}' references column '{token}', "
                        f"which is not on fact table "
                        f"'{fact_def.table_name}'.{self._hint(token, cols)} "
                        f"Available columns: {sorted(cols)}"
                    )
            try:
                out[out_col] = out.eval(expression)
            except Exception as exc:  # noqa: BLE001 — re-raised with context
                raise ValueError(
                    f"Measure '{out_col}' expression {expression!r} could not "
                    f"be evaluated: {type(exc).__name__}: {exc}"
                ) from exc
        return out

    def _apply_ratios(
        self,
        df: pd.DataFrame,
        ratios: dict[str, tuple[str, str]],
    ) -> pd.DataFrame:
        """
        Compute ratio measures from already-aggregated columns.

        Division happens on the totals, so ``margin_pct`` is
        ``sum(margin) / sum(revenue)`` — not the mean of per-row ratios,
        which is a different and usually wrong number.
        """
        if not ratios:
            return df
        out = df.copy()
        for name, (num, den) in ratios.items():
            if num not in out.columns or den not in out.columns:
                continue
            denominator = out[den].replace(0, pd.NA)
            out[name] = out[num] / denominator
        return out

    def _parse_filters(
        self,
        filters: dict[str, Any],
        fact_def: "_FactDef",
        fact_cols: set,
    ) -> list[_Predicate]:
        """
        Turn the user-facing filter dict into validated predicates.

        Accepts three spellings per entry::

            {"status": "shipped"}                 # eq
            {"region": ["NE", "SE"]}              # in
            {"revenue": {"gte": 1000}}            # explicit operator

        A key containing a dot is resolved as ``dim_name.attribute`` against
        the registered dimensions — filtering by a dimension attribute is the
        most common analytic gesture and used to raise.
        """
        preds: list[_Predicate] = []

        for key, raw in filters.items():
            dim_name = attribute = None
            if "." in key:
                cand_dim, cand_attr = key.split(".", 1)
                if cand_dim not in self._dimensions:
                    raise ValueError(
                        f"Filter '{key}' refers to dimension '{cand_dim}', "
                        f"which is not registered in model '{self.name}'."
                        f"{self._hint(cand_dim, self._dimensions)} "
                        f"Available dimensions: {sorted(self._dimensions)}"
                    )
                dim_name, attribute = cand_dim, cand_attr
            elif key not in fact_cols:
                # Not a fact column — maybe they meant a dimension attribute.
                matches = [
                    f"{dn}.{key}" for dn, dd in self._dimensions.items()
                    if key in (dd.attributes or []) or key == dd.key_col
                ]
                extra = (
                    f" It exists on {matches[0].split('.')[0]}; "
                    f"reference it as '{matches[0]}'."
                    if matches else self._hint(key, fact_cols)
                )
                raise ValueError(
                    f"Filter column '{key}' not found on fact table "
                    f"'{fact_def.table_name}'.{extra} "
                    f"Available columns: {sorted(fact_cols)}"
                )

            # Normalise the value into (op, value)
            if isinstance(raw, dict):
                if len(raw) != 1:
                    raise ValueError(
                        f"Filter '{key}' must specify exactly one operator, "
                        f"got {sorted(raw)}. Combine conditions by passing "
                        f"separate filter entries."
                    )
                op, value = next(iter(raw.items()))
                op = str(op).lower()
                if op not in FILTER_OPS:
                    raise ValueError(
                        f"Unknown filter operator '{op}' for '{key}'."
                        f"{self._hint(op, FILTER_OPS)} "
                        f"Supported: {', '.join(FILTER_OPS)}"
                    )
            elif isinstance(raw, (list, tuple, set)):
                op, value = "in", list(raw)
            else:
                op, value = "eq", raw

            if op in _LIST_OPS and not isinstance(value, (list, tuple, set)):
                raise ValueError(
                    f"Filter '{key}' with operator '{op}' needs a list of "
                    f"values, got {type(value).__name__}."
                )
            if op == "between":
                if not isinstance(value, (list, tuple)) or len(value) != 2:
                    raise ValueError(
                        f"Filter '{key}' with operator 'between' needs a "
                        f"two-element [low, high], got {value!r}."
                    )
            if op in _LIST_OPS:
                value = list(value)

            preds.append(_Predicate(
                target=key, op=op, value=value,
                dim_name=dim_name, attribute=attribute,
            ))

        return preds

    def _validate_dim_predicates(
        self,
        preds: list[_Predicate],
        dim_dfs: dict[str, pd.DataFrame],
    ) -> None:
        """Check that every dimension predicate's attribute actually exists."""
        for p in preds:
            if not p.is_dim:
                continue
            dim_def = self._dimensions[p.dim_name]
            declared = dim_def.attributes
            if declared and p.attribute not in declared and p.attribute != dim_def.key_col:
                raise ValueError(
                    f"Filter attribute '{p.attribute}' is not declared on "
                    f"dimension '{p.dim_name}'.{self._hint(p.attribute, declared)} "
                    f"Declared attributes: {declared}"
                )
            cols = set(dim_dfs[p.dim_name].columns)
            if p.attribute not in cols:
                raise ValueError(
                    f"Filter attribute '{p.attribute}' not found on dimension "
                    f"table '{dim_def.table_name}'."
                    f"{self._hint(p.attribute, cols)} "
                    f"Available columns: {sorted(cols)}"
                )

    def _check_dimension_keys(
        self,
        dim_dfs: dict[str, pd.DataFrame],
        parsed_dims: list[tuple[str, str]],
        fact_df: pd.DataFrame,
        fact_def: "_FactDef",
        allow_fanout: bool,
        lineage: list[LineageNode],
    ) -> None:
        """
        Reject dimensions whose key is not unique.

        A star-schema join assumes one dimension row per key. When the key
        repeats, the LEFT JOIN multiplies fact rows and every additive
        measure is silently inflated — the query returns a confident,
        fully-lineaged, wrong number. Same principle as
        ``_validate_query_columns``: never return a silently wrong result.

        With ``allow_fanout=True`` the join proceeds (legitimate for
        many-to-many) but the opt-in is recorded as a warning lineage node
        so the audit trail shows the multiplication was intentional.
        """
        for dim_name in {d for d, _ in parsed_dims}:
            dim_def = self._dimensions[dim_name]
            dim_df = dim_dfs[dim_name]
            key = dim_def.key_col

            n_null = int(dim_df[key].isna().sum())
            dup_mask = dim_df[key].duplicated(keep=False)
            n_dup_rows = int(dup_mask.sum())

            if n_dup_rows:
                dup_values = dim_df.loc[dup_mask, key].drop_duplicates()
                sample = [repr(v) for v in dup_values.head(3).tolist()]
                if len(dup_values) > 3:
                    sample.append("…")
                # Rows the fact side would gain, for the keys it actually uses.
                fk_col = fact_def.foreign_keys.get(dim_name, key)
                if fk_col in fact_df.columns:
                    counts = dim_df[key].value_counts()
                    rows_after = int(fact_df[fk_col].map(counts).fillna(1).sum())
                else:
                    rows_after = len(fact_df)
                factor = (rows_after / len(fact_df)) if len(fact_df) else 1.0

                if not allow_fanout:
                    raise ValueError(
                        f"Dimension '{dim_name}' has a non-unique key: "
                        f"'{dim_def.table_name}.{key}' repeats across "
                        f"{n_dup_rows} rows ({len(dup_values)} duplicated "
                        f"value(s): {', '.join(sample)}). Joining would fan "
                        f"out the fact table {len(fact_df)} → {rows_after} "
                        f"rows (x{factor:.2f}) and inflate every additive "
                        f"measure. Deduplicate the dimension, pick a key "
                        f"column that is unique, or pass allow_fanout=True "
                        f"if the multiplication is intended."
                    )

                lineage.append(LineageNode(
                    operation="warning",
                    description=(
                        f"Fan-out allowed on dimension '{dim_name}': "
                        f"key '{key}' is not unique; measures are multiplied "
                        f"x{factor:.2f}"
                    ),
                    metadata={
                        "dimension": dim_name,
                        "key_column": key,
                        "duplicate_rows": n_dup_rows,
                        "duplicate_values": len(dup_values),
                        "rows_before": len(fact_df),
                        "rows_after": rows_after,
                        "fanout_factor": round(factor, 4),
                        "allow_fanout": True,
                    },
                ))

            if n_null:
                lineage.append(LineageNode(
                    operation="warning",
                    description=(
                        f"Dimension '{dim_name}' key '{key}' contains "
                        f"{n_null} null value(s); those rows cannot be "
                        f"matched by the join"
                    ),
                    metadata={
                        "dimension": dim_name,
                        "key_column": key,
                        "null_keys": n_null,
                    },
                ))

    def validate(self) -> dict[str, Any]:
        """
        Check the model's declared structure against the actual data.

        Loads only each dimension's key column and reports uniqueness and
        null status. Returns a structured result rather than printing, so
        the CLI, the web API, and agent tooling can all consume it::

            {"ok": bool, "dimensions": [{...}], "errors": [str], "warnings": [str]}

        Call this before running queries — a non-unique dimension key is the
        difference between a correct number and a silently inflated one.
        """
        dims: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []

        for dim_name, dim_def in self._dimensions.items():
            entry: dict[str, Any] = {
                "dimension": dim_name,
                "table": dim_def.table_name,
                "key_column": dim_def.key_col,
            }
            try:
                df = self.load(dim_def.table_name, columns=[dim_def.key_col]).to_pandas()
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                entry.update(ok=False, error=str(exc))
                errors.append(f"Dimension '{dim_name}': could not load key column — {exc}")
                dims.append(entry)
                continue

            n_dup = int(df[dim_def.key_col].duplicated(keep=False).sum())
            n_null = int(df[dim_def.key_col].isna().sum())
            entry.update(
                rows=len(df),
                duplicate_rows=n_dup,
                null_keys=n_null,
                key_unique=(n_dup == 0),
                ok=(n_dup == 0),
            )
            if n_dup:
                errors.append(
                    f"Dimension '{dim_name}': key "
                    f"'{dim_def.table_name}.{dim_def.key_col}' is not unique "
                    f"({n_dup} duplicated rows) — joins will inflate measures."
                )
            if n_null:
                warnings.append(
                    f"Dimension '{dim_name}': key "
                    f"'{dim_def.table_name}.{dim_def.key_col}' has "
                    f"{n_null} null value(s)."
                )
            dims.append(entry)

        return {
            "ok": not errors,
            "model": self.name,
            "dimensions": dims,
            "errors": errors,
            "warnings": warnings,
        }

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

    def _declared_fact_columns(self, fact_def: "_FactDef") -> set[str]:
        """
        Every fact-table column the model *declares*: the fact's measure
        columns and foreign keys, plus any column a named measure reads
        (directly or inside a row expression). A subset of the table's
        actual columns — knowable without loading a row.
        """
        cols = set(fact_def.measures) | set(fact_def.foreign_keys.values())
        for m in self._measures.values():
            if m.column:
                cols.add(m.column)
            if m.expr:
                cols |= {
                    t for t in _EXPR_TOKEN.findall(m.expr) if not t.isdigit()
                }
        return cols

    def check_query_spec(
        self, spec: QuerySpec
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """
        Validate a :class:`QuerySpec` against the model's declared structure,
        without loading any data.

        The declaration-time twin of the execution-time checks
        (``_validate_query_columns``, ``_parse_filters``,
        ``_validate_dim_predicates``), kept beside them so the rules cannot
        drift. Whatever the model itself declares — facts, named measures,
        dimensions and their attributes, the closed aggregation-function
        set — is authoritative, and a mismatch is an **error**. A reference
        only the physical table can confirm (an ad-hoc measure column or a
        bare filter column beyond the declared ones) is a **warning**:
        execution re-checks it against the actual columns and fails loudly
        there.

        Returns ``(errors, warnings)``, each a list of ``(subpath, message)``
        pairs relative to the query — e.g. ``("filters.region", "…")`` — so
        a caller can prefix its own location (``sections[0].data.query``).
        """
        errors: list[tuple[str, str]] = []
        warnings: list[tuple[str, str]] = []

        fact_def = self._facts.get(spec.fact)
        if fact_def is None:
            errors.append((
                "fact",
                f"'{spec.fact}' is not a fact on model '{self.name}'."
                f"{self._hint(spec.fact, self._facts)} "
                f"Available: {sorted(self._facts)}",
            ))
            return errors, warnings

        declared_cols = self._declared_fact_columns(fact_def)

        # ── Measures ──────────────────────────────────────────
        if isinstance(spec.measures, dict):
            for out_col, mspec in spec.measures.items():
                if isinstance(mspec, (tuple, list)) and len(mspec) == 2:
                    src, func = str(mspec[0]), str(mspec[1])
                else:
                    src, func = str(out_col), str(mspec)
                if func.lower() not in _AGG_FUNCS:
                    errors.append((
                        f"measures.{out_col}",
                        f"unsupported aggregation '{func}'."
                        f"{self._hint(func, sorted(_AGG_FUNCS))} "
                        f"Supported: {', '.join(sorted(_AGG_FUNCS))}",
                    ))
                if src not in declared_cols:
                    warnings.append((
                        f"measures.{out_col}",
                        f"column '{src}' is not among the declared columns "
                        f"of fact '{spec.fact}'."
                        f"{self._hint(src, declared_cols)} "
                        f"Declared: {sorted(declared_cols)}. It cannot be "
                        f"verified before execution, which checks it "
                        f"against the actual table.",
                    ))
        else:
            for m in spec.measures or ():
                if not isinstance(m, str):
                    errors.append((
                        "measures",
                        f"list-form measures must be declared measure names "
                        f"(strings); got {type(m).__name__}: {m!r}. Use the "
                        f"dict form {{column: agg}} for ad-hoc measures.",
                    ))
                    continue
                if m not in self._measures:
                    errors.append((
                        "measures",
                        f"'{m}' is not a declared measure on model "
                        f"'{self.name}'.{self._hint(m, self._measures)} "
                        f"Declared: {sorted(self._measures)}",
                    ))

        # ── Dimensions ────────────────────────────────────────
        for ref in spec.dimensions or ():
            ref_s = str(ref)
            if "." not in ref_s:
                errors.append((
                    "dimensions",
                    f"'{ref_s}' must use dot notation: 'dim_name.attribute'",
                ))
                continue
            dim_name, attribute = ref_s.split(".", 1)
            err = self._check_declared_dim_ref(dim_name, attribute)
            if err:
                errors.append(("dimensions", err))

        # ── Filters ───────────────────────────────────────────
        for key in (spec.filters or {}):
            key_s = str(key)
            sub = f"filters.{key_s}"
            val = (spec.filters or {}).get(key)
            if isinstance(val, dict):
                for op in val:
                    if str(op) not in FILTER_OPS:
                        errors.append((
                            f"{sub}.{op}",
                            f"unknown filter operator '{op}'."
                            f"{self._hint(str(op), sorted(FILTER_OPS))} "
                            f"Supported: {', '.join(sorted(FILTER_OPS))}",
                        ))
            if "." in key_s:
                dim_name, attribute = key_s.split(".", 1)
                err = self._check_declared_dim_ref(dim_name, attribute)
                if err:
                    errors.append((sub, err))
                continue
            if key_s in declared_cols:
                continue
            matches = [
                f"{dn}.{key_s}" for dn, dd in self._dimensions.items()
                if key_s in (dd.attributes or []) or key_s == dd.key_col
            ]
            if matches:
                # A warning, not an error: the name may also be a physical
                # column on the fact table (denormalised facts do this), and
                # a bare fact-column filter and a dimension-attribute filter
                # have different semantics — execution accepts the former.
                warnings.append((
                    sub,
                    f"'{key_s}' is not a declared column on fact "
                    f"'{spec.fact}' but matches dimension attribute "
                    f"'{matches[0]}'. If you mean the dimension, reference "
                    f"it as '{matches[0]}'; a bare name filters the fact "
                    f"table's own column, which is checked at execution.",
                ))
            else:
                warnings.append((
                    sub,
                    f"filter column '{key_s}' is not among the declared "
                    f"columns of fact '{spec.fact}'."
                    f"{self._hint(key_s, declared_cols)} "
                    f"Declared: {sorted(declared_cols)}. It cannot be "
                    f"verified before execution, which checks it against "
                    f"the actual table.",
                ))

        # ── Ordering ──────────────────────────────────────────
        if spec.limit is not None and not (spec.order_by or ()):
            errors.append((
                "limit",
                "limit without order_by is refused: without a stated "
                "ordering, 'first N rows' silently masquerades as 'top N'. "
                "Add order_by to state the ranking.",
            ))
        if spec.order_by:
            try:
                normalized = _normalize_order_by(spec.order_by)
            except ValueError as exc:
                errors.append(("order_by", str(exc)))
                normalized = ()
            result_cols: Optional[list[str]] = None
            if not errors:
                try:
                    result_cols = self.spec_result_columns(spec)
                except ValueError:
                    result_cols = None   # unresolvable measures already reported
            for i, o in enumerate(normalized):
                col = o["column"]
                if result_cols is not None and col not in result_cols:
                    errors.append((
                        f"order_by[{i}]",
                        f"'{col}' is not a result column of this query."
                        f"{self._hint(col, result_cols)} "
                        f"Result columns: {sorted(result_cols)}",
                    ))

        return errors, warnings

    def _check_declared_dim_ref(
        self, dim_name: str, attribute: str
    ) -> Optional[str]:
        """One ``dim_name.attribute`` reference against the declarations."""
        dim_def = self._dimensions.get(dim_name)
        if dim_def is None:
            return (
                f"'{dim_name}' is not a dimension on model '{self.name}'."
                f"{self._hint(dim_name, self._dimensions)} "
                f"Available: {sorted(self._dimensions)}"
            )
        declared = dim_def.attributes
        if declared and attribute not in declared and attribute != dim_def.key_col:
            return (
                f"attribute '{attribute}' is not declared on dimension "
                f"'{dim_name}'.{self._hint(attribute, declared)} "
                f"Declared attributes: {declared}"
            )
        return None

    def spec_result_columns(self, spec: QuerySpec) -> list[str]:
        """
        The column names a :class:`QuerySpec`'s result frame will carry,
        computed from declarations alone: each dimension reference as
        written (``dim_name.attribute``) plus every measure output —
        ratio components included — exactly as ``execute()`` produces
        them via ``_resolve_measures``. Raises ``ValueError`` when the
        fact or measures cannot be resolved; check the spec first.
        """
        fact_def = self._facts.get(spec.fact)
        if fact_def is None:
            raise ValueError(
                f"Fact '{spec.fact}' is not registered in model '{self.name}'."
            )
        agg_map, _derived, ratios = self._resolve_measures(spec.measures, fact_def)
        return (
            [str(d) for d in (spec.dimensions or ())]
            + list(agg_map)
            + list(ratios)
        )

    @staticmethod
    def _predicate_sql(pred: _Predicate, column_sql: str) -> tuple[str, list]:
        """Render one predicate as parameterised SQL."""
        op, v = pred.op, pred.value
        if op == "eq":       return f"{column_sql} = ?", [v]
        if op == "ne":       return f"{column_sql} <> ?", [v]
        if op == "gt":       return f"{column_sql} > ?", [v]
        if op == "gte":      return f"{column_sql} >= ?", [v]
        if op == "lt":       return f"{column_sql} < ?", [v]
        if op == "lte":      return f"{column_sql} <= ?", [v]
        if op == "between":  return f"{column_sql} BETWEEN ? AND ?", [v[0], v[1]]
        if op == "is_null":  return f"{column_sql} IS NULL", []
        if op == "not_null": return f"{column_sql} IS NOT NULL", []
        if op == "contains": return f"CAST({column_sql} AS VARCHAR) LIKE ?", [f"%{v}%"]
        if op in _LIST_OPS:
            if not v:
                # An empty IN matches nothing; NOT IN matches everything.
                return ("1 = 0", []) if op == "in" else ("1 = 1", [])
            marks = ", ".join("?" for _ in v)
            neg = "NOT " if op == "not_in" else ""
            return f"{column_sql} {neg}IN ({marks})", list(v)
        raise ValueError(f"Unhandled filter operator '{op}'")

    @staticmethod
    def _predicate_mask(pred: _Predicate, series: "pd.Series"):
        """Render one predicate as a pandas boolean mask."""
        op, v = pred.op, pred.value
        if op == "eq":       return series == v
        if op == "ne":       return series != v
        if op == "gt":       return series > v
        if op == "gte":      return series >= v
        if op == "lt":       return series < v
        if op == "lte":      return series <= v
        if op == "between":  return series.between(v[0], v[1])
        if op == "is_null":  return series.isna()
        if op == "not_null": return series.notna()
        if op == "contains": return series.astype(str).str.contains(str(v), na=False)
        if op == "in":       return series.isin(list(v))
        if op == "not_in":   return ~series.isin(list(v))
        raise ValueError(f"Unhandled filter operator '{op}'")

    # ── DuckDB engine ──────────────────────────────────────────

    def _execute_duckdb(
        self,
        *,
        fact_df: pd.DataFrame,
        fact_def: _FactDef,
        dim_dfs: dict[str, pd.DataFrame],
        parsed_dims: list[tuple[str, str]],
        measures: dict[str, str],
        predicates: list[_Predicate],
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

            # Join every loaded dimension — those grouped by and those only
            # referenced in a filter.
            from_clause = "fact"
            for dim_name in dim_dfs:
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
            for p in predicates:
                if p.is_dim:
                    column_sql = f'dim_{p.dim_name}."{p.attribute}"'
                else:
                    column_sql = f'fact."{p.target}"'
                clause, vals = self._predicate_sql(p, column_sql)
                where_clauses.append(clause)
                params.extend(vals)

            sql = "SELECT " + ", ".join(select_cols_sql) + f" FROM {from_clause}"
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            if aggregate and group_cols_sql:
                sql += " GROUP BY " + ", ".join(group_cols_sql)
                # Deterministic row order. Without it DuckDB returns groups in
                # hash-table order, which varies between identical runs — so
                # DataSet.fingerprint() differed across runs of the same query
                # and manifest fingerprints were not re-verifiable. It also
                # matches pandas' groupby, which sorts by default, keeping the
                # two engines byte-comparable.
                sql += " ORDER BY " + ", ".join(group_cols_sql)

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
        predicates: list[_Predicate],
        aggregate: bool,
        lineage: list[LineageNode],
    ) -> pd.DataFrame:
        df = fact_df
        # Fact predicates apply before the join (smaller frame to join).
        for p in predicates:
            if not p.is_dim and p.target in df.columns:
                df = df[self._predicate_mask(p, df[p.target])]

        for dim_name in dim_dfs:
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
            rows_before = len(df)
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
                    "rows_before": rows_before,
                    "rows_after":  len(df),
                },
            ))

        # Dimension predicates can only be applied once the dimension is
        # joined. Columns are prefixed "dim_name.attribute" by the merge above,
        # except the key column which keeps its own name.
        for p in predicates:
            if not p.is_dim:
                continue
            dim_def = self._dimensions[p.dim_name]
            col = (dim_def.key_col if p.attribute == dim_def.key_col
                   else f"{p.dim_name}.{p.attribute}")
            if col in df.columns:
                df = df[self._predicate_mask(p, df[col])]

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
        facts, dimensions, measures). This is the stable surface the web
        layer reads — prefer it over touching private attributes.

        It is also the machine-readable description of the model's
        vocabulary: what can be measured, sliced, and filtered. Declared
        measures carry their definition, description, and format so a
        consumer can tell what a number *means*, not just what it's called.
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
            "measures": [m.to_dict() for m in self._measures.values()],
            "filter_operators": list(FILTER_OPS),
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

    def help_text(self) -> str:
        """Return a cheat sheet of the DataModel API as a string."""
        return (
            "\nDataModel — governed semantic model over your tables.\n"
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

    def help(self) -> None:
        """Print a cheat sheet of the DataModel API."""
        print(self.help_text())

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
