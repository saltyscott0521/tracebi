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
back to the base-grain fact columns. ``nunique`` and percentiles need base
grain. A column the plan needs that the slice does not carry makes the plan
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
     "columns": [str]}               # the result, in DataModel.execute's order

The engine runs it in this order, and every step is exactly what
``DataModel.execute`` does:

1. **Filter** the slice rows: ``filters`` AND the applied ``selection``
   (added by :func:`apply_selection`). SQL rules: a predicate on a null cell
   is false, except ``is_null``.
2. **Group** by ``group_by``. With no group columns the result is always
   exactly one row, even when no rows passed the filter.
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

4. **means**: ``name = sum / count``, null when count is 0 or either is null.
5. **ratios**: ``name = num / den`` over the aggregated columns, null when
   den is 0 or either is null.
6. **shares**: ``name = base / total``, where total is the sum of base over
   every result row (nulls skipped); null for every row when total is 0.
7. **combines**: ``EXPR`` over aggregated columns (``{"ref": name}``); a
   division by zero is null.
8. **ranks**, then **runnings**: order the rows by ``partition_by``
   ascending, then ``base`` descending, then every other group column
   ascending in ``group_by`` order (nulls last in each key). A rank is the
   1-based position within its partition; a running is the cumulative sum of
   ``base`` within its partition in that order (a null base gives null at its
   row and adds nothing).
9. **having**: keep rows where every condition holds. pandas rules, unlike
   ``filters``: ``ne`` and ``not_in`` keep a null cell, every other
   comparison drops it.
10. **order_by**: a stable sort by the listed keys, nulls last in each. The
    compiler already appended the group columns as the tie-break, and with
    no ``order_by`` on the query the list is the group columns ascending
    (DuckDB's ``ORDER BY`` of the groups).
11. **limit**: the first ``limit`` rows.
12. **columns**: project to these, dropping parts the plan made for itself
    (a ``mean``'s ``<m>:sum`` / ``<m>:count``).

Strings compare by Unicode code point (DuckDB's byte order on UTF-8, and
Python's); ``false`` sorts before ``true``.

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
import dataclasses
from typing import Any, Mapping, Optional, Sequence

import pandas as pd

from tracebi.model.data_model import (
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
    if not query.aggregate:
        raise _Fixed("a raw-row query (aggregate=False) is not recomputed on the "
                      "page this round")
    try:
        view = model.with_measures(query.calculated) if query.calculated else model
        resolved = view._resolve_measures(query.measures, view._facts[fact])
    except KeyError:
        raise _Fixed(f"fact '{fact}' is not declared on model '{model.name}'")
    except ValueError as exc:
        raise _Fixed(f"the query does not resolve: {exc}")
    for bucket, kind in (("period_ends", "period_end"), ("pops", "offset/growth"),
                         ("to_dates", "to_date")):
        names = sorted(getattr(resolved, bucket))
        if names:
            raise _Fixed(f"{kind} measure(s) {names} are not recomputed on the "
                         f"page this round")

    def need(column: str, why: str) -> None:
        if column not in types:
            raise _Fixed(f"the slice for '{fact}' does not carry '{column}' "
                         f"({why})")

    group_by = list(query.dimensions or ())
    for dim in group_by:
        need(dim, "a group column")

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
        elif func in ("sum", "count", "min", "max", "nunique"):
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

    columns = (group_by + list(resolved.agg_map) + list(resolved.ratios)
               + list(resolved.shares) + list(resolved.combines)
               + list(resolved.ranks) + list(resolved.runnings))
    order_by = [dict(o) for o in (query.order_by or ())]
    for o in order_by:
        if o["column"] not in columns:
            raise _Fixed(f"order_by column '{o['column']}' is not a result column")
    named = {o["column"] for o in order_by}
    order_by += [{"column": d, "desc": False} for d in group_by if d not in named]

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
    model = DataModel("calc_slice")
    model.add_connector(MemoryConnector("calc_slice", tables=tables))
    for table in tables:
        model.add_table(table, connector="calc_slice", source=table)
    for dim, attrs in dims.items():
        model.add_dimension(dim, table_name=f"dim/{dim}", key_col="__row",
                            attributes=attrs)
    model.add_fact(plan["fact"], table_name="slice",
                   measures=[c for c in fact_cols if c != "__row"],
                   foreign_keys={dim: "__row" for dim in dims})

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
    for kind in ("ranks", "runnings"):
        for w in plan[kind]:
            model.add_measure(w["name"], **{kind[:-1]: w["base"]},
                              partition_by=w["partition_by"] or None)
    model.connect()

    group_by = plan["group_by"]
    spec = QuerySpec(
        fact=plan["fact"],
        measures=[c for c in plan["columns"] if c not in group_by],
        dimensions=tuple(group_by),
        filters=_filter_dict(plan["filters"]) if plan["filters"] else None,
        having={h["column"]: {h["op"]: h.get("value", True)}
                for h in plan["having"]} or None,
        allow_rate_agg=True,
        order_by=tuple(plan["order_by"]),
        limit=plan["limit"],
    )
    out = model.execute(selection_query(spec, applied)).to_pandas()
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
