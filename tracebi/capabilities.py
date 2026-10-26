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
from tracebi.model.data_model import _AGG_FUNCS, _TIME_GRAINS, FILTER_OPS
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


REPORT_JSON_EXAMPLE = {
    "name": "Sales by region",
    "data": {
        "kpis": {
            "model": "sales",
            "query": {
                "fact": "fact_orders",
                "measures": {"revenue": "sum"},
            },
        },
        "region": {
            "model": "sales",
            "query": {
                "fact": "fact_orders",
                "measures": {"revenue": "sum"},
                "dimensions": ["dim_customer.region"],
                "order_by": ["-revenue"],
            },
        },
    },
    "figures": {
        "total": {
            "kind": "value",
            "binding": "kpis",
            "cell": "revenue",
            "label": "Revenue",
            "format": "currency",
        },
        "by_region": {
            "kind": "chart",
            "binding": "region",
            "chart_type": "bar",
            "x": "dim_customer.region",
            "y": "revenue",
        },
    },
}

REPORT_JSON_LIBS_NOTE = (
    "libs is optional. The build inlines D3 automatically when the page "
    "contains a chart figure and draws every chart type with it, and leaves "
    "it out when the page has no chart figure. List \"d3\" for a custom "
    "figure drawn in script.js with tracebi.draw. List \"echarts\" to keep "
    "the older ECharts engine for the page's charts (configureChart patches "
    "apply only there). Any other name is refused when the package loads."
)


def _presentation() -> dict:
    """
    The presentation system as data (architecture v2 §2.4): the stack, the
    tokens, the component classes, and the figure attributes — so an agent
    can style a page from the vocabulary alone, the same way it authors
    queries.
    """
    return {
        "stack": [
            "tracebi.css (shipped design system)",
            "reports/_theme.css (project brand layer — optional)",
            "style.css / spec 'theme' file (per-report — optional)",
        ],
        "rule": "Later layers win. Override tokens, don't fork the sheet. "
                "Presentation never changes a number.",
        "report_json": {
            "example": REPORT_JSON_EXAMPLE,
            "name": "The display name people read in every list and title "
                    "(\"Sales by region\"), not the folder slug: the path "
                    "(reports/<model>/<slug>/) is the identifier commands take.",
            "description": "One sentence for the reader: what the page shows "
                           "(measures, breakdowns, period), shown under the name "
                           "in the library. How the page is built goes in "
                           "\"notes\" (for authors; nothing renders it) or a "
                           "comment, never here.",
            "libs": REPORT_JSON_LIBS_NOTE,
            "embed": {
                "keys": "\"embed\": \"required\" | \"model\" | \"none\" "
                        "(default \"required\"), \"embed_budget_mb\": <number> "
                        "(default 25)",
                "note": "What the built page carries besides each binding's "
                        "stamped rows: the slice, the rows a live page "
                        "recomputes from. Per fact the page reads, one Parquet "
                        "block (tracebi-slice-<fact>) at the coarsest grain "
                        "that answers every figure and every filter control "
                        "(base grain when a measure is nunique, a percentile or "
                        "a row expression; a mean is stored as its sum and "
                        "count), plus one tracebi-calc-plans block with each "
                        "binding's calc plan. required embeds that grain; model "
                        "embeds every fact at base grain with every dimension "
                        "attribute it reaches; none embeds nothing new and the "
                        "figures stay as built. Past embed_budget_mb the build "
                        "fails and names the fix (remove a control or a "
                        "grouping, raise the budget, or embed none). A slice "
                        "holds numbers, booleans, strings and naive datetimes "
                        "only; any other type in a column the page needs fails "
                        "the build by name. A SQL binding and a report.py "
                        "output are never in a slice: they stay fixed at build. "
                        "The manifest records each block's payload_sha256 "
                        "under slice and every plan under plans.",
            },
            "report_measures": {
                "key": "measures",
                "shape": "{\"<model>\": {\"<name>\": {<add_measure keywords>}}}",
                "example": "\"measures\": {\"wealth_model\": {\"purchases\": "
                           "{\"column\": \"amount\", \"agg\": \"sum\", \"filters\": "
                           "{\"activity_type\": \"purchase\"}}, \"sales\": "
                           "{\"column\": \"amount\", \"agg\": \"sum\", \"filters\": "
                           "{\"activity_type\": \"sale\"}}, \"net_new_assets\": "
                           "{\"measure_expr\": \"purchases - sales\", \"format\": "
                           "\"currency0\"}}}",
                "note": "This report's own calculations, not the shared model's. "
                        "Each takes the same keywords as add_measure (simple, "
                        "expression, ratio, share, filters, measure_expr, and "
                        "the rest), so the vocabulary is the model's. A binding "
                        "that lists one by name in its measures gets it for that "
                        "query only; the model stays as it is, and a name the "
                        "model already declares is refused. The trace labels "
                        "them 'calculated in this report' (the semantic contract "
                        "carries scope: report), and the stamped query carries "
                        "their definitions, so verify re-runs them. Report "
                        "calculations are re-runnable, never a governed "
                        "definition: promote one into the model to make it "
                        "shared.",
            },
            "sql_calculations": {
                "key": "sql_calculations",
                "shape": "{\"<model>\": {\"<name>\": \"SELECT ...\"}}",
                "example": "\"sql_calculations\": {\"sample_model\": {\"running_revenue\": "
                           "\"SELECT region_id, order_date, SUM(revenue) OVER (PARTITION BY "
                           "region_id ORDER BY order_date) AS running_revenue FROM fact_orders\"}}"
                           ", bound as \"data\": {\"running\": {\"model\": \"sample_model\", "
                           "\"sql\": \"running_revenue\"}}",
                "note": "A named calculation the report runs as one read-only SELECT (or WITH) "
                        "over its model's warehouse tables. It is not a model query: write the "
                        "SQL with the warehouse's own table and column names. Anything else (a "
                        "write, ATTACH, COPY, PRAGMA, SET, INSTALL, LOAD, or more than one "
                        "statement) is refused when the report is discovered. The engine opens "
                        "the warehouse read-only and reaches no other file or network. "
                        "{{ measure('name') }} inside the SQL expands to a model measure: simple "
                        "measures (sum, count, mean, min, max, nunique of one column) and filtered "
                        "ones; any other kind (ratio, expression, share, rank, period_end, ...) is "
                        "refused by name, so write it out in SQL or query the model. Rows come back "
                        "in a canonical order (by columns, left to right); put the grouping and date "
                        "columns first. A selection or filter cannot reach a SQL binding yet. The "
                        "trace records the SQL and labels it 'calculated in this report (SQL)' "
                        "(the semantic contract's sql_calculations); the stamped query carries the "
                        "SQL and verify re-runs it, reporting source drift when the warehouse "
                        "changes.",
            },
        },
        "app": {
            "what": "The React lane: app.jsx in place of template.html, for app-like "
                    "dashboards. One component (export default), compiled in the page from "
                    "a fixed kit; still one offline file with its trace.",
            "imports": "react, react-dom, recharts, lucide-react (icons by name; only "
                       "those are embedded), tracebi. Any other import fails the build.",
            "kit": "<Masthead title kicker period mark> opens the page (children are the "
                   "standfirst; kicker defaults to the model's label; title is a string or text with <Value>s in it; period "
                   "is presentation, \"Q3 2026\"; it holds the build time and the "
                   "verdict chip), <Footer /> where the build's footer goes (the end "
                   "of the main column; without it the footer follows the app), "
                   "<Kpi binding cell format label context lead deltaBinding deltaCell "
                   "deltaFormat deltaGood> (the delta is a stamped change shown with "
                   "its arrow, sign and colour, deltaGood \"up\" or \"down\" saying "
                   "which way is good; no comparison measure, no delta; a <Spark> "
                   "child sits on the card's bottom edge), <Value binding cell "
                   "format>, <Chart binding type x y valueFormat ...>, <Spark ...> (a "
                   "sparkline), <Table binding columns sort bars rows selectRows> "
                   "(selectRows: a row click selects the row's dimension values), "
                   "<Filter binding "
                   "column multiple> (no binding: a page-wide filter; on a live page "
                   "every filter recomputes every figure it reaches; multiple picks "
                   "several values), <Range column label min max step> (data-tb-range), "
                   "<SelectionBar /> (where the selection bar goes, data-tb-selection), "
                   "<Search binding>, <Download "
                   "binding>, <Built> (the build time alone; <Masthead> already "
                   "shows it); <Segmented options value onChange> to choose which "
                   "figure shows (each option its own binding — never to compute one); "
                   "useUrlState(key, initial) keeps a view or period in the URL so a "
                   "shared link opens on it; usePrinting() is true while the page "
                   "prints (Ctrl+P and the PDF build), so an app with views renders "
                   "all of them; useBinding(name) returns the stamped rows; "
                   "fmt(value, format).",
            "claims": "Kit figures are claims: binding, cell, x and y (and a Kpi's "
                      "deltaBinding / deltaCell) must be literal strings, and the "
                      "build refuses a binding or column that does not exist. A "
                      "number the app computes or draws itself is presentation, "
                      "not a checked figure; the page's footer says so. A number "
                      "typed into the app's text (two or more digits) fails the build, as "
                      "in template.html: bind it with <Value binding cell />.",
            "styling": "Tailwind classes, with the TraceBi tokens as colours (bg-page, "
                       "bg-card, bg-surface, text-ink, text-muted, border-rule, bg-accent "
                       "with text-on-accent, "
                       "text-good, text-bad, chart-1..8) and the kit's tb-* classes.",
            "when": "app.jsx for dashboards people work in; template.html for briefs, "
                    "long-form, emailed and printed pages (they read with JavaScript off).",
            "scaffold": "tracebi new-dashboard \"Name\" writes a dashboard app.jsx; "
                        "--job overview|trend|leaderboard|scorecard|monitor|funnel picks "
                        "what it is for (trend and monitor need a time dimension; "
                        "scorecard shows every measure, up to four, with its trend; "
                        "monitor the latest period and a lowest-first watch list; "
                        "funnel each count measure as a stage, its conversion a "
                        "report-level ratio), and --nav top|side, --title-at, "
                        "--mode, --density and --theme shape it. (new-report writes "
                        "pages to be read.)",
            "without_javascript": "The build writes the kit figures into the app's "
                                  "mount point as a static view (labelled KPIs, the "
                                  "charts' static pictures, tables), so an email "
                                  "preview or a phone's file viewer shows the "
                                  "numbers; the app replaces it when it starts.",
        },
        "tokens": [
            "--tb-font", "--tb-ink", "--tb-bg", "--tb-muted", "--tb-accent",
            "--tb-font-display (unset by default: the one display face a "
            "theme may give the masthead headline, the lead number and the "
            "trace's title; unset, a dashboard keeps the sans and an "
            "editorial headline the serif)",
            "--tb-on-accent (text on an accent fill)",
            "--tb-dark-accent / --tb-dark-accent-text (the accent on the "
            "dark ground; a theme sets both pairs)",
            "--tb-rule", "--tb-grid (chart gridlines, 6% ink)", "--tb-radius",
            "--tb-space-1..4",
            "--tb-text-xs..3xl (the type scale: 12/13/14/16/20/28/40px), "
            "--tb-tracking-tight (28px and up)",
            "--tb-good / --tb-bad (direction tones), --tb-warn (the amber "
            "verdict tone)",
            "--tb-cell-pad (table density)",
            "--tb-measure (an editorial's reading column, 68ch of its serif)",
            "--tb-chart-1..8 (the chart palette; chart-1 is the accent)",
        ],
        "components": [
            ".tb-page (the page measure, 1,200px; an app's <main "
            "className=\"tb-page px-6 py-8\">)",
            ".tb-masthead (opens every page: optional .tb-masthead-mark — "
            "empty; a report's style.css gives it a logo, e.g. width, height "
            "and background: url(assets/logo.svg) — .tb-kicker (the model's "
            "label: the build adds it when the masthead has none), <h1> (the "
            "report's name or its finding), .tb-standfirst, .tb-masthead-meta."
            " data-tb-period=\"…\" on the "
            "masthead names what the numbers cover; the runtime fills the "
            "meta with the period, the build time and the verdict chip, "
            "adding whichever is missing. data-tb-title=\"center|banner|nav\" "
            "places it. The editorial hero is <header class=\"tb-masthead "
            "tb-article-head\">)",
            ".tb-verdict (the verdict chip, in the masthead: the runtime sets "
            "data-tb-verdict from the file itself — draft on a working "
            "preview, not-checked on a built file, since nothing has re-run "
            "its queries; tracebi verify does. The four verdicts are "
            "reproduces (green), needs-a-look (amber), does-not-reproduce "
            "(red), not-checked (neutral). A page never sets it green; framed "
            "in the web app, it shows the app's re-check, which the app tells it)",
            ".tb-footer (ends the page: your sources first, then the build's "
            "one line — when, which model by its label, and that the page does "
            "not claim the numbers are right — and 'How these numbers were "
            "made', which opens the trace drawer (a <details> holds the "
            "stated methodology for a reader without the runtime). The build "
            "adds it when the template places no data-tb-methodology)",
            ".tb-grid", ".tb-span-4 / .tb-span-6 / .tb-span-8 / .tb-span-12 "
            "(children of a .tb-grid make it the 12-column grid: a third, a "
            "half, two thirds, the row; full width under 720px)",
            ".tb-card",
            ".tb-lede (the page's answer sentence under the title, its "
            "numbers bound as value figures)",
            ".tb-kpi (.tb-kpi-label / .tb-kpi-value / .tb-kpi-context — the "
            "comparison line under the number; .tb-kpi-delta, a value figure "
            "with data-tb-direction leading that line, is the stamped change)",
            ".tb-table (variants: .tb-table--striped, .tb-table--compact, "
            ".tb-table--freeze — the first column stays put while a wide "
            "table scrolls sideways)",
            ".tb-callout", ".tb-note",
            ".tb-article (an editorial report: the masthead as "
            ".tb-article-head, the hero on the accent, .tb-kicker, "
            ".tb-standfirst; the prose in one 68ch serif column, while "
            "figure.tb-figure with figcaption, tables and a .tb-grid KPI "
            "strip take the sheet's width; "
            ".tb-pullstat / .tb-pullstat-value / .tb-pullstat-text)",
            ".tb-good / .tb-bad (direction tones; pair with a sign or word, "
            "never color alone)",
            ".tb-badge (--derived / --unverified, or .tb-verdict on a figure "
            "a re-runnable query backs — provenance chooses the class; a "
            "stylesheet can restyle, never re-color honesty). The query-backed "
            "badge is the verdict chip with the file's own state, 'Draft' on a "
            "preview or 'Not checked' on a build: never green on the page, "
            "since only a host that re-ran the queries may say 'Reproduces' — "
            "the trace attests reproduction, not correctness",
        ],
        "figure_attributes": {
            "data-tb-figure": "value | chart | table | custom — on ANY "
                              "element, not just cards: a <span> inside a "
                              "sentence works, so prose numbers can be live "
                              "figures instead of typed-in text",
            "data-tb-binding": "which stamped binding feeds this element",
            "data-tb-cell": "value figures: the column of a one-row "
                            "binding to read. Give that binding its own "
                            "query with no dimensions, or order_by plus "
                            "limit 1; the build refuses any other row "
                            "count. A text cell, such as the top sector's "
                            "name, is shown as text. The hydrator fills a "
                            ".tb-kpi-value child when one exists, else the "
                            "element itself",
            "data-tb-format": "value figures: compact | comma | currency | "
                              "currency0 | currency_compact ($285.9M) | "
                              "percent | decimal. Omitted, a "
                              "numeric cell takes the model's declared "
                              "format, then a readable shape default "
                              "(4,846.10) — as a table column does",
            "data-tb-type / data-tb-x / data-tb-y / data-tb-color": "chart wiring",
            "data-tb-value-format": "chart labels (each bar's own value, a "
                                    "line's last value), axes, and tooltips — every "
                                    "chart type: compact | comma | currency | "
                                    "currency0 | currency_compact | percent | decimal "
                                    "(compact → '550.7B')",
            "data-tb-stack": "bar, barh and area charts (no value): stack "
                             "the series into one slot per category. The "
                             "stack lays rows end to end; no total is written",
            "data-tb-x-title / data-tb-y-title": "chart axis titles",
            "data-tb-unit": "chart suffix after every value, tick and mark "
                            "(\"%\" on a rate stored as 6.81, \"×\" on a "
                            "ratio): text only, the number is never rescaled",
            "data-tb-mark": "line, area and bar charts: max | min | first | "
                            "last, comma-separated — circle and label that "
                            "row's own value (\"High 6.81\")",
            "data-tb-annotate": "categorical charts: \"2008=Financial crisis; "
                                "2020=Pandemic\" — a dashed rule and a note "
                                "at each x category, in the author's words",
            "data-tb-facet": "bar, barh, line and area charts: a column; one "
                             "small panel per value, sharing one scale and one "
                             "category axis. Line and area charts with 8 or "
                             "more categories zoom by dragging across the "
                             "plot; double-click or Reset zoom returns",
            "data-tb-columns": "table figures: column allowlist/order",
            "data-tb-labels": "table figures: header text per column, "
                              "\"col=Label; col2=Label\" (';' separates "
                              "pairs, so a label may hold a comma); wins "
                              "over the derived header",
            "data-tb-formats": "table figures: number format per column, "
                               "\"fair_value=currency0; mark=percent\" — "
                               "compact | comma | currency | currency0 | "
                               "currency_compact | percent | decimal; wins over the derived "
                               "format. A column or format that does not "
                               "exist fails the build",
            "data-tb-totals": "table figures: a one-row binding (the same "
                              "query with no dimensions) whose values fill a "
                              "totals row — the model computes each total, so "
                              "a ratio's total is a ratio of totals. Hidden "
                              "while a filter or search is on. A spec's "
                              "table 'totals' compiles to this",
            "data-tb-sort": "table figures (no value needed): headers become "
                            "buttons the reader clicks to sort ascending, "
                            "descending, then back to the query's order. It "
                            "reorders stamped rows and computes nothing; the "
                            "query's order_by stays the default",
            "data-tb-bars": "table figures: \"col, col2\" — a thin bar "
                            "after each named numeric cell, in its own lane, proportional to "
                            "the stamped value (zero at the left edge, or in "
                            "the middle when the column has negatives; scaled "
                            "over all rows, not the visible window, so a "
                            "filter or a scroll never rescales). A "
                            "non-numeric or missing column fails the build",
            "data-tb-direction": "value figures: up-good | down-good — marks "
                                 "a change figure up / down / flat (an arrow) "
                                 "and good or bad (--tb-good / --tb-bad) from "
                                 "the stamped value's sign. The text stays the "
                                 "formatted number; use it on a bound "
                                 "comparison, e.g. a growth measure",
            "data-tb-unverified": "the honest mark for an unbacked figure",
            "data-tb-stage": "exploration — stripped at final build",
            "data-tb-methodology": "one per page, on any container element "
                                   "(<footer class=\"tb-footer\" "
                                   "data-tb-methodology>); the author's own "
                                   "children (sources) stay FIRST; the build "
                                   "appends the footer's line and, behind "
                                   "'How these numbers were made', the "
                                   "pipeline's stated methodology (transform "
                                   "notes, per-check rationale, measure "
                                   "descriptions) — an appendix, never a "
                                   "claim: no badge, no status",
        },
        "figure_helper": {
            "rule": "You keep the layout; the framework builds the figure. "
                    "Declare figures in report.json under 'figures', then "
                    "place each one in template.html with "
                    "{{ figure(\"name\") }} — anywhere inside your own "
                    "markup, CSS and script. The emitted element is "
                    "byte-identical to what a spec would compile, so you "
                    "never hand-write the data-tb-* grammar. Hand-written "
                    "figures still work; this is sugar, not a replacement.",
            "declaration": "\"figures\": {\"total\": {\"kind\": \"value\", "
                           "\"binding\": \"totals\", \"cell\": \"revenue\", "
                           "\"label\": \"Revenue\", \"format\": "
                           "\"currency\"}}",
            "kinds": "value (needs 'cell' and a one-row binding) | chart "
                     "(chart_type, x, y, color, "
                     "palette, value_format) | table (columns, style, labels, formats — "
                     "labels/formats are {column: text} objects). A 'custom' figure "
                     "has no framework markup — draw it in script.js with "
                     "tracebi.draw.",
            "figure_id": "The declared name becomes the figure id "
                         "(fig-<name>) — the trace's stable address.",
            "refusals": "A figure naming an undeclared binding fails when "
                        "the package loads. Declaring a figure and never "
                        "placing it fails the build (a declared number must "
                        "not silently vanish); placing one twice fails too "
                        "(one id addresses one number).",
        },
        "controls": {
            "rule": "The law: a figure's number is only ever a query "
                    "result. A page built with a slice (report.json \"embed\", the "
                    "default) holds ONE selection state, {column: "
                    "[values]}: every data-tb-filter writes its column into "
                    "it, and the page engine (tracebi-calc.js) re-runs each "
                    "binding's own calc plan — its query, compiled at build "
                    "— over the embedded slice under that state, so every "
                    "figure the selection reaches (values, tables, charts, "
                    "sparks, tracebi.draw figures) is recomputed as a query "
                    "result, never as arithmetic over the rows on screen. "
                    "A selected field applies to a figure when its fact "
                    "reaches that dimension through a declared "
                    "relationship; otherwise the figure keeps its number "
                    "and is marked data-tb-unfiltered-by. What the engine "
                    "cannot run keeps its build value and is marked "
                    "data-tb-fixed. Search only narrows the rows shown. On "
                    "a page built with \"embed\": \"none\" there is "
                    "nothing to recompute from: filters subset which stamped "
                    "rows tables and charts display, and value figures never "
                    "react.",
            "selection": "\"selection\": {\"model\": \"portfolio_model\", "
                         "\"filters\": {\"dim_sector.sector\": "
                         "\"Technology\"}} sets the page's AUTHORED "
                         "selection: the state the page opens in and the "
                         "build's trace (verify re-runs it). Absent or "
                         "\"filters\": {} is no cut. Binding filters always "
                         "apply; the selection wins on the same target. "
                         "having, order_by, and limit stay on the binding. "
                         "In the web app, Ask reads pins, then resolves a "
                         "question to a value one of the page's controls "
                         "already has and recomputes on the server "
                         "(POST /api/reports/<name>/selection). A question "
                         "that names one declared dimension the report does "
                         "not already cut becomes a new binding in "
                         "report.json, then a rebuild. A question that names "
                         "no declared value, or names two columns, is "
                         "refused. A number in the reply is a value figure "
                         "beside its fingerprint.",
            "data-tb-filter": "<select data-tb-filter data-tb-binding=\"B\" "
                              "data-tb-column=\"C\" [multiple]> — on a page "
                              "built with a slice (report.json \"embed\", the "
                              "default) every filter, binding-scoped or \"*\", "
                              "writes ONE selection state for its column "
                              "({column: [values]}; multiple picks several, "
                              "'All' removes it) and tracebi-calc.js re-runs "
                              "each binding's own calc plan over the embedded "
                              "slice under it: values, tables (rows, bars, "
                              "data-tb-totals), charts, sparks and tracebi.draw "
                              "figures all redraw from that query result. "
                              "Options are the column's values present under "
                              "the rest of the selection, then the others "
                              "after a separator; none is hidden. The state "
                              "lives in the URL hash (#sel=…, beside an app's "
                              "own keys), so a link or a reload opens the same "
                              "view; a hash naming no field the page's filters "
                              "offer is ignored. While it differs from the "
                              "authored selection the verdict chip reads Local "
                              "(recomputed on this page from the embedded "
                              "data; never green) and the trace row of each "
                              "figure shows its plan, the selection applied "
                              "and the slice block's payload_sha256. `tracebi "
                              "verify <manifest> --local` replays every plan "
                              "by the page engine and by the server. A filter "
                              "on a column no slice carries, and every filter "
                              "on a page built with embed none, subsets the "
                              "binding's stamped rows as before (sorted "
                              "distinct values plus 'All', re-rendering that "
                              "binding's tables and charts; the control gets "
                              "data-tb-fixed=\"column not in slice\"). Download "
                              "of the selection names it in the filename and "
                              "a header line; data-tb-download stays the full "
                              "stamped binding",
            "data-tb-fixed": "set by the runtime on a live page: this figure "
                             "keeps its build value under any selection, "
                             "with the reason (a SQL binding, a report.py "
                             "output, a having on 'contains', a plan the "
                             "page engine could not run). Shown, while the "
                             "page is Local, as a small note: \"Fixed at "
                             "build · report.py\"",
            "data-tb-unfiltered-by": "set by the runtime on a live page: the "
                                     "selected fields this figure's fact "
                                     "does not reach (no declared "
                                     "relationship), so they do not narrow "
                                     "it; shown as \"Not filtered by "
                                     "Sector\". A value with no row under "
                                     "the selection shows — and \"No rows "
                                     "under this selection\"",
            "gestures": "On a live page every gesture writes the same "
                        "selection state a filter does, and every figure "
                        "re-runs from it: a click on a bar, a pie slice, a "
                        "line's category or a legend entry selects that "
                        "value of the chart's x (or data-tb-color series) "
                        "column — {column: [value]} — whenever a slice "
                        "carries the column, with no data-tb-filter needed; "
                        "the same value again removes it; shift-click adds "
                        "it to the list. A sparkline does not select (a "
                        "click opens its KPI's trace). On a page built with "
                        "embed none a click only sets an existing "
                        "data-tb-filter for that column, as before. A "
                        "selectable mark says \"select Software\" / "
                        "\"clear Software\" (aria-label). Escape clears the "
                        "selection back to the authored one (not while "
                        "typing). tracebi.onSelection(fn) is called with "
                        "{selection, authored, figures} on every change",
            "data-tb-select-rows": "<table data-tb-figure=\"table\" "
                                   "data-tb-select-rows[=\"dim.attr,…\"] …> "
                                   "(kit <Table selectRows> or "
                                   "selectRows=\"dim_issuer.issuer\") — on a "
                                   "live page a click (or Enter) on a row "
                                   "writes the row's values of every "
                                   "dimension column the table shows "
                                   "(dim.attr), or of the columns named, "
                                   "into the selection; again, it clears "
                                   "them; shift adds. The table keeps the "
                                   "other values of only the fields its own "
                                   "rows wrote; a filter, mark or another "
                                   "table on the same field narrows it like "
                                   "any figure. A row stands out "
                                   "(aria-selected) when its value of any "
                                   "select column is picked, unless every "
                                   "row is",
            "data-tb-range": "<span data-tb-range data-tb-column=\"C\" "
                             "[data-tb-label=\"…\"] [data-tb-min] "
                             "[data-tb-max] [data-tb-step]> (kit <Range "
                             "column label min max step>) — a range "
                             "control: for a number column (a dimension "
                             "attribute, or a fact's own column such as a "
                             "holding's fair value, which keeps that "
                             "fact's slice at base grain) two handles "
                             "over one track with the bounds as text; for "
                             "a time grain's labels (2026-03, 2026-Q1) a "
                             "from and a to picker. It writes {column: "
                             "{gte, lte}} and removes the field when both "
                             "ends are back at the domain, which is the "
                             "column's values under the rest of the "
                             "selection. It cuts the whole page, like a "
                             "page filter",
            "data-tb-selection": "<div data-tb-selection></div> (kit "
                                 "<SelectionBar />) — where the selection "
                                 "bar goes. Without one, every live page "
                                 "gets the bar under the masthead (above a "
                                 "React app). One chip per selected value "
                                 "(\"Sector: Software ×\"; a range is one "
                                 "chip), Clear when two or more, and "
                                 "\"Download what I see\": one CSV of each "
                                 "visible figure's current rows, the "
                                 "selection in its header line and file "
                                 "name. Hidden while the state is the "
                                 "authored one. Printed (and in the PDF) "
                                 "it is one plain line, \"Filtered to: "
                                 "Sector Software · Fund Fund I\", and the "
                                 "footer's built line adds \" · filtered "
                                 "on this page\". A field has one name "
                                 "everywhere the page says it (chips, the "
                                 "print line, the download header, \"Not "
                                 "filtered by\" notes, the trace): its "
                                 "control's data-tb-label or the <label> "
                                 "around it, else the header a table or "
                                 "the x title a chart gives the column, "
                                 "else one derived from the column name",
            "data-tb-highlight": "cross-highlighting: a chart keeps the "
                                 "other values of its own x and series "
                                 "columns (drawn from its query under the "
                                 "rest of the selection, which its trace "
                                 "row states as Highlights) and draws the "
                                 "ones not picked at reduced emphasis (a "
                                 "class; the numbers are untouched), so "
                                 "shift-click can add one; a row-select "
                                 "table does the same for its rows. "
                                 "data-tb-highlight=\"off\" on the figure "
                                 "or any ancestor (the page root) turns it "
                                 "off: the figure is then cut by its own "
                                 "field like every other",
            "data-tb-search": "<input data-tb-search data-tb-binding=\"B\">"
                              " — case-insensitive substring match across "
                              "all columns; ANDs with the filters",
            "data-tb-rows": "after hydration, a table figure with more "
                            "rows than data-tb-rows (default 10) is "
                            "wrapped in a .tb-scroll container sized to "
                            "show about that many rows, sticky header; "
                            "data-tb-rows=\"all\" opts out. Presentation "
                            "only. Tables past 500 rows render only the "
                            "visible rows; printing and download still "
                            "use every row. Find-in-page cannot see rows "
                            "outside that window — search with "
                            "data-tb-search",
            "data-tb-download": "<button data-tb-download "
                                "data-tb-binding=\"B\" "
                                "[data-tb-label=\"…\"]> — downloads the "
                                "binding's embedded canonical CSV — the "
                                "stamped CSV verbatim — a "
                                "trace-preserving export, saved as "
                                "<B>.csv. Taken under a selection it "
                                "says so: its first line is \"# "
                                "selection: none (full binding)\"",
        },
        "scenarios": {
            "rule": "The one place a page computes: a what-if from the "
                    "READER's own inputs, evaluated in the browser. A "
                    "scenario is never a figure, never in the trace, and "
                    "the runtime labels every one 'computed in your browser "
                    "… not part of the trace'. The manifest records its "
                    "declaration (inputs, formulas, presets) with "
                    "verifiable: false, never a value. Use it for 'what if "
                    "the rate were 7.8%', never for a number a query "
                    "could produce.",
            "data-tb-scenario": "<form data-tb-scenario=\"NAME\">…</form> — "
                                "holds the inputs, presets and outputs. Never "
                                "inside a figure, never holds a figure, never "
                                "nested; names are unique on the page",
            "data-tb-input": "<input data-tb-input=\"rate\" type=\"number\" "
                             "[value=\"…\"]> — a named input the formulas "
                             "read (a plain identifier)",
            "data-tb-calc": "<output data-tb-calc=\"pmt(rate / 1200, years * "
                            "12, price * (1 - down / 100))\" "
                            "[data-tb-format=\"currency\"]> — a closed "
                            "formula: numbers, input names, + - * / ^, "
                            "parentheses, pmt(rate, periods, principal), "
                            "min, max, round(x[, digits]), abs. No eval; "
                            "checked at build (unknown names and functions "
                            "fail it)",
            "data-tb-preset": "<select data-tb-preset=\"BINDING\" "
                              "data-tb-key=\"COLUMN\" data-tb-fill=\"input="
                              "column, …\" [data-tb-default=\"VALUE\"]> — "
                              "options are the binding's key values; picking "
                              "one fills the inputs from that STAMPED row. "
                              "The build checks the binding, key and "
                              "columns exist",
            "data-tb-key": "the preset's key column (see data-tb-preset)",
            "data-tb-fill": "input=column pairs a preset fills (see "
                            "data-tb-preset)",
            "data-tb-default": "the key value a preset starts on (see "
                               "data-tb-preset)",
            "example": "examples/portfolio_project/reports/housing_model/affordability/",
        },
        "assets": {
            "rule": "Fonts and images live in the package's assets/ folder. "
                    "url(assets/…) in style.css and src=\"assets/…\" in "
                    "template.html are inlined as data: URIs when the "
                    "package loads, so the file stays self-contained and "
                    "fetches nothing from the web.",
            "types": "woff2 | woff | ttf | otf | svg | png | jpg | jpeg | "
                     "webp | gif | avif",
            "refusals": "A missing file, any other type, or a path that "
                        "leaves assets/ fails the load and names the file.",
        },
        "layout": {
            "tabs": "<div class=\"tb-tabs\"><section "
                    "data-tb-tab=\"Label\">…</section>…</div> — the "
                    "runtime builds the tab bar from the labels and shows "
                    "one section at a time",
            "columns": "The 12-column grid: a .tb-grid whose panels carry "
                       ".tb-span-4 / -6 / -8 / -12 (.tb-span-8 beside "
                       ".tb-span-4 is the dashboard row: a wide panel beside "
                       "a narrow one); every span is the full row under "
                       "720px. .tb-cols-2 / .tb-cols-3 / .tb-cols-2-1 / "
                       ".tb-cols-1-2 still work as shorthands",
            "kpi_strip": "A .tb-grid of .tb-kpi cells renders as ONE panel "
                         "with hairlines between the cells. Mark the number "
                         "the page is about .tb-kpi--lead (larger, not "
                         "wider) — never a row of identical boxes. A change "
                         "the model measures goes first on the context line "
                         "as <span class=\"tb-kpi-delta\" "
                         "data-tb-figure=\"value\" data-tb-direction="
                         "\"up-good\" ...>: arrow, sign and --tb-good / "
                         "--tb-bad from the stamped value, zero neutral. "
                         "No comparison measure, no delta. "
                         "A line or area chart with class .tb-spark inside "
                         "a .tb-kpi is its trend's shape: no axes or legend, "
                         "32px tall on the card's bottom edge, zero-based, "
                         "hover still reads each value",
            "recipes": {
                "editorial": "A report to be read top to bottom (the default for "
                             "new-report): <article class=\"tb-article\"> — a "
                             "masthead (<header class=\"tb-masthead "
                             "tb-article-head\">: .tb-kicker, an <h1> that "
                             "states the finding, a .tb-standfirst, a "
                             ".tb-masthead-meta), a .tb-lede with its numbers "
                             "bound, <h2> sections of prose, <figure "
                             "class=\"tb-figure\"> with a <figcaption> saying "
                             "what to see, an <aside class=\"tb-pullstat\">, a "
                             "table, What to do, the .tb-footer. Serif body, "
                             "reads with JavaScript off, prints and emails. "
                             "tracebi new-report \"Name\" --layout editorial",
                "brief": "One finding: answer sentence (.tb-lede), a few "
                         "KPIs (.tb-grid / .tb-kpi), one chart in one "
                         ".tb-card. "
                         "tracebi new-report \"Name\" --layout brief",
                "dashboard": "A page people work in: tracebi new-dashboard "
                             "\"Name\" writes an app.jsx (presentation.app) — "
                             "the title, a KPI strip with a lead, a chart "
                             "beside its ranking, a filterable detail, and the "
                             "navigation asked for. new-dashboard --html (or "
                             "tracebi new-report \"Name\" --layout dashboard) "
                             "writes the template.html version (brief, then "
                             "a .tb-span-8 chart beside a .tb-span-4 detail).",
                "tabbed": "The same header, then .tb-tabs / data-tb-tab "
                          "(Overview and Detail). "
                          "tracebi new-report \"Name\" --layout tabbed",
            },
            "look": {
                "ask_first": "With a person in the loop, ask once before "
                             "building, in one message: the title and where "
                             "it sits, one page / top tabs / sidebar, light / "
                             "dark / the reader's choice, comfortable / "
                             "compact. Offer the look of their last report "
                             "first. No person: use the defaults.",
                "page": "On <html>: data-tb-mode=\"dark\" or \"light\" "
                        "(unset is \"auto\": follows the reader's system), "
                        "data-tb-density=\"compact\", data-tb-width=\"full\" "
                        "(the whole window, for a dashboard). Tokens only: "
                        "never a number, never the trace's tones",
                "sidebar": "<div class=\"tb-tabs\" data-tb-nav=\"side\"> — "
                           "the same data-tb-tab sections with the bar as a "
                           "column; put the whole page inside it",
                "title": "<header class=\"tb-masthead\" data-tb-title=\"left|"
                         "center|banner|nav\" data-tb-period=\"…\"><h1>…</h1>"
                         "<p class=\"tb-standfirst\">…</p><p class=\""
                         "tb-masthead-meta\"><span data-tb-built></span>"
                         "<span class=\"tb-verdict\"></span></p></header> — "
                         "data-tb-built shows when the file was built, from "
                         "its trace; nav moves the masthead to the top of a "
                         "sidebar. (.tb-title, the older title block, still "
                         "works)",
                "app": "An app.jsx has no <html>: its mode and density are "
                       "report.json \"look\": {\"mode\": \"dark\"|\"auto\", "
                       "\"density\": \"compact\"}; its navigation and title "
                       "are its own components (the scaffold writes them)",
                "scaffold": "tracebi new-dashboard|new-report \"Name\" --mode "
                            "light|dark|auto --density comfortable|compact --nav "
                            "top|side --title-at left|center|banner|nav "
                            "--theme <name> (new-dashboard --html for a "
                            "template dashboard)",
                "themes": "Shipped themes, contrast-checked token sets: "
                          + ", ".join(_named_themes()) + ". A report names one in report.json "
                          "\"theme\"; tracebi theme use <name> makes one the "
                          "project default (writes reports/_theme.css); "
                          "tracebi theme list",
                "for_everyone": "reports/_theme.css restyles every report in "
                                "the project (token overrides: accent, fonts, "
                                "spacing)",
                "style_css": "A report's own style.css is a theme preset at "
                             "most: the accent pairs (--tb-accent / "
                             "--tb-accent-text, --tb-dark-accent / "
                             "--tb-dark-accent-text) and one display face, as "
                             "--tb-font-display (an @font-face from assets/; "
                             "the system puts it on .tb-masthead h1 and "
                             ".tb-kpi--lead .tb-kpi-value). Tokens only: no rule "
                             "of its own. Set a pair where a report should "
                             "differ from the project's accent. No gradient, hatch, "
                             "glow or resting shadow; the showcase's style.css "
                             "is the example",
                "house_style": "reports/_style.md is the team's design rules, "
                               "returned as house_style by tracebi context and "
                               "get_context. Read it before building and follow "
                               "its Rules over these defaults",
            },
        },
        "receipt_drawer": (
            "Every built artifact embeds a tracebi-receipt JSON block — "
            "report, render stamp, git SHA, per-figure binding "
            "fingerprints, compact transform-contract statuses, the "
            "semantic-contract model names, whether stated methodology "
            "shipped and its text, who built the file, and per binding the "
            "query as run, its rows and how many ordering keys the author "
            "wrote. The drawer is a provenance display from "
            "the recorded block — it renders only what the block "
            "records, never re-colored; the manifest remains the trace "
            "of record. It reads as a certificate headed with the report's "
            "name and 'How each number was made': the verdict chip and "
            "'This page does not claim the numbers are right; it records how "
            "each was made so it can be checked.', how to "
            "check the file, then per figure its value as shown, label, "
            "the measure's definition, the query in one line and the "
            "fingerprint's first 8 characters, with the raw query and full "
            "fingerprint behind 'Raw', and 'About this build' last. It "
            "opens from the masthead's Trace link or verdict chip, a "
            "click on a value figure (at its row), a chart tooltip's "
            "'Trace ->' or the footer's 'How these numbers were made'; a "
            "full-height sheet on a phone; it prints as an appendix. "
            "tracebi.renderReceipt(mount, block, options) renders the same "
            "certificate into any element. Draft snapshots carry no trace."
        ),
        "prose_values": "When explaining results in prose, BIND the numbers: "
                        "<span data-tb-figure=\"value\" data-tb-binding=... "
                        "data-tb-cell=... data-tb-format=...>—</span> inside "
                        "the sentence makes each one a verified figure in the "
                        "manifest. Narrative prose is where hard-coded "
                        "numbers usually hide; here the honest path costs "
                        "one attribute.",
        "runtime": [
            "tracebi.data(name) → rows from the embedded fingerprinted bytes "
            "(the only data source)",
            "tracebi.ready(fn) → run fn once the data is loaded. ALWAYS wrap "
            "script.js data access in this: a large-detail artifact decodes "
            "its data at DOM-ready, AFTER script.js runs, so a bare "
            "tracebi.data() call there returns [] on those reports and rows "
            "on small ones. ready(fn) behaves the same on both.",
            "tracebi.fmt(value, 'compact') → the one '550.7B' formatter",
            "tracebi.configureChart(figureId, patch) → restyle an ECharts "
            "option, on a report that lists \"echarts\" (the D3 engine "
            "ignores it); series data is always re-sourced from the stamped "
            "bytes",
            "tracebi.draw(figureId, fn) → draw a data-tb-figure=\"custom\" "
            "element in code, usually d3 (report.json \"libs\": [\"d3\"]): "
            "fn(surface, rows, theme) runs once the data is loaded and again "
            "whenever the figure's rows change (filter, search, selection) or "
            "its width does. surface is an empty div inside the figure; rows "
            "are copies of its binding's stamped rows as the page's filters "
            "leave them; drawing never adds a number. Use it instead of "
            "tracebi.ready + tracebi.data for anything you draw",
            "tracebi.setSelection({column: value or [values]}) → set the "
            "page's selection from code, as a filter would (a click on a "
            "drawn mark); {} returns to the authored view. Every figure "
            "recomputes as from a filter; a page built with embed none "
            "ignores it",
            "tracebi.onSelection(fn) → fn({selection, authored, figures}) "
            "on every change of a live page's selection, from any control, "
            "mark, row, range, chip, Escape or setSelection; returns a "
            "function that stops it. Keep a drawn figure's own picking in "
            "step with the page (the showcase treemap)",
            "tracebi.result(figureId) → a live figure's current answer as "
            "the page engine gave it: {cols, rows, selection, "
            "unfiltered_by, highlights}, {fixed} for a build value, null "
            "as built. Read-only; it computes nothing",
            "tracebi.theme() → the page's resolved tokens {ink, muted, rule, "
            "bg, surface, accent, good, bad, font, mono, palette} — colour a "
            "drawn figure from these so it follows the theme",
        ],
        "embed_format": (
            "A built artifact embeds each binding's data as CSV, or as "
            "Parquet decoded in the browser by the inlined page engine "
            "(tracebi-calc.js, plain JavaScript) when the data is large "
            "enough that the engine pays for itself. tracebi CHOOSES this automatically per "
            "artifact by size — you never declare it, and one artifact never "
            "mixes both. It is a transport choice, not a trust one: a CSV "
            "block ships the fingerprinted triple verbatim, a Parquet "
            "block's shipped bytes are hashed exactly (payload_sha256), and "
            "verify --file checks both offline with no extra dependency. "
            "What it changes is the artifact's shape — a Parquet artifact "
            "carries ~45KB of engine (a page with a slice carries it anyway), "
            "so a small report stays CSV, readable as text. Only BUILDING the "
            "Parquet form needs PyArrow (pip install 'tracebi[reports]')."
        ),
        "semantic_contract": (
            "Every built artifact embeds one tb-semantic-contract-<model> "
            "JSON block per model its bindings reference, fingerprinted in "
            "the manifest's semantic_contract field: the contract as "
            "exercised, snapshotted at render — a record of what the "
            "vocabulary meant when the numbers were produced, never a live "
            "claim; the slice, not the whole model, so a report cannot leak "
            "vocabulary it never used. verify --file rehashes the embedded "
            "record byte-exactly; verify_manifest uses it only to sharpen a "
            "model-shaped failure's detail with the named difference — it "
            "never changes any status."
        ),
    }


def _transform_contracts() -> dict:
    """The phase-① sink-contract vocabulary — declared, closed, re-runnable."""
    return {
        "what": "Declared checks on the tables a transform SINKS, run as "
                "read-only SQL at sink time and recorded beside the "
                "warehouse, swapping its extension: data/warehouse.duckdb → "
                "data/warehouse.contracts.json. A failed check raises. This "
                "certifies the SINK — the exact claim is 'the sink "
                "satisfied its contract', never 'the transform was "
                "verified': nothing machine-checks the pandas above it.",
        "usage": "from tracebi.contracts import contract\n"
                 "with contract('holdings', warehouse=WAREHOUSE,\n"
                 "              note='unkeyed rows dropped and counted') as c:\n"
                 "    c.rows('fact_holdings', at_least=10)\n"
                 "    c.unique('dim_issuer', ['issuer_id'])",
        "file_form": "Beside a transform (SQL or Python): "
                     "transforms/<name>.contract.yaml, run after it by "
                     "`tracebi run-transform`, the same vocabulary through "
                     "the same parser, the same certificate:\n"
                     "name: holdings            # the record; default <name>\n"
                     "note: unkeyed rows dropped and counted\n"
                     "checks:\n"
                     "  - rows: fact_holdings\n"
                     "    at_least: 10\n"
                     "  - foreign_key: fact_holdings\n"
                     "    column: issuer_id\n"
                     "    refers_to: [dim_issuer, issuer_id]",
        "checks": [
            {"check": "rows",
             "args": ["table", "at_least?", "at_most?", "exactly?", "note?"],
             "means": "row-count bounds"},
            {"check": "unique", "args": ["table", "columns", "note?"],
             "means": "the columns form a unique key"},
            {"check": "not_null", "args": ["table", "columns", "note?"],
             "means": "no NULLs in any named column"},
            {"check": "foreign_key",
             "args": ["table", "column", "refers_to=(table, column)",
                      "note?"],
             "means": "no orphaned keys"},
            {"check": "values", "args": ["table", "column", "within",
                                         "note?"],
             "means": "every value drawn from a closed set"},
            {"check": "reconcile",
             "args": ["table", "column", "against=(table, column)", "by",
                      "tolerance", "note?"],
             "means": "per-key sums match across two tables within tolerance"},
        ],
        "stated_methodology": "contract(..., note='…') records the "
                              "transform-level STATED methodology, and every "
                              "check takes note='…' for per-check rationale "
                              "('dropped the 9 unkeyed rows'). A note is "
                              "prose the author states, recorded verbatim in "
                              "the certificate, carried into the manifest's "
                              "transform_contracts entries and a report's "
                              "data-tb-methodology appendix. It is never a "
                              "verified claim: say 'the transform states', "
                              "never 'verified methodology' — a note earns "
                              "no badge and never colors any status.",
        "manifest_join": "At report build, each loaded warehouse table is "
                         "classified in the manifest's transform_contracts "
                         "block: satisfied (the recorded certificate still "
                         "fingerprint-matches the table), stale (re-sunk "
                         "after its contract was checked — never reads "
                         "green), or no_contract. A separate claim beside "
                         "the figure claims; it never colors a figure "
                         "status. `tracebi verify --contracts` re-runs the "
                         "recorded checks against the current warehouse.",
        "constraints": [
            "The vocabulary is closed and declarative — no callables — so "
            "every check is serializable, reviewable, and re-runnable.",
            "Fingerprints are computed by reading the sunk table back "
            "through the connector load path, so the later satisfied/stale "
            "comparison is same-path on both sides.",
        ],
    }


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
                "note": "SQL by default: transforms/<name>.sql, DuckDB "
                        "statements run top to bottom in ONE fresh warehouse "
                        "connection by `tracebi run-transform <name>`, which "
                        "reports form: sql | python | notebook (the run "
                        "records it). A table it creates (not TEMP) is a sink "
                        "table: it lands in the warehouse on the file and "
                        "remote tiers and as <location>/<table>.parquet on the "
                        "object tier, or write COPY (…) TO "
                        "'{{ sink }}/<table>.parquet' (FORMAT PARQUET) "
                        "yourself. A view it creates (CREATE OR REPLACE VIEW) "
                        "is a sink view on the file and remote tiers, read by "
                        "a model as a table is and recorded in the certificate "
                        "under views (name, definition_sha256, bases); it may "
                        "read warehouse tables and views and a -- source: "
                        "table its connection's allowlist admits (agents: "
                        "tables; the model's query connection attaches it "
                        "live), and one over any other -- source: table, a "
                        "file or a TEMP object fails the run (the object "
                        "tier refuses every view). "
                        "Exactly two placeholders: {{ sink }} (the "
                        "warehouse address from tracebi.yaml) and {{ root }} "
                        "(the project root); any other {{ … }} is an error. "
                        "Relative reads (read_csv('inputs/x.csv')) resolve "
                        "against the project root. A table of a declared "
                        "connection (connections/<name>.yaml, e.g. Postgres) "
                        "is read with a header line `-- source: "
                        "<connection>.<table>` (one per table; a bare "
                        "connection is refused): before the first statement "
                        "the runner attaches it, through DuckDB's scanner for "
                        "Postgres, MySQL and SQLite (read in place), else as "
                        "Arrow (Snowflake, BigQuery, ADBC), else through the "
                        "connector, and the SQL reads it as "
                        "<connection>.<table>; nothing of it lands in the "
                        "warehouse. `fallback: inputs/<x>.csv` at the "
                        "end of the line names a committed snapshot read only "
                        "when the connection's ${VAR} is unset. The "
                        "certificate records each load under sources "
                        "(connection, rows, fingerprint, loaded_at, method: "
                        "scanner | arrow | pandas, source_fallback: csv when "
                        "the snapshot stood in) and "
                        "`tracebi verify --contracts` re-reads them; in "
                        "Python, tracebi.transforms.load_source(ref, root, "
                        "fallback=) returns the same frame and record for "
                        "contract(..., sources=). Saving back: a line `-- "
                        "sink: <connection>` just above a CREATE OR REPLACE "
                        "TABLE sends that table to the connection through its "
                        "connector's write once every statement ran (`-- "
                        "sink: <connection> only` drops the warehouse copy); "
                        "a bucket is COPY (…) TO 's3://…'; after the fact, "
                        "`tracebi export <table> --to <connection|prefix>` "
                        "(admin; POST /api/tables/{source}/{table}/export) "
                        "writes a warehouse table or view out, recorded as a "
                        "run (kind: export). The sink contract sits "
                        "beside it as <name>.contract.yaml (honoured beside a "
                        ".py too). `tracebi new-transform \"Name\"` scaffolds "
                        "both in the idiom of the project's tier; --python "
                        "scaffolds the escape hatch, notebook-shaped pandas "
                        "(# %% cells) ending in DuckDBConnector(...).write(df, "
                        "table); a literal .ipynb runs too. x.sql and x.py "
                        "together are refused. The contract is what lands: "
                        "named star tables. Not discovered by the server; "
                        "models read the sink. Reference: "
                        "docs/reference/transform-sql.md.",
            },
            {
                "path": "models/",
                "must_define": "model",
                "type": "DataModel",
                "note": "Also loadable without a server: "
                        "tracebi.model_registry.get_model(name). "
                        "A model that failed to load is listed under skipped "
                        "with its error; fix the file and call again (models "
                        "reload when the file changes).",
            },
            {
                "path": "pipelines/",
                "must_define": "runner",
                "type": "PipelineRunner",
                "note": "Also loadable via tracebi.pipeline_registry.get_runner(name). "
                        "Declarative by default: pipelines/<name>.yaml is "
                        "{name, transform, models, reports ('all' or names), "
                        "schedule, description}; it only NAMES the Python "
                        "transform. A .py beside a .yaml of the same name "
                        "wins (the .yaml is refused; see /api/discovery). "
                        "`tracebi new-pipeline` writes YAML (--python for "
                        "the old form); `tracebi migrate pipeline "
                        "pipelines/x.py [--write]` converts a "
                        "model_pipeline(...) runner. `tracebi run-pipeline "
                        "<name>` runs the transform, then builds the "
                        "reports (all of reports/<model>/ by default); the "
                        "app's Refresh data runs the same.",
            },
            {
                "path": "connections/",
                "must_define": "a connections/<name>.yaml per source",
                "type": "connection",
                "note": "{name, type, ...fields}; type is duckdb, csv, sql, "
                        "postgres, mysql, snowflake, bigquery or upload (one "
                        "CSV or Parquet file under inputs/: file). Any value may be "
                        "${ENV_VAR} (the whole value); password, and a url "
                        "that carries credentials, MUST be, or the file is "
                        "refused. ${ENV_VAR:-default} gives a default for "
                        "when the name is set nowhere, checked like a literal "
                        "(a password has none). The variable is read when the "
                        "connection is used (environment, then .env, then the "
                        "project's store: `tracebi secret set NAME`; an unset "
                        "one is an error naming it), never at discovery. A "
                        "model's connector says "
                        "`connection: <name>`. Written by `tracebi connect`, "
                        "or by a signed-in admin's Add a connection on the "
                        "Sources page. agents: {tables: [a, b] | \"*\"} names "
                        "the tables an agent may read (absent: none); "
                        "tracebi.connections.agent_may_read(connection, table) "
                        "is the one check. postgres and mysql say either "
                        "url, or its fields (never both): host, database "
                        "(required), port, user, password (${NAME}; the app and "
                        "`tracebi connect --host` name it "
                        "TRACEBI_<CONNECTION>_PASSWORD), ssl (postgres "
                        "sslmode: disable|prefer|require|verify-full; mysql "
                        "on|off), options (extra query parameters, no "
                        "credential), connect_timeout (seconds); the loader "
                        "builds the URL (tracebi.connections.build_url; "
                        "parse_url is the inverse). snowflake adds "
                        "authenticator: password|externalbrowser|key_pair "
                        "(key_pair reads private_key_path; only password "
                        "needs password). bigquery takes credentials (a "
                        "service-account file path) or credentials_json "
                        "(${NAME}: the key's JSON, kept in the store).",
            },
            {
                "path": "tracebi.yaml",
                "must_define": None,
                "type": "project settings",
                "note": "Optional, at the project root; `tracebi init` writes "
                        "a commented one. engine: {memory_limit (default 1GB), "
                        "threads (min(4, CPUs)), temp_directory (default "
                        "data/.duckdb-tmp), query_timeout_s (default 30)}: the "
                        "limits of the read-only DuckDB connection every model "
                        "query runs in. That connection reads the warehouse and "
                        "nothing else (no file, URL, extension, ATTACH or "
                        "COPY; the settings are locked); an Explore, Ask or "
                        "agent query stops at query_timeout_s with an error "
                        "naming it. warehouse: {tier: file (default, location "
                        "data/warehouse.duckdb) | object (a Parquet file per "
                        "table under s3://, gs:// or a directory; endpoint, "
                        "region, url_style, and key_id / secret that MUST be "
                        "${ENV_VAR}) | remote (a DuckDB database to ATTACH, "
                        "md:…), location}: where transforms sink and models "
                        "read. A model's connector `type: warehouse` and a "
                        "transform's `sink_target()` (tracebi.project_config) "
                        "follow it, so neither names a path; the certificate "
                        "records engine_version and, on the object tier, each "
                        "file's ETag, and a rewritten file reads stale. "
                        "Reference: docs/reference/tracebi-yaml.md.",
            },
            {
                "path": "reports/",
                "must_define": None,
                "type": "report package",
                "note": "A report is a PACKAGE, in a folder named for its model: "
                        "reports/<model>/<name>/ (report.json + "
                        "template.html, plus optional style.css / script.js), "
                        "or a reports/<model>/<name>.json spec compiled into "
                        "one. Scaffold with `tracebi new-report "
                        "\"<model>/<name>\"`. There "
                        "is one renderer: a registered report with no package "
                        "is refused, never served as a weaker page.",
            },
        ],
        "rules": [
            "Files starting with '_' are skipped (that is why _template.py is ignored).",
            "models/ load only .py (and .ipynb) and pipelines/ only .py at the top "
            "level, plus the declarative .yaml/.yml forms (models also .json). "
            "reports/ is scanned recursively: a subdirectory that is not a "
            "package is a folder, and a report inside it is named by its path "
            "(`finance/weekly_summary`) everywhere — `tracebi report build "
            "finance/weekly_summary`, output/finance/weekly_summary.html, the "
            "web URL. Code modules in reports/ load only from the top level.",
            "A folder may hold a `_folder.yaml` granting view / build / publish / "
            "manage to sign-in groups or names (the nearest file wins; none "
            "means roles decide). A report in a folder you cannot view is "
            "absent from list_reports and every read of it answers as if it did "
            "not exist; a build or publish refusal names the permission needed. "
            "Reference: docs/reference/folder-yaml.md.",
            "Registration happens as an import side effect, so module scope must "
            "be safe to execute at server startup.",
            "A file that raises on import is skipped with a warning, not an error — "
            "list_models (skipped) and list_reports name what failed to load. "
            "The CLI is `tracebi validate`.",
        ],
        "env_overrides": [
            "TRACEBI_MODELS_DIR", "TRACEBI_PIPELINES_DIR",
            "TRACEBI_CONNECTIONS_DIR", "TRACEBI_REPORTS_DIR", "TRACEBI_LIBRARY_MOUNTS",
            "TRACEBI_TRANSFORMS_DIR",
            "TRACEBI_SCHEDULED_DIR", "TRACEBI_APP", "TRACEBI_DOCS_DIR",
        ],
    }


def _schedule() -> dict:
    """A recurring report: the report.json ``schedule`` block
    (``tracebi/schedule.py``)."""
    return {
        "rule": "A report that repeats declares when it runs and who "
                "receives it in its own report.json, so a reviewer approves "
                "when and to whom in the same diff as what. One run is "
                "build → verify → email → record. A failed refresh or build "
                "is retried twice by default. A build that does not "
                "verify is recorded 'refused' and nothing is sent. "
                "A Slack file upload runs on a successful send when "
                "TRACEBI_SLACK_BOT_TOKEN and TRACEBI_SLACK_CHANNEL are "
                "both set.",
        "block": "\"schedule\": {\"cron\": \"0 9 * * MON\", "
                 "\"timezone\": \"America/New_York\", "
                 "\"to\": [\"cfo@example.com\"]}",
        "fields": "cron: five fields, required. timezone: IANA name, "
                  "default UTC. to: email list, optional; without it a run "
                  "sends no email. Slack file delivery is delivery_env, "
                  "not a schedule field. refresh: "
                  "optional {\"transforms\": [...], \"pipelines\": [...]} "
                  "run first, in that order, each in a fresh process; a "
                  "failed step (a sink contract included) fails the run "
                  "before anything is built or sent. retries: integer 0 to "
                  "5, default 2. A failed refresh or build is retried that "
                  "many times, waiting 60s then 300s, and 300s for any "
                  "further retry; 0 disables. A build that does not "
                  "verify, and a delivery failure, are not retried. "
                  "owner: one email address, optional. A run recorded "
                  "failed, refused, or empty emails that address a "
                  "plain-text alert and does not send the report. Without "
                  "owner, nothing is alerted. burst: optional; one build "
                  "per filter value, each with its own recipients — see "
                  "burst. Any other field fails when the package loads.",
        "burst": "Optional object on the schedule block. One build per "
                 "filter value, each emailed to its own recipients. "
                 "{\"filter\": {\"dim_region.region\": {\"in\": [\"EMEA\", "
                 "\"APAC\"]}}, \"to\": {\"EMEA\": [\"emea@example.com\"], "
                 "\"APAC\": [\"apac@example.com\"]}}. filter is one "
                 "dimension key (dim.attribute) mapped to a list or "
                 "{\"in\": [...]}. Each value is built with that single "
                 "value as a filter, applied through the same "
                 "query_under_selection path a kept selection uses, on "
                 "every binding whose model has the dimension. Recipients "
                 "are burst.to[value]. A value missing from to is skipped "
                 "and recorded, and is not sent to the top-level to. burst "
                 "without a to object is refused when the package loads. "
                 "Each slice is verified on its own. A refused, empty, or "
                 "failed slice is not sent; the others still are. One "
                 "parent run records every slice (value, status, "
                 "recipients, output path). If any slice failed, came back "
                 "empty, or was refused, one owner alert names those slices.",
        "commands": "tracebi schedule list | run <name> [--no-send] | serve "
                    "(one run: refresh → build → verify → email → record). "
                    "Runs are recorded in tracebi_runs (kind schedule). An existing "
                    "output/schedule_runs.jsonl is imported once. Status "
                    "delivered | built | refused | failed | empty, plus "
                    "attempts. A figure binding that returned zero rows is "
                    "recorded empty and is not sent. "
                    "serve needs "
                    "tracebi[pipeline]; cron can call `schedule run` instead.",
        "delivery_env": "TRACEBI_SMTP_URL, TRACEBI_SMTP_FROM; "
                        "TRACEBI_SLACK_WEBHOOK is a text ping. "
                        "TRACEBI_SLACK_BOT_TOKEN and TRACEBI_SLACK_CHANNEL "
                        "together upload the scheduled HTML and manifest "
                        "(report name, rendered_at, verify verdict, up to "
                        "five headline value figures). A Slack failure is "
                        "recorded on the run and not retried. --no-send "
                        "records the intent and does not call Slack.",
    }


def _init_templates() -> dict:
    """Named starters for ``tracebi init --template``.

    The list is the catalog in ``tracebi.project_templates``, so a new
    template shows up in ``tracebi context`` when it is registered there.
    """
    from tracebi.project_templates import known_template_names, template_catalog

    return {
        "what": "tracebi init --template <name> scaffolds a working "
                "mini-project — sample data, a sink contract, a model, and "
                "two reports — that an agent re-points at real tables. "
                "tracebi init with no --template scaffolds the sample "
                "orders dashboard.",
        "cli": "tracebi init <project> --template saas-metrics | "
               "tracebi init <project> --template sales-pipeline",
        "aliases": "saas_metrics is accepted for saas-metrics; "
                   "sales_pipeline is accepted for sales-pipeline. Any other "
                   "name is refused and the error lists the known templates.",
        "names": known_template_names(),
        "known": template_catalog(),
    }


def _analyst_knowledge() -> dict:
    """The good-practice curriculum, as a cheap index (slug/title/when) plus how
    to pull a lesson in full. Present in BOTH tiers, brief included — teaching an
    agent to reach for the right lesson is exactly what the lean loop needs, and
    the index is small. The bodies live in ``tracebi/knowledge/lessons`` and are
    fetched on demand (``tracebi://knowledge/{slug}``, the same text as
    ``tracebi knowledge <slug>``), so this never bloats the payload."""
    from tracebi.knowledge import index

    return {
        "what": "Good-practice lessons for doing the analysis RIGHT, not just "
                "producing a number — and, in the 'design-' lessons, for a report "
                "page a reader understands at a glance. Reach for the one whose "
                "'when' matches the decision you are making.",
        "fetch": "The lesson index (slug, title, when) is already in this "
                 "payload under lessons. Read a body at "
                 "tracebi://knowledge/{slug} — the same text as "
                 "tracebi knowledge <slug> (or the tracebi-analyst / "
                 "tracebi-designer skills).",
        "lessons": index(),
    }


def _named_themes() -> list[str]:
    from tracebi.reports.stack import named_themes
    return named_themes()


def describe(brief: bool = False) -> dict:
    """
    Return TraceBi's vocabulary as plain, JSON-serializable data.

    Generated from the code, so it stays correct as the framework changes.

    ``brief=True`` returns the token-lean tier (~40% of the full payload):
    the semantic model, the figure/presentation grammar, transform
    contracts, and the project conventions — everything the package-first
    authoring loop needs. Omitted: the legacy section classes, the DataSet
    verb catalogue, and the Python cheat sheets, which matter only when
    writing Python against the library directly; the brief payload names
    them so an agent knows more exists.
    """
    import pandas as pd

    from tracebi.model.data_model import DataModel
    from tracebi.model.dataset import DataSet
    from tracebi.reports.report import Report

    # The cheat sheets are static text, but read them off real instances
    # rather than bypassing __init__ — a throwaway object is cheap and
    # cannot break if these ever start reading state.
    full: dict = {
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
                {
                    "kind": "share",
                    "args": ["share"],
                    "example": "add_measure('revenue_share', share='revenue', "
                               "format='percent')",
                    "note": "% of total — each row's value over the total of the "
                            "named measure across the WHOLE result (before any "
                            "limit), computed governed at query time. This is the "
                            "share-of-total a report.py used to compute "
                            "ungoverned; a governed query keeps its trace.",
                },
                {
                    "kind": "rank",
                    "args": ["rank", "partition_by"],
                    "example": "add_measure('rev_rank', rank='revenue'); "
                               "add_measure('rank_in_region', rank='revenue', "
                               "partition_by='dim_region.region')",
                    "note": "1..N position ordered by the named measure "
                            "descending (rank 1 = largest), with a total "
                            "tie-break so it is reproducible. partition_by (one "
                            "or more dimension refs, which must be in the query's "
                            "dimensions) restarts the rank per group — rank 1 per "
                            "group; pair it with having={'rank_in_region':{'lte': "
                            "3}} for TOP-N-PER-GROUP (top 3 per region), which a "
                            "global order_by+limit cannot express.",
                },
                {
                    "kind": "running",
                    "args": ["running", "partition_by"],
                    "example": "add_measure('cum_share', running='revenue_share', "
                               "format='percent')",
                    "note": "cumulative (running) sum of the named measure, "
                            "largest-first — the Pareto/concentration direction. "
                            "running of a share measure is the cumulative % of "
                            "total. rank + share + running(share) is the whole "
                            "concentration table, governed — what report.py did. "
                            "partition_by restarts the cumulative per group.",
                },
                {
                    "kind": "combine",
                    "args": ["measure_expr"],
                    "example": "add_measure('net_new', measure_expr='purchases - sales', "
                               "format='currency0')",
                    "note": "Arithmetic over OTHER measures (names and numbers, "
                            "+ - * / and parentheses), computed after aggregation "
                            "from their totals, so a combination of governed "
                            "numbers. It takes no agg of its own. A zero "
                            "denominator gives NaN. Used for net new assets, "
                            "spread between two filtered totals, and the like.",
                },
                {
                    "kind": "period_end",
                    "args": ["period_end"],
                    "example": "add_measure('aum', period_end=('balance', "
                               "'dim_date.as_of_date'))",
                    "note": "semi-additive (point-in-time) measure: a balance — "
                            "AUM/NAV/headcount/inventory — summed across non-time "
                            "dimensions but taken at the LATEST snapshot over "
                            "time, never summed across snapshots (Jan AUM + Feb "
                            "AUM is not AUM). Group by a time grain to get the "
                            "period-end series. Assumes entities snapshot on "
                            "common dates. A plain sum of a stock-named measure "
                            "is refused (pass allow_additive=True for a genuine "
                            "flow). See the semi-additive lesson.",
                },
                {
                    "kind": "offset",
                    "args": ["offset"],
                    "example": "add_measure('rev_ly', offset=('revenue', "
                               "'year', 1))",
                    "note": "period-over-period: the base measure's value one "
                            "(unit, n) EARLIER — the prior period's value. unit "
                            "is a time grain (year/quarter/month/week/day). The "
                            "query must group by exactly one declared time grain "
                            "(the period axis). Compares against periods PRESENT "
                            "in the result, so include the comparison period — "
                            "restrict the display with order_by+limit (after the "
                            "shift), not a filter (WHERE removes the prior). See "
                            "the period-over-period lesson.",
                },
                {
                    "kind": "growth",
                    "args": ["growth"],
                    "example": "add_measure('rev_yoy', growth=('revenue', "
                               "'year', 1), format='percent')",
                    "note": "period-over-period GROWTH: (current - prior) / "
                            "prior, where prior is the base one (unit, n) earlier "
                            "— YoY with ('revenue','year',1), QoQ/MoM by unit. "
                            "Same time-grain requirement and same "
                            "compares-against-what's-in-the-result rule as offset.",
                },
                {
                    "kind": "to_date",
                    "args": ["to_date"],
                    "example": "add_measure('rev_ytd', to_date=('revenue', "
                               "'year'))",
                    "note": "to-date cumulative (YTD/QTD/MTD): a running total "
                            "from the start of the reset period (year/quarter/"
                            "month/week) up to the current period, over the "
                            "query's finer time grain — YTD revenue in March is "
                            "Jan+Feb+Mar. The query must group by exactly one time "
                            "grain, and it must be FINER than the reset period "
                            "(YTD/QTD over monthly; MTD needs a daily/weekly "
                            "grain). See the year-to-date lesson.",
                },
            ],
            "time_grains": {
                "declare": "model.add_time_grain(dim, name, source, grain)",
                "grains": sorted(_TIME_GRAINS),
                "note": "Group by a date rolled up to a grain (month/quarter/…) "
                        "— a governed date_trunc, returned as the period's "
                        "label (2026, 2026-Q1, 2026-03, 2026-W09, 2026-03-14). "
                        "Declared on a dimension over a "
                        "date column, referenced as dim.name like any attribute; "
                        "a model's declared grains show under its dimensions' "
                        "'derived'. This is 'group by month' without dropping to "
                        "report.py or pre-baking the bucket in the transform.",
            },
            "value_bins": {
                "declare": "model.add_value_bins(dim, name, source, edges, "
                           "labels=None)",
                "note": "Group by a BAND of a numeric dimension column (credit "
                        "score, age, vintage) — a governed CASE over ranges. N "
                        "edges make N+1 bands; referenced as dim.name like any "
                        "attribute. A NULL source groups as NULL, not the top "
                        "band. Bands sort lexicographically by label, so choose "
                        "labels that sort if magnitude order matters. Groupable, "
                        "not filterable — filter on the source column. 'group by "
                        "band' without report.py or a pre-baked bucket column.",
            },
            "measure_filters": {
                "declare": "model.add_measure(name, column=..., agg=..., "
                           "filters={col: value}); YAML: a filters: mapping on "
                           "the measure",
                "applies_to": ["simple", "expression"],
                "example": "add_measure('purchases', column='amount', agg='sum', "
                           "filters={'activity_type': 'purchase'})",
                "note": "A per-measure WHERE inside the aggregation, so only this "
                        "measure sees the matching rows. The query's own filters "
                        "still narrow every measure in it, and a ratio or share of "
                        "filtered measures is a ratio of their filtered totals. "
                        "The same filter vocabulary as a query's filters over the "
                        "fact's own columns (equality, lists, operator dicts, "
                        "or/and groups); dimension references are refused. A "
                        "column the fact lacks is refused by name at execution. "
                        "The stamped lineage and the trace carry the filter, and "
                        "verify re-runs it: changing it in the model shows as "
                        "drift.",
            },
            "measure_labels": {
                "declare": "model.add_measure(name, ..., label='Share of fair "
                           "value'); YAML: label: on the measure",
                "note": "The name people read for a measure, where the app "
                        "shows it (Ask's tokens, its answers and definitions). "
                        "Without one the app humanises the identifier "
                        "(fv_share reads 'Fv share'). Presentation only: a "
                        "label never changes a number, and queries and "
                        "bindings still name the measure by its identifier.",
            },
            "semantic_words": {
                "declare": "YAML: description: and synonyms: [..] on the model, "
                           "a dimension, an attribute ({name, label, "
                           "description, synonyms} in place of the plain "
                           "column name) and a measure; questions: [..] on the "
                           "model. Python: DataModel(name, description=, "
                           "synonyms=, questions=), add_dimension(..., "
                           "description=, synonyms=), add_measure(..., "
                           "description=, synonyms=)",
                "example": "synonyms: [market value, FV] on fair_value; "
                           "questions: ['Which sectors hold the most fair value?']",
                "note": "The model is the semantic layer: description says what "
                        "a thing means, synonyms the other words people use for "
                        "it, questions example questions the model answers (Ask "
                        "offers them as starting chips). They are words for "
                        "people and agents: nothing computes from them, and a "
                        "query still names a measure and an attribute by its "
                        "identifier. Match a person's word to a synonym, then "
                        "query the identifier. describe_model and get_context "
                        "(model=) return them; the brief tier keeps descriptions "
                        "and drops synonyms.",
            },
            "aggregations": sorted(_AGG_FUNCS) + ["p<N> (percentile, e.g. p90)"],
            "aggregations_note": "median and stddev summarize a distribution's "
                                 "shape — a mean hides skew and tails, so use "
                                 "them for returns/P&L/sizes/spreads (see the "
                                 "summarize-a-distribution lesson). count counts "
                                 "non-null rows; nunique counts distinct values. "
                                 "p<N> is a percentile (p50 = median, p90/p95/p99 "
                                 "the tail a mean and even a median hide — worst "
                                 "marks, largest drawdowns); any p0–p100.",
            "filter_operators": list(FILTER_OPS),
            "filter_forms": [
                {"form": "{'status': 'shipped'}", "means": "equality"},
                {"form": "{'region': ['NE', 'SE']}", "means": "in"},
                {"form": "{'revenue': {'gte': 1000}}", "means": "explicit operator"},
                {"form": "{'dim_customer.region': 'West'}",
                 "means": "filter on a dimension attribute"},
                {"form": "{'or': [{'sector': 'Tech'}, {'rating': 'AAA'}]}",
                 "means": "OR of condition groups — sector=Tech OR rating=AAA. "
                          "'and' groups the same way. Every OTHER key in the "
                          "same dict AND-s with the group, and groups nest, so "
                          "{'status':'active', 'or':[A, B]} is status=active AND "
                          "(A OR B). Use 'in' for OR over one column's values; "
                          "use 'or' for OR across DIFFERENT columns/operators."},
            ],
            "having": {
                "means": "post-aggregation filters (HAVING) on result columns — "
                         "measure names and ratios — applied AFTER grouping. "
                         "`filters` are WHERE (before aggregation), so a filter "
                         "on a measure column changes the group totals; `having` "
                         "keeps groups by their aggregated value with totals "
                         "intact.",
                "example": "having={'revenue': {'gte': 250}}  # groups whose "
                           "TOTAL revenue >= 250 (not raw rows >= 250)",
                "operators": "same spellings and operators as filters",
            },
            "ordering": {
                "order_by": [
                    {"form": "[{'column': 'fair_value', 'desc': True}]",
                     "means": "a LIST of sort keys, each a result column — "
                              "dimension refs, measure names, ratio measures "
                              "included; earlier keys sort first"},
                    {"form": "['-fair_value']",
                     "means": "string shorthand in the list: '-col' descending, "
                              "'col' ascending"},
                ],
                "order_by_note": "order_by is a LIST of keys. A lone key — "
                                 "'-fair_value' or {'column':..} — is accepted "
                                 "and wrapped, but the canonical form is a list.",
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
                "Aggregating a rate-named measure (*_pct, *_bps, *_yield, "
                "anything 'weighted') with sum/mean/avg is REFUSED — you do not "
                "additively combine per-row rates (summing is meaningless, "
                "averaging overweights small rows); min/max stay fine. Declare a "
                "ratio measure instead (ratio of totals); see the ratio-of-totals "
                "lesson. Override with allow_rate_agg=True only when it is truly "
                "correct.",
                "The same guard also fires at QUERY time on values, not just the "
                "name: an additive aggregation (sum/mean) of a column whose "
                "values look like per-row ratios — floating, centred near 1.0 "
                "(e.g. mark_cost = fair_value/cost) — is refused even when the "
                "name matches no rate token. Declare a ratio measure, or pass "
                "allow_rate_agg=True on the measure or the query if the column is "
                "genuinely additive.",
                "Summing a stock-named measure (aum, nav, balance, headcount, "
                "inventory) with agg='sum' is REFUSED — a point-in-time balance "
                "double-counts when summed across snapshots. Declare a period_end "
                "(semi-additive) measure instead; see the semi-additive lesson. "
                "Override with allow_additive=True only for a genuine flow.",
            ],
        },
        "number_formats": dict(NAMED_NUMBER_FORMATS),
        "presentation": _presentation(),
        "transform_contracts": _transform_contracts(),
        "conventions": _conventions(),
        "schedule": _schedule(),
        "templates": _init_templates(),
        "connect": {
            "what": "Point a project at a warehouse it did not sink. Tests "
                    "the connection, writes the secret to .env (never "
                    "printed), and writes connections/<name>.yaml, where "
                    "the secret appears only as a ${ENV_VAR} reference "
                    "(read from the environment, else the project's .env, "
                    "when the connection is used; .env is never loaded into "
                    "os.environ). --python writes the legacy "
                    "models/_connections/<name>.py instead. "
                    "`tracebi migrate connection <that .py> [--write]` "
                    "converts one.",
            "cli": "tracebi connect <name> --kind postgres|mysql|snowflake|bigquery|duckdb "
                   "[kind flags] [--test/--no-test] [--force] [--agents a,b|all]; "
                   "tracebi connect <name> --agents a,b|all (only the allowlist); "
                   "tracebi connect <name> --test (test an existing one); "
                   "tracebi connect --list",
            "kinds": {
                "postgres": "--url postgresql://..., or --host H --database D "
                            "[--port] [--user] [--password-stdin | --password-var NAME] "
                            "[--ssl require] (the file holds the fields)",
                "mysql": "as postgres; --ssl on|off",
                "snowflake": "--account --user --password --warehouse "
                             "--database --schema [--role]",
                "bigquery": "--project --dataset [--credentials PATH]",
                "duckdb": "--database PATH",
            },
            "env": "TRACEBI_<NAME>_URL, TRACEBI_<NAME>_PASSWORD, and the "
                   "other constructor fields, uppercase name. An existing "
                   "key is kept unless --force.",
            "then": "tracebi new-model \"<Name>\" --from <name> --tables a,b,c "
                    "drafts a star schema from column metadata only (no row "
                    "scan). A table named fact_* or with numeric non-key "
                    "columns and *_id/*_key columns that match another "
                    "listed table's key is a fact; the rest are dimensions. "
                    "Edit every line marked # DRAFT: review.",
            "dbt": "tracebi import dbt <path> drafts models/<name>.py from a "
                   "dbt manifest.json (a project root with target/manifest.json, "
                   "or the file). It does not run dbt and does not load .env. "
                   "--connection <name> wires connections/<name>.yaml. "
                   "--schema keeps one schema. Relationships and measures are "
                   "# DRAFT: review comments — foreign keys are not invented.",
        },
        "warehouse": {
            "what": "Column names and types of a sunk table, from connector "
                    "metadata. Never a row scan, and never a substitute for "
                    "the model. A connector that raises is reported in place "
                    "(name, type, error: exception type plus the first "
                    "message line); the others still list.",
            "mcp": "describe_table(table='', connector='')",
            "cli": "tracebi warehouse tables [--connector NAME] [--table T] [--json]",
            "when": "Call describe_table before writing a model or an ad-hoc "
                    "measure, so column names come from the catalog instead "
                    "of from an error.",
        },
        "source_onboarding": {
            "mcp": "list_connections(), list_source_tables(connection), "
                   "describe_source_table(connection, table, sample=20), "
                   "propose_transform(name, sql, contract_yaml, note), "
                   "export_table(source, table, to)",
            "sop": "docs/agents/sop-onboarding.md",
            "what": "From a connection to a model, when none exists yet. A person "
                    "sets up the connection in the app and ticks which tables "
                    "agents may read (agents: {tables: [a, b] | '*'} in "
                    "connections/<name>.yaml; absent means none). "
                    "list_connections shows each connection's agent_tables; "
                    "list_source_tables lists those tables with columns and row "
                    "estimates; describe_source_table gives columns, a profile "
                    "and a sample (at most 500 rows). A table agents may not "
                    "read is 'not found', as a missing one is. "
                    "propose_transform stores transforms/<name>.sql and "
                    "<name>.contract.yaml as one code request (the same review "
                    "as tracebi push): checked first (a new name, SQL that "
                    "parses in DuckDB, every -- source: a table agents may "
                    "read, a contract with at least one check); nothing runs "
                    "until an admin approves it in the app (review_url), and "
                    "approving runs it once. Then start_draft(kind='models') "
                    "over the sunk tables. export_table (admin) writes a "
                    "warehouse table or view to a connection or an object "
                    "prefix (<prefix>/<table>.parquet) and records an export run.",
        },
        "pointing": {
            "mcp": "workbench_state(report) -> pointing",
            "http": "POST|GET|DELETE /api/reports/<name>/workbench/pointing "
                    "(only when the server runs with TRACEBI_DEV_MODE=1)",
            "what": "What the human is pointing at in the web app's Build "
                    "mode (`tracebi dev <name>` opens the report with the "
                    "workbench beside it): a figure (id, binding, cell) or an "
                    "element (selector, text, section), or null. It is what "
                    "'this' or 'here' means in their message. They instruct "
                    "in chat (or leave a note in the panel, which is an open "
                    "pin); the app is where they watch (the report "
                    "re-rendered on each save, a timeline of what changed, "
                    "your exhibits, the data each binding reads, and checks "
                    "for unbound figures, unused bindings and numbers typed "
                    "outside figures). Dev-state under "
                    ".tracebi/workbench/<report>/; never in a build or a "
                    "trace.",
        },
        "project_feed": {
            "mcp": "workbench_state() with no report",
            "http": "GET /api/workbench/project, POST /api/workbench/project/note "
                    "(only when the server runs with TRACEBI_DEV_MODE=1)",
            "what": "Before a report is open, `tracebi dev` opens the app on "
                    "Data and the human sees your show() exhibits there "
                    "(From your agent) and leaves notes. While it is up any "
                    "script in the project can call tracebi.workbench.show() "
                    "with no setup. Your gateway work posts there too: each "
                    "query_model result as a table, and each build_report / "
                    "render_report_spec as one line (refusals included). "
                    "Dev-state under .tracebi/workbench/_discovery/.",
        },
        "pins": {
            "cli": "tracebi report pins <name> [--resolve ID] [--note TEXT]",
            "mcp": "resolve_pin(report, pin_id, note='')",
            "what": "Lists open pins. --resolve moves one into the resolved "
                    "list in pins.json (resolved_at, resolved_by, the agent's "
                    "note). Nothing is deleted. Writes only pins.json. "
                    "workbench_state then shows open pins only, plus "
                    "resolved_count.",
        },
        "drafts": {
            "push": "From a laptop: tracebi push <paths> --server <url> --note 'why' "
                    "(after tracebi login). Report packages and models/<name>.yaml|.json "
                    "become the person's drafts; transforms/, pipelines/, "
                    "models/<name>.py, connections/ and report.py become one code "
                    "request (POST /api/code-requests) that an admin approves in the "
                    "app: the files go in and the pipelines they touch run once on "
                    "the server. Data files are refused.",
            "mcp": "list_drafts(), start_draft(kind, path, from_published=False), "
                   "read_draft(kind, path), write_draft_file(kind, path, file, content), "
                   "preview_draft(kind, path), model_impact(path), "
                   "publish_draft(kind, path, note='', accept_impact=False, folder=''), "
                   "list_publish_requests(status=''), "
                   "decide_publish_request(request_id, approve, note='')",
            "http": "GET /api/drafts, GET /api/drafts/{owner}/{kind}/{path}/files|preview|version|impact, "
                    "POST /api/drafts/{owner}/{kind}/{path}/publish (body: note, accept_impact, folder), DELETE /api/drafts/{owner}/{kind}/{path}, "
                    "GET /api/publish-requests, POST /api/publish-requests/{id}/approve|reject",
            "what": "Remote drafts: a report or model written before it goes live. "
                    "Drafts live under drafts/<owner>/ (TRACEBI_DRAFTS_DIR, default "
                    "drafts/). A report draft holds only report.json, template.html, "
                    "style.css and script.js. A model draft is one models/<name>.yaml or "
                    ".json, one form at a time (see model_json). preview_draft "
                    "renders against the published models plus the owner's draft models, in memory, and returns "
                    "the url where the person sees it. publish_draft validates "
                    "first: a report must render against the PUBLISHED models only, "
                    "and a model must compile. It keeps the version it replaces "
                    "under .tracebi/history/, copies the draft into the library, "
                    "and records a publish run with the actor. The draft is kept. "
                    "A report publishes to `folder` (a library path, created if "
                    "needed; default its own path). With Publish on that folder it "
                    "is published (history records who and when); with only Build "
                    "(its _folder.yaml) the answer is status='requested': a publish "
                    "request, stored as a file under drafts/_requests/, that someone "
                    "with Publish there approves (the snapshot taken at request time "
                    "is published; the history records requester, approver, time) "
                    "or rejects with a note, via decide_publish_request or the app. "
                    "The requester cannot decide their own. A folder whose "
                    "_folder.yaml says `accepts: checkable` refuses a report with a "
                    "report.py or a figure no query can re-run, at publish and at "
                    "request, naming why; `accepts: labelled` is the default. "
                    "Every signed-in person also has a folder of their own, "
                    "`my-published/<their sign-in name>` (shown in the app as My "
                    "published), where they hold Publish: publish there with "
                    "folder='my-published/<name>' to share or schedule a report "
                    "without a shared folder. Only they see it unless a "
                    "_folder.yaml inside it grants View; the app only shows "
                    "permissions, so a folder is shared by editing that file. "
                    "A session with no sign-in identity (the shared token, the "
                    "CLI, an app without sign-in) has no personal folder and "
                    "holds Manage everywhere instead. "
                    "A MODEL publish first runs the impact check (model_impact): "
                    "the recorded queries of every published report that reads the "
                    "model are re-run against the draft and compared with each "
                    "report's last build. Each report is unchanged, moves (the "
                    "figures, old and new), breaks (the query no longer runs, with "
                    "the error) or not_built (listed, never counted unchanged). If "
                    "any moves or breaks, publish_draft is refused (HTTP 409, MCP "
                    "ok=false, both with the impact) unless accept_impact=true; a "
                    "break needs accepting too, and the accepted impact is recorded "
                    "in the publish run. Show the person model_impact before you "
                    "pass accept_impact. "
                    "A model may declare `owners` (sign-in names). Only an owner "
                    "or an admin may publish a change to it: anyone else is "
                    "refused (HTTP 403, MCP ok=false, naming the owners) but can "
                    "still draft it and read model_impact, then ask an owner to "
                    "publish. Owners are read from the PUBLISHED model, so a "
                    "draft cannot grant itself ownership; no owners, or a brand "
                    "new model, means any analyst may publish. Names only: the "
                    "session carries no group membership to match. "
                    "Python (report.py, models/*.py, transforms, pipelines) cannot "
                    "be drafted remotely: it would run on the server with its "
                    "secrets, so it comes only through a laptop and review. "
                    "script.js is accepted: it runs only in the reader's browser, "
                    "in a sandboxed frame with no network and no access to the "
                    "app, and if it changes a stamped figure's text the trace "
                    "says 'changed on the page by a custom script'. "
                    "list_models and describe_model say draftable per model.",
        },
        "model_json": {
            "file": "models/<name>.yaml (also .yml, or .json)",
            "reference": "docs/reference/model-json.md",
            "what": "A declarative model: the same star schema as a Python "
                    "DataModel, written as one YAML document (comments allowed; "
                    "JSON is the same schema). Top-level keys: name (the identifier, "
                    "equal to the file name), label (optional: what people read "
                    "in lists, e.g. \"Direct Lending Portfolio\"; unset, the name "
                    "title-cased; DataModel(name, label=) in Python), owners (a list "
                    "of sign-in names allowed to publish it; see drafts), "
                    "description, synonyms and questions (the semantic layer's "
                    "words; see semantic_model.semantic_words), connectors, "
                    "tables, relationships, dimensions, facts, measures, "
                    "time_grains (dimension, name, source, grain) and value_bins "
                    "(dimension, name, source, edges, labels). Loading it reads "
                    "no rows, and a remote agent can draft it without the server "
                    "running any code. A query opens the warehouse, as with a .py "
                    "model. A model is one file: a .py beside a .yaml/.json of "
                    "the same name wins; two declarative forms of one name are "
                    "both refused (see /api/discovery). A repeated YAML key is an "
                    "error. `tracebi new-model` writes YAML (--python for the old "
                    "form); `tracebi migrate model models/x.py [--write]` "
                    "converts a Python model and leaves the .py in place.",
        },
        "spreadsheet": {
            "mcp": "build_report(report, output_dir='output', format='xlsx')",
            "fetch": "fetch_artifact(path=<the xlsx_path build_report "
                     "returned>) — encoding is base64, "
                     "content_type is the spreadsheet media type. "
                     "Every other suffix stays refused.",
            "note": "The spreadsheet carries no trace and is not "
                    "verifiable. format='xlsx' still writes the HTML and "
                    "manifest beside the workbook; those are the checkable "
                    "artifact. The result's spreadsheet_note says so.",
        },
        "pdf": {
            "cli": "tracebi report build <name> --format pdf",
            "mcp": "build_report(report, output_dir='output', format='pdf')",
            "web": "GET /api/reports/{name}/download?format=pdf — the last "
                   "build, printed.",
            "fetch": "fetch_artifact(path=<the pdf_path a pdf build "
                     "returned>) — encoding is base64, "
                     "content_type is application/pdf.",
            "note": "The PDF is a print of the built HTML (headless "
                    "Chromium, so charts render). It carries no trace "
                    "and is not verifiable. format='pdf' still writes the "
                    "HTML and manifest; those are the checkable artifact. "
                    "The result's pdf_note says so. Needs "
                    "pip install 'tracebi[pdf]' and "
                    "python -m playwright install chromium.",
        },
        "analyst_knowledge": _analyst_knowledge(),
    }
    if not brief:
        return full
    # The token-lean tier: everything the package-first loop needs, with a
    # pointer at what was omitted so more can be fetched deliberately.
    omitted = ("cheat_sheets", "report_sections", "dataset_verbs")
    out = {k: v for k, v in full.items() if k not in omitted}
    out["brief"] = {
        "omitted": list(omitted),
        "note": "Legacy section classes, DataSet verbs, and Python cheat "
                "sheets — needed only when writing Python against the "
                "library directly. Fetch the full vocabulary (no --brief / "
                "brief=false) when you do.",
    }
    return out


def describe_model(model, brief: bool = False) -> dict:
    """
    Describe one model's own vocabulary — its tables, relationships,
    facts, dimensions and declared measures, with the semantic layer's words
    (descriptions, synonyms, example questions). ``DataModel.info()``, here
    so every consumer has one entry point: ``tracebi context --model``, the
    gateway's ``get_context`` and ``describe_model``, and the app's
    ``GET /api/models/{name}/context`` all return this, so the page shows the
    exact text an agent receives.

    ``brief=True`` (the token-lean tier) keeps descriptions and questions and
    drops synonyms.
    """
    info = model.info()
    if not brief:
        return info
    info.pop("synonyms", None)
    for d in info.get("dimensions", []):
        d.pop("synonyms", None)
        for about in d.get("attribute_info", {}).values():
            about.pop("synonyms", None)
    for m in info.get("measures", []):
        m.pop("synonyms", None)
    return info


def to_json(indent: Optional[int] = 2) -> str:
    """``describe()`` rendered as a JSON string."""
    import json
    return json.dumps(describe(), indent=indent, default=str)
