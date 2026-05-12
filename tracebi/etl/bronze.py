"""
BronzeLayer — raw ingest from a connector with zero transformations.

Stamps lineage with ``operation="bronze"`` and an ingestion timestamp.
This is the first layer in the medallion architecture: data arrives
exactly as the source delivers it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode


class BronzeLayer:
    """
    Raw ingest layer — load data as-is from any connector.

    Usage::

        bronze = BronzeLayer(connector=csv_connector, source="orders.csv")
        ds = bronze.load(name="orders_raw")
        ds.print_lineage()
    """

    def __init__(
        self,
        connector: BaseConnector,
        source: str,
        description: str = "",
    ) -> None:
        """
        Args:
            connector:   Any BaseConnector subclass (CSV, SQL, Memory, etc.).
            source:      Source identifier passed to ``connector.load()``
                         (file path, table name, SQL query, …).
            description: Optional human-readable description for this ingest.
        """
        self._connector = connector
        self._source = source
        self._description = description or f"Bronze ingest from '{connector.name}': {source}"

    def load(self, name: Optional[str] = None) -> DataSet:
        """
        Load raw data and return a lineage-tracked DataSet.

        Every call re-reads from the source — no caching.

        Args:
            name: DataSet name. Defaults to the source identifier.
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
                "layer":           "bronze",
                "ingestion_time":  ingestion_ts,
                "rows_ingested":   len(df),
                "columns":         list(df.columns),
            },
        )
        return DataSet(df=df, name=name or self._source, lineage=[node])

    def __repr__(self) -> str:
        return (
            f"<BronzeLayer connector={self._connector.name!r} "
            f"source={self._source!r}>"
        )
