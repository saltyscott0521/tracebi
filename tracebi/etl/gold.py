"""
GoldLayer — aggregated, analytics-ready DataSets built from a StarSchema.

Delegates to ``StarSchema.query()`` and stamps the result with an additional
``operation="gold"`` lineage node capturing the query parameters.
"""

from __future__ import annotations

from typing import Any, Optional

from tracebi.model.dataset import DataSet, LineageNode
from tracebi.model.star_schema import StarSchema


class GoldLayer:
    """
    Analytics-ready aggregation layer backed by a StarSchema.

    Usage::

        gold = GoldLayer(schema=schema)

        revenue_by_region = gold.query(
            fact="fact_orders",
            measures={"revenue": "sum", "order_id": "count"},
            dimensions=["dim_customer.region"],
            filters={"status": "shipped"},
        )
        revenue_by_region.print_lineage()
    """

    def __init__(self, schema: StarSchema) -> None:
        """
        Args:
            schema: A configured StarSchema that knows all facts and dimensions.
        """
        self._schema = schema

    def query(
        self,
        fact: str,
        measures: dict[str, str],
        dimensions: Optional[list[str]] = None,
        filters: Optional[dict[str, Any]] = None,
        aggregate: bool = True,
        name: Optional[str] = None,
    ) -> DataSet:
        """
        Execute a star schema query and return a gold-layer DataSet.

        All args are passed through to ``StarSchema.query()``.  The result
        gains an extra ``operation="gold"`` lineage node.

        Args:
            fact:       Registered fact name.
            measures:   ``{column: agg_func}`` aggregation spec.
            dimensions: ``["dim_name.attribute"]`` grouping columns.
            filters:    ``{column: value}`` equality pre-filters.
            aggregate:  Whether to group and aggregate (default ``True``).
            name:       Override the DataSet name.  Defaults to
                        ``"{fact}_gold"``.
        """
        ds = self._schema.query(
            fact=fact,
            measures=measures,
            dimensions=dimensions,
            filters=filters,
            aggregate=aggregate,
        )

        gold_node = LineageNode(
            operation="gold",
            description=(
                f"Gold layer: {fact} "
                f"measures={list(measures.keys())} "
                f"dims={dimensions or []} "
                f"filters={filters or {}}"
            ),
            metadata={
                "layer":      "gold",
                "fact":       fact,
                "measures":   measures,
                "dimensions": dimensions or [],
                "filters":    filters or {},
                "aggregate":  aggregate,
            },
        )

        output_name = name or f"{fact}_gold"
        return DataSet(df=ds.to_pandas(), name=output_name, lineage=ds.lineage + [gold_node])

    def __repr__(self) -> str:
        return f"<GoldLayer schema={self._schema.name!r}>"
