"""
BronzeLayer — raw ingest from a connector with zero transformations.

Stamps lineage with ``operation="bronze"`` and an ingestion timestamp.

Pipeline mode: supply ``sink`` + ``sink_table`` and call ``execute()``
to load, write to the sink, and return the DataSet in one step.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode

if TYPE_CHECKING:
    pass


class BronzeLayer:
    """
    Raw ingest layer — load data as-is from any connector.

    Standalone usage::

        bronze = BronzeLayer(connector=csv_connector, source="orders.csv")
        ds = bronze.load(name="orders_raw")

    Pipeline usage (with sink)::

        bronze = BronzeLayer(
            connector=source_connector,
            source="orders",
            sink=db_connector,
            sink_table="orders_bronze",
        )
        ds = bronze.execute()   # loads + writes to sink
    """

    def __init__(
        self,
        connector: BaseConnector,
        source: str,
        description: str = "",
        sink: Optional[BaseConnector] = None,
        sink_table: Optional[str] = None,
    ) -> None:
        self._connector = connector
        self._source = source
        self._description = description or f"Bronze ingest from '{connector.name}': {source}"
        self._sink = sink
        self._sink_table = sink_table

    def load(self, name: Optional[str] = None) -> DataSet:
        """
        Load raw data and return a lineage-tracked DataSet.

        Every call re-reads from the source — no caching.
        Does NOT write to the sink; use ``execute()`` for that.
        """
        ingestion_ts = datetime.now(timezone.utc).isoformat()
        df = self._connector.load(self._source)
        node = LineageNode(
            operation="bronze",
            description=self._description,
            connector={
                "connector_name": self._connector.name,
                "connector_type": type(self._connector).__name__,
            },
            source=self._source,
            metadata={
                "layer":          "bronze",
                "ingestion_time": ingestion_ts,
                "rows_ingested":  len(df),
                "columns":        list(df.columns),
            },
        )
        return DataSet(df=df, name=name or self._source, lineage=[node])

    def execute(self, name: Optional[str] = None) -> DataSet:
        """
        Load raw data, write to the configured sink, and return the DataSet.

        Requires ``sink`` and ``sink_table`` to be set.
        """
        if self._sink is None or self._sink_table is None:
            raise RuntimeError(
                "BronzeLayer.execute() requires 'sink' and 'sink_table' to be configured."
            )
        ds = self.load(name=name or self._sink_table)
        self._sink.write(ds.to_pandas(), self._sink_table)
        return ds

    def __repr__(self) -> str:
        return (
            f"<BronzeLayer connector={self._connector.name!r} "
            f"source={self._source!r} "
            f"sink_table={self._sink_table!r}>"
        )
