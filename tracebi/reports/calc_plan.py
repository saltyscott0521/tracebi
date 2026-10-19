"""The calc plan: one binding's query as closed JSON a page engine can run.

The build compiles every binding with :func:`compile_plan` against the slice
it embedded for the binding's fact (``tracebi/reports/slice.py``). The page
engine (``tracebi-calc.js``) runs the plan over that slice, under the page's
selection state, and never sees a model. The plan is also what the trace row
of a recomputed figure shows. Python is the source of truth for what a plan
means: :func:`execute_plan` runs one through ``DataModel.execute`` over the
same slice, and the parity fixtures in ``tests/fixtures/calc_parity/`` (made
by ``scripts/gen_calc_parity.py``) pin the expected rows the engine must
reproduce.

A plan is data: no callables, no SQL, no free expressions. A query this round
cannot recompute compiles to ``{"fixed": "<reason>"}`` and the figure keeps its
build-time value, marked as fixed.

The slice a plan reads
----------------------
One table per fact. Its columns are named so that a plan can find them:

* ``"<dim>.<attr>"``: a dimension attribute, exactly as a query names it.
  Time grains and value bins are string labels under their declared name.
* a bare name: a fact column at base grain (one slice row per fact row).
* ``"<measure>:<part>"``: a measure pre-aggregated at the slice's grain,
  under the measure's own filters. Parts are ``sum``, ``count``, ``min`` and
  ``max``; a ``mean`` is stored as ``<m>:sum`` and ``<m>:count``.

For each aggregate the compiler prefers the measure's part columns and falls
back to the base-grain fact columns. ``nunique``, ``stddev`` and percentiles
need base grain. A column the plan needs that the slice does not carry makes the plan
fixed, naming the column.

The plan (``"version": 1``)
---------------------------
::

    {"version": 1, "model": str, "fact": str,
     "slice_columns": [str],         # every column of the fact's slice
     "filters": FILTER | null,       # the binding's own WHERE; always applies
     "group_by": [str],              # slice columns, in query order
     "aggregates": [AGG],
     "means": [{"name", "sum", "count"}],
     "ratios": [{"name", "num", "den"}],
     "shares": [{"name", "base"}],
     "combines": [{"name", "expr": EXPR}],
     "ranks": [{"name", "base", "partition_by": [str]}],
     "runnings": [{"name", "base", "partition_by": [str]}],
     "having": [{"column", "op", "value"}],
     "order_by": [{"column", "desc": bool}],
     "limit": int | null,
     "columns": [str],               # the result, in DataModel.execute's order
     # Time intelligence. Each key is present only when the query has such
     # a measure; absent means empty, so a plan without them is unchanged.
     "period_ends": [{"name", "value", "date"}],
     "pops": [{"name", "base", "unit", "n", "mode"}],
     "to_dates": [{"name", "base", "period"}],
     "time_grain": {"column", "grain"}}  # with pops or to_dates

A ``period_end`` names the slice column it sums (``value``: the measure's
``<m>:sum`` part on an aggregated slice, the fact's value column on a
base-grain one) and the snapshot date column (``date``, a dimension attribute
the slice carries). A ``pop`` is an ``offset`` (``mode`` ``"value"``) or a
``growth`` (``mode`` ``"growth"``) of the result column ``base``, ``n``
``unit`` back (``unit`` one of ``year quarter month week day``). A
``to_date`` accumulates ``base`` within each ``period`` (``year quarter month
week``). Both read the query's one time grain, ``time_grain``: the group
column holding its labels and the grain they are at (see "Label
arithmetic").

The engine runs it in this order, and every step is exactly what
``DataModel.execute`` does:

1. **Filter** the slice rows: ``filters`` AND the applied ``selection``
   (added by :func:`apply_selection`). SQL rules: a predicate on a null cell
   is false, except ``is_null``.
2. **Group** by ``group_by``. With no group columns the result is exactly
   one row, even when no rows passed the filter; except that a plan with no
   ``aggregates`` (its measures are period_ends and what is computed from
   them) has one row when any row passed and none when none did
   (DataModel's skeleton row).
3. **Aggregate** each ``AGG`` within the group::

       {"name": str, "func": FUNC, "source": EXPR, "where": FILTER?, "q": float?}

   ``source`` is evaluated per row; ``where`` (a filtered measure) restricts
   only that aggregate. Nulls are skipped. ``FUNC`` is one of:

   * ``sum``: the sum; null when there are no non-null inputs.
   * ``count``: the number of non-null inputs; 0 when there are none.
   * ``sum_counts``: the sum of pre-aggregated counts; 0 when there are none
     (it re-aggregates a ``count`` part, so it keeps COUNT's zero).
   * ``min`` / ``max``: null when there are no non-null inputs.
   * ``nunique``: the number of distinct non-null inputs.
   * ``quantile`` with ``q`` in [0, 1]: DuckDB's ``quantile_cont``. Sort the
     n non-null inputs ascending (x[0..n-1]); h = (n - 1) * q; lo = floor(h);
     the value is x[lo] when h is whole, else
     x[lo] + (h - lo) * (x[lo + 1] - x[lo]). Null when n is 0. ``median`` and
     ``p<N>`` both compile to it.
   * ``stddev``: the sample standard deviation (DuckDB's ``STDDEV``, which
     is ``stddev_samp``): the square root of the summed squared deviations
     from the mean over n - 1. Null when n is below 2.

4. **period_ends**: within each group, the latest ``date`` among the group's
   rows (nulls skipped; dates and labels compare as strings, below, which is
   time order for ISO dates and for labels of one grain), then the sum of
   ``value`` over the group's rows at that date, nulls skipped, 0 when every
   one is null. A group whose dates are all null gets null; with no group
   columns the one global latest is used, and no rows at it sum to 0.
5. **means**: ``name = sum / count``, null when count is 0 or either is null.
6. **ratios**: ``name = num / den`` over the aggregated columns, null when
   den is 0 or either is null.
7. **shares**: ``name = base / total``, where total is the sum of base over
   every result row (nulls skipped); null for every row when total is 0.
8. **combines**: ``EXPR`` over aggregated columns (``{"ref": name}``); a
   division by zero is null.
9. **ranks**, then **runnings**: order the rows by ``partition_by``
   ascending, then ``base`` descending, then every other group column
   ascending in ``group_by`` order (nulls last in each key). A rank is the
   1-based position within its partition; a running is the cumulative sum of
   ``base`` within its partition in that order (a null base gives null at its
   row and adds nothing).
10. **pops**: a row's prior row is the result row whose ``time_grain`` label
    is ``shift_label(label, grain, unit, n)`` and whose every other group
    column holds the same value (a null matches a null, as pandas' merge
    does; a null label shifts to null, so a null-label row is its own
    prior). ``value`` mode gives the prior row's ``base``, null when there is
    no prior row; ``growth`` gives ``(base - prior) / prior``, null when
    either is null or the prior is 0.
11. **to_dates**: partition the rows by every other group column and
    ``reset_label(label, grain, period)``; within each partition, in
    ascending label order, the cumulative sum of ``base`` (a null base gives
    null at its row and adds nothing). A row with a null in another group
    column gets null; null labels form a partition of their own.
12. **having**: keep rows where every condition holds. pandas rules, unlike
    ``filters``: ``ne`` and ``not_in`` keep a null cell, every other
    comparison drops it.
13. **order_by**: a stable sort by the listed keys, nulls last in each. The
    compiler already appended the group columns as the tie-break, and with
    no ``order_by`` on the query the list is the group columns ascending
    (DuckDB's ``ORDER BY`` of the groups).
14. **limit**: the first ``limit`` rows.
15. **columns**: project to these, dropping parts the plan made for itself
    (a ``mean``'s ``<m>:sum`` / ``<m>:count``).

Strings compare by Unicode code point (DuckDB's byte order on UTF-8, and
Python's); ``false`` sorts before ``true``.

A raw-row query (``aggregate=False``) compiles to a plan with ``"raw":
true``. Nothing is grouped: ``group_by`` lists the dimension columns, which
are projected as they are; ``project`` (``[{"name", "source": EXPR}]``) the
measure columns, each evaluated per row by the row rules below; and
``aggregates`` and every post-aggregate list are empty. The engine filters
(step 1), projects every passing row, then runs ``order_by``, ``limit`` and
``columns``. The compiler writes out the whole order DataModel sorts by: the
query's ``order_by``, then every other column ascending, dimensions first;
with no ``order_by``, every column ascending in result order. A raw query
with a measure that is not a column or a row expression (a ratio, share,
window, period_end, offset, to_date, calculated combination or filtered
measure), or with a ``having``, stays fixed.

Label arithmetic
----------------
A time grain travels in the slice as a string label (``_grain_strings`` in
``slice.py``): year ``2026``, quarter ``2026-Q1``, month ``2026-03``, week
``2026-W09`` (the ISO 8601 year and week; weeks start on Monday), day
``2026-03-14``. A label stands for the date its period starts on
(:func:`label_start`): 1 January, the first day of the quarter, the first of
the month, the Monday of the ISO week, the day itself. Labels of one grain
sort by time as strings, so a range selection on one compares them as text.

* :func:`shift_label` (the pops): move the start date ``n`` ``unit`` back.
  Year, quarter and month move 12n, 3n and n calendar months, clamping the
  day to the last of the target month (pandas' ``DateOffset``: 29 February
  2024 less a year is 28 February 2023). Week and day move 7n and n days.
  The moved date has a label only when it starts a period of the grain,
  because DataModel matches the shifted date exactly; otherwise the row has
  no prior. So 2026-01 less a month is 2025-12, 2026-Q1 less a quarter is
  2025-Q4, 2026-W01 less a week is 2025-W52, and a month less a week has no
  prior.
* :func:`reset_label` (the to_dates): the label, at the reset period, of the
  label's start date. A week belongs to the year, quarter or month its
  Monday falls in, as DataModel's ``to_period`` puts it: 2025-W01 starts on
  2024-12-30, so it accumulates into 2024.

``EXPR``, a closed arithmetic tree (``derived`` row expressions and
``combines``)::

    {"col": str}  {"ref": str}  {"num": number}
    {"op": "+" | "-" | "*" | "/", "args": [EXPR, EXPR]}
    {"op": "neg", "args": [EXPR]}

In a row expression a null operand gives null and division follows IEEE
(x / 0 is ±Infinity, 0 / 0 is NaN, which ``sum`` treats as null). Anything
else in an expression (a call, ``**``, ``//``, a comparison) is refused by
name and the plan is fixed.

``FILTER``, a closed boolean tree::

    {"and": [FILTER, ...]}  {"or": [FILTER, ...]}
    {"column": str, "op": OP, "value": ...}

``OP`` is ``eq ne gt gte lt lte`` (a scalar), ``in not_in`` (a list; an empty
``in`` matches nothing, an empty ``not_in`` everything), ``between`` (``[lo,
hi]``, inclusive), ``is_null not_null`` (no value), ``contains`` (a
case-sensitive substring of a string column; a value with ``%``, ``_`` or
``\\`` is fixed, since SQL ``LIKE`` would read them as wildcards).

The selection state
-------------------
One object per page, ``{field: condition}``. A condition is a list of values
(the row's value is one of them; an empty list is no selection on that
field) or a range ``{"gte"|"gt": v, "lte"|"lt": v}`` with at least one bound.
:func:`apply_selection` composes it onto a plan by one rule: a field applies
when the plan's ``slice_columns`` carry it, and the selection ANDs with the
binding's filters, so it can narrow a figure and never widen one. A field the
slice does not carry leaves the figure untouched and is listed in
``unfiltered_by``.
"""

from __future__ import annotations

import ast
import calendar
import dataclasses
import datetime as dt
import math
import re
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from tracebi.model.data_model import (
    _GRAIN_RANK,
    FILTER_OPS,
    QuerySpec,
    _combine_tree,
    _percentile_fraction,
)
from tracebi.model.sql_calc import SqlQuery

PLAN_VERSION = 1

#: The selection's range bounds, in the order a folded query lists them.
RANGE_OPS = ("gt", "gte", "lt", "lte")

_PART_OF = {"sum": ("sum",), "count": ("count",), "min": ("min",),
            "max": ("max",), "mean": ("sum", "count")}
_ARITH = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_WILDCARDS = ("%", "_", "\\")


class _Fixed(Exception):
    """Raised inside the compiler: this binding stays at its build value."""


def compile_plan(model, query, slice_columns) -> dict:
    """The calc plan for one binding, or ``{"fixed": reason}``.

    *slice_columns* describes the slice the build embedded for the query's
    fact: a list of column names, or of ``{"name", "type"}`` (type one of
    ``number``, ``boolean``, ``string``, ``datetime``), or a mapping of fact
    name to either. ``None`` (or a mapping without the fact) means the page
    has no slice for it.
    """
    if isinstance(query, SqlQuery):
        return _fixed("a SQL binding is computed on the server; it is fixed at build")
    try:
        return _compile(model, query, slice_columns)
    except _Fixed as exc:
        return _fixed(str(exc))


def _fixed(reason: str) -> dict:
    return {"fixed": reason}


def _compile(model, query: QuerySpec, slice_columns) -> dict:
    fact = query.fact
    types = _column_types(slice_columns, fact)
    if types is None:
        raise _Fixed(f"the report embeds no slice for fact '{fact}'")
    try:
        view = model.with_measures(query.calculated) if query.calculated else model
        resolved = view._resolve_measures(query.measures, view._facts[fact])
    except KeyError:
        raise _Fixed(f"fact '{fact}' is not declared on model '{model.name}'")
    except ValueError as exc:
        raise _Fixed(f"the query does not resolve: {exc}")

    def need(column: str, why: str) -> None:
        if column not in types:
            raise _Fixed(f"the slice for '{fact}' does not carry '{column}' "
                         f"({why})")

    group_by = list(query.dimensions or ())
    for dim in group_by:
        need(dim, "a group column")
    if not query.aggregate:
        return _compile_raw(model, query, resolved, types, group_by, need)

    aggregates: list[dict] = []
    means: list[dict] = []
    for name, func in resolved.agg_map.items():
        func = str(func).lower()
        func = "mean" if func == "avg" else func
        source = resolved.derived.get(name, name)
        where = resolved.filtered.get(name)
        parts = _PART_OF.get(func)
        if parts and all(f"{name}:{p}" in types for p in parts):
            # Pre-aggregated at the slice's grain: re-aggregate the parts.
            for p in parts:
                col = f"{name}:{p}"
                agg_func = {"sum": "sum", "count": "sum_counts",
                            "min": "min", "max": "max"}[p]
                aggregates.append({"name": name if len(parts) == 1 else col,
                                   "func": agg_func, "source": {"col": col}})
            if func == "mean":
                means.append({"name": name, "sum": f"{name}:sum",
                              "count": f"{name}:count"})
            continue
        expr = _row_expr(name, source)
        for col in _expr_columns(expr):
            need(col, f"measure '{name}' reads it"
                      + (f" and the slice has no '{name}:{parts[0]}' part"
                         if parts else ""))
        tree = _filter_tree(where, types, f"measure '{name}' filters on it") if where else None
        base = {"source": expr, **({"where": tree} if tree else {})}
        if func == "mean":
            aggregates.append({"name": f"{name}:sum", "func": "sum", **base})
            aggregates.append({"name": f"{name}:count", "func": "count", **base})
            means.append({"name": name, "sum": f"{name}:sum",
                          "count": f"{name}:count"})
        elif func in ("sum", "count", "min", "max", "nunique", "stddev"):
            aggregates.append({"name": name, "func": func, **base})
        elif func == "median" or _percentile_fraction(func) is not None:
            q = 0.5 if func == "median" else _percentile_fraction(func)
            aggregates.append({"name": name, "func": "quantile", "q": q, **base})
        else:
            raise _Fixed(f"measure '{name}': agg '{func}' is not computed on the "
                         f"page this round")

    for wname, part in resolved.partitions.items():
        for col in part:
            if col not in group_by:
                raise _Fixed(f"measure '{wname}' partitions by '{col}', which "
                             f"is not one of the query's dimensions")

    having = []
    for column, raw in (query.having or {}).items():
        op, value = _op_value(column, raw)
        if op == "contains":
            raise _Fixed("a having 'contains' is a pattern match the page "
                         "engine does not reproduce")
        having.append({"column": column, "op": op,
                       **({} if op in ("is_null", "not_null") else {"value": value})})

    period_ends = []
    for name, (value_col, date_ref) in resolved.period_ends.items():
        need(date_ref, f"period_end '{name}' takes its latest snapshot on it")
        # The measure's own part on an aggregated slice (summed at a grain
        # that includes the snapshot date), else the value column itself on
        # a base-grain slice.
        value = f"{name}:sum" if f"{name}:sum" in types else value_col
        need(value, f"period_end '{name}' sums it")
        period_ends.append({"name": name, "value": value, "date": date_ref})

    time_grain = None
    if resolved.pops or resolved.to_dates:
        time_grain = _time_grain(view, group_by,
                                 sorted({**resolved.pops, **resolved.to_dates}))
    for name, (_base, period) in resolved.to_dates.items():
        if _GRAIN_RANK.get(period, 0) <= _GRAIN_RANK.get(time_grain["grain"], 0):
            raise _Fixed(f"to_date '{name}': reset period '{period}' is not "
                         f"coarser than the query's time grain "
                         f"'{time_grain['grain']}'")
    if time_grain and any(h["column"] == time_grain["column"] for h in having):
        raise _Fixed(f"a having on the time axis '{time_grain['column']}' is not "
                     f"recomputed on the page")

    columns = (group_by + list(resolved.agg_map) + list(resolved.period_ends)
               + list(resolved.ratios) + list(resolved.shares)
               + list(resolved.combines) + list(resolved.ranks)
               + list(resolved.runnings) + list(resolved.pops)
               + list(resolved.to_dates))
    order_by = [dict(o) for o in (query.order_by or ())]
    for o in order_by:
        if o["column"] not in columns:
            raise _Fixed(f"order_by column '{o['column']}' is not a result column")
    named = {o["column"] for o in order_by}
    order_by += [{"column": d, "desc": False} for d in group_by if d not in named]

    # Time intelligence goes in only when the query has it, so every other
    # plan keeps the exact shape version 1 started with.
    timed: dict[str, Any] = {}
    if period_ends:
        timed["period_ends"] = period_ends
    if resolved.pops:
        timed["pops"] = [{"name": n, "base": b, "unit": u, "n": k, "mode": m}
                         for n, (b, u, k, m) in resolved.pops.items()]
    if resolved.to_dates:
        timed["to_dates"] = [{"name": n, "base": b, "period": p}
                             for n, (b, p) in resolved.to_dates.items()]
    if time_grain:
        timed["time_grain"] = time_grain

    return {
        "version": PLAN_VERSION,
        "model": model.name,
        "fact": fact,
        "slice_columns": list(types),
        "filters": (_filter_tree(query.filters, types, "a binding filter")
                    if query.filters else None),
        "group_by": group_by,
        "aggregates": aggregates,
        "means": means,
        "ratios": [{"name": n, "num": a, "den": b}
                   for n, (a, b) in resolved.ratios.items()],
        "shares": [{"name": n, "base": b} for n, b in resolved.shares.items()],
        "combines": [{"name": n, "expr": _measure_expr(n, e)}
                     for n, e in resolved.combines.items()],
        "ranks": [{"name": n, "base": b,
                   "partition_by": list(resolved.partitions.get(n, ()))}
                  for n, b in resolved.ranks.items()],
        "runnings": [{"name": n, "base": b,
                      "partition_by": list(resolved.partitions.get(n, ()))}
                     for n, b in resolved.runnings.items()],
        "having": having,
        "order_by": order_by,
        "limit": query.limit,
        "columns": columns,
        **timed,
    }


def _time_grain(model, group_by: list, names: list) -> dict:
    """The query's one declared time grain, the axis pops and to_dates read.
    DataModel refuses a query without exactly one, so such a binding never
    builds; the compiler says so rather than guessing an axis."""
    found = []
    for ref in group_by:
        dim, _, attr = str(ref).partition(".")
        dim_def = model._dimensions.get(dim)
        derived = dim_def.derived.get(attr) if dim_def is not None else None
        if derived and derived.get("kind") == "date_trunc":
            found.append({"column": ref, "grain": derived["grain"]})
    if len(found) != 1:
        raise _Fixed(f"measure(s) {names} need exactly one declared time grain "
                     f"among the query's dimensions, found "
                     f"{[f['column'] for f in found] or 'none'}")
    return found[0]


def _compile_raw(model, query: QuerySpec, resolved, types: dict,
                 group_by: list, need) -> dict:
    """A raw-row query: the dimension columns and each measure's row value,
    for every row that passes, in DataModel's total order."""
    kinds = [kind for kind in ("ratios", "shares", "ranks", "runnings",
                               "period_ends", "pops", "to_dates", "combines",
                               "filtered") if getattr(resolved, kind)]
    if kinds:
        raise _Fixed(f"a raw-row query (aggregate=False) with {', '.join(kinds)} "
                     f"measures is not recomputed on the page")
    if query.having:
        raise _Fixed("a raw-row query (aggregate=False) has no groups to apply "
                     "a having to")
    project = []
    for name in resolved.agg_map:
        expr = _row_expr(name, resolved.derived.get(name, name))
        for col in _expr_columns(expr):
            need(col, f"raw column '{name}' reads it")
        project.append({"name": name, "source": expr})
    columns = group_by + [p["name"] for p in project]
    order_by = [dict(o) for o in (query.order_by or ())]
    for o in order_by:
        if o["column"] not in columns:
            raise _Fixed(f"order_by column '{o['column']}' is not a result column")
    named = {o["column"] for o in order_by}
    # DataModel breaks every tie: the dimensions, then every column, so the
    # same rows always come back in the same order.
    order_by += [{"column": c, "desc": False}
                 for c in dict.fromkeys(group_by + columns) if c not in named]
    return {
        "version": PLAN_VERSION,
        "model": model.name,
        "fact": query.fact,
        "slice_columns": list(types),
        "raw": True,
        "filters": (_filter_tree(query.filters, types, "a binding filter")
                    if query.filters else None),
        "group_by": group_by,
        "project": project,
        "aggregates": [], "means": [], "ratios": [], "shares": [],
        "combines": [], "ranks": [], "runnings": [], "having": [],
        "order_by": order_by,
        "limit": query.limit,
        "columns": columns,
    }


def _column_types(slice_columns, fact: str) -> Optional[dict]:
    if isinstance(slice_columns, Mapping):
        slice_columns = slice_columns.get(fact)
    if slice_columns is None:
        return None
    out: dict[str, Optional[str]] = {}
    for col in slice_columns:
        if isinstance(col, Mapping):
            out[str(col["name"])] = col.get("type")
        else:
            out[str(col)] = None
    return out


def _row_expr(name: str, source: str) -> dict:
    """A measure's row expression (a column, or arithmetic over columns) as EXPR."""
    try:
        tree = ast.parse(str(source), mode="eval").body
    except SyntaxError:
        raise _Fixed(f"measure '{name}': expression {source!r} does not parse")
    return _arith(name, source, tree, lambda n: {"col": n})


def _measure_expr(name: str, expr: str) -> dict:
    return _arith(name, expr, _combine_tree(name, expr), lambda n: {"ref": n})


def _arith(name: str, text: str, node: ast.AST, leaf) -> dict:
    if isinstance(node, ast.Name):
        return leaf(node.id)
    if (isinstance(node, ast.Constant) and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)):
        return {"num": node.value}
    if isinstance(node, ast.BinOp) and type(node.op) in _ARITH:
        return {"op": _ARITH[type(node.op)],
                "args": [_arith(name, text, node.left, leaf),
                         _arith(name, text, node.right, leaf)]}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return {"op": "neg", "args": [_arith(name, text, node.operand, leaf)]}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _arith(name, text, node.operand, leaf)
    what = type(node.op).__name__ if isinstance(node, (ast.BinOp, ast.UnaryOp)) \
        else type(node).__name__
    raise _Fixed(f"measure '{name}': expression {text!r} uses {what}, which the "
                 f"page engine does not compute (only + - * / and numbers)")


def _expr_columns(expr: dict) -> list[str]:
    if "col" in expr:
        return [expr["col"]]
    out: list[str] = []
    for arg in expr.get("args", ()):
        out += [c for c in _expr_columns(arg) if c not in out]
    return out


def _op_value(column: str, raw: Any) -> tuple[str, Any]:
    """The (op, value) of one condition, in the spellings filters accept."""
    if isinstance(raw, dict):
        if len(raw) != 1:
            raise _Fixed(f"condition on '{column}' must name exactly one operator")
        op, value = next(iter(raw.items()))
        op = str(op).lower()
    elif isinstance(raw, (list, tuple, set)):
        op, value = "in", list(raw)
    else:
        op, value = "eq", raw
    if op not in FILTER_OPS:
        raise _Fixed(f"condition on '{column}': unknown operator '{op}'")
    if op in ("in", "not_in"):
        value = list(value)
    if op == "between":
        value = list(value)
    return op, value


def _filter_tree(raw: dict, types: dict, why: str) -> dict:
    """A query's filter dict as the closed FILTER tree, every column checked."""
    children: list[dict] = []
    for key, val in raw.items():
        kl = str(key).lower()
        if kl in ("and", "or"):
            children.append({kl: [_filter_tree(sub, types, why) for sub in val]})
            continue
        if key not in types:
            raise _Fixed(f"the slice does not carry '{key}' ({why})")
        op, value = _op_value(key, val)
        if op == "contains" and (types[key] != "string"
                                 or any(w in str(value) for w in _WILDCARDS)):
            raise _Fixed(f"'contains' on '{key}' is recomputed only on a string "
                         f"column and without SQL wildcards")
        leaf = {"column": key, "op": op}
        if op not in ("is_null", "not_null"):
            leaf["value"] = value
        children.append(leaf)
    return children[0] if len(children) == 1 else {"and": children}


# ── Label arithmetic ─────────────────────────────────────────
# The one statement of how a time-grain label shifts and resets (the module
# docstring's "Label arithmetic"); engine.js ports these three functions.

_LABEL = {
    "year": re.compile(r"(\d{4})"),
    "quarter": re.compile(r"(\d{4})-Q([1-4])"),
    "month": re.compile(r"(\d{4})-(\d{2})"),
    "week": re.compile(r"(\d{4})-W(\d{2})"),
    "day": re.compile(r"(\d{4})-(\d{2})-(\d{2})"),
}
_MONTHS_PER = {"year": 12, "quarter": 3, "month": 1}


def label_start(label: str, grain: str) -> dt.date:
    """The date the period *label* names starts on."""
    match = _LABEL[grain].fullmatch(str(label))
    if match is None:
        raise ValueError(f"'{label}' is not a {grain} label")
    parts = [int(p) for p in match.groups()]
    if grain == "year":
        return dt.date(parts[0], 1, 1)
    if grain == "quarter":
        return dt.date(parts[0], 3 * parts[1] - 2, 1)
    if grain == "month":
        return dt.date(parts[0], parts[1], 1)
    if grain == "week":
        return dt.date.fromisocalendar(parts[0], parts[1], 1)
    return dt.date(*parts)


def grain_label(day: dt.date, grain: str) -> str:
    """The label of the *grain* period *day* falls in (``_grain_strings``)."""
    if grain == "year":
        return f"{day.year:04d}"
    if grain == "quarter":
        return f"{day.year:04d}-Q{(day.month - 1) // 3 + 1}"
    if grain == "month":
        return f"{day.year:04d}-{day.month:02d}"
    if grain == "week":
        iso = day.isocalendar()
        return f"{iso[0]:04d}-W{iso[1]:02d}"
    return day.isoformat()


def shift_label(label: str, grain: str, unit: str, n: int) -> Optional[str]:
    """The label *n* *unit* before *label*, or None when the shifted date
    does not start a period of *grain* (the row has no prior)."""
    start = label_start(label, grain)
    if unit in _MONTHS_PER:
        months = start.year * 12 + start.month - 1 - n * _MONTHS_PER[unit]
        year, month = months // 12, months % 12 + 1
        moved = dt.date(year, month,
                        min(start.day, calendar.monthrange(year, month)[1]))
    else:
        moved = start - dt.timedelta(days=n * (7 if unit == "week" else 1))
    out = grain_label(moved, grain)
    return out if label_start(out, grain) == moved else None


def reset_label(label: str, grain: str, period: str) -> str:
    """The *period* a to_date restarts in, for a *grain* label."""
    return grain_label(label_start(label, grain), period)


# ── The selection ────────────────────────────────────────────

def _condition(field: str, raw: Any) -> Any:
    """A selection condition, checked; None when it selects nothing."""
    if isinstance(raw, list):
        return list(raw) if raw else None
    if isinstance(raw, dict) and raw and set(raw) <= set(RANGE_OPS):
        return {op: raw[op] for op in RANGE_OPS if op in raw}
    raise ValueError(
        f"selection '{field}' must be a list of values or a range "
        f"{{'gte'|'gt': v, 'lte'|'lt': v}}, got {raw!r}")


def apply_selection(plan: dict, selection: Optional[dict]) -> dict:
    """*plan* with the page's *selection* composed onto it (decision 4).

    A field applies when the plan's slice carries that column; the applied
    fields land in ``plan["selection"]`` and AND with ``plan["filters"]``. A
    field the slice does not carry is listed in ``plan["unfiltered_by"]`` and
    changes nothing else. A fixed plan is returned as it is.
    """
    if "fixed" in plan:
        return plan
    applied: dict[str, Any] = {}
    unfiltered: list[str] = []
    for field in sorted(selection or {}):
        cond = _condition(field, selection[field])
        if cond is None:
            continue
        if field in plan["slice_columns"]:
            applied[field] = cond
        else:
            unfiltered.append(field)
    return {**plan, "selection": applied, "unfiltered_by": unfiltered}


def selection_filters(selection: dict) -> list[dict]:
    """An applied selection as ``DataModel`` filter groups, one per bound."""
    groups: list[dict] = []
    for field, cond in selection.items():
        if isinstance(cond, list):
            groups.append({field: {"in": list(cond)}})
        else:
            groups += [{field: {op: cond[op]}} for op in RANGE_OPS if op in cond]
    return groups


def selection_query(query: QuerySpec, plan: dict) -> QuerySpec:
    """The server's equivalent of a plan under its applied selection: *query*
    with the selection ANDed onto its own filters. What ``DataModel.execute``
    runs to say what the page should have computed."""
    groups = selection_filters(plan.get("selection") or {})
    if not groups:
        return query
    if query.filters:
        groups.insert(0, dict(query.filters))
    filters = groups[0] if len(groups) == 1 else {"and": groups}
    return dataclasses.replace(query, filters=filters)


# ── Python's reading of a plan ───────────────────────────────

def execute_plan(plan: dict, frame: pd.DataFrame,
                 selection: Optional[dict] = None) -> pd.DataFrame:
    """Run *plan* over the slice *frame* through ``DataModel.execute``.

    The slice becomes a one-fact model (each ``<dim>.<attr>`` column a
    dimension attribute), every plan step becomes the measure kind that
    defines it, and DuckDB answers. This is the plan's meaning on the server:
    the parity fixtures and the build check a page engine against it.
    """
    if "fixed" in plan:
        raise ValueError(f"a fixed plan has nothing to run: {plan['fixed']}")
    applied = apply_selection(plan, selection or {})
    from tracebi import DataModel, MemoryConnector

    df = frame.reset_index(drop=True).copy()
    df["__row"] = range(len(df))
    dims: dict[str, list[str]] = {}
    for col in df.columns:
        if "." in str(col):
            dim, attr = str(col).split(".", 1)
            dims.setdefault(dim, []).append(attr)
    fact_cols = [c for c in df.columns if "." not in str(c)]
    tables = {"slice": df[fact_cols]}
    for dim, attrs in dims.items():
        tables[f"dim/{dim}"] = df[["__row"] + [f"{dim}.{a}" for a in attrs]].rename(
            columns={f"{dim}.{a}": a for a in attrs})
    # pops and to_dates need DataModel's own time axis: the labels' start
    # dates, declared as a time grain on a dimension of their own. The label
    # column stays a plain attribute, so a selection still filters it; the
    # query groups by the time grain in its place and the result is spelled
    # back as labels.
    time_grain = plan.get("time_grain")
    time_alias = "__time.period"
    if time_grain:
        tables["dim/__time"] = pd.DataFrame({
            "__row": df["__row"],
            "start": pd.to_datetime([
                None if v is None or (not isinstance(v, str) and pd.isna(v))
                else label_start(v, time_grain["grain"])
                for v in df[time_grain["column"]]])})
    model = DataModel("calc_slice")
    model.add_connector(MemoryConnector("calc_slice", tables=tables))
    for table in tables:
        model.add_table(table, connector="calc_slice", source=table)
    for dim, attrs in dims.items():
        model.add_dimension(dim, table_name=f"dim/{dim}", key_col="__row",
                            attributes=attrs)
    keys = {dim: "__row" for dim in dims}
    if time_grain:
        model.add_dimension("__time", table_name="dim/__time", key_col="__row",
                            attributes=["start"])
        model.add_time_grain("__time", "period", source="start",
                             grain=time_grain["grain"])
        keys["__time"] = "__row"
    model.add_fact(plan["fact"], table_name="slice",
                   measures=[c for c in fact_cols if c != "__row"],
                   foreign_keys=keys)

    if plan.get("raw"):
        model.connect()
        measures = {}
        for p in plan["project"]:
            src = p["source"]
            measures[p["name"]] = ("sum" if src.get("col") == p["name"]
                                   else {"expr": _render(src), "agg": "sum"})
        spec = QuerySpec(
            fact=plan["fact"], measures=measures,
            dimensions=tuple(plan["group_by"]),
            filters=_filter_dict(plan["filters"]) if plan["filters"] else None,
            aggregate=False, allow_rate_agg=True,
            order_by=tuple(plan["order_by"]), limit=plan["limit"])
        return model.execute(selection_query(spec, applied)).to_pandas()[
            plan["columns"]]

    trusted = {"allow_rate_agg": True, "allow_additive": True}
    for agg in plan["aggregates"]:
        func = agg["func"]
        if func == "quantile":
            func = f"p{round(agg['q'] * 100)}"
        elif func == "sum_counts":
            func = "sum"
        src = agg["source"]
        spec = ({"column": src["col"]} if "col" in src
                else {"expr": _render(src)})
        if agg.get("where"):
            spec["filters"] = _filter_dict(agg["where"])
        model.add_measure(agg["name"], agg=func, **spec, **trusted)
    for m in plan["means"]:
        model.add_measure(m["name"], ratio=(m["sum"], m["count"]))
    for r in plan["ratios"]:
        model.add_measure(r["name"], ratio=(r["num"], r["den"]))
    for s in plan["shares"]:
        model.add_measure(s["name"], share=s["base"])
    for c in plan["combines"]:
        model.add_measure(c["name"], measure_expr=_render(c["expr"]))
    for p in plan.get("period_ends", ()):
        model.add_measure(p["name"], period_end=(p["value"], p["date"]))

    # On the time axis the query reads the declared grain, not the label.
    def axis(column: str) -> str:
        return time_alias if time_grain and column == time_grain["column"] else column

    for kind in ("ranks", "runnings"):
        for w in plan[kind]:
            model.add_measure(w["name"], **{kind[:-1]: w["base"]},
                              partition_by=[axis(c) for c in w["partition_by"]]
                              or None)
    for p in plan.get("pops", ()):
        model.add_measure(p["name"], **{"offset" if p["mode"] == "value"
                                        else "growth": (p["base"], p["unit"], p["n"])})
    for t in plan.get("to_dates", ()):
        model.add_measure(t["name"], to_date=(t["base"], t["period"]))
    model.connect()

    group_by = plan["group_by"]
    spec = QuerySpec(
        fact=plan["fact"],
        measures=[c for c in plan["columns"] if c not in group_by],
        dimensions=tuple(axis(c) for c in group_by),
        filters=_filter_dict(plan["filters"]) if plan["filters"] else None,
        having={h["column"]: {h["op"]: h.get("value", True)}
                for h in plan["having"]} or None,
        allow_rate_agg=True,
        order_by=tuple({**o, "column": axis(o["column"])} for o in plan["order_by"]),
        limit=plan["limit"],
    )
    out = model.execute(selection_query(spec, applied)).to_pandas()
    if time_grain:
        # DataModel returns the grain as its period label, the slice's own
        # spelling, so the axis column goes back under its slice name as is.
        out[time_grain["column"]] = out.pop(time_alias)
    out = out[plan["columns"]]
    for agg in plan["aggregates"]:
        # A re-aggregated count keeps COUNT's zero over no rows; SUM gives null.
        if agg["func"] == "sum_counts" and agg["name"] in out.columns:
            out[agg["name"]] = out[agg["name"]].fillna(0)
    return out


def _render(expr: dict) -> str:
    """EXPR back to the arithmetic text a measure declares."""
    if "col" in expr:
        return expr["col"]
    if "ref" in expr:
        return expr["ref"]
    if "num" in expr:
        return repr(expr["num"])
    args = [_render(a) for a in expr["args"]]
    if expr["op"] == "neg":
        return f"(-{args[0]})"
    return f"({args[0]} {expr['op']} {args[1]})"


def _filter_dict(tree: dict) -> dict:
    """A FILTER tree back to the filter dict ``DataModel`` parses."""
    for group in ("and", "or"):
        if group in tree:
            return {group: [_filter_dict(t) for t in tree[group]]}
    return {tree["column"]: {tree["op"]: tree.get("value", True)}}


def slice_frame(columns: Sequence[Mapping], rows: Sequence[Sequence]) -> pd.DataFrame:
    """A slice as a frame from its JSON form (``{"name", "type"}`` columns and
    row arrays), with ``number`` columns numeric and ``datetime`` ones parsed."""
    names = [c["name"] for c in columns]
    frame = pd.DataFrame([list(r) for r in rows], columns=names)
    for col in columns:
        if col.get("type") == "number":
            frame[col["name"]] = pd.to_numeric(frame[col["name"]])
        elif col.get("type") == "datetime":
            frame[col["name"]] = pd.to_datetime(frame[col["name"]])
    return frame


# ── Comparing two engines' answers ───────────────────────────

def _cells(result) -> "tuple[list, list]":
    if isinstance(result, pd.DataFrame):
        return ([str(c) for c in result.columns],
                [list(r) for r in result.itertuples(index=False, name=None)])
    return [str(c) for c in result["cols"]], [list(r) for r in result["rows"]]


def _number(value) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def first_mismatch(a, b, rel: float = 1e-9) -> Optional[dict]:
    """Where two results of one plan first differ, or ``None`` when they match.

    *a* and *b* are frames or ``{"cols", "rows"}`` (rows as lists, in column
    order). The columns must be the same, in the same order, and so must the
    rows, compared in order since the order is part of the answer. Two cells
    match when they are equal after :func:`~tracebi.model.dataset.canonical_cell`
    (nine significant digits; every null alike), or when both are numbers
    within *rel* of each other (within *rel* absolutely near zero). The
    rounded fingerprint alone is not enough between two engines: a correct
    sum can sit an ulp either side of a nine-digit rounding boundary
    (``CALC_NOTICE.md``), and then the two round apart.
    """
    from tracebi.model.dataset import canonical_cell

    cols_a, rows_a = _cells(a)
    cols_b, rows_b = _cells(b)
    if cols_a != cols_b:
        return {"row": None, "column": None, "left": cols_a, "right": cols_b,
                "detail": "the columns differ"}
    if len(rows_a) != len(rows_b):
        return {"row": None, "column": None, "left": len(rows_a),
                "right": len(rows_b), "detail": "the row counts differ"}
    for i, (ra, rb) in enumerate(zip(rows_a, rows_b)):
        for col, x, y in zip(cols_a, ra, rb):
            if canonical_cell(x) == canonical_cell(y):
                continue
            nx, ny = _number(x), _number(y)
            if (nx is not None and ny is not None
                    and abs(nx - ny) <= max(rel * max(abs(nx), abs(ny)), rel)):
                continue
            return {"row": i, "column": col, "left": x, "right": y,
                    "detail": f"row {i}, column '{col}': {x!r} against {y!r}"}
    return None


def rows_match(a, b, rel: float = 1e-9) -> bool:
    """Whether two results of one plan agree, by :func:`first_mismatch`'s rule."""
    return first_mismatch(a, b, rel) is None
