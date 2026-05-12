"""
GoldLayer — aggregated, analytics-ready DataSets built from a StarSchema.

Delegates to ``StarSchema.query()`` and stamps the result with an additional
``operation="gold"`` lineage node.

Pipeline mode: pre-configure query parameters in the constructor and call
``execute()`` to query, write to sink, and return the DataSet in one step.
"""

from __future__ import annotations

from typing import Any, Optional

from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode
from tracebi.model.star_schema import StarSchema


class GoldLayer:
    """
    Analytics-ready aggregation layer backed by a StarSchema.

    Standalone usage::

        gold = GoldLayer(schema=schema)
        ds = gold.query(
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
        )

    Pipeline usage (pre-configured)::

        gold = GoldLayer(
            schema=schema,
            fact="fact_orders",
            measures={"revenue": "sum"},
            dimensions=["dim_customer.region"],
            sink=db_connector,
            sink_table="revenue_by_region_gold",
        )
        ds = gold.execute()   # queries + writes to sink
    """

    def __init__(
        self,
        schema: StarSchema,
        fact: Optional[str] = None,
        measures: Optional[dict[str, str]] = None,
        dimensions: Optional[list[str]] = None,
        filters: Optional[dict[str, Any]] = None,
        aggregate: bool = True,
        sink: Optional[BaseConnector] = None,
        sink_table: Optional[str] = None,
    ) -> None:
        self._schema = schema
        self._fact = fact
        self._measures = measures
        self._dimensions = dimensions
        self._filters = filters
        self._aggregate = aggregate
        self._sink = sink
        self._sink_table = sink_table

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

        All args are passed through to ``StarSchema.query()``.
        Does NOT write to the sink; use ``execute()`` for that.
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

    def execute(self, name: Optional[str] = None) -> DataSet:
        """
        Run the pre-configured query, write to sink, and return the DataSet.

        Requires ``fact``, ``measures``, ``sink``, and ``sink_table`` to be
        set in the constructor.
        """
        if self._fact is None or self._measures is None:
            raise RuntimeError(
                "GoldLayer.execute() requires 'fact' and 'measures' to be configured."
            )
        if self._sink is None or self._sink_table is None:
            raise RuntimeError(
                "GoldLayer.execute() requires 'sink' and 'sink_table'."
            )
        ds = self.query(
            fact=self._fact,
            measures=self._measures,
            dimensions=self._dimensions,
            filters=self._filters,
            aggregate=self._aggregate,
            name=name or self._sink_table,
        )
        self._sink.write(ds.to_pandas(), self._sink_table)
        return ds

    def __repr__(self) -> str:
        return (
            f"<GoldLayer schema={self._schema.name!r} "
            f"fact={self._fact!r} "
            f"sink_table={self._sink_table!r}>"
        )
