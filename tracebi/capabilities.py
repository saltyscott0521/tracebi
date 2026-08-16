"""
A machine-readable description of what TraceBi can build.

``describe()`` returns the framework's vocabulary as plain data: every
report section with its fields, types, defaults and allowed values;
the DataSet verbs; the measure kinds, filter operators and
aggregations; and the file conventions that make a project discoverable.

Everything here is **generated** from dataclass fields and type
annotations rather than written by hand. That matters: the section
type → class → parameter mapping previously existed only in docstrings and
two hard-coded renderer dispatchers, so any hand-maintained copy would
drift the first time a field was added.

Intended consumers are tools rather than people — an agent authoring a
TraceBi project, an editor completing a section constructor, or a UI
building a form. Available as ``tracebi.capabilities.describe()``,
``tracebi context --json`` on the command line, and ``GET /api/schema``.

Importable on the base install: it reads class metadata and never touches
an optional dependency.
"""

from __future__ import annotations

import dataclasses
import inspect
import typing
from typing import Any, Optional

from tracebi._version import get_version

# Closed value domains, imported from where they are enforced so the two
# can never disagree.
from tracebi.model.data_model import _AGG_FUNCS, FILTER_OPS
from tracebi.reports.report import (
    CHART_TYPES,
    NAMED_NUMBER_FORMATS,
    TABLE_STYLES,
    TEXT_STYLES,
)

# Fields whose allowed values are a closed set. Keyed by (class name, field).
_ENUMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("TextSection", "style"): TEXT_STYLES,
    ("TableSection", "style"): TABLE_STYLES,
    ("ChartSection", "chart_type"): CHART_TYPES,
}

# Fields that hold a live DataSet rather than plain data. Flagged so a
# consumer knows a spec must reference data rather than inline it.
_DATA_FIELDS = {"dataset"}


def _type_name(annotation: Any) -> str:
    """Render a type annotation as a short, readable string."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return "Any"
    if isinstance(annotation, str):
        return annotation
    origin = typing.get_origin(annotation)
    if origin is None:
        return getattr(annotation, "__name__", str(annotation))
    args = typing.get_args(annotation)
    # Optional[X] reads better than Union[X, None]
    if origin is typing.Union and len(args) == 2 and type(None) in args:
        inner = next(a for a in args if a is not type(None))
        return f"Optional[{_type_name(inner)}]"
    rendered = ", ".join(_type_name(a) for a in args)
    name = getattr(origin, "__name__", str(origin))
    return f"{name}[{rendered}]" if rendered else name


def _default_of(field: dataclasses.Field) -> Any:
    if field.default is not dataclasses.MISSING:
        return field.default
    if field.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
        try:
            return field.default_factory()  # type: ignore[misc]
        except Exception:  # noqa: BLE001 - a default we cannot show is not fatal
            return None
    return None


def _jsonable(value: Any) -> Any:
    """Reduce a default to something JSON can carry."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def _describe_dataclass(cls: type, skip: tuple[str, ...] = ()) -> dict:
    """Fields, types, defaults and allowed values for one dataclass."""
    fields = []
    for f in dataclasses.fields(cls):
        if f.name in skip:
            continue
        entry: dict[str, Any] = {
            "name": f.name,
            "type": _type_name(f.type),
            "default": _jsonable(_default_of(f)),
            "required": (
                f.default is dataclasses.MISSING
                and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
            ),
        }
        allowed = _ENUMS.get((cls.__name__, f.name))
        if allowed:
            entry["allowed"] = list(allowed)
        if f.name in _DATA_FIELDS:
            entry["holds_data"] = True
        fields.append(entry)
    return {
        "class": cls.__name__,
        "summary": (cls.__doc__ or "").strip().split("\n")[0],
        "fields": fields,
    }


def _sections() -> list[dict]:
    from tracebi.reports.report import (
        ChartSection,
        MetricSection,
        RowSection,
        SpacerSection,
        TableSection,
        TextSection,
    )

    out = []
    for cls in (TextSection, TableSection, ChartSection,
                MetricSection, RowSection, SpacerSection):
        # section_type is set in __post_init__, never passed by a caller.
        entry = _describe_dataclass(cls, skip=("section_type",))
        instance_type = getattr(cls(), "section_type", None)
        entry["section_type"] = getattr(instance_type, "value", None)
        out.append(entry)
    return out


def _dataset_verbs() -> list[dict]:
    """
    The chainable DataSet API.

    Every verb returns a new DataSet and appends a lineage node, so an
    agent can compose them freely without worrying about mutation.
    """
    from tracebi.model.dataset import DataSet

    # Not transforms: accessors and output helpers.
    non_verbs = {
        "to_pandas", "fingerprint", "help", "help_text",
        "print_lineage", "lineage_to_dict",
    }
    out = []
    for name, fn in inspect.getmembers(DataSet, inspect.isfunction):
        if name.startswith("_") or name in non_verbs:
            continue
        sig = inspect.signature(fn)
        params = [
            {
                "name": p,
                "type": _type_name(v.annotation),
                "required": v.default is inspect.Parameter.empty,
            }
            for p, v in sig.parameters.items()
            if p != "self" and v.kind is not inspect.Parameter.VAR_KEYWORD
        ]
        out.append({
            "name": name,
            "summary": (fn.__doc__ or "").strip().split("\n")[0],
            "params": params,
            "returns": "DataSet",
        })
    return out


def _conventions() -> dict:
    """
    How a project is discovered. These rules are enforced by
    ``tracebi/web/discovery.py`` and the model/pipeline registries, and
    they fail quietly — a file in the wrong place simply never appears.
    """
    return {
        "directories": [
            {
                "path": "inputs/",
                "must_define": None,
                "type": "raw input",
                "note": "Phase ⓪ — raw pulls land here (API export, CSV, SQL "
                        "dump). Not discovered by the server; transforms read it.",
            },
            {
                "path": "transforms/",
                "must_define": None,
                "type": "phase-① transform",
                "note": "Unconstrained pandas run explicitly (python "
                        "transforms/<name>.py). The contract is what lands: "
                        "named star tables sunk to the DuckDB warehouse. Not "
                        "discovered by the server; models read the sink.",
            },
            {
                "path": "models/",
                "must_define": "model",
                "type": "DataModel",
                "note": "Also loadable without a server: "
                        "tracebi.model_registry.get_model(name)",
            },
            {
                "path": "pipelines/",
                "must_define": "runner",
                "type": "PipelineRunner",
                "note": "Also loadable via tracebi.pipeline_registry.get_runner(name)",
            },
            {
                "path": "reports/",
                "must_define": None,
                "type": "Report",
                "note": "Decorate a zero-arg factory with @register.report('name')",
            },
            {
                "path": "requests/",
                "must_define": "report",
                "type": "Report",
                "note": "Ad-hoc scripts, .py or .ipynb. Also needs a run() to render.",
            },
        ],
        "rules": [
            "Files starting with '_' are skipped (that is why _template.py is ignored).",
            "Only .py and .ipynb are loaded; subdirectories are not scanned.",
            "Registration happens as an import side effect, so module scope must "
            "be safe to execute at server startup.",
            "A file that raises on import is skipped with a warning, not an error — "
            "run `tracebi validate` to see what failed to load.",
        ],
        "env_overrides": [
            "TRACEBI_MODELS_DIR", "TRACEBI_PIPELINES_DIR",
            "TRACEBI_REPORTS_DIR", "TRACEBI_REQUESTS_DIR",
            "TRACEBI_SCHEDULED_DIR", "TRACEBI_APP", "TRACEBI_DOCS_DIR",
        ],
    }


def describe() -> dict:
    """
    Return TraceBi's full vocabulary as plain, JSON-serializable data.

    Generated from the code, so it stays correct as the framework changes.
    """
    import pandas as pd

    from tracebi.model.data_model import DataModel
    from tracebi.model.dataset import DataSet
    from tracebi.reports.report import Report

    # The cheat sheets are static text, but read them off real instances
    # rather than bypassing __init__ — a throwaway object is cheap and
    # cannot break if these ever start reading state.
    return {
        "tracebi_version": get_version(),
        "cheat_sheets": {
            "DataSet": DataSet(pd.DataFrame(), name="_").help_text(),
            "DataModel": DataModel("_").help_text(),
            "Report": Report("_").help_text(),
        },
        "report_sections": _sections(),
        "dataset_verbs": _dataset_verbs(),
        "semantic_model": {
            "measure_kinds": [
                {
                    "kind": "simple",
                    "args": ["column", "agg"],
                    "example": "add_measure('revenue', column='revenue', agg='sum')",
                },
                {
                    "kind": "expression",
                    "args": ["expr", "agg"],
                    "example": "add_measure('margin', expr='revenue - cost', agg='sum')",
                    "note": "Arithmetic over column names only — no function calls.",
                },
                {
                    "kind": "ratio",
                    "args": ["ratio"],
                    "example": "add_measure('margin_pct', ratio=('margin', 'revenue'))",
                    "note": "Divides aggregated totals, not per-row values.",
                },
            ],
            "aggregations": sorted(_AGG_FUNCS),
            "filter_operators": list(FILTER_OPS),
            "filter_forms": [
                {"form": "{'status': 'shipped'}", "means": "equality"},
                {"form": "{'region': ['NE', 'SE']}", "means": "in"},
                {"form": "{'revenue': {'gte': 1000}}", "means": "explicit operator"},
                {"form": "{'dim_customer.region': 'West'}",
                 "means": "filter on a dimension attribute"},
            ],
            "ordering": {
                "order_by": [
                    {"form": "{'column': 'fair_value', 'desc': True}",
                     "means": "sort the result by a result column — dimension "
                              "refs, measure names, ratio measures included"},
                    {"form": "'-fair_value'",
                     "means": "string shorthand: '-col' descending, 'col' "
                              "ascending"},
                ],
                "limit": "keep the first N rows after sorting; REFUSED without "
                         "order_by — 'first N' must never masquerade as 'top N'",
                "note": "Ties are broken by the remaining dimension columns and "
                        "the fully resolved ordering is stamped in the recorded "
                        "query, so a 'top 10' replays exactly.",
            },
            "constraints": [
                "Measures are declarative data. Callables are rejected — they "
                "cannot be serialized, diffed, or validated before execution.",
                "A dimension whose key is not unique raises rather than silently "
                "inflating every additive measure. Override with allow_fanout=True.",
            ],
        },
        "number_formats": dict(NAMED_NUMBER_FORMATS),
        "conventions": _conventions(),
    }


def describe_model(model) -> dict:
    """
    Describe one model's own vocabulary — its tables, relationships,
    facts, dimensions and declared measures. Thin wrapper over
    ``DataModel.info()``, here so a consumer has a single entry point.
    """
    return model.info()


def to_json(indent: Optional[int] = 2) -> str:
    """``describe()`` rendered as a JSON string."""
    import json
    return json.dumps(describe(), indent=indent, default=str)
