"""
DataSet — pandas DataFrame wrapper with a full, immutable lineage chain.

Every operation (filter, transform, sort, join, …) returns a *new* DataSet
with the original DataSet's lineage plus a new LineageNode appended.
The underlying DataFrame is never mutated in place.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Union

import pandas as pd
from numpy import bool_ as np_bool, datetime64 as np_datetime64


#: pandas 3.0 (PDEP-14) renamed the default string dtype: a column pandas 2
#: called ``object`` is now ``str`` (with pyarrow variants under either
#: major). The CSV bytes are identical — only the dtype's NAME moved — so a
#: receipt rendered under pandas 2 would stop re-verifying after a pandas
#: upgrade purely because of this label. Canonicalize toward the LEGACY
#: name: every existing manifest and the pre-change fingerprint corpus were
#: hashed with ``object``, and a fingerprint algorithm must never orphan
#: the receipts it already issued.
_DTYPE_CANON = {
    "str": "object",
    "string": "object",
    "string[python]": "object",
    "string[pyarrow]": "object",
    "str[pyarrow]": "object",
    "large_string[pyarrow]": "object",
}


def canonical_dtypes_repr(df: pd.DataFrame) -> str:
    """The dtype list exactly as the fingerprint hashes it — one rule,
    shared by :func:`frame_fingerprint` and the embedded canonical triple,
    so the offline rehash can never disagree with the live one."""
    return repr([_DTYPE_CANON.get(s, s)
                 for s in (str(t) for t in df.dtypes)])


def frame_fingerprint(df: pd.DataFrame, algo: Optional[int] = None) -> str:
    """
    SHA-256 hash of a DataFrame's content — the audit primitive.

    Covers column names, dtypes, and every cell value in row order, via a
    canonical CSV serialization. This is the single fingerprint algorithm:
    ``DataSet.fingerprint()`` delegates here, and ``DataModel.load()`` uses
    it to fingerprint source tables while the frame is already in memory,
    so query lineage and manifests record exactly which inputs produced a
    result.

    Dtype names are canonicalized (:data:`_DTYPE_CANON`) so the fingerprint
    is stable across the pandas 2→3 string-dtype rename: same bytes, same
    receipt, whichever pandas rendered it.

    ``algo`` picks the algorithm a receipt was stamped under. ``None``, 1 and
    2 hash the bytes above (they differ only in how the engine ordered the
    rows it handed over); 3 is :func:`rounded_fingerprint`, the one that
    compares two engines.
    """
    if algo == FINGERPRINT_ALGO_ROUNDED:
        return rounded_fingerprint(df)
    if algo not in (None, FINGERPRINT_ALGO_LEGACY, FINGERPRINT_ALGO_TOTAL_ORDER):
        raise ValueError(
            f"fingerprint algorithm {algo!r} is not one this tracebi knows "
            f"(1, 2 or 3); upgrade tracebi to check it"
        )
    h = hashlib.sha256()
    h.update(repr(list(df.columns)).encode("utf-8"))
    h.update(canonical_dtypes_repr(df).encode("utf-8"))
    h.update(df.to_csv(index=False).encode("utf-8"))
    return h.hexdigest()


# ─────────────────────────────────────────────────────────────
# Fingerprint algorithm versioning
# ─────────────────────────────────────────────────────────────
# Every stamped query result records which algorithm produced its fingerprint.
# This is the SEAM a verifier needs: when a new algorithm lands (algo 3 below;
# a Merkle-columnar leaf would be another), verify reproduces each receipt
# under the rules it was stamped with instead of silently re-classifying it. Verify hashes the
# re-run under the recorded algorithm: 1 and 2 share bytes (a legacy algo-1
# non-aggregate receipt was nondeterministic, so was never reliably
# reproducible anyway), and 3 is the rounded algorithm below.
# The bytes are identical across 1 and 2; the difference is purely that algo 2
# gives a non-aggregate result a canonical total row order (algo 1 left it in
# engine scan order, which varied between identical runs).
FINGERPRINT_ALGO_LEGACY = 1        # columns+dtypes+to_csv, rows in engine order
FINGERPRINT_ALGO_TOTAL_ORDER = 2   # same bytes; aggregate=False rows total-ordered
FINGERPRINT_ALGO_ROUNDED = 3       # numbers to 9 significant digits, rows sorted
CURRENT_FINGERPRINT_ALGO = FINGERPRINT_ALGO_TOTAL_ORDER

# Algo 3 exists so that two engines can agree on a number. The page engine
# (tracebi-calc.js) sums in a different order than DuckDB, so the last bits of
# a float differ, and it hands back JSON numbers with no dtype. Algo 3 rounds
# every number to 9 significant digits, drops dtypes, and sorts the rows, so
# the same result reads the same from either side. A server stamp stays on
# algo 2: the CSV embed ships those exact bytes in display order and its
# offline check hashes them, which rounding or re-sorting would break.
# ``verify`` re-runs a receipt under whichever algorithm it records.
FINGERPRINT_SIG_DIGITS = 9


def round_significant(value: float, digits: int = FINGERPRINT_SIG_DIGITS) -> float:
    """*value* rounded to *digits* significant digits, half away from zero.

    The tie rule is the one JavaScript's ``Number(x.toPrecision(9))`` uses
    (it rounds the exact binary value, ties away from zero), so the page
    engine ports it in one line. ``Decimal(value)`` is the exact binary value,
    which is why a tie is decided the same way on both sides. Python's own
    ``format(x, ".9g")`` rounds ties to even and would differ on them.
    """
    if value == 0 or not math.isfinite(value):
        return value + 0.0                     # -0.0 reads as 0.0
    exact = Decimal(value)
    step = Decimal(1).scaleb(exact.adjusted() - (digits - 1))
    return float(exact.quantize(step, rounding=ROUND_HALF_UP)) + 0.0


def canonical_cell(value: Any) -> Any:
    """One cell as algo 3 sees it: a JSON scalar with no dtype.

    Every number (int, float, Decimal, numpy) is rounded with
    :func:`round_significant` and written as an int when the rounded value is
    whole, so a count that one engine returns as ``3`` and another as ``3.0``
    reads the same. A null of any kind (None, NaN, NaT, pd.NA) is None.
    Infinities are the strings ``"Infinity"`` / ``"-Infinity"``, since JSON
    has no spelling for them. Datetimes are ISO-8601 strings; strings and
    booleans are themselves.
    """
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, (bool, np_bool)):
        return bool(value)
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date, pd.Timestamp, np_datetime64)):
        return pd.Timestamp(value).isoformat()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return str(value)
    if isinstance(value, (int, float, Decimal)) or hasattr(value, "dtype"):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if math.isinf(number):
            return "Infinity" if number > 0 else "-Infinity"
        rounded = round_significant(number)
        return int(rounded) if rounded.is_integer() else rounded
    return str(value)


def _cell_order(value: Any) -> tuple:
    # Numbers, then booleans, then strings, then nulls: a total order over
    # whatever a column holds, nulls last as in every other sort here.
    if value is None:
        return (3,)
    if isinstance(value, bool):
        return (1, value)
    if isinstance(value, str):
        return (2, value)
    return (0, value)


def canonical_rows(df: pd.DataFrame, total_order: bool = True) -> "tuple[list, list]":
    """``(columns, rows)`` with every cell through :func:`canonical_cell`.

    With *total_order* the rows are sorted by every column, left to right
    (numbers by value, strings by code point, nulls last), so two engines
    that return the same rows in a different order agree. Without it the
    rows keep the frame's order, which is what a parity check compares when
    the order is itself part of the answer (an ``order_by``).
    """
    cols = [str(c) for c in df.columns]
    rows = [[canonical_cell(v) for v in row]
            for row in df.itertuples(index=False, name=None)]
    if total_order:
        rows.sort(key=lambda r: [_cell_order(v) for v in r])
    return cols, rows


def rounded_fingerprint(df: pd.DataFrame) -> str:
    """Fingerprint algo 3: SHA-256 of the canonical rows as compact JSON.

    Column names and every cell after :func:`canonical_rows` (rounded, total
    order); dtypes are not hashed, because a page engine has none to report.
    """
    cols, rows = canonical_rows(df, total_order=True)
    text = json.dumps({"algo": FINGERPRINT_ALGO_ROUNDED, "cols": cols, "rows": rows},
                      ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────
# LineageNode
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LineageNode:
    """
    A single step in a DataSet's lineage chain.

    Instances are immutable: attributes cannot be reassigned, and
    ``connector`` / ``metadata`` are exposed as read-only mappings.
    This is what makes the lineage chain a trustworthy audit record —
    no code can rewrite history after the fact.

    Fields:
        operation:   Operation type string: 'load', 'filter', 'transform',
                     'join', 'sort', 'select', 'rename', …
        description: Human-readable description of the step.
        connector:   Mapping with connector metadata (for 'load' steps).
        source:      Source identifier (table name, file path, …).
        timestamp:   ISO-8601 UTC timestamp when this node was created.
        metadata:    Arbitrary key/value pairs (e.g. rows_before/after for filters).
    """

    operation: str
    description: str = ""
    connector: Optional[Mapping[str, str]] = None
    source: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Wrap mutable dicts in read-only views so the audit chain
        # cannot be edited in place after creation.
        if self.connector is not None and not isinstance(self.connector, MappingProxyType):
            object.__setattr__(self, "connector", MappingProxyType(dict(self.connector)))
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict:
        return {
            "operation":   self.operation,
            "description": self.description,
            "connector":   dict(self.connector) if self.connector is not None else None,
            "source":      self.source,
            "timestamp":   self.timestamp,
            "metadata":    dict(self.metadata),
        }


def last_query_node(lineage: list) -> Optional[dict]:
    """The lineage node that stamps the resolved query, or None.

    THE last-node-with-a-``query_spec`` rule: ``DataModel.execute`` appends
    the query node last, so the last node whose metadata carries a
    ``query_spec`` is the one that speaks for the frame. Operates on the
    dict form of a lineage chain (``DataSet.lineage_to_dict()`` or a
    manifest's recorded lineage) and returns the matching node itself, so a
    caller may compare it by identity against the chain. The one shared
    implementation behind ``reports.embed``, ``verify`` and ``spec``.
    """
    for node in reversed(lineage or []):
        if not isinstance(node, dict):
            continue
        md = node.get("metadata")
        if isinstance(md, dict) and md.get("query_spec"):
            return node
    return None


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

    def fingerprint(self, algo: Optional[int] = None) -> str:
        """
        SHA-256 hash of the DataFrame content — a stable audit primitive.

        Covers column names, dtypes, and every cell value in row order,
        via a canonical CSV serialization. Deterministic across sessions
        and pandas versions, so a manifest fingerprint can be re-verified
        long after the report was rendered. ``algo`` re-hashes under the
        algorithm a receipt recorded (see :func:`frame_fingerprint`).
        """
        return frame_fingerprint(self._df, algo=algo)

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
        rows_before = len(self._df)
        cols_before = set(self._df.columns)
        new_df = func(self._df.copy())
        cols_after = set(new_df.columns)
        metadata: dict[str, Any] = {
            "rows_before": rows_before,
            "rows_after":  len(new_df),
        }
        added = sorted(cols_after - cols_before)
        removed = sorted(cols_before - cols_after)
        if added:
            metadata["columns_added"] = added
        if removed:
            metadata["columns_removed"] = removed
        node = LineageNode(
            operation="transform",
            description=description or "transform",
            metadata=metadata,
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
            metadata={"by": by, "ascending": ascending, "rows": len(new_df)},
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def select(self, columns: list[str], description: str = "") -> "DataSet":
        """Return a new DataSet with only the specified columns."""
        new_df = self._df[columns]
        node = LineageNode(
            operation="select",
            description=description or f"Selected columns: {columns}",
            metadata={"columns": columns, "rows": len(new_df)},
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
            metadata={"columns": columns, "rows": len(new_df)},
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def join(
        self,
        other: "DataSet",
        on: Optional[Union[str, list[str]]] = None,
        how: str = "left",
        left_on: Optional[Union[str, list[str]]] = None,
        right_on: Optional[Union[str, list[str]]] = None,
        description: str = "",
    ) -> "DataSet":
        """
        Join another DataSet and return a new one.

        The result's lineage contains both sides' full chains plus a join
        step recording the keys, join type, and left/right/after row counts.

        Args:
            on:          Key column(s) present on both sides. Mutually
                         exclusive with ``left_on``/``right_on``.
            how:         'left' (default), 'inner', 'right', or 'outer'.
            left_on:     Key column(s) on this DataSet.
            right_on:    Key column(s) on ``other``.
            description: Human-readable description for the lineage record.
        """
        if on is not None and (left_on is not None or right_on is not None):
            raise ValueError("Pass either 'on' or 'left_on'/'right_on', not both.")
        if on is None and (left_on is None or right_on is None):
            raise ValueError("join() requires 'on', or both 'left_on' and 'right_on'.")

        lk = on if on is not None else left_on
        rk = on if on is not None else right_on
        self._require_columns([lk] if isinstance(lk, str) else lk, "join key")
        other._require_columns([rk] if isinstance(rk, str) else rk, "join key")

        merged = self._df.merge(
            other._df,
            left_on=lk,
            right_on=rk,
            how=how,
            suffixes=("", f"_{other.name}"),
        )
        key_str = lk if lk == rk else f"{lk}={rk}"
        node = LineageNode(
            operation="join",
            description=description
            or f"Joined '{self.name}' → '{other.name}' on {key_str} ({how})",
            metadata={
                "right":      other.name,
                "left_key":   lk,
                "right_key":  rk,
                "how":        how,
                "rows_left":  len(self._df),
                "rows_right": len(other._df),
                "rows_after": len(merged),
                # How many trailing pre-join lineage nodes belong to the right
                # side — lets graph renderers reconstruct the branch structure
                # from the flat lineage list.
                "right_chain_len": len(other._lineage),
            },
        )
        return DataSet(
            df=merged,
            name=self.name,
            lineage=self._lineage + other._lineage + [node],
        )

    def aggregate(
        self,
        by: Union[str, list[str]],
        description: str = "",
        **measures: Union[str, tuple[str, str]],
    ) -> "DataSet":
        """
        Group by one or more columns and aggregate, returning a new DataSet.

        Each keyword argument names an output column. A string value
        aggregates the column of the same name (``revenue="sum"``); a
        ``(column, fn)`` tuple aggregates a different source column
        (``orders=("order_id", "nunique")``).

        Args:
            by:          Column name or list of column names to group by.
            description: Human-readable description for the lineage record.
        """
        if not measures:
            raise ValueError(
                'aggregate() requires at least one measure, e.g. revenue="sum".'
            )
        by_list = [by] if isinstance(by, str) else list(by)
        named: dict[str, tuple[str, str]] = {
            out: (out, spec) if isinstance(spec, str) else (spec[0], spec[1])
            for out, spec in measures.items()
        }
        self._require_columns(
            by_list + [col for col, _ in named.values()], "aggregate"
        )

        rows_before = len(self._df)
        new_df = (
            self._df.groupby(by_list, as_index=False, dropna=False)
            .agg(**{out: pd.NamedAgg(column=col, aggfunc=fn)
                    for out, (col, fn) in named.items()})
        )
        measure_str = ", ".join(f"{out}={fn}({col})" if out != col else f"{fn}({col})"
                                for out, (col, fn) in named.items())
        node = LineageNode(
            operation="aggregate",
            description=description
            or f"Aggregated by {', '.join(by_list)}: {measure_str}",
            metadata={
                "by":          by_list,
                "measures":    {out: {"column": col, "fn": fn}
                                for out, (col, fn) in named.items()},
                "rows_before": rows_before,
                "rows_after":  len(new_df),
            },
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def assign(self, description: str = "", **columns: Any) -> "DataSet":
        """
        Add or replace columns and return a new DataSet.

        Works like ``DataFrame.assign``: values may be scalars, Series, or
        callables receiving the DataFrame
        (``ds.assign(margin=lambda df: df.revenue - df.cost)``).
        """
        if not columns:
            raise ValueError("assign() requires at least one column keyword.")
        existing = set(self._df.columns)
        new_df = self._df.assign(**columns)
        added = [c for c in columns if c not in existing]
        replaced = [c for c in columns if c in existing]
        metadata: dict[str, Any] = {"rows": len(new_df)}
        if added:
            metadata["columns_added"] = added
        if replaced:
            metadata["columns_replaced"] = replaced
        node = LineageNode(
            operation="assign",
            description=description or f"Assigned columns: {', '.join(columns)}",
            metadata=metadata,
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def dropna(
        self,
        subset: Optional[Union[str, list[str]]] = None,
        description: str = "",
    ) -> "DataSet":
        """
        Drop rows containing nulls and return a new DataSet.

        Args:
            subset:      Column name or list of columns to check (default: all).
            description: Human-readable description for the lineage record.
        """
        cols = [subset] if isinstance(subset, str) else subset
        if cols:
            self._require_columns(cols, "dropna()")
        rows_before = len(self._df)
        new_df = self._df.dropna(subset=cols)
        rows_after = len(new_df)
        scope = f" in {cols}" if cols else ""
        node = LineageNode(
            operation="dropna",
            description=description or f"Dropped {rows_before - rows_after} rows with nulls{scope}",
            metadata={
                "subset":       cols,
                "rows_before":  rows_before,
                "rows_after":   rows_after,
                "rows_removed": rows_before - rows_after,
            },
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def fillna(
        self,
        values: Union[Any, dict[str, Any]],
        description: str = "",
    ) -> "DataSet":
        """
        Fill nulls and return a new DataSet.

        Args:
            values:      Scalar applied to every column, or a dict
                         ``{column: fill_value}``.
            description: Human-readable description for the lineage record.
        """
        if isinstance(values, dict):
            self._require_columns(list(values), "fillna()")
        nulls_before = int(self._df.isna().sum().sum())
        new_df = self._df.fillna(value=values)
        nulls_after = int(new_df.isna().sum().sum())
        node = LineageNode(
            operation="fillna",
            description=description or f"Filled {nulls_before - nulls_after} null cells",
            metadata={
                "values":       {k: repr(v) for k, v in values.items()} if isinstance(values, dict) else repr(values),
                "cells_filled": nulls_before - nulls_after,
                "rows":         len(new_df),
            },
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def deduplicate(
        self,
        subset: Optional[Union[str, list[str]]] = None,
        keep: str = "first",
        description: str = "",
    ) -> "DataSet":
        """
        Drop duplicate rows and return a new DataSet.

        Args:
            subset:      Column name or list of columns that define a
                         duplicate (default: all columns).
            keep:        Which duplicate to keep: "first" (default) or "last".
            description: Human-readable description for the lineage record.
        """
        cols = [subset] if isinstance(subset, str) else subset
        if cols:
            self._require_columns(cols, "deduplicate()")
        rows_before = len(self._df)
        new_df = self._df.drop_duplicates(subset=cols, keep=keep)
        rows_after = len(new_df)
        scope = f" by {cols}" if cols else ""
        node = LineageNode(
            operation="deduplicate",
            description=description or f"Removed {rows_before - rows_after} duplicate rows{scope}",
            metadata={
                "subset":       cols,
                "keep":         keep,
                "rows_before":  rows_before,
                "rows_after":   rows_after,
                "rows_removed": rows_before - rows_after,
            },
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def cast(
        self,
        types: dict[str, Any],
        description: str = "",
    ) -> "DataSet":
        """
        Convert column dtypes and return a new DataSet.

        Args:
            types:       Dict ``{column: dtype}``, e.g.
                         ``{"order_id": "int64", "placed_at": "datetime64[ns]"}``.
            description: Human-readable description for the lineage record.
        """
        self._require_columns(list(types), "cast()")
        new_df = self._df.astype(types)
        type_strs = {k: str(v) for k, v in types.items()}
        node = LineageNode(
            operation="cast",
            description=description or f"Cast columns: {type_strs}",
            metadata={"types": type_strs, "rows": len(new_df)},
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def limit(self, n: int, description: str = "") -> "DataSet":
        """
        Keep only the first ``n`` rows and return a new DataSet.

        Combine with :meth:`sort` for top-N analyses:
        ``ds.sort("revenue", ascending=False).limit(10)``.
        """
        rows_before = len(self._df)
        new_df = self._df.head(n)
        node = LineageNode(
            operation="limit",
            description=description or f"Limited to first {n} rows (from {rows_before})",
            metadata={"n": n, "rows_before": rows_before, "rows_after": len(new_df)},
        )
        return DataSet(df=new_df, name=self.name, lineage=self._lineage + [node])

    def _require_columns(self, columns: list[str], context: str) -> None:
        """Raise ValueError naming missing columns, with close-match hints."""
        import difflib

        missing = [c for c in columns if c not in self._df.columns]
        if not missing:
            return
        hints = []
        for c in missing:
            close = difflib.get_close_matches(c, self._df.columns, n=1)
            hints.append(f"'{c}'" + (f" (did you mean '{close[0]}'?)" if close else ""))
        raise ValueError(
            f"DataSet '{self.name}': {context} column(s) not found: "
            f"{', '.join(hints)}. Available: {list(self._df.columns)}"
        )

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

    def help_text(self) -> str:
        """Return a cheat sheet of the fluent DataSet API as a string."""
        return (
            "\nDataSet — immutable DataFrame wrapper with a lineage chain.\n"
            "\n"
            "Transforms (each returns a NEW DataSet and records a lineage step):\n"
            '  .filter(expr, description="")     Pandas query string, e.g. "status == \'shipped\'"\n'
            '  .assign(margin=lambda df: ...)    Add/replace columns (like DataFrame.assign)\n'
            '  .join(other, on="key", how="left")  Join another DataSet; lineage keeps both sides\n'
            '  .aggregate(by="region", revenue="sum", orders=("order_id", "nunique"))\n'
            "                                    Group + aggregate; kwargs name output columns\n"
            '  .transform(func, description="")  Any function (DataFrame) -> DataFrame (escape hatch)\n'
            "  .sort(by, ascending=True)         Sort by column(s)\n"
            "  .select(columns)                  Keep only these columns\n"
            '  .rename({"old": "new"})           Rename columns\n'
            "\n"
            "Cleaning (structured lineage — prefer these over transform() lambdas):\n"
            '  .dropna(subset=None)              Drop rows with nulls\n'
            '  .fillna(0)  /  .fillna({"qty": 0})  Fill nulls (scalar or per-column)\n'
            '  .deduplicate(subset="order_id")   Drop duplicate rows\n'
            '  .cast({"qty": "int64"})           Convert column dtypes\n'
            "  .limit(10)                        First n rows (chain after .sort for top-N)\n"
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

    def help(self) -> None:
        """Print a cheat sheet of the fluent DataSet API."""
        print(self.help_text())

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
