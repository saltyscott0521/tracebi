"""
DataSet — pandas DataFrame wrapper with a full, immutable lineage chain.

Every operation (filter, transform, sort, join, …) returns a *new* DataSet
with the original DataSet's lineage plus a new LineageNode appended.
The underlying DataFrame is never mutated in place.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Union

import pandas as pd


# ─────────────────────────────────────────────────────────────
# LineageNode
# ─────────────────────────────────────────────────────────────

@dataclass
class LineageNode:
    """
    A single step in a DataSet's lineage chain.

    Fields:
        operation:   Operation type string: 'load', 'filter', 'transform',
                     'join', 'sort', 'select', 'rename', …
        description: Human-readable description of the step.
        connector:   Dict with connector metadata (for 'load' steps).
        source:      Source identifier (table name, file path, …).
        timestamp:   ISO-8601 UTC timestamp when this node was created.
        metadata:    Arbitrary key/value pairs (e.g. rows_before/after for filters).
    """

    operation: str
    description: str = ""
    connector: Optional[dict[str, str]] = None
    source: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "operation":   self.operation,
            "description": self.description,
            "connector":   self.connector,
            "source":      self.source,
            "timestamp":   self.timestamp,
            "metadata":    self.metadata,
        }


# ─────────────────────────────────────────────────────────────
# DataSet
# ─────────────────────────────────────────────────────────────

class DataSet:
    """
    An immutable pandas DataFrame wrapper with a full lineage chain.

    Every fluent method returns a **new** DataSet; the original is unchanged.
    The lineage chain records every operation applied to produce this DataSet,
    from the initial load through every filter, transform, and join.

    Usage:
        from tracebi.model.dataset import DataSet, LineageNode

        node = LineageNode(
            operation="load",
            description="Loaded orders from CSV",
            connector={"connector_name": "sales_csv", "connector_type": "CSVConnector"},
            source="orders.csv",
        )
        ds = DataSet(df=orders_df, name="orders", lineage=[node])

        filtered = (
            ds
            .filter("status == 'shipped'", description="Shipped orders only")
            .transform(lambda df: df.assign(margin=df.revenue - df.cost),
                       description="margin = revenue - cost")
            .sort("margin", ascending=False)
        )

        filtered.print_lineage()
    """

    def __init__(
        self,
        df: pd.DataFrame,
        name: str,
        lineage: Optional[list[LineageNode]] = None,
    ) -> None:
        self._df = df.copy()
        self.name = name
        self._lineage: list[LineageNode] = list(lineage or [])

    # ── Properties ─────────────────────────────────────────────

    @property
    def lineage(self) -> list[LineageNode]:
        return list(self._lineage)

    @property
    def shape(self) -> tuple[int, int]:
        return self._df.shape

    @property
    def columns(self) -> list[str]:
        return list(self._df.columns)

    # ── Data access ────────────────────────────────────────────

    def to_pandas(self) -> pd.DataFrame:
        """Return a copy of the underlying DataFrame."""
        return self._df.copy()

    def fingerprint(self) -> str:
        """MD5 hash of the DataFrame content — useful for change detection."""
        raw = pd.util.hash_pandas_object(self._df, index=True).values.tobytes()
        return hashlib.md5(raw).hexdigest()

    def lineage_to_dict(self) -> list[dict]:
        return [node.to_dict() for node in self._lineage]

    # ── Fluent operations ──────────────────────────────────────

    def filter(self, expr: str, description: str = "") -> "DataSet":
        """
        Apply a pandas query expression and return a new DataSet.

        Args:
            expr:        Pandas query string, e.g. ``"status == 'shipped'"``
            description: Human-readable description for the lineage record.
        """
        rows_before = len(self._df)
        new_df = self._df.query(expr)
        rows_after = len(new_df)
        node = LineageNode(
            operation="filter",
            description=description or f"Filter: {expr}",
            metadata={
                "expr":         expr,
                "rows_before":  rows_before,
                "rows_after":   rows_after,
                "rows_removed": rows_before - rows_after,
            },
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def transform(
        self,
        func: Callable[[pd.DataFrame], pd.DataFrame],
        description: str = "",
    ) -> "DataSet":
        """
        Apply an arbitrary function to the DataFrame and return a new DataSet.

        Args:
            func:        A callable ``(pd.DataFrame) -> pd.DataFrame``.
            description: Human-readable description for the lineage record.
        """
        new_df = func(self._df.copy())
        node = LineageNode(
            operation="transform",
            description=description or "transform",
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def sort(
        self,
        by: Union[str, list[str]],
        ascending: Union[bool, list[bool]] = True,
        description: str = "",
    ) -> "DataSet":
        """
        Sort the DataSet and return a new one.

        Args:
            by:          Column name or list of column names to sort by.
            ascending:   Sort direction (default True = ascending).
            description: Human-readable description for the lineage record.
        """
        new_df = self._df.sort_values(by=by, ascending=ascending)
        by_str = by if isinstance(by, str) else ", ".join(by)
        dir_str = ("asc" if ascending is True
                   else "desc" if ascending is False
                   else str(ascending))
        node = LineageNode(
            operation="sort",
            description=description or f"Sorted by {by_str} ({dir_str})",
            metadata={"by": by, "ascending": ascending},
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def select(self, columns: list[str], description: str = "") -> "DataSet":
        """Return a new DataSet with only the specified columns."""
        new_df = self._df[columns]
        node = LineageNode(
            operation="select",
            description=description or f"Selected columns: {columns}",
            metadata={"columns": columns},
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def rename(
        self,
        columns: dict[str, str],
        description: str = "",
    ) -> "DataSet":
        """Return a new DataSet with columns renamed."""
        new_df = self._df.rename(columns=columns)
        node = LineageNode(
            operation="rename",
            description=description or f"Renamed columns: {columns}",
            metadata={"columns": columns},
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    # ── Inspection ─────────────────────────────────────────────

    def print_lineage(self) -> None:
        """Pretty-print the full lineage chain to stdout."""
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  Lineage for DataSet: '{self.name}'")
        print(f"  Shape: {self._df.shape[0]} rows × {self._df.shape[1]} cols")
        print(sep)
        for i, node in enumerate(self._lineage, 1):
            print(f"  Step {i}: [{node.operation.upper()}]  {node.description}")
            if node.connector:
                for k, v in node.connector.items():
                    label = k.replace("_", " ").title().ljust(12)
                    print(f"    {label}: {v}")
            if node.source:
                print(f"    {'Source'.ljust(12)}: {node.source}")
            for k, v in node.metadata.items():
                label = k.replace("_", " ").title().ljust(12)
                print(f"    {label}: {v}")
        print(f"{sep}\n")

    def help(self) -> None:
        """Print a cheat sheet of the fluent DataSet API."""
        print(
            "\nDataSet — immutable DataFrame wrapper with a lineage chain.\n"
            "\n"
            "Transforms (each returns a NEW DataSet and records a lineage step):\n"
            '  .filter(expr, description="")     Pandas query string, e.g. "status == \'shipped\'"\n'
            '  .transform(func, description="")  Any function (DataFrame) -> DataFrame\n'
            "  .sort(by, ascending=True)         Sort by column(s)\n"
            "  .select(columns)                  Keep only these columns\n"
            '  .rename({"old": "new"})           Rename columns\n'
            "\n"
            "Inspection:\n"
            "  .shape / .columns / len(ds)\n"
            "  .to_pandas()                      Copy of the underlying DataFrame\n"
            "  .lineage / .print_lineage()       Full audit chain\n"
            "  .fingerprint()                    Content hash for change detection\n"
            "\n"
            "Reporting:\n"
            "  Pass a DataSet to TableSection / ChartSection — its lineage is\n"
            "  included in the report manifest automatically.\n"
        )

    def _repr_html_(self) -> str:
        """Rich notebook display: header, lineage chain, and a preview table."""
        import html as _h

        n_preview = 10
        head = self._df.head(n_preview)
        rows, cols = self._df.shape

        badge_css = (
            "display:inline-block;padding:2px 8px;border-radius:10px;"
            "font-size:10px;font-weight:600;background:#DEEBF7;color:#1F3864;"
        )
        chain = ' <span style="color:#999">→</span> '.join(
            f'<span style="{badge_css}" title="{_h.escape(node.description)}">'
            f'{_h.escape(node.operation)}</span>'
            for node in self._lineage
        ) or '<span style="color:#999;font-size:11px">no lineage</span>'

        th_css = (
            "background:#1F3864;color:#fff;padding:5px 10px;text-align:left;"
            "font-size:11px;font-weight:600;"
        )
        td_css = "padding:4px 10px;border-bottom:1px solid #dde4ef;font-size:11px;"

        header_cells = "".join(
            f'<th style="{th_css}">{_h.escape(str(c))}'
            f'<div style="font-weight:400;opacity:0.7">{_h.escape(str(self._df[c].dtype))}</div></th>'
            for c in head.columns
        )
        body_rows = ""
        for _, r in head.iterrows():
            cells = "".join(
                f'<td style="{td_css}">'
                f'{_h.escape(str(v)) if pd.notna(v) else "<i>NaN</i>"}</td>'
                for v in r
            )
            body_rows += f"<tr>{cells}</tr>"

        more = ""
        if rows > n_preview:
            more = (
                f'<div style="font-size:11px;color:#999;margin-top:4px">'
                f'… {rows - n_preview:,} more rows</div>'
            )

        return f"""
<div style="font-family:'Segoe UI',Calibri,Arial,sans-serif;border:1px solid #dde4ef;border-radius:6px;padding:12px 14px;display:inline-block;max-width:100%;overflow-x:auto">
  <div style="margin-bottom:6px">
    <span style="font-weight:700;color:#1F3864;font-size:13px">{_h.escape(self.name)}</span>
    <span style="color:#666;font-size:11px;margin-left:8px">{rows:,} rows × {cols} cols</span>
  </div>
  <div style="margin-bottom:8px">{chain}</div>
  <table style="border-collapse:collapse"><thead><tr>{header_cells}</tr></thead>
  <tbody>{body_rows}</tbody></table>
  {more}
</div>"""

    # ── Dunder ─────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._df)

    def __repr__(self) -> str:
        return (
            f"<DataSet name={self.name!r} "
            f"shape={self.shape} "
            f"lineage_steps={len(self._lineage)}>"
        )
