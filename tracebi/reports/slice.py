"""The slice: what a built report carries so its page can recompute.

A live page filters, groups, sums and divides in the browser
(``docs/architecture/live-reports-plan.md``, decisions 2 and 8). It does that
over the **slice**: per fact, one table the build computes with the model's own
engine, embedded as one Parquet block. This module derives the slice's grain,
runs the one query per fact that produces it, and encodes the block. It never
computes a figure's number; the number is still a query result, run by the
page engine over these rows with the binding's calc plan.

**The grain derivation rule.** For each fact a page reads, the required grain
is the union of every dimension attribute the page could group or filter that
fact by: each binding's ``dimensions``; the dimension attributes each binding
filters on; every rank or running measure's ``partition_by``; the column of
every filter control on the page (``data-tb-filter`` in a template, ``<Filter
column=...>`` in an app.jsx) when the fact reaches that dimension through a
declared foreign key; and every dimension attribute the authored ``selection``
block filters. A time grain or a value bin is a dimension attribute like any
other, so it lands in the grain when the page names it. The slice groups the
fact by that grain with no filter at all, so every predicate the page applies
later (a binding's own filters, the reader's selection) is applied by the
engine to these rows, never baked in.

A fact is kept at its **base grain** (one row per fact row, nothing
aggregated) when a measure the page uses cannot be recombined from grain rows:
``nunique``, ``median``, ``stddev`` and percentiles (``p<N>``), and a measure
over a row expression (``expr``), whose arithmetic the engine evaluates on the
fact's own columns. A binding that filters on a raw fact column also keeps its
fact at base grain, because a grain is made of dimension attributes and that
column must survive for the filter to apply, and so does a raw-row binding
(``aggregate=False``), which lists the fact's own rows. Otherwise every measure is
additive at the grain: ``sum``, ``count``, ``min`` and ``max`` are aggregated
to it as the parts ``<measure>:sum``, ``<measure>:count``, ``<measure>:min``
and ``<measure>:max``, which re-aggregate with ``sum``, ``sum``, ``min`` and
``max``; a ``mean`` is stored as ``<measure>:sum`` and ``<measure>:count``, so
the page divides after it filters and an average is recomputed, never
averaged. Parts are keyed by the measure's output name, so two bindings that
give one name two definitions keep the fact at base grain.
A ``period_end`` measure puts its snapshot date attribute into the grain and
is stored as ``<measure>:sum``, its value column summed at that grain: the
page groups those rows by the query's dimensions and the date, finds each
group's latest date, and sums there. Ratios, shares, ranks, runnings,
calculated combinations, ``offset`` / ``growth`` and ``to_date`` are computed
after aggregation, so they add nothing to the slice beyond the measures they
read; the time grain an offset or a to_date runs along is one of its
binding's dimensions, so it is in the grain like any other.

**What the slice holds.** Grain columns are named as the query names them,
``dim.attribute``, which is also how the selection state names a field: a
selected field applies to a fact exactly when that fact's slice carries the
column. Time grains are strings (``2026``, ``2026-Q1``, ``2026-03``,
``2026-W09``, ``2026-03-14``), value bins their labels. A bare name is a fact
column at base grain: on a base-grain slice the fact's raw columns that the
page's measures and filters read sit beside the grain columns under their fact
column names. On an aggregated slice every measure column is a
``<measure>:<part>`` (its own filters already applied), never a bare name, so
it cannot be mistaken for a fact column. This is the naming
``tracebi/reports/calc_plan.py`` compiles plans against ("The slice a plan
reads"). A slice holds only numbers, booleans, strings and naive datetimes;
any other type fails the build by column name, because the page engine would
show it differently from the server. Column types are recorded as
``number``, ``boolean``, ``string`` or ``datetime``.

**What contributes nothing.** A ``{"model", "sql"}`` binding and a
``report.py`` output have no query the engine can re-run, so they stay fixed at
build and widen no grain.

``report.json`` chooses how much is embedded: ``"embed": "required"`` (the
default) embeds the grain above, ``"model"`` every fact the page reads at base
grain with every dimension attribute it reaches, and ``"none"`` nothing new,
so the page behaves as it did before slices existed. ``"embed_budget_mb"``
(default 25) caps the slice blocks' size in the page; past it the build fails
and names the fix.
"""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, field

import pandas as pd

EMBED_REQUIRED = "required"
EMBED_MODEL = "model"
EMBED_NONE = "none"
EMBED_MODES = (EMBED_REQUIRED, EMBED_MODEL, EMBED_NONE)
DEFAULT_EMBED_BUDGET_MB = 25

#: Element id prefix of a slice block, and the id of the calc payload.
SLICE_ID_PREFIX = "tracebi-slice-"
CALC_PLANS_ID = "tracebi-calc-plans"

#: Aggregations a grain row cannot be recombined from.
_BASE_GRAIN_AGGS = {"nunique", "median", "stddev"}
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PERCENTILE = re.compile(r"^p\d{1,3}$")
_SLICE_MEASURE = "slice__"


class SliceError(ValueError):
    """The build cannot embed a slice; the message names the fix."""


@dataclass(frozen=True)
class SliceBlock:
    """One fact's slice, encoded once: the bytes shipped are the bytes hashed."""

    key: str
    model: str
    fact: str
    grain: list
    base_grain: bool
    reason: str
    frame: pd.DataFrame = field(repr=False)
    columns: list
    parquet: bytes = field(repr=False)
    payload_sha256: str
    bindings: list

    @property
    def block_id(self) -> str:
        return SLICE_ID_PREFIX + self.key

    def block_html(self) -> str:
        """The page block: the same carrier as a Parquet data block. The id
        prefix keeps it out of the runtime's and verify's ``tracebi-data-``
        scans; the manifest's ``slice`` entry records its hash."""
        from tracebi.reports.embed import embed_json

        return embed_json({
            "name": self.key,
            "format": "parquet",
            "parquet_b64": base64.b64encode(self.parquet).decode("ascii"),
            "payload_sha256": self.payload_sha256,
        }, self.block_id)

    def manifest_record(self, embed: str) -> dict:
        return {
            "block": self.block_id,
            "model": self.model,
            "fact": self.fact,
            "grain": list(self.grain),
            "base_grain": self.base_grain,
            "reason": self.reason,
            "columns": [dict(c) for c in self.columns],
            "rows": int(len(self.frame)),
            "payload_sha256": self.payload_sha256,
            "embed": embed,
            "bindings": list(self.bindings),
        }


# ── Controls ─────────────────────────────────────────────────────────────────

def page_controls(package) -> list[dict]:
    """Every filter control on the page: ``[{"column", "binding"}]``.

    A template's ``data-tb-filter`` elements are read from its source; an
    app.jsx's ``<Filter>`` tags from its source too (the kit renders them at
    runtime, so the shell holds none). A ``<Search>`` names no column: it
    narrows the rows shown, it does not cut a fact, so it is not a control
    here.
    """
    if package.app_source is not None:
        from tracebi.reports.app_lane import scan_controls
        pairs = scan_controls(package.app_source)
    else:
        from tracebi.reports.selection import filter_controls
        pairs = filter_controls(package.template_html)
    out: list[dict] = []
    for binding, column in pairs:
        entry = {"column": column, "binding": binding}
        if entry not in out:
            out.append(entry)
    return out


# ── The grain ────────────────────────────────────────────────────────────────

def _add(seq: list, item) -> None:
    if item not in seq:
        seq.append(item)


def _reaches(model, fact_def, column: str) -> bool:
    """Whether *column* (``dim.attr``) is a dimension attribute this fact
    reaches through a declared foreign key."""
    dim, dot, attr = str(column).partition(".")
    if not dot:
        return False
    dim_def = model._dimensions.get(dim)
    if dim_def is None or dim not in fact_def.foreign_keys:
        return False
    return attr in dim_def.attributes or attr in dim_def.derived


def _grain_for(package, model_key: str, model, controls: list[dict]) -> dict:
    """``required_grain`` for the bindings of one model (see the module
    docstring for the rule). Besides ``dimensions``, ``base_grain`` and
    ``reason``, each fact carries the bindings it serves and, for
    :func:`build_slice`, the measures to aggregate (``leaves``) and the raw
    fact columns a base-grain slice keeps (``raw``)."""
    from tracebi.model.data_model import _filter_columns
    from tracebi.model.sql_calc import SqlQuery

    facts: dict[str, dict] = {}
    for name, ref in package.bindings.items():
        if ref.model != model_key or isinstance(ref.query, SqlQuery):
            continue
        query = ref.query
        view = model.with_measures(query.calculated) if query.calculated else model
        fact_def = view._facts.get(query.fact)
        if fact_def is None:
            continue
        resolved = view._resolve_measures(query.measures, fact_def)
        entry = facts.setdefault(query.fact, {
            "dimensions": [], "base_grain": False, "reason": "",
            "bindings": [], "leaves": {}, "raw": [],
        })

        def base(why: str) -> None:
            if not entry["base_grain"]:
                entry["base_grain"], entry["reason"] = True, why

        entry["bindings"].append(name)
        if not query.aggregate:
            base(f"binding '{name}' lists raw rows")
        for dim in query.dimensions or ():
            _add(entry["dimensions"], str(dim))
        for column in sorted(_filter_columns(query.filters or {})):
            if "." in column:
                _add(entry["dimensions"], column)
            else:
                _add(entry["raw"], column)
                base(f"binding '{name}' filters on fact column '{column}'")
        for part in resolved.partitions.values():
            for dim in part:
                _add(entry["dimensions"], str(dim))
        for out, func in resolved.agg_map.items():
            func = str(func).lower()
            source = resolved.derived.get(out, out)
            filters = resolved.filtered.get(out)
            leaf = {"func": "mean" if func == "avg" else func,
                    "source": source, "filters": filters}
            if entry["leaves"].setdefault(out, leaf) != leaf:
                base(f"measure '{out}' is defined two ways")
            for token in _IDENT.findall(str(source)):
                _add(entry["raw"], token)
            for column in sorted(_filter_columns(filters or {})):
                _add(entry["raw"], column)
            if func in _BASE_GRAIN_AGGS or _PERCENTILE.match(func):
                base(f"measure '{out}' is {func}")
            elif not _IDENT.fullmatch(str(source)):
                base(f"measure '{out}' is a row expression")
        for out, (value_col, date_ref) in resolved.period_ends.items():
            # The value summed at a grain that includes the snapshot date, so
            # the page can find each group's latest date and sum at it.
            _add(entry["dimensions"], str(date_ref))
            leaf = {"func": "sum", "source": value_col, "filters": None}
            if entry["leaves"].setdefault(out, leaf) != leaf:
                base(f"measure '{out}' is defined two ways")
            _add(entry["raw"], value_col)

    selected = []
    selection = getattr(package, "selection", None)
    if selection and selection.get("model") == model_key:
        selected = [k for k in sorted(_filter_columns(selection["filters"]))
                    if "." in k]
    for fact, entry in facts.items():
        fact_def = model._facts[fact]
        for column in [c["column"] for c in controls] + selected:
            if _reaches(model, fact_def, column):
                _add(entry["dimensions"], column)
        if not entry["base_grain"]:
            entry["reason"] = "every measure is additive at the grain"
    return facts


def required_grain(package, model) -> dict:
    """Per fact of *model* that *package* reads: ``{fact: {"dimensions": [...],
    "base_grain": bool, "reason": str, ...}}``. The rule is the module
    docstring's."""
    return _grain_for(package, model.name, model, page_controls(package))


def _model_grain(package, model_key: str, model) -> dict:
    """``embed: model``: every fact the page reads, at base grain, with every
    attribute of every dimension it reaches and every raw fact column."""
    from tracebi.model.sql_calc import SqlQuery

    facts: dict[str, dict] = {}
    for name, ref in package.bindings.items():
        if ref.model != model_key or isinstance(ref.query, SqlQuery):
            continue
        fact_def = model._facts.get(ref.query.fact)
        if fact_def is None:
            continue
        entry = facts.get(ref.query.fact)
        if entry is None:
            dims = []
            for dim in fact_def.foreign_keys:
                dim_def = model._dimensions.get(dim)
                if dim_def is None:
                    continue
                for attr in list(dim_def.attributes) + list(dim_def.derived):
                    _add(dims, f"{dim}.{attr}")
            keys = set(fact_def.foreign_keys.values())
            frame = model.load(fact_def.table_name).to_pandas()
            entry = facts[ref.query.fact] = {
                "dimensions": dims, "base_grain": True,
                "reason": "embed: model", "bindings": [], "leaves": {},
                "raw": [str(c) for c in frame.columns if c not in keys],
            }
        entry["bindings"].append(name)
    return facts


# ── The query ────────────────────────────────────────────────────────────────

def _slice_query(fact: str, grain: dict):
    """The ONE query that produces a fact's slice, as a QuerySpec, plus the
    renames from the query's output names to the slice's column names.

    Aggregated: each additive leaf becomes a measure this query declares for
    itself (``calculated``), named ``slice__<measure>__<part>`` because a
    report's own measure may not shadow the model's; the rename gives it its
    slice name, ``<measure>:<part>``. ``allow_rate_agg`` and
    ``allow_additive`` are set because the slice re-expresses measures the
    model already accepted (a mean's ``:sum`` part is never shown, and a
    period_end's balance is summed only within one snapshot date, since the
    date is in the grain).
    Base grain: the raw fact columns, unaggregated."""
    from tracebi.model.data_model import QuerySpec

    dims = tuple(grain["dimensions"])
    if grain["base_grain"]:
        return QuerySpec(fact=fact, measures={c: "sum" for c in grain["raw"]},
                         dimensions=dims, aggregate=False,
                         allow_rate_agg=True), {}
    calculated: dict[str, dict] = {}
    renames: dict[str, str] = {}

    def part(out: str, source: str, agg: str, filters) -> None:
        definition = {"column": source, "agg": agg, "allow_rate_agg": True,
                      "allow_additive": True}
        if filters:
            definition["filters"] = dict(filters)
        name = f"{_SLICE_MEASURE}{out}__{agg}"
        calculated[name] = definition
        renames[name] = f"{out}:{agg}"

    for out, leaf in grain["leaves"].items():
        for agg in (("sum", "count") if leaf["func"] == "mean" else (leaf["func"],)):
            part(out, leaf["source"], agg, leaf["filters"])
    return QuerySpec(fact=fact, measures=list(calculated), dimensions=dims,
                     aggregate=True, allow_rate_agg=True,
                     calculated=calculated), renames


def _grain_strings(model, frame: pd.DataFrame) -> pd.DataFrame:
    """Time grains and bins as strings, so the page groups and compares
    them as text (decision 8)."""
    from tracebi.model.data_model import time_grain_labels

    out = frame.copy()
    for column in frame.columns:
        dim, dot, attr = str(column).partition(".")
        derived = (model._dimensions[dim].derived.get(attr)
                   if dot and dim in model._dimensions else None)
        if not derived:
            continue
        series = frame[column]
        if derived["kind"] == "bin":
            out[column] = series.astype(object).where(series.notna(), None)
            continue
        # DataModel already returns a time grain as its labels; one rule.
        out[column] = time_grain_labels(series, derived["grain"])
    return out


def _column_type(frame: pd.DataFrame, column: str, where: str) -> str:
    """A slice column's type, or the build error naming it and the fix."""
    series = frame[column]
    dtype = series.dtype
    kind = getattr(dtype, "kind", "")
    if kind == "b":
        return "boolean"
    if kind in "iuf":
        return "number"
    if kind == "M" and getattr(dtype, "tz", None) is None:
        return "datetime"
    if kind in ("O", "U", "T") or str(dtype) in ("string", "str"):
        values = series.dropna()
        if all(isinstance(v, str) for v in values):
            return "string"
        if len(values) and all(isinstance(v, bool) for v in values):
            return "boolean"
    raise SliceError(
        f"{where}: slice column '{column}' is {dtype}, which a slice cannot "
        f"carry (numbers, booleans, strings and naive datetimes only; the page "
        f"engine would show anything else differently from the server). Cast "
        f"it to one of those in the transform, or set \"embed\": \"none\" in "
        f"report.json to keep this page's figures fixed at build.")


def _encode(frame: pd.DataFrame) -> bytes:
    from tracebi.reports.parquet_embed import to_parquet_bytes

    # Snappy pages: what the page's pure-JS reader decodes natively.
    return to_parquet_bytes(frame, compression="snappy")


def _run(package, model_key: str, model, fact: str, grain: dict, key: str) -> SliceBlock:
    where = f"Package '{package.name}', fact '{fact}'"
    query, renames = _slice_query(fact, grain)
    frame = model.execute(query).to_pandas().rename(columns=renames)
    frame = _grain_strings(model, frame)
    columns = [{"name": str(c), "type": _column_type(frame, c, where)}
               for c in frame.columns]
    if grain["base_grain"]:
        # Raw rows come back in scan order; sort them so the same warehouse
        # always ships the same bytes.
        frame = frame.sort_values(list(frame.columns), kind="mergesort",
                                  na_position="last").reset_index(drop=True)
    raw = _encode(frame)
    return SliceBlock(
        key=key, model=model_key, fact=fact, grain=list(grain["dimensions"]),
        base_grain=bool(grain["base_grain"]), reason=grain["reason"],
        frame=frame, columns=columns, parquet=raw,
        payload_sha256=hashlib.sha256(raw).hexdigest(),
        bindings=list(grain["bindings"]),
    )


def build_slice(package, models: dict) -> dict:
    """``{fact: SliceBlock}`` for every fact the page reads, per the
    package's ``embed`` setting; ``{}`` for ``embed: none``. One DuckDB query
    per fact, through ``DataModel.execute``, so each slice carries the model's
    lineage. Fails naming the fix when the blocks pass ``embed_budget_mb``."""
    embed = getattr(package, "embed", EMBED_REQUIRED)
    if embed == EMBED_NONE:
        return {}
    controls = page_controls(package)
    blocks: dict[str, SliceBlock] = {}
    for model_key in dict.fromkeys(ref.model for ref in package.bindings.values()):
        model = models[model_key]
        grains = (_model_grain(package, model_key, model) if embed == EMBED_MODEL
                  else _grain_for(package, model_key, model, controls))
        for fact, grain in grains.items():
            key = fact if fact not in blocks else f"{model_key}.{fact}"
            blocks[key] = _run(package, model_key, model, fact, grain, key)
    budget = float(getattr(package, "embed_budget_mb", DEFAULT_EMBED_BUDGET_MB))
    size = sum((len(b.parquet) + 2) // 3 * 4 for b in blocks.values())
    if size > budget * 1024 * 1024:
        widest = max(blocks.values(), key=lambda b: len(b.parquet))
        raise SliceError(
            f"Package '{package.name}': the embedded slice is "
            f"{size / 1024 / 1024:.1f} MB, over \"embed_budget_mb\": {budget:g}. "
            f"The largest is '{widest.key}' ({len(widest.frame):,} rows, "
            f"{'base grain: ' + widest.reason if widest.base_grain else 'grain ' + ', '.join(widest.grain)}). "
            f"Coarsen it (remove a filter control or a dimension the page "
            f"groups by), raise \"embed_budget_mb\", or set \"embed\": "
            f"\"none\" in report.json to keep this page's figures fixed at "
            f"build.")
    return blocks


# ── Plans ────────────────────────────────────────────────────────────────────

def _plan_for(model, query, slice_columns) -> dict:
    """A binding's calc plan from ``tracebi.reports.calc_plan``, or
    ``{"fixed": reason}``: the compiler's own reason, or why it refused."""
    from tracebi.reports.calc_plan import compile_plan

    try:
        return compile_plan(model, query, slice_columns)
    except Exception as exc:  # noqa: BLE001 — a refused plan is fixed, with why
        return {"fixed": f"plan refused: {exc}"}


def binding_plans(package, models: dict, blocks: dict,
                  outputs=()) -> dict:
    """Every binding's plan, by name: a SQL binding and a ``report.py``
    output are fixed by construction; the rest compile against the columns
    (with their types) of their fact's slice. A fact with no slice is
    passed as an empty one, so the compiler names what is missing."""
    from tracebi.model.sql_calc import SqlQuery

    columns = {(b.model, b.fact): [dict(c) for c in b.columns]
               for b in blocks.values()}
    plans: dict[str, dict] = {}
    for name, ref in package.bindings.items():
        if isinstance(ref.query, SqlQuery):
            plans[name] = {"fixed": "sql binding"}
            continue
        plans[name] = _plan_for(models[ref.model], ref.query,
                                columns.get((ref.model, ref.query.fact), []))
    for name in outputs:
        plans[name] = {"fixed": "report.py"}
    return plans


def calc_plans_payload(package, models: dict, blocks: dict, plans: dict) -> dict:
    """The ``tracebi-calc-plans`` block: what the page engine needs besides
    the slice blocks, and nothing about the model beyond its label."""
    labels = package.model_labels(models)
    selection = getattr(package, "selection", None)
    return {
        "model_label": " · ".join(labels),
        "facts": {
            key: {"block": b.block_id, "model": b.model, "fact": b.fact,
                  "columns": [dict(c) for c in b.columns],
                  "grain": list(b.grain), "base_grain": b.base_grain}
            for key, b in blocks.items()
        },
        "bindings": plans,
        "controls": page_controls(package),
        "authored_selection": dict(selection["filters"]) if selection else {},
    }
