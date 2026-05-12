"""
SilverLayer — clean, type-cast, deduplicate, and lightly join raw data.

Accepts a DataSet (typically from BronzeLayer) and applies a declarative
pipeline of cleaning steps.  Each step appends a lineage node with
``operation="silver"``.

Final DataSet lineage carries the full bronze + silver chain.
"""

from __future__ import annotations

from typing import Any, Optional, Union

import pandas as pd

from tracebi.model.dataset import DataSet, LineageNode


class SilverLayer:
    """
    Declarative cleaning pipeline for bronze data.

    Every method is fluent and returns ``self`` so steps can be chained.
    Call ``apply(dataset)`` to execute the pipeline on a DataSet.

    Usage::

        silver = (
            SilverLayer()
            .cast({"order_date": "datetime64[ns]", "qty": "int64"})
            .drop_nulls(subset=["order_id", "customer_id"])
            .deduplicate(subset=["order_id"])
            .rename({"cust_id": "customer_id"})
        )

        clean_ds = silver.apply(raw_ds, name="orders_silver")
        clean_ds.print_lineage()
    """

    def __init__(self) -> None:
        self._steps: list[dict[str, Any]] = []

    # ── Step declarations ──────────────────────────────────────

    def cast(self, type_map: dict[str, str]) -> "SilverLayer":
        """
        Cast columns to specified dtypes.

        Args:
            type_map: ``{column: dtype}`` — e.g.
                      ``{"order_date": "datetime64[ns]", "qty": "int64"}``.
        """
        self._steps.append({"op": "cast", "type_map": type_map})
        return self

    def drop_nulls(self, subset: Optional[list[str]] = None) -> "SilverLayer":
        """
        Drop rows that have null values in any of the specified columns.

        Args:
            subset: Columns to check. ``None`` checks all columns.
        """
        self._steps.append({"op": "drop_nulls", "subset": subset})
        return self

    def deduplicate(self, subset: Optional[list[str]] = None) -> "SilverLayer":
        """
        Remove duplicate rows.

        Args:
            subset: Columns to consider for duplicate detection.
                    ``None`` considers all columns.
        """
        self._steps.append({"op": "deduplicate", "subset": subset})
        return self

    def rename(self, columns: dict[str, str]) -> "SilverLayer":
        """
        Rename columns.

        Args:
            columns: ``{old_name: new_name}`` mapping.
        """
        self._steps.append({"op": "rename", "columns": columns})
        return self

    def transform(
        self,
        func,
        description: str = "",
    ) -> "SilverLayer":
        """
        Apply an arbitrary ``(pd.DataFrame) -> pd.DataFrame`` function.

        Args:
            func:        Callable that takes and returns a DataFrame.
            description: Human-readable description for this step.
        """
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
                        "step":            "deduplicate",
                        "subset":          subset,
                        "rows_before":     rows_before,
                        "rows_after":      len(df),
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

    def __repr__(self) -> str:
        step_names = [s["op"] for s in self._steps]
        return f"<SilverLayer steps={step_names}>"
