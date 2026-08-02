"""
Presentation defaults derived from what the model already knows.

Without this, a table rendered straight from a star-schema query shows a
heading of ``DIM_BRANCH.REGION`` and a figure of ``1705495.2200000002``. Both
are fixable — ``column_labels`` and ``number_formats`` have always existed —
but only by an author remembering to reach for them on every table. A human
authoring one report and looking at the result will notice. Something
composing reports at volume, with nobody reading the output, will not.

So the defaults should not be raw; they should be derived. The information
needed is already present:

* a query result carries its model, its measures and its query spec in the
  last lineage node, so the renderer can tell a measure from a dimension
  attribute rather than guessing from dtype alone
* a named measure declared with ``format="currency"`` states its own
  presentation, and that declaration is the shared definition every report
  already agrees on

Anything explicit always wins. These are defaults, not policy — an author who
sets a label or a format gets exactly what they asked for.
"""

from __future__ import annotations

import re
from typing import Any, Optional

#: Column-name suffixes that imply a format when the model says nothing.
#: Deliberately short: a guess that is usually right and always overridable
#: beats a long list that is confidently wrong in someone's schema.
_SUFFIX_HINTS = {
    "_pct": "percent",
    "_percent": "percent",
    "_rate": "percent",
    "_ratio": "percent",
}


def humanise(column: str) -> str:
    """
    ``dim_branch.region`` → ``Region``;  ``market_value`` → ``Market value``.

    The dimension prefix is dropped because it is addressing, not meaning: it
    tells the query engine where to look and tells a reader nothing.
    """
    name = column.split(".")[-1]
    name = re.sub(r"^(dim|fact)_", "", name)
    name = name.replace("_", " ").strip()
    if not name:
        return column
    return name[0].upper() + name[1:]


def _query_metadata(dataset) -> dict:
    """Model, measures and query spec from the last lineage node, if any."""
    lineage = getattr(dataset, "lineage", None) or []
    for node in reversed(lineage):
        meta = getattr(node, "metadata", None) or {}
        if "measures" in meta or "model" in meta:
            return dict(meta)
    return {}


def _declared_formats(model_name: Optional[str]) -> dict:
    """``{measure_name: format}`` for measures the model declares a format on."""
    if not model_name:
        return {}
    try:
        from tracebi.model_registry import get_model, list_models
    except Exception:  # noqa: BLE001 — model registry is optional at render time
        return {}

    for candidate in {model_name, *list_models()}:
        try:
            model = get_model(candidate)
        except Exception:  # noqa: BLE001
            continue
        if getattr(model, "name", None) != model_name and candidate != model_name:
            continue
        out = {}
        for m in (model.info().get("measures") or []):
            if isinstance(m, dict) and m.get("format") and m.get("name"):
                out[m["name"]] = m["format"]
        return out
    return {}


def derive_column_labels(columns, dataset=None, explicit: Optional[dict] = None) -> dict:
    """Readable headings for *columns*, with *explicit* winning outright."""
    explicit = explicit or {}
    derived = {}
    for col in columns:
        if col in explicit:
            continue
        label = humanise(col)
        if label != col:
            derived[col] = label
    return {**derived, **explicit}


def derive_number_formats(
    df, dataset=None, explicit: Optional[dict] = None
) -> dict[str, Any]:
    """
    Formats for the numeric columns of *df*.

    Order of preference: what the author asked for, then what the model
    declares for that measure, then a suffix hint, then a shape-based default
    — whole numbers get thousands separators, fractional ones get two decimal
    places. The last of those is what stops raw float noise reaching a page.
    """
    explicit = explicit or {}
    meta = _query_metadata(dataset) if dataset is not None else {}
    declared = _declared_formats(meta.get("model"))

    derived: dict[str, Any] = {}
    for col in df.select_dtypes(include="number").columns:
        if col in explicit:
            continue
        if col in declared:
            derived[col] = declared[col]
            continue
        hint = next((f for suf, f in _SUFFIX_HINTS.items()
                     if str(col).lower().endswith(suf)), None)
        if hint:
            derived[col] = hint
            continue
        series = df[col].dropna()
        # `comma` for counts and whole amounts, two decimals otherwise. Both
        # beat repr(float), which is the only thing on offer today.
        if len(series) and (series % 1 == 0).all():
            derived[col] = "comma"
        else:
            derived[col] = "decimal"

    return {**derived, **explicit}
