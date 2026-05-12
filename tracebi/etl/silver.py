"""
SilverLayer — clean, type-cast, deduplicate, and lightly transform raw data.

Accepts a DataSet (standalone) or reads from a source connector (pipeline mode).
Each step appends a lineage node with ``operation="silver"``.

Pipeline mode: supply ``source`` + ``source_table`` + ``sink`` + ``sink_table``
and call ``execute()`` to load → clean → write in one step.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import pandas as pd

from tracebi.connectors.base import BaseConnector
from tracebi.model.dataset import DataSet, LineageNode


class SilverLayer:
    """
    Declarative cleaning pipeline for bronze data.

    Every method is fluent and returns ``self``.
    Call ``apply(dataset)`` for standalone use or ``execute()`` for pipelines.

    Standalone usage::

        silver = (
            SilverLayer()
            .cast({"qty": "int64"})
            .drop_nulls(subset=["order_id"])
            .deduplicate(subset=["order_id"])
        )
        clean_ds = silver.apply(raw_ds, name="orders_silver")

    Pipeline usage::

        silver = (
            SilverLayer(
                source=db_connector,
                source_table="orders_bronze",
                sink=db_connector,
                sink_table="orders_silver",
            )
            .cast({"qty": "int64"})
            .deduplicate(subset=["order_id"])
        )
        clean_ds = silver.execute()
    """

    def __init__(
        self,
        source: Optional[BaseConnector] = None,
        source_table: Optional[str] = None,
        sink: Optional[BaseConnector] = None,
        sink_table: Optional[str] = None,
    ) -> None:
        self._steps: list[dict[str, Any]] = []
        self._source = source
        self._source_table = source_table
        self._sink = sink
        self._sink_table = sink_table

    # ── Step declarations ──────────────────────────────────────

    def cast(self, type_map: dict[str, str]) -> "SilverLayer":
        """Cast columns to specified dtypes."""
        self._steps.append({"op": "cast", "type_map": type_map})
        return self

    def drop_nulls(self, subset: Optional[list[str]] = None) -> "SilverLayer":
        """Drop rows with nulls in any of the specified columns (all if omitted)."""
        self._steps.append({"op": "drop_nulls", "subset": subset})
        return self

    def deduplicate(self, subset: Optional[list[str]] = None) -> "SilverLayer":
        """Remove duplicate rows (considering all columns if subset is omitted)."""
        self._steps.append({"op": "deduplicate", "subset": subset})
        return self

    def rename(self, columns: dict[str, str]) -> "SilverLayer":
        """Rename columns via ``{old: new}`` mapping."""
        self._steps.append({"op": "rename", "columns": columns})
        return self

    def transform(
        self,
        func: Callable[[pd.DataFrame], pd.DataFrame],
        description: str = "",
    ) -> "SilverLayer":
        """Apply an arbitrary ``(DataFrame) -> DataFrame`` function."""
        self._steps.append({"op": "transform", "func": func, "description": description})
        return self

    # ── Execution ──────────────────────────────────────────────

    def apply(self, dataset: DataSet, name: Optional[str] = None) -> DataSet:
        """
        Execute all declared steps on *dataset* and return a new DataSet.

        Args:
            dataset: Input DataSet (typically from BronzeLayer).
            name:    Name for the output DataSet. Defaults to
                     ``dataset.name + "_silver"``.
        """
        df = dataset.to_pandas()
        lineage = list(dataset.lineage)
        output_name = name or f"{dataset.name}_silver"

        for step in self._steps:
            op = step["op"]

            if op == "cast":
                type_map: dict = step["type_map"]
                df = df.astype({k: v for k, v in type_map.items() if k in df.columns})
                lineage.append(LineageNode(
                    operation="silver",
                    description=f"Cast columns: {type_map}",
                    metadata={"step": "cast", "type_map": type_map},
                ))

            elif op == "drop_nulls":
                subset = step["subset"]
                rows_before = len(df)
                df = df.dropna(subset=subset)
                lineage.append(LineageNode(
                    operation="silver",
                    description=(
                        f"Dropped nulls in {subset or 'all columns'} "
                        f"({rows_before - len(df)} rows removed)"
                    ),
                    metadata={
                        "step":         "drop_nulls",
                        "subset":       subset,
                        "rows_before":  rows_before,
                        "rows_after":   len(df),
                        "rows_removed": rows_before - len(df),
                    },
                ))

            elif op == "deduplicate":
                subset = step["subset"]
                rows_before = len(df)
                df = df.drop_duplicates(subset=subset)
                lineage.append(LineageNode(
                    operation="silver",
                    description=(
                        f"Deduplicated on {subset or 'all columns'} "
                        f"({rows_before - len(df)} rows removed)"
                    ),
                    metadata={
                        "step":               "deduplicate",
                        "subset":             subset,
                        "rows_before":        rows_before,
                        "rows_after":         len(df),
                        "duplicates_dropped": rows_before - len(df),
                    },
                ))

            elif op == "rename":
                columns: dict = step["columns"]
                df = df.rename(columns=columns)
                lineage.append(LineageNode(
                    operation="silver",
                    description=f"Renamed columns: {columns}",
                    metadata={"step": "rename", "columns": columns},
                ))

            elif op == "transform":
                desc = step.get("description") or "silver transform"
                df = step["func"](df.copy())
                lineage.append(LineageNode(
                    operation="silver",
                    description=desc,
                    metadata={"step": "transform"},
                ))

        return DataSet(df=df, name=output_name, lineage=lineage)

    def execute(self) -> DataSet:
        """
        Load from source connector, apply all steps, write to sink, return DataSet.

        Requires ``source``, ``source_table``, ``sink``, and ``sink_table``.
        """
        if self._source is None or self._source_table is None:
            raise RuntimeError(
                "SilverLayer.execute() requires 'source' and 'source_table'."
            )
        if self._sink is None or self._sink_table is None:
            raise RuntimeError(
                "SilverLayer.execute() requires 'sink' and 'sink_table'."
            )
        raw_df = self._source.load(self._source_table)
        load_node = LineageNode(
            operation="load",
            description=f"Pipeline load: '{self._source_table}' from '{self._source.name}'",
            connector={
                "connector_name": self._source.name,
                "connector_type": type(self._source).__name__,
            },
            source=self._source_table,
            metadata={"rows_loaded": len(raw_df)},
        )
        input_ds = DataSet(df=raw_df, name=self._source_table, lineage=[load_node])
        ds = self.apply(input_ds, name=self._sink_table)
        self._sink.write(ds.to_pandas(), self._sink_table)
        return ds

    def __repr__(self) -> str:
        step_names = [s["op"] for s in self._steps]
        return f"<SilverLayer steps={step_names} sink_table={self._sink_table!r}>"
