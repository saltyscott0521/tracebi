"""
Template-package renderer (architecture §2 lane B, §8-M1).

A *freeform package* is a directory ``reports/<name>/`` in which the analyst
draws the whole page — the built-in section renderers are not involved:

    report.json    declarative data bindings (model + query per name)
    template.html  a Jinja2 page shell the analyst controls
    style.css      the page's stylesheet
    script.js      client-side code that reads the embedded data and draws
    report.py      OPTIONAL escape hatch — arbitrary Python that computes the
                   drawn data from the stamped bindings (architecture §8-M3)

**The escape hatch (report.py).** Some data the declarative query surface
cannot express — several queries combined, a window function, an algorithm.
When a package includes ``report.py`` with a ``build(inputs) -> {name:
DataFrame}`` function, the ``data`` bindings become its *stamped inputs*
(resolved via ``model.execute``, so query-reproducible) and its *outputs* are
embedded beside them. Verifiability is carried **per binding**
(report-architecture-v2 §2.1): the declared bindings stay embedded with
``verifiable: true`` — a report.py in the directory does not poison them —
while each output is run through the same embed/fingerprint kernel (the
canonical triple is embedded and hashed, so ``verify --file`` catches
tampering of it) but carries no query, so ``verify_manifest`` classifies it
UNVERIFIABLE and the receipt says the number is python-derived and not
query-reproducible. The honesty rule (§4): inputs stamped and green-eligible,
outputs not replay-proved, never green.

This module is thin orchestration over the existing kernel — it adds no new
rendering primitive. For each binding it calls the M0 :func:`stamp` helper
(``model.execute`` stamps query+model+input fingerprints into lineage), builds a
:class:`Report` of synthetic carrier sections so the manifest-first receipt
fingerprints every binding through the ordinary ``to_manifest_dict`` path, then
renders the analyst's ``template.html`` through :class:`HTMLRenderer`.

**Why the data/style/script are injected by string insertion, not template
placeholders (architecture §8-M1).** Jinja2's ``StrictUndefined`` only fails on
a *referenced* undefined name, never an *omitted* one. If the loader depended on
the analyst writing ``{{ head_extra }}`` / ``{{ body_extra }}`` and they forgot,
the page would ship silently with **no data** — the one failure the whole
product exists to prevent. So the ``<style>``, the app ``<script>``, and the
safe embedded-data ``<script>`` blocks are inserted before ``</head>`` /
``</body>`` of the *rendered* HTML. A pure fragment (no ``<html>`` or
``<head>`` token) is wrapped into a minimal document first; a page that
already has those tags but no closing ``</head>`` or ``</body>`` fails
loudly rather than dropping the injection on the floor.

The embedded data carries the M0 canonical triple, so ``tracebi verify --file``
works on the output.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import inspect
from dataclasses import replace
from datetime import datetime
from typing import Optional

import pandas as pd

from tracebi.reports.embed import (
    KNOWN_LIBS, StampedData, data_blocks_html, embed_json, insert_before,
    plan_embed, stamp, stamp_frame,
)
from tracebi.reports.figures import (
    Figure, FigureError, assign_figure_ids, extract_figures, fill_figures,
    lint_numeric_literals, methodology_insertion, strip_stage,
)
from tracebi.reports.base_renderer import _warn_if_unknown_git_sha
from tracebi.reports.figure_markup import (
    TABLE_FORMATS,
    chart_element,
    parse_column_map,
    table_element,
    value_element,
)
from tracebi.reports.html_renderer import HTMLRenderer
from tracebi.reports.report import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION, PARQUET_MANIFEST_SCHEMA_VERSION,
    Report, ReportManifest, TableSection,
)
from tracebi.model.data_model import DataModel, default_label, measure_references
from tracebi.model.sql_calc import SqlQuery, check_read_only
from tracebi.spec import DataRef

#: Files that make up a package. ``report.json`` and ``template.html`` are
#: required; the stylesheet and script are read when present. ``report.py`` is
#: the optional escape hatch (architecture §8-M3).

REPORT_JSON = "report.json"
TEMPLATE_HTML = "template.html"
STYLE_CSS = "style.css"
SCRIPT_JS = "script.js"
REPORT_PY = "report.py"
APP_JSX = "app.jsx"

#: Figure kinds ``{{ figure(...) }}`` can build. ``custom`` is deliberately
#: absent: a custom figure is one the analyst's own script draws, so there is
#: no framework markup to emit for it — it stays hand-written.
BUILDABLE_FIGURE_KINDS = ("value", "chart", "table")


def _validate_figure(name: str, fig, bindings: dict, where: str) -> dict:
    """Structurally check one ``figures`` entry, loudly.

    A figure naming a binding that does not exist is the silent-blank-panel
    failure caught at load instead of at render, where it would surface as an
    empty box the reader cannot distinguish from "no data".
    """
    if not isinstance(fig, dict):
        raise ValueError(
            f"{where}: figure '{name}' must be an object with 'kind' and "
            f"'binding'."
        )
    kind = fig.get("kind")
    if kind not in BUILDABLE_FIGURE_KINDS:
        raise ValueError(
            f"{where}: figure '{name}' has kind {kind!r}; expected one of "
            f"{list(BUILDABLE_FIGURE_KINDS)}."
        )
    binding = fig.get("binding")
    if binding not in bindings:
        raise ValueError(
            f"{where}: figure '{name}' names binding {binding!r}, which is not "
            f"declared in 'data'. Available: {sorted(bindings)}."
        )
    if kind == "value" and not fig.get("cell"):
        raise ValueError(
            f"{where}: figure '{name}' is a value figure and needs 'cell' — "
            f"the column it reads from binding '{binding}'."
        )
    for key in ("labels", "formats"):
        if key in fig and not (isinstance(fig[key], dict) and all(
                isinstance(k, str) and isinstance(v, str)
                and ";" not in k + v and "=" not in k
                for k, v in fig[key].items())):
            raise ValueError(
                f"{where}: figure '{name}' '{key}' must map column names to "
                f"strings, e.g. {{\"fair_value\": \"currency0\"}}.")
    return dict(fig)


#: File types a package may inline from its ``assets/`` folder, by extension.
#: The artifact's CSP allows ``data:`` for images and fonts only.
ASSET_MIME = {
    ".woff2": "font/woff2", ".woff": "font/woff", ".ttf": "font/ttf",
    ".otf": "font/otf", ".svg": "image/svg+xml", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".avif": "image/avif",
}

_CSS_ASSET = re.compile(r"""url\(\s*(['"]?)(assets/[^'")\s]+)\1\s*\)""")
_HTML_ASSET = re.compile(r"""\b(src)=(["'])(assets/[^"']+)\2""")


def _asset_data_uri(directory: str, ref: str, where: str) -> str:
    """``assets/<file>`` inside *directory* → a base64 ``data:`` URI.

    Refuses a path that leaves ``assets/``, a missing file, and a type the
    artifact's CSP would block — each naming the file and the fix, so a
    broken image or font fails the load instead of shipping blank.
    """
    import base64

    root = os.path.realpath(os.path.join(directory, "assets"))
    path = os.path.realpath(os.path.join(directory, ref))
    if not path.startswith(root + os.sep):
        raise ValueError(f"{where}: '{ref}' leaves the package's assets/ folder.")
    ext = os.path.splitext(path)[1].lower()
    if ext not in ASSET_MIME:
        raise ValueError(
            f"{where}: '{ref}' has type '{ext}'; a report can inline "
            f"{sorted(ASSET_MIME)}.")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"{where}: '{ref}' does not exist. Put the file in the package's "
            f"assets/ folder.")
    with open(path, "rb") as f:
        payload = base64.b64encode(f.read()).decode("ascii")
    return f"data:{ASSET_MIME[ext]};base64,{payload}"


def inline_package_assets(text: str, directory: str, where: str) -> str:
    """Replace ``url(assets/…)`` (CSS) and ``src="assets/…"`` (HTML) with
    ``data:`` URIs, so fonts and images ride inside the one self-contained
    file. Anything not under ``assets/`` is left alone."""
    if "assets/" not in text:
        return text
    text = _CSS_ASSET.sub(
        lambda m: f'url("{_asset_data_uri(directory, m.group(2), where)}")',
        text)
    return _HTML_ASSET.sub(
        lambda m: f'{m.group(1)}="{_asset_data_uri(directory, m.group(3), where)}"',
        text)


def _is_tie(a: float, digits: int) -> bool:
    """Mirror tracebi.js ``isTie``: is *a* (>= 0) exactly halfway at *digits*?"""
    # A non-finite value is never a tie. The old ``a >= 1e15`` early-out caught
    # +inf only by accident (inf >= 1e15 is True) and let NaN through — every
    # comparison with NaN is False, so ``nan >= 1e15`` was False and NaN fell
    # into format(nan, '.Nf') → 'nan' → split('.')[1] → IndexError, crashing the
    # build on any null in a formatted numeric column. Make the guard explicit.
    if not math.isfinite(a):
        return False
    if a >= 1e15:
        return False
    frac = format(a, f".{digits + 15}f").split(".")[1]
    return frac[digits] == "5" and frac[digits + 1:].strip("0") == ""


def _py_fixed(v: float, digits: int, *, grouped: bool = False) -> str:
    """Fixed-point matching tracebi.js ``pyFixed`` / ``fixedGrouped`` byte for
    byte. On an exact ``.5`` tie the runtime rounds half-to-even and formats the
    ROUNDED value — so a tie landing on zero prints "0" (no negative sign),
    unlike Python's ``format`` of the original. Mirror that structure exactly.
    """
    if _is_tie(abs(v), digits):
        pow_ = 10 ** digits
        t = v * pow_
        if abs(t) < 4503599627370496:            # 2**52 — the tie is exact
            fl = math.floor(t)
            v = (fl if fl % 2 == 0 else fl + 1) / pow_   # half to even
    spec = f",.{digits}f" if grouped else f".{digits}f"
    return format(v, spec)


def _trim_zeros(s: str) -> str:
    """tracebi.js ``trimZeros``: "1.50" → "1.5", "2.0" → "2"."""
    return s.rstrip("0").rstrip(".") if "." in s else s


def _compact(n: float) -> str:
    """tracebi.js ``fmt(n, "compact")``, byte for byte: K/M/B/T from the
    *rounded* magnitude, so 999,999.99 is "1M", never "1000K"."""
    a2 = abs(float(_py_fixed(abs(n), 2)))
    if a2 >= 1000:
        up = {"K": "M", "M": "B", "B": "T"}
        for div, unit in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
            if a2 >= div:
                mant = _py_fixed(n / div, 1)
                if abs(float(mant)) >= 1000 and unit != "T":
                    div, unit = div * 1000, up[unit]
                    mant = _py_fixed(n / div, 1)
                return _trim_zeros(mant) + unit
    if n % 1 == 0 and abs(n) < 1e15:
        return _py_fixed(n, 0, grouped=True)
    return _trim_zeros(_py_fixed(n, 2, grouped=True))


def _ssr_format(raw, name: str) -> str:
    """Format *raw* byte-identically to the runtime's ``applyNamedFormat``
    (tracebi.js), so a server-rendered number and the hydrated one never differ
    — no flicker on hydrate, and the no-JS reader sees exactly what a browser
    would. Parity is pinned by a node test over a value corpus.
    """
    try:
        num = float(raw)               # the runtime formats toNum(raw): a float64
    except (TypeError, ValueError):
        return str(raw)                # non-numeric: the runtime leaves it raw
    if not math.isfinite(num):
        # The runtime's toNum returns null for a non-finite value (isFinite),
        # so renderBody skips the format and shows the raw token — a NaN cell is
        # blank, an inf cell prints "inf". Mirror that (and never crash): a null
        # in a formatted numeric column now renders empty instead of killing the
        # build. _ssr_cell gives NaN → "", inf/-inf → the string, matching CSV.
        return _ssr_cell(raw)
    if num == 0:
        num = 0.0                      # JS renders no negative zero; -0.0 -> 0.0
    if name == "compact":   return _compact(num)
    if name == "comma":     return _py_fixed(num, 0, grouped=True)
    if name == "decimal":   return _py_fixed(num, 2, grouped=True)
    if name == "currency":  return ("-$" if num < 0 else "$") + _py_fixed(abs(num), 2, grouped=True)
    if name == "currency0": return ("-$" if num < 0 else "$") + _py_fixed(abs(num), 0, grouped=True)
    if name == "currency_compact": return ("-$" if num < 0 else "$") + _compact(abs(num))
    if name == "percent":   return _py_fixed(num * 100, 1) + "%"
    return str(raw)                    # unknown name: applyNamedFormat -> raw


def _ssr_direction(ds, fig) -> str:
    """The classes the runtime's ``markDirection`` puts on a value figure that
    names ``data-tb-direction`` (``up-good`` / ``down-good``): its direction
    from the stamped value's sign, and whether that is good. ``""`` when the
    figure names none or the value is not a number."""
    want = fig.attrs.get("data-tb-direction")
    if want not in ("up-good", "down-good"):
        return ""
    df = ds.to_pandas()
    cell = fig.cell or (str(df.columns[0]) if len(df.columns) == 1 else None)
    if df.empty or cell not in df.columns:
        return ""
    try:
        n = float(df[cell].iloc[0])
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(n):
        return ""
    if n == 0:
        return "tb-flat"
    good = (n > 0) == (want == "up-good")
    return ("tb-up " if n > 0 else "tb-down ") + ("tb-good" if good else "tb-bad")


#: Server-rendered rows per table before the runtime hydrates the full set from
#: embedded data. Generous enough to render normal tables whole; a ceiling so a
#: huge binding cannot re-inflate the page it was embedded as Parquet to shrink.
_SSR_MAX_ROWS = 1000


def _ssr_bar_scales(df, want, cols, numeric) -> dict:
    """The runtime's barScales: for each data-tb-bars column that is shown and
    numeric, the largest magnitude over ALL rows and whether any is negative."""
    out = {}
    for col in (c.strip() for c in (want or "").split(",")):
        if col not in cols or col not in numeric:
            continue
        vals = pd.to_numeric(df[col], errors="coerce").dropna()
        top = float(vals.abs().max()) if len(vals) else 0.0
        if top > 0:
            out[col] = (top, bool((vals < 0).any()))
    return out


def _ssr_bar(raw, scale) -> str:
    """The runtime's paintBar as markup: a lane after the number whose bar's
    left/width are the same percentages (the stamped value never changes)."""
    if scale is None or raw is None or pd.isna(raw):
        return ""
    top, neg = scale
    n = float(raw)
    span = (50 if neg else 100) * abs(n) / top
    zero = 50 if neg else 0

    def pct(x):  # JS Number#toString for the values this produces
        return f"{int(x)}%" if float(x).is_integer() else f"{x!r}%"
    return ('<span class="tb-bar-track" aria-hidden="true"><span class="tb-bar'
            + (" tb-bar--neg" if n < 0 else "")
            + f'" aria-hidden="true" style="left:{pct(zero - span if n < 0 else zero)};'
            f'width:{pct(span)}"></span></span>')


def _ssr_cell(raw) -> str:
    """A table cell's unformatted text — the runtime shows the raw value for a
    non-numeric or unformatted (identity) column."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return ""
    return str(raw)


def declared_column_formats(model, columns) -> dict:
    """``{column: format}`` for the *columns* that are measures *model*
    declares a format on — including a ratio's inputs, which a query returns as
    their own columns. Presentation only: it picks how a number is written,
    never which number."""
    declared = model.measures()
    out = {c: declared[c].format for c in sorted(str(c) for c in columns)
           if c in declared and declared[c].format}
    # A declared time grain is a period label ("2026", "2026-03"): "label"
    # tells the runtime to write it as it is, never as a number ("2,026").
    for c in sorted(str(c) for c in columns):
        dim, dot, attr = c.partition(".")
        dim_def = model._dimensions.get(dim) if dot else None
        if dim_def is not None and (dim_def.derived.get(attr) or {}).get("kind") == "date_trunc":
            out[c] = "label"
    return out


def table_number_formats(df, declared=None) -> dict:
    """The format each numeric column of a table gets before an author's own
    overrides: the shape-derived default (``derive_number_formats``, which
    tracebi.js ``deriveFormat`` ports), then the model's declared format on a
    measure, which wins. One place decides it, for the built report's tables and
    for the web app's Explore results alike."""
    from tracebi.reports.derive import derive_number_formats
    numeric = {str(c) for c in df.select_dtypes(include="number").columns}
    formats = derive_number_formats(df)      # dataset=None: shape-only == JS
    formats.update({c: v for c, v in (declared or {}).items() if c in numeric})
    return formats


def display_rows(df, declared=None) -> list[dict]:
    """Each row of *df* as the text a built report's table shows for it:
    numeric columns through their format, everything else as plain text. The
    raw values stay in *df*; this is only how they are written."""
    numeric = {str(c) for c in df.select_dtypes(include="number").columns}
    formats = table_number_formats(df, declared)
    # Column by column, never iterrows: a row of an all-numeric frame is one
    # float Series, which would print the year 1979 as "1979.0".
    names = [str(c) for c in df.columns]
    values = [df.iloc[:, i].tolist() for i in range(len(names))]
    rows = []
    for r in range(len(df)):
        cells = {}
        for name, col in zip(names, values):
            fmt = formats.get(name) if name in numeric else None
            cells[name] = _ssr_format(col[r], fmt) if fmt else _ssr_cell(col[r])
        rows.append(cells)
    return rows


class _PythonDerivedSection(TableSection):
    """A carrier section for a ``report.py`` output (architecture §4).

    Identical to :class:`TableSection` — it fingerprints its dataset through
    the ordinary manifest path, so the embedded bytes stay file-checkable —
    but it stamps ``verifiable: false`` on its manifest dict. That flag is what
    ``verify_manifest`` reads to classify the section UNVERIFIABLE *by
    construction*, not merely because a query happens to be absent from
    lineage: a python-derived number must never read as query-reproducible.
    """

    def to_manifest_dict(self) -> dict:
        d = super().to_manifest_dict()
        d["verifiable"] = False
        return d


#: The keywords a report-level measure definition may take: exactly the
#: ``add_measure`` keywords, so a report declares a measure in the model's words.
_REPORT_MEASURE_KEYWORDS = frozenset(
    inspect.signature(DataModel.add_measure).parameters) - {"self", "name"}


def _report_measures(raw, path: str) -> dict[str, dict[str, dict]]:
    """The report.json ``measures`` block: ``{model: {name: definition}}``.

    A structural check only (discovery's rule): the keys are closed to the
    ``add_measure`` keywords. Whether a definition fits its model is checked
    when a query runs, where a real error can be reported.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"{path}: 'measures' maps a model name to its report-level "
            f"measures, e.g. {{\"wealth_model\": {{\"net_new\": {{...}}}}}}.")
    out: dict[str, dict[str, dict]] = {}
    for model_name, defs in raw.items():
        if not isinstance(defs, dict) or not defs:
            raise ValueError(
                f"{path}: measures['{model_name}'] must be an object of named "
                f"measure definitions.")
        out[model_name] = {}
        for mname, definition in defs.items():
            if not isinstance(definition, dict):
                raise ValueError(
                    f"{path}: measure '{mname}' of '{model_name}' must be an "
                    f"object of add_measure keywords.")
            unknown = set(definition) - _REPORT_MEASURE_KEYWORDS
            if unknown:
                raise ValueError(
                    f"{path}: measure '{mname}' of '{model_name}' has unknown "
                    f"key(s) {sorted(unknown)}. One of: "
                    f"{', '.join(sorted(_REPORT_MEASURE_KEYWORDS))}.")
            out[model_name][str(mname)] = dict(definition)
    return out


def _sql_calculations(raw, path: str) -> dict[str, dict[str, str]]:
    """The report.json ``sql_calculations`` block: ``{model: {name: SELECT}}``.

    Structural and read-only: each calculation must be one SELECT, so a write
    is refused when the report is discovered, not when it first runs.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"{path}: 'sql_calculations' maps a model name to its named SQL "
            f"calculations, e.g. {{\"wealth_model\": {{\"running\": \"SELECT ...\"}}}}.")
    out: dict[str, dict[str, str]] = {}
    for model_name, calcs in raw.items():
        if not isinstance(calcs, dict) or not calcs:
            raise ValueError(
                f"{path}: sql_calculations['{model_name}'] must be an object of "
                f"named SQL calculations.")
        out[model_name] = {}
        for cname, text in calcs.items():
            if not isinstance(text, str):
                raise ValueError(
                    f"{path}: SQL calculation '{cname}' of '{model_name}' must be "
                    f"a SQL string.")
            try:
                check_read_only(text)
            except ValueError as exc:
                raise ValueError(
                    f"{path}: SQL calculation '{cname}' of '{model_name}': {exc}"
                ) from exc
            out[model_name][str(cname)] = text
    return out


def _sql_binding(binding_name: str, ref_raw: dict, calcs: dict, path: str) -> DataRef:
    """A data binding that names a SQL calculation: ``{"model", "sql"}``."""
    if set(ref_raw) != {"model", "sql"} or not isinstance(ref_raw["sql"], str):
        raise ValueError(
            f"{path}: data binding '{binding_name}' binds a SQL calculation with "
            f"{{\"model\": ..., \"sql\": <name>}} and nothing else.")
    model_name, cname = ref_raw["model"], ref_raw["sql"]
    text = calcs.get(model_name, {}).get(cname)
    if text is None:
        raise ValueError(
            f"{path}: data binding '{binding_name}' names SQL calculation "
            f"'{cname}' of model '{model_name}', which 'sql_calculations' does "
            f"not declare.")
    return DataRef(model=model_name, query=SqlQuery(sql=text))


def _measures_for_query(names, defs: dict[str, dict]) -> dict[str, dict]:
    """The report-level definitions a query needs: the names it lists, plus
    every report-level measure those read, transitively. Nothing else, so one
    binding's receipt never carries another binding's calculations."""
    needed: dict[str, dict] = {}
    stack = [str(n) for n in names]
    while stack:
        n = stack.pop()
        if n in needed or n not in defs:
            continue
        needed[n] = defs[n]
        stack.extend(measure_references(n, defs[n]))
    return needed


class TemplatePackage:
    """A loaded freeform report package (architecture §7).

    Construct from the package directory, then :meth:`render` with the models
    its bindings name. Loading validates the *structure* of every binding
    (reusing :class:`~tracebi.spec.DataRef` / ``QuerySpec`` parsing); the query
    is checked against the model — and executed — only at render time, so a
    model registered after discovery still resolves.
    """

    def __init__(self, directory: str):
        self.directory = directory
        # Registry key is the directory name. ``name`` below may be a display
        # title; the selection endpoint is addressed by this id.
        from tracebi.report_paths import report_name_for_dir
        # "finance/weekly" for a package in a folder: the name pins, the
        # workbench and the web API all address it by.
        self.package_id = report_name_for_dir(directory)
        self.name = self.package_id

        report_json_path = os.path.join(directory, REPORT_JSON)
        template_path = os.path.join(directory, TEMPLATE_HTML)
        app_path = os.path.join(directory, APP_JSX)
        if not os.path.isfile(report_json_path):
            raise FileNotFoundError(
                f"Template package '{directory}' has no {REPORT_JSON}."
            )
        has_template = os.path.isfile(template_path)
        has_app = os.path.isfile(app_path)
        if has_template and has_app:
            raise ValueError(
                f"Package '{directory}' has both {TEMPLATE_HTML} and {APP_JSX}. "
                f"A page is one or the other: keep {APP_JSX} for an app-like "
                f"dashboard, {TEMPLATE_HTML} for a report page."
            )
        if not has_template and not has_app:
            raise FileNotFoundError(
                f"Template package '{directory}' has no {TEMPLATE_HTML} "
                f"(or {APP_JSX})."
            )

        with open(report_json_path, encoding="utf-8") as f:
            declaration = json.load(f)
        if not isinstance(declaration, dict):
            raise ValueError(
                f"{report_json_path}: the top level must be an object."
            )

        self.name = declaration.get("name") or self.name
        raw_title = declaration.get("title")
        self.page_title = (
            raw_title if isinstance(raw_title, str) and raw_title.strip()
            else self.name
        )
        self.author = declaration.get("author", "")
        # A shipped theme by name ("theme": "ocean"): token overrides stacked
        # over the project's reports/_theme.css.
        self.theme = declaration.get("theme")
        self.theme_css = ""
        if self.theme is not None:
            from tracebi.reports.stack import named_theme_css
            try:
                self.theme_css = named_theme_css(str(self.theme))
            except ValueError as exc:
                raise ValueError(f"{report_json_path}: {exc}") from None
        self.description = declaration.get("description", "")

        data = declaration.get("data")
        if not isinstance(data, dict) or not data:
            raise ValueError(
                f"{report_json_path}: needs a non-empty 'data' object mapping "
                f"each binding name to {{'model': ..., 'query': ...}}."
            )
        # Reuse DataRef's structural validation for every binding.
        sql_calcs = _sql_calculations(
            declaration.get("sql_calculations"), report_json_path)
        self.bindings: dict[str, DataRef] = {}
        for binding_name, ref_raw in data.items():
            if not isinstance(ref_raw, dict):
                raise ValueError(
                    f"{report_json_path}: data binding '{binding_name}' must be "
                    f"an object with 'model' and 'query'."
                )
            if "sql" in ref_raw:
                self.bindings[binding_name] = _sql_binding(
                    binding_name, ref_raw, sql_calcs, report_json_path)
            else:
                self.bindings[binding_name] = DataRef.from_dict(ref_raw)

        # Report-level measures: calculations this report declares for its own
        # bindings, not added to the shared model. Each binding carries exactly
        # the ones its query needs, so the stamped query (and so the receipt and
        # verify) holds the definition the number was computed under.
        self.calculated_measures = _report_measures(
            declaration.get("measures"), report_json_path)
        for binding_name, ref in list(self.bindings.items()):
            defs = self.calculated_measures.get(ref.model)
            if not defs or not isinstance(ref.query.measures, (list, tuple)):
                continue
            needed = _measures_for_query(ref.query.measures, defs)
            if needed:
                self.bindings[binding_name] = DataRef(
                    model=ref.model,
                    query=replace(ref.query, calculated={
                        **(ref.query.calculated or {}), **needed}))

        # Opt-in. Absent: controls subset stamped rows and value figures stay
        # still. Present: a filter is a selection DataModel re-runs.
        from tracebi.reports.selection import parse_selection_block
        if "selection" in declaration:
            self.selection = parse_selection_block(
                declaration.get("selection"),
                path=report_json_path,
                binding_models={ref.model for ref in self.bindings.values()},
            )
        else:
            self.selection = None
        if self.selection:
            for binding_name, ref in self.bindings.items():
                if isinstance(ref.query, SqlQuery) and ref.model == self.selection["model"]:
                    raise ValueError(
                        f"{report_json_path}: the selection filters model "
                        f"'{ref.model}', and binding '{binding_name}' is a SQL "
                        f"calculation, which a selection cannot filter yet.")

        # What the built page carries so it can recompute (the slice):
        # "required" (the default) embeds per fact the grain the page needs,
        # "model" every fact at base grain, "none" nothing new.
        from tracebi.reports.slice import (
            DEFAULT_EMBED_BUDGET_MB, EMBED_MODES, EMBED_REQUIRED,
        )
        self.embed = declaration.get("embed", EMBED_REQUIRED)
        if self.embed not in EMBED_MODES:
            raise ValueError(
                f"{report_json_path}: 'embed' must be one of "
                f"{', '.join(repr(m) for m in EMBED_MODES)}; got {self.embed!r}.")
        self.embed_budget_mb = declaration.get(
            "embed_budget_mb", DEFAULT_EMBED_BUDGET_MB)
        if (isinstance(self.embed_budget_mb, bool)
                or not isinstance(self.embed_budget_mb, (int, float))
                or self.embed_budget_mb <= 0):
            raise ValueError(
                f"{report_json_path}: 'embed_budget_mb' must be a positive "
                f"number of megabytes; got {self.embed_budget_mb!r}.")

        # Optional: when this report runs and who receives it. Read by
        # `tracebi schedule`; the build itself ignores it.
        if "schedule" in declaration:
            from tracebi.schedule import parse_schedule_block
            self.schedule = parse_schedule_block(
                declaration.get("schedule"), path=report_json_path)
        else:
            self.schedule = None

        # The React lane: the page is app.jsx, compiled in the browser from
        # the fixed kit. The template is a generated shell — a mount point and
        # the kit figures' claims, read from the source without running it.
        self.app_source: Optional[str] = None
        self.app_imports: dict = {}
        self.app_icons: dict = {}
        if has_app:
            from tracebi.reports import app_lane
            self.app_source = _read_text(app_path)
            self.app_imports = app_lane.scan_imports(self.app_source)
            self.app_icons = app_lane.icon_nodes(self.app_imports)
            app_shell = app_lane.shell_html(
                self.page_title, app_lane.scan_figures(self.app_source),
                app_lane.parse_look(declaration.get("look"), report_json_path))

        # Fonts and images under assets/ are inlined as data: URIs here, at
        # load, so every render path (dev, build, snapshot, web) carries them.
        self.template_html = (app_shell if has_app else inline_package_assets(
            _read_text(template_path), directory, TEMPLATE_HTML))
        self.style_css = inline_package_assets(
            _read_optional(os.path.join(directory, STYLE_CSS)), directory,
            STYLE_CSS)
        self.script_js = _read_optional(os.path.join(directory, SCRIPT_JS))

        # Charting libraries the package names. Unknown names fail loudly.
        # ``echarts`` is also inlined at inject time when the page the reader
        # gets contains a chart figure and this list omitted it — see
        # ``_libs_for_page``. A page with no chart figure stays without it.
        libs = declaration.get("libs", [])
        if not isinstance(libs, list) or any(lib not in KNOWN_LIBS for lib in libs):
            raise ValueError(
                f"{report_json_path}: 'libs' must be a list drawn from "
                f"{sorted(KNOWN_LIBS)}."
            )
        self.libs = libs

        # Declared figures the template places with ``{{ figure("name") }}``.
        # The framework builds the element; the analyst owns everything around
        # it. Optional: a package that hand-writes its own data-tb-* markup
        # declares none and is unaffected.
        self.figures: dict[str, dict] = {}
        declared = declaration.get("figures", {})
        if not isinstance(declared, dict):
            raise ValueError(
                f"{report_json_path}: 'figures' must be an object mapping each "
                f"figure name to its declaration."
            )
        for fig_name, fig in declared.items():
            self.figures[fig_name] = _validate_figure(
                fig_name, fig, self.bindings, report_json_path
            )

        # The escape hatch (architecture §8-M3). When present, the ``data``
        # bindings above are the *stamped inputs* to report.py's ``build``;
        # the page embeds its python-derived *outputs* beside them.
        report_py = os.path.join(directory, REPORT_PY)
        self.report_py_path: Optional[str] = (
            report_py if os.path.isfile(report_py) else None
        )

    # ── Build + render ──────────────────────────────────────────────────────

    def build(self, models: dict, filters: Optional[dict] = None):
        """Resolve every binding and assemble the carrier :class:`Report`.

        Returns ``(report, stamped)`` where *stamped* is the list of
        :class:`~tracebi.reports.embed.StampedData`, one per binding, in
        declaration order.

        *filters* is an optional predicate dict in the same spelling as a
        binding filter. It is conjoined through
        :func:`~tracebi.reports.selection.query_under_selection` onto every
        binding whose model has that dimension — the same path a selection
        uses. A filter that matches no binding model is an error: the page
        must not ship unfiltered while claiming the cut.
        """
        report = Report(self.name)
        if self.author:
            report.author(self.author)
        if self.description:
            report.description(self.description)

        def takes(model) -> bool:
            if not filters:
                return False
            names = {d["name"] for d in model.info().get("dimensions") or []}
            for key in filters:
                head, dot, attr = str(key).partition(".")
                if not dot or not attr or head not in names:
                    return False
            return True

        if filters or self.selection:
            from tracebi.reports.selection import query_under_selection

        stamped = []
        applied = 0
        for binding_name, ref in self.bindings.items():
            model = (models or {}).get(ref.model)
            if model is None:
                raise ValueError(
                    f"Cannot render package '{self.name}': binding "
                    f"'{binding_name}' names model '{ref.model}', which was not "
                    f"supplied. Available: {sorted(models or {})}."
                )
            query = ref.query
            if self.selection and ref.model == self.selection["model"]:
                query = query_under_selection(ref.query, self.selection["filters"])
            if takes(model):
                if isinstance(query, SqlQuery):
                    raise ValueError(
                        f"Cannot render package '{self.name}': binding "
                        f"'{binding_name}' is a SQL calculation, which a filter "
                        f"cannot reach yet.")
                query = query_under_selection(query, filters)
                applied += 1
            sd = stamp(model, query, name=binding_name)
            stamped.append(sd)
            # A synthetic carrier: it exists only so the manifest-first receipt
            # fingerprints this binding through the ordinary to_manifest_dict
            # path. The analyst's template decides what is actually drawn.
            report.add(TableSection(title=binding_name, dataset=sd.dataset,
                                    id=binding_name))
        if filters and applied == 0:
            shown = ", ".join(repr(k) for k in filters)
            raise ValueError(
                f"Cannot render package '{self.name}': filter {shown} "
                f"matches no binding model, so it was not applied."
            )
        return report, stamped

    def _build_figure(self, name: str, fig: dict) -> str:
        """Emit the ``data-tb-*`` element for one declared figure.

        The markup comes from the shared emitter, so a figure the template
        places is byte-for-byte the figure the spec compiler would have built
        for the same declaration.
        """
        kind, binding, fig_id = fig["kind"], fig["binding"], f"fig-{name}"
        if kind == "table":
            return table_element(binding, fig_id=fig_id,
                                 columns=fig.get("columns"),
                                 style=fig.get("style"),
                                 labels=fig.get("labels"),
                                 formats=fig.get("formats"))
        if kind == "chart":
            return chart_element(binding, fig_id=fig_id,
                                 chart_type=fig.get("chart_type", "bar"),
                                 x=fig.get("x"), y=fig.get("y"),
                                 color=fig.get("color"),
                                 palette=fig.get("palette"),
                                 value_format=fig.get("value_format"))
        return value_element(binding, fig_id=fig_id, cell=fig["cell"],
                             label=fig.get("label", ""), fmt=fig.get("format"))

    def _refuse_unplaced(self, unplaced: list[str]) -> None:
        """Declared and never placed: the figure is simply absent from the
        page. The dev view only warns (the template is mid-edit), but a final
        build and a draft preview must not pass a report quietly missing a
        number the author declared."""
        if not unplaced:
            return
        raise ValueError(
            f"Package '{self.name}': {REPORT_JSON} declares "
            f"{', '.join(repr(n) for n in unplaced)} under 'figures', but "
            f"{TEMPLATE_HTML} never places "
            f"{'them' if len(unplaced) > 1 else 'it'} — add "
            + " ".join('{{ figure("%s") }}' % n for n in unplaced)
            + " where the figure belongs, or remove the declaration."
        )

    def model_labels(self, models: dict) -> list[str]:
        """The label of each model the bindings read, in binding order: what
        the masthead's kicker defaults to and the footer names. A model's
        declared label, else its identifier title-cased."""
        labels: list[str] = []
        for name in dict.fromkeys(ref.model for ref in self.bindings.values()):
            label = getattr((models or {}).get(name), "label", None)
            if not (isinstance(label, str) and label.strip()):
                label = default_label(name)
            if label not in labels:
                labels.append(label)
        return labels

    def render_page(self, report: Report, *, strip_exploration: bool):
        """Render a carrier *report* through this package's template.

        The one place the package's template, ``HTMLRenderer`` and figure-id
        assignment are wired — shared by :meth:`render` (final build,
        ``strip_exploration=True``), :meth:`render_exploration` and the
        workbench's ``collect_state`` (dev view, exploration kept). Returns
        ``(page, id_warnings, unplaced)``; each caller extracts and validates
        figures itself, because a final build raises where the dev view
        captures.

        ``{{ figure("name") }}`` is the framework's half of the freeform lane:
        the analyst owns the layout, the CSS and the script, and the framework
        supplies the figure element so the ``data-tb-*`` grammar never has to
        be hand-written. Placing one twice raises here — a figure id is the
        receipt's address for one number — and *unplaced* carries the mirror
        case (declared, never placed) back to the caller, because a declared
        figure that silently fails to appear is the failure this package
        format exists to prevent.
        """
        emitted: dict[str, int] = {}

        def figure(name: str) -> str:
            fig = self.figures.get(name)
            if fig is None:
                raise ValueError(
                    f"Package '{self.name}': template calls figure('{name}'), "
                    f"which is not declared in {REPORT_JSON} 'figures'. "
                    f"Declared: {sorted(self.figures)}."
                )
            emitted[name] = emitted.get(name, 0) + 1
            if emitted[name] > 1:
                raise ValueError(
                    f"Package '{self.name}': figure('{name}') is placed more "
                    f"than once. A figure id is the trace's address for one "
                    f"number — declare a second figure instead of reusing it."
                )
            return self._build_figure(name, fig)

        renderer = HTMLRenderer(
            template=self.template_html,
            document_title=self.page_title,
            template_context={"bindings": list(self.bindings),
                              "figure": figure},
        )
        page = renderer.to_html(report)
        if strip_exploration:
            page = strip_stage(page, "exploration")
        page, id_warnings = assign_figure_ids(page)
        unplaced = [n for n in self.figures if n not in emitted]
        return page, id_warnings, unplaced

    def render(
        self,
        models: dict,
        output_path: str,
        save_manifest: bool = True,
        manifest_path: Optional[str] = None,
        badges: bool = False,
        filters: Optional[dict] = None,
    ) -> ReportManifest:
        """Render the package to one self-contained ``.html`` (+ manifest).

        Manifest first, artifact second — the receipt is built and the embedded
        fingerprints recorded before a byte of the page is written, so a render
        that half-fails cannot leave a page without a receipt.

        *filters* is passed to :meth:`build` and applied the same way a
        selection filter is.
        """
        report, inputs = self.build(models, filters=filters)

        # Verifiability is carried per binding, never per package
        # (report-architecture-v2 §2.1). Every declared ``data`` binding is
        # query-reproducible and embeds ``verifiable: true`` — a report.py
        # beside it no longer flattens it to false. Every report.py output
        # embeds ``verifiable: false``, hardcoded: a python-derived number
        # never reads as query-reproducible, whatever sits next to it.
        outputs: list[StampedData] = []
        if self.report_py_path is not None:
            outputs = self.apply_report_py(report, inputs)
        embed_items = inputs + outputs

        # Final build: exploration blocks are DELETED by the build, not by a
        # rewrite (v2 §2.1) — then ids are assigned and the figure claims
        # validated against what is actually embedded. Extraction, the strip,
        # and verify --file all share the one tokenizer in figures.py.
        page, id_warnings, unplaced = self.render_page(
            report, strip_exploration=True)
        for w in id_warnings:
            print(f"[tracebi] {self.name}: {w}", file=sys.stderr)
        self._refuse_unplaced(unplaced)
        figs = extract_figures(page)
        self._validate_figures(figs, inputs, outputs)
        # Scenarios: the reader's what-if, computed in the browser. Checked
        # here so a typo'd formula or a preset naming a missing column fails
        # the build instead of showing a blank on the page.
        from tracebi.reports.figures import extract_scenarios
        from tracebi.reports import scenario as _scenario
        scenarios = extract_scenarios(page)
        columns = {sd.name: [str(c) for c in sd.dataset.to_pandas().columns]
                   for sd in (inputs + outputs)}
        for sc in scenarios:
            _scenario.validate(sc, columns)
        # Exploration is already stripped. A numeral left in the prose is a
        # number the build would ship with no figure claim.
        outside = lint_numeric_literals(page)
        if self.app_source is not None:
            from tracebi.reports import app_lane
            typed = app_lane.lint_jsx_numbers(self.app_source)
            if typed:
                raise FigureError(
                    f"Package '{self.name}': {typed} number"
                    f"{'s are' if typed != 1 else ' is'} typed into app.jsx's text. "
                    f"Bind each one with <Value binding=\"…\" cell=\"…\" />, or say "
                    f"it in words. A hand-typed number cannot ship as if it were checked.")
        if outside:
            raise FigureError(
                f"Package '{self.name}': {outside} numeric literal"
                f"{'s' if outside != 1 else ''} "
                f"{'sit' if outside != 1 else 'sits'} outside figures. "
                f"Bind each one — a <span> with data-tb-figure=\"value\" "
                f"works inside a sentence — or move it into "
                f"data-tb-stage=\"exploration\", which this build strips. "
                f"A hand-typed number cannot ship as if it were checked."
            )
        # The kicker a masthead shows when its author wrote none: the model's
        # label. After the lint: the label is the model's, not typed prose.
        page = _with_kicker(page, " · ".join(self.model_labels(models)),
                            app=self.app_source is not None)

        # Server-side render (SSR): fill each figure's value/table/chart with the
        # resolved data at build, so a reader with JavaScript off still sees the
        # numbers — the runtime then hydrates identically (progressive
        # enhancement). Every filled number is the same stamped bytes the
        # runtime reads and nothing touches the embed blocks, so no fingerprint
        # moves. See _ssr_content.
        frames = {sd.name: sd.dataset for sd in (inputs + outputs)}
        declared_formats = self._declared_column_formats(models, frames)
        page = fill_figures(page, self._ssr_content(figs, frames, declared_formats))

        # Manifest first, artifact second — and the figure claims layer rides
        # in it (schema v2: the refuse-newer-schema path in verify is the
        # compatibility mechanism it was reserved for).
        manifest = report.build_manifest("html", output_path)
        # A receipt that cannot pin itself to a code state is worth less, and the
        # build is the moment to say so — one loud line, not a silent
        # git_sha:"unknown" in the manifest. Same warning the spec/HTML lane
        # already emits; the package lane (the primary one) was missing it.
        _warn_if_unknown_git_sha(manifest)
        # ONE embed plan for the whole artifact: the format decision, the page
        # blocks, and the manifest's payload hashes all come from the same
        # single encoding (embed.py plan_embed) — so for a Parquet artifact the
        # bytes the page carries are byte-for-byte the bytes the receipt
        # records, and verify --file checks them by hashing, never by
        # re-deriving anything on the verifier's machine.
        embed_plan = plan_embed(embed_items)
        manifest.embedded_data = (
            [embed_plan.record(sd, verifiable=True) for sd in inputs]
            + [embed_plan.record(sd, verifiable=False) for sd in outputs]
        )
        # A Parquet artifact stamps the higher schema so an older checker
        # refuses it cleanly rather than misreading its payload records; a CSV
        # artifact stays version 2 and verifies on any checker. payload_sha256
        # is populated only for the Parquet transport.
        manifest.schema_version = (PARQUET_MANIFEST_SCHEMA_VERSION
                                   if embed_plan.payload_sha256
                                   else ARTIFACT_MANIFEST_SCHEMA_VERSION)
        manifest.stage = "final"
        manifest.figures = [_figure_record(f) for f in figs]
        if scenarios:
            manifest.scenarios = [_scenario.manifest_record(sc) for sc in scenarios]

        # The phase-① join (v2 §2.6): per warehouse table this render loaded,
        # did the sink satisfy a declared contract? A separate claim beside
        # the figure claims — it never colors them.
        from tracebi.contracts import (
            stated_methodology_block, transform_contracts_block,
        )
        lineages = [sd.dataset.lineage_to_dict() for sd in inputs]
        contracts = transform_contracts_block(models, lineages)
        if contracts:
            manifest.transform_contracts = contracts

        # The footer that ends the page (default on). A template may place
        # ONE data-tb-methodology container; otherwise the build adds a
        # <footer class="tb-footer">. Either way, after the author's own
        # children (their sources), one visible line — when, which model
        # (by label), and that the page does not claim the numbers are right —
        # then "How these numbers were made" behind a <details>: what the
        # trace is for and the stated methodology notes. With the runtime the
        # line's own link opens the drawer instead, whose About this build
        # holds the same notes; the <details> serves a reader without it.
        # Prose, never a verified claim: no badge, no status, and it never
        # colors a figure. Stated notes are recorded in the manifest (and the receipt block)
        # when present.
        page, insert_at = _ensure_about_home(page)
        notes = stated_methodology_block(models, lineages)
        measure_notes = self._measure_notes(models)
        if measure_notes:
            notes["measure_notes"] = measure_notes
        notes_html = (_methodology_html(notes, contracts) if notes else "")
        footer = _footer_html(manifest, self.model_labels(models), notes_html,
                              app=self.app_source is not None)
        page = page[:insert_at] + footer + page[insert_at:]
        if notes:
            manifest.methodology = notes

        # The embedded semantic contract: per model the bindings reference,
        # the contract AS EXERCISED — snapshotted at render, a record of
        # what the vocabulary meant when the numbers were produced, never a
        # live claim. Recorded in the manifest (before the page is written,
        # like every other receipt field) with a SHA-256 over the exact
        # payload string embedded, so the offline check is byte-exact.
        contract_blocks: list[str] = []
        semantic_record: dict = {}
        for model_name in sorted({ref.model for ref in self.bindings.values()}):
            slice_ = self._semantic_slice(model_name, models[model_name])
            block = embed_json(slice_, f"tb-semantic-contract-{model_name}")
            contract_blocks.append(block + "\n")
            semantic_record[model_name] = {
                "slice": slice_,
                "sha256": hashlib.sha256(
                    _embedded_payload(block).encode("utf-8")).hexdigest(),
            }
        manifest.semantic_contract = semantic_record

        # The receipt block — the drawer's provenance feed (shared drawer
        # contract). Presentation feed ONLY: every fact here duplicates one
        # the manifest already records (report, render stamp, per-figure
        # binding fingerprints, compact contract statuses), embedded so the
        # in-page drawer can display provenance offline. The MANIFEST
        # remains the receipt of record — verify reads the manifest, never
        # this block, and the drawer renders only what is recorded here:
        # provenance display, never re-colored. Rides the same extra-blocks
        # slot as the semantic-contract blocks.
        receipt = _receipt_payload(
            manifest, figs,
            fingerprints={sd.name: sd.fingerprint for sd in embed_items},
            binding_models={n: ref.model for n, ref in self.bindings.items()},
            contracts=contracts,
            bindings=self._receipt_bindings(embed_items),
            app=self.app_source is not None,
        )
        contract_blocks.append(embed_json(receipt, "tracebi-receipt") + "\n")
        contract_blocks.append(embed_json(declared_formats, "tracebi-formats") + "\n")
        contract_blocks.append(self._selection_blocks())
        contract_blocks.append(self._slice_blocks(
            models, manifest, [sd.name for sd in outputs]))

        # Provenance for the runtime's badges, decided from what was actually
        # embedded (v2 §2.4): a stylesheet can restyle a badge, never re-color
        # honesty. On-page badges are OFF by default — a mark on every figure is
        # noise; the receipt drawer carries full provenance in one opt-in place.
        # Pass badges=True (CLI --badges) to render them; the manifest is
        # unaffected either way.
        from tracebi.reports.stack import figures_config
        cfg = {"badges": bool(badges),
               "figures": figures_config(figs, {sd.name for sd in outputs})}

        page = self._inject(page, embed_plan.blocks_html, stage="final",
                            figures_cfg=cfg,
                            extra_blocks_html="".join(contract_blocks))

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(page)
        if save_manifest:
            manifest.save(manifest_path or output_path + ".manifest.json")
        return manifest

    # ── Server-side render (progressive enhancement) ────────────────────────

    def _ssr_content(self, figs, frames, declared_formats=None) -> dict:
        """Server-rendered inner content per figure id, for the SSR fill.

        VALUE figures get the formatted number the runtime would hydrate, so a
        no-JS reader sees it (and the runtime overwrites it with the identical
        bytes on hydrate). Table and chart figures are filled by later build
        steps; until then they keep the author placeholder and hydrate as
        before.
        """
        import html as _html
        content: dict = {}
        for fig in figs:
            if fig.id is None or fig.binding is None:
                continue
            ds = frames.get(fig.binding)
            if ds is None:
                continue
            if fig.kind == "value":
                text = self._ssr_value(
                    ds, fig, (declared_formats or {}).get(fig.binding))
                if text is not None:
                    content[fig.id] = _html.escape(text)
                    cls = _ssr_direction(ds, fig)
                    if cls:
                        # The arrow and its colour for a no-JS reader; the
                        # runtime writes the same text and classes over it.
                        content[fig.id] = f'<span class="{cls}">{content[fig.id]}</span>'
            elif fig.kind == "table":
                markup = self._ssr_table(
                    ds, fig, (declared_formats or {}).get(fig.binding),
                    frames.get(fig.attrs.get("data-tb-totals") or ""))
                if markup is not None:
                    content[fig.id] = markup
            elif fig.kind == "chart":
                svg = self._ssr_chart(ds, fig)
                if svg is not None:
                    content[fig.id] = svg
        return content

    def _declared_column_formats(self, models: dict, frames: dict) -> dict:
        """``{binding: {column: format}}`` for columns that are measures the
        model declares a format on — including a ratio's inputs, which the
        query returns as their own columns. Presentation only: it picks how a
        number is written, never which number."""
        out: dict = {}
        for name, ref in self.bindings.items():
            ds, model = frames.get(name), models.get(ref.model)
            if ds is None or model is None:
                continue
            cols = ds.to_pandas().columns
            fmts = declared_column_formats(model, cols)
            # A report-level measure's format is declared here, not on the model.
            for col, d in self.calculated_measures.get(ref.model, {}).items():
                if col in cols and d.get("format"):
                    fmts[col] = d["format"]
            if fmts:
                out[name] = fmts
        return out

    @staticmethod
    def _ssr_chart(ds, fig):
        """A static SVG of the chart, tagged ``.tb-chart-fallback``, so a no-JS
        reader sees a picture of it. The runtime removes the fallback and draws
        the interactive ECharts version over the same (min-height:320px)
        container. Axis ticks and labels use the figure's data-tb-value-format
        (the same named formats as the runtime; percent multiplies by 100 for
        display only).
        """
        import dataclasses
        import types
        from tracebi.reports.chart import ChartSpec
        from tracebi.reports.derive import humanise
        a = fig.attrs
        x, y = a.get("data-tb-x"), a.get("data-tb-y")
        if not x or not y:
            return None
        palette = a.get("data-tb-palette")
        shim = types.SimpleNamespace(
            chart_type=a.get("data-tb-type") or "bar",
            x=x,
            y=[c.strip() for c in y.split(",") if c.strip()],
            color=a.get("data-tb-color"),
            palette=[c.strip() for c in palette.split(",")] if palette else None,
            dataset=ds, title="", xlabel=None, ylabel=None, show_values=False,
        )
        # from_section validates the chart config (unknown columns, and a pie
        # with negative values) — those are build errors the author must fix,
        # so they propagate. Only the SVG rendering is guarded: a rendering
        # quirk drops the no-JS fallback but never fails an otherwise-valid page.
        spec = ChartSpec.from_section(shim)
        # Read like the live chart: no axis titles, and plain series names
        # (``median_price`` → ``Median price``) unless they are group values.
        names = {} if shim.color else {s: humanise(s) for s in spec.series}
        if len(set(names.values())) < len(names) or shim.x in names.values():
            names = {}
        spec = dataclasses.replace(
            spec, xlabel="", ylabel="",
            value_format=a.get("data-tb-value-format") or "",
            series=tuple(names.get(s, s) for s in spec.series),
            rows=tuple({names.get(k, k): v for k, v in r.items()}
                       for r in spec.rows))
        try:
            svg = spec.to_svg()
        except Exception:  # noqa: BLE001 — a rendering quirk: hydrate as before
            return None
        return svg.replace(
            '<svg class="tb-chart',
            '<svg style="display:block;width:100%;height:auto" '
            'class="tb-chart-fallback tb-chart', 1)

    @staticmethod
    def _ssr_value(ds, fig, declared=None):
        """The formatted first-row cell for a value figure, or None to leave
        the author placeholder (an empty cell — matching the runtime). With no
        ``data-tb-format``, a numeric cell takes a table column's precedence:
        the model's declared format, then the shape guess (hydrateValues)."""
        df = ds.to_pandas()
        if df.empty:
            return None
        cell = fig.cell
        if cell is None:
            if len(df.columns) != 1:
                return None
            cell = str(df.columns[0])
        if cell not in df.columns:
            return None
        raw = df[cell].iloc[0]
        if raw is None or raw == "" or (isinstance(raw, float) and pd.isna(raw)):
            return None
        name = fig.attrs.get("data-tb-format")
        if not name and cell in df.select_dtypes(include="number").columns:
            from tracebi.reports.derive import derive_number_formats
            name = ((declared or {}).get(cell)
                    or derive_number_formats(df).get(cell))
        return _ssr_format(raw, name or "")

    @staticmethod
    def _ssr_table(ds, fig, declared=None, totals_ds=None):
        """Server-rendered ``<thead>`` + ``<tbody data-tb-hydrate>`` for a table
        figure, matching the runtime's hydrateTables/renderBody: numeric columns
        (pandas number dtype) get ``tb-num`` and the shape-derived format
        (derive_number_formats, the very logic tracebi.js deriveFormat ports);
        cells format through _ssr_format (== applyNamedFormat). The
        ``data-tb-hydrate`` marker tells the runtime to re-render over these rows
        (its renderBody clears the tbody first, so no duplication) and thereby
        re-register the table for filter/search.
        """
        import html as _html
        from tracebi.reports.derive import humanise
        df = ds.to_pandas()
        cols = [str(c) for c in df.columns]
        allow = fig.attrs.get("data-tb-columns")
        if allow:
            cols = [c.strip() for c in allow.split(",") if c.strip() in cols]
        if not cols:
            return None
        numeric = {str(c) for c in df.select_dtypes(include="number").columns}
        # A format the model declares on a measure beats the shape guess (the
        # runtime reads the same map from the tracebi-formats block).
        formats = table_number_formats(df, declared)
        # Author overrides win over the derived defaults (validated at build);
        # a format applies only to a numeric column, as in the runtime.
        labels = parse_column_map(fig.attrs.get("data-tb-labels"))
        formats.update({c: v for c, v in
                        parse_column_map(fig.attrs.get("data-tb-formats")).items()
                        if c in numeric})
        bars = _ssr_bar_scales(df, fig.attrs.get("data-tb-bars"), cols, numeric)

        def cls(c, base=""):
            names = " ".join(n for n in ("tb-bar-cell" if c in bars else "", base) if n)
            return f' class="{names}"' if names else ""

        head = []
        for c in cols:
            head.append(f"<th{cls(c, 'tb-num' if c in numeric else '')}>"
                        f"{_html.escape(labels.get(c) or humanise(c))}</th>")
        thead = "<thead><tr>" + "".join(head) + "</tr></thead>"
        if df.empty:
            # An empty binding says so, rather than showing a header over a void
            # (the runtime bails on an empty block, leaving this row in place).
            empty = (f'<tr><td class="tb-empty" colspan="{len(cols)}">no data'
                     f"</td></tr>")
            return thead + '<tbody data-tb-hydrate>' + empty + "</tbody>"
        # Cap the SERVER-rendered rows. The runtime clears this tbody and
        # re-renders the full set from the embedded data, so SSR is only the
        # pre-hydrate / no-JS fallback — and baking every row of a large binding
        # into the page as literal <tr>s would re-inflate the very bytes the
        # Parquet transport saved (300k rows → ~24MB of HTML). A generous cap
        # renders every normal table whole and previews only the huge ones.
        body = []
        for _, row in df.head(_SSR_MAX_ROWS).iterrows():
            cells = []
            for c in cols:
                raw = row[c]
                if c in numeric:
                    fmt = formats.get(c)
                    text = _ssr_format(raw, fmt) if fmt else _ssr_cell(raw)
                    cells.append(f'<td{cls(c, "tb-num")}>{_html.escape(text)}'
                                 f'{_ssr_bar(raw, bars.get(c))}</td>')
                else:
                    cells.append(f"<td>{_html.escape(_ssr_cell(raw))}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        if len(df) > _SSR_MAX_ROWS:
            # Honest to a no-JS reader (JS clears this row and loads them all).
            more = len(df) - _SSR_MAX_ROWS
            body.append(f'<tr><td class="tb-empty" colspan="{len(cols)}">'
                        f"+{more:,} more rows — enable JavaScript to load them"
                        f"</td></tr>")
        tfoot = ""
        if totals_ds is not None:
            tf = totals_ds.to_pandas()
            if len(tf) == 1:
                row, cells = tf.iloc[0], []
                for i, c in enumerate(cols):
                    if c in tf.columns:
                        fmt = formats.get(c)
                        text = _ssr_format(row[c], fmt) if fmt else _ssr_cell(row[c])
                        cells.append(f'<td{cls(c, "tb-num")}>{_html.escape(text)}</td>')
                    elif i == 0 and c not in numeric:
                        cells.append(f"<td{cls(c)}>Total</td>")
                    else:
                        cells.append(f"<td{cls(c)}></td>")
                tfoot = ('<tfoot><tr class="tb-total">' + "".join(cells)
                         + "</tr></tfoot>")
        return (thead + "<tbody data-tb-hydrate>" + "".join(body) + "</tbody>"
                + tfoot)

    def _validate_figures(
        self,
        figs: list[Figure],
        inputs: list[StampedData],
        outputs: list[StampedData],
    ) -> None:
        """Every figure names an embedded binding or is honestly unverified.

        Build-enforced (v2 §2.1): a figure with neither is a hard error with
        did-you-mean hints; a ``value`` figure must sit over a one-row binding
        and name a real cell. No fourth state, and no silent third one.
        """
        import difflib

        frames = {sd.name: sd.dataset.to_pandas() for sd in inputs + outputs}

        def _hint(name: str) -> str:
            close = difflib.get_close_matches(name or "", list(frames), n=1)
            return f" Did you mean '{close[0]}'?" if close else ""

        for f in figs:
            where = f"figure '{f.id}' ({f.kind})"
            if f.unverified:
                continue
            if not f.binding:
                raise FigureError(
                    f"{where} names no binding and carries no "
                    f"data-tb-unverified mark. Every element that displays "
                    f"data is stamped or says it is not — there is no third "
                    f"state. Bindings: {sorted(frames)}."
                )
            if f.binding not in frames:
                raise FigureError(
                    f"{where} names binding '{f.binding}', which is not "
                    f"declared in report.json or produced by report.py."
                    f"{_hint(f.binding)} Available: {sorted(frames)}."
                )
            direction = f.attrs.get("data-tb-direction")
            if direction is not None and (
                    f.kind != "value" or direction not in ("up-good", "down-good")):
                raise FigureError(
                    f"{where}: data-tb-direction goes on a value figure and is "
                    f"'up-good' (a rise is good) or 'down-good' (a fall is "
                    f"good); got '{direction}' on a {f.kind} figure.")
            if f.kind == "value":
                df = frames[f.binding]
                if len(df) != 1:
                    raise FigureError(
                        f"{where} reads a single cell but binding "
                        f"'{f.binding}' has {len(df)} rows — a value figure "
                        f"needs a one-row binding (aggregate the query, or "
                        f"use a table figure)."
                    )
                cell = f.cell
                if cell is None:
                    if len(df.columns) == 1:
                        continue     # unambiguous: the only column
                    raise FigureError(
                        f"{where} needs data-tb-cell — binding '{f.binding}' "
                        f"has columns {list(df.columns)}."
                    )
                if cell not in df.columns:
                    close = difflib.get_close_matches(cell, list(df.columns), n=1)
                    hint = f" Did you mean '{close[0]}'?" if close else ""
                    raise FigureError(
                        f"{where}: cell '{cell}' is not a column of binding "
                        f"'{f.binding}'.{hint} Columns: {list(df.columns)}."
                    )
            if f.kind == "table":
                cols = [str(c) for c in frames[f.binding].columns]
                totals = f.attrs.get("data-tb-totals")
                if totals:
                    if totals not in frames:
                        raise FigureError(
                            f"{where}: data-tb-totals names binding '{totals}', "
                            f"which is not declared in report.json.{_hint(totals)}")
                    tdf = frames[totals]
                    if len(tdf) != 1:
                        raise FigureError(
                            f"{where}: data-tb-totals binding '{totals}' has "
                            f"{len(tdf)} rows — a totals row needs a one-row "
                            f"binding (the same query with no dimensions).")
                    if not set(map(str, tdf.columns)) & set(cols):
                        raise FigureError(
                            f"{where}: data-tb-totals binding '{totals}' shares "
                            f"no column with '{f.binding}' ({cols}), so the "
                            f"totals row would be empty.")
                for attr_name in ("data-tb-labels", "data-tb-formats"):
                    try:
                        mapping = parse_column_map(f.attrs.get(attr_name))
                    except ValueError as exc:
                        raise FigureError(f"{where}: {attr_name}: {exc}") from None
                    for col, val in mapping.items():
                        if col not in cols:
                            close = difflib.get_close_matches(col, cols, n=1)
                            hint = f" Did you mean '{close[0]}'?" if close else ""
                            raise FigureError(
                                f"{where}: {attr_name} names '{col}', which is "
                                f"not a column of binding '{f.binding}'.{hint} "
                                f"Columns: {cols}.")
                        if attr_name == "data-tb-formats" and val not in TABLE_FORMATS:
                            raise FigureError(
                                f"{where}: data-tb-formats gives '{col}' the "
                                f"format '{val}'. Use one of "
                                f"{list(TABLE_FORMATS)}.")
                bars = f.attrs.get("data-tb-bars")
                if bars:
                    tdf = frames[f.binding]
                    numeric = {str(c) for c in
                               tdf.select_dtypes(include="number").columns}
                    for col in (c.strip() for c in bars.split(",")):
                        if col not in numeric:
                            close = difflib.get_close_matches(col, sorted(numeric), n=1)
                            hint = f" Did you mean '{close[0]}'?" if close else ""
                            raise FigureError(
                                f"{where}: data-tb-bars names '{col}', which is "
                                f"not a numeric column of binding "
                                f"'{f.binding}'.{hint} Numeric columns: "
                                f"{sorted(numeric)}.")

    def _semantic_slice(self, model_name: str, model) -> dict:
        """The model contract AS EXERCISED by this package's bindings.

        Read from the public ``model.info()``, keeping ONLY the facts the
        queries name, the dimensions they reference (grouped or filtered
        via ``dim.attr``), the declared measures they use by name — each
        with its full declaration — and the tables backing what was kept
        (name + connector + source). Deliberately not the whole model: a
        report must not leak vocabulary it never used. Every list is
        sorted so the embedded JSON is byte-stable across renders.
        """
        info = model.info()
        declared_dims = {d["name"] for d in info["dimensions"]}
        fact_names: set[str] = set()
        dim_names: set[str] = set()
        measure_names: set[str] = set()
        for ref in self.bindings.values():
            if ref.model != model_name:
                continue
            q = ref.query
            fact_names.add(q.fact)
            for dref in q.dimensions or ():
                dim_names.add(str(dref).split(".", 1)[0])
            for target in (q.filters or {}):
                head = str(target).split(".", 1)[0]
                if "." in str(target) and head in declared_dims:
                    dim_names.add(head)
            # Only list-form measures reference declared measures by name
            # (dict form aggregates raw columns) — same rule as
            # _measure_notes above.
            if isinstance(q.measures, (list, tuple)):
                measure_names.update(str(m) for m in q.measures)

        facts = sorted((f for f in info["facts"] if f["name"] in fact_names),
                       key=lambda f: f["name"])
        dims = sorted((d for d in info["dimensions"] if d["name"] in dim_names),
                      key=lambda d: d["name"])
        measures = [m for m in info["measures"] if m["name"] in measure_names]
        # The report's own measures, labelled as such: a calculation this report
        # made, never part of the shared model's vocabulary.
        calculated: dict[str, dict] = {}
        for ref in self.bindings.values():
            if ref.model == model_name and ref.query.calculated:
                calculated.update(ref.query.calculated)
        if calculated:
            view = model.with_measures(calculated).measures()
            for name in sorted(calculated):
                measures.append({
                    **view[name].to_dict(),
                    "scope": "report",
                    "label": "calculated in this report",
                })
        measures = sorted(measures, key=lambda m: m["name"])
        table_names = {f["table"] for f in facts} | {d["table"] for d in dims}
        tables = sorted((t for t in info["tables"] if t["name"] in table_names),
                        key=lambda t: t["name"])
        # SQL calculations this report runs on the model's warehouse: the SQL
        # the author wrote, labelled. Only when present, so a report without
        # one contracts byte-for-byte as before.
        sql_calcs = [
            {"binding": bname, "label": "calculated in this report (SQL)",
             "sql": ref.query.sql}
            for bname, ref in sorted(self.bindings.items())
            if ref.model == model_name and isinstance(ref.query, SqlQuery)
        ]
        contract = {
            "model": info["name"],
            "facts": [
                {"name": f["name"], "table": f["table"],
                 "measures": sorted(f["measures"]),
                 "foreign_keys": {k: f["foreign_keys"][k]
                                  for k in sorted(f["foreign_keys"])}}
                for f in facts
            ],
            "dimensions": [
                {"name": d["name"], "table": d["table"], "key": d["key"],
                 "attributes": sorted(d["attributes"])}
                for d in dims
            ],
            "measures": [{k: m[k] for k in sorted(m)} for m in measures],
            "tables": [
                {"name": t["name"], "connector": t["connector"],
                 "source": t["source"]}
                for t in tables
            ],
        }
        if sql_calcs:
            contract["sql_calculations"] = sql_calcs
        return contract

    def _receipt_bindings(self, items: list[StampedData]) -> dict:
        """Per binding, what the receipt drawer states about its query: the
        query as run (a copy of the manifest's ``query_spec``), the rows it
        returned, and how many of its ordering keys the author wrote. A
        report.py output has no query; it records its rows only."""
        out: dict = {}
        for sd in items:
            rec: dict = {}
            if sd.query_spec:
                rec["query"] = sd.query_spec
                ref = self.bindings.get(sd.name)
                stated = getattr(getattr(ref, "query", None), "order_by", None)
                if stated and sd.query_spec.get("order_by"):
                    rec["order_stated"] = len(stated)
            rec["rows"] = int(sd.dataset.to_pandas().shape[0])
            out[sd.name] = rec
        return out

    def _measure_notes(self, models: dict) -> dict[str, str]:
        """Descriptions of the declared measures the bindings reference.

        Only list-form ``measures`` reference declared measures by name
        (dict form aggregates raw columns); only measures the model states
        a description for appear. Stated methodology — the model's own
        words about its vocabulary, never a verified claim.
        """
        out: dict[str, str] = {}
        for ref in self.bindings.values():
            measures = ref.query.measures
            if not isinstance(measures, (list, tuple)):
                continue
            model = models[ref.model]
            if ref.query.calculated:
                model = model.with_measures(ref.query.calculated)
            declared = model.measures()
            for name in measures:
                mdef = declared.get(name)
                if mdef is not None and mdef.description:
                    out[name] = mdef.description
        return out

    def render_exploration(self, models: dict, *, require_placed: bool = False):
        """Render the working state in memory (v2 §2.5) — the dev loop's page.

        Exploration blocks are KEPT, ids assigned, badges on, stage
        ``exploration``. Figure validation is deliberately skipped: a working
        page may hold unbound figures mid-thought; the workbench lints, the
        final build enforces. Returns ``(page, inputs, outputs)`` so the dev
        server can watch binding fingerprints without a second resolve;
        :meth:`snapshot` is this plus the banner and code appendix, on disk.

        *require_placed* refuses a declared figure the template never places,
        the same refusal :meth:`render` makes — the draft preview passes it,
        so a preview cannot show green where publish would refuse.
        """
        report, inputs = self.build(models)
        outputs: list[StampedData] = []
        if self.report_py_path is not None:
            outputs = self.apply_report_py(report, inputs)

        page, _warnings, unplaced = self.render_page(
            report, strip_exploration=False)
        page = _with_kicker(page, " · ".join(self.model_labels(models)),
                            app=self.app_source is not None)
        if require_placed:
            self._refuse_unplaced(unplaced)
        try:
            work_figs = extract_figures(page)
        except FigureError:
            work_figs = []          # a working page may be mid-edit; lint, don't block
        from tracebi.reports.stack import figures_config
        cfg = {"badges": True,
               "figures": figures_config(work_figs,
                                         {sd.name for sd in outputs})}
        # The model's declared formats, as the build embeds them — a preview
        # that formats numbers differently from the file that ships is no
        # preview.
        formats = self._declared_column_formats(
            models, {sd.name: sd.dataset for sd in inputs + outputs})
        page = self._inject(
            page, data_blocks_html(inputs + outputs),
            stage="exploration", figures_cfg=cfg,
            extra_blocks_html=(embed_json(formats, "tracebi-formats") + "\n"
                               + self._selection_blocks()))
        return page, inputs, outputs

    def snapshot(self, models: dict, output_path: str) -> None:
        """Write the review snapshot — the sendable working state (v2 §2.5).

        Exploration blocks are KEPT, a persistent banner names the stage, a
        read-only code appendix satisfies "look through the code if
        necessary", and **no manifest is written** — a draft receipt must
        never exist to launder, so the file carries none and ``verify --file``
        refuses it by name.
        """
        import html as _html

        page, _inputs, _outputs = self.render_exploration(models)

        banner = (
            '<div style="position:sticky;top:0;z-index:9999;background:#b45309;'
            'color:#fff;font:600 13px/1.4 system-ui,sans-serif;padding:8px 16px;'
            'text-align:center">EXPLORATION SNAPSHOT — working state for '
            'review. Carries no trace; numbers here are not verified.</div>'
        )
        body_open = page.find("<body")
        if body_open != -1:
            body_open = page.index(">", body_open) + 1
            page = page[:body_open] + banner + page[body_open:]

        appendix = ['<hr><section style="font:12px/1.5 ui-monospace,monospace">'
                    "<h2>Code appendix (read-only)</h2>"]
        for label, text in (
            ("report.json", json.dumps(
                {"name": self.name,
                 "data": {k: v.to_dict() for k, v in self.bindings.items()}},
                indent=2)),
            ("report.py", _read_optional(self.report_py_path or "")),
            ("script.js", self.script_js),
        ):
            if text.strip():
                appendix.append(f"<h3>{label}</h3><pre>"
                                f"{_html.escape(text)}</pre>")
        appendix.append("</section>")
        page = insert_before(page, "</body>", "".join(appendix))

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(page)

    # ── Escape hatch: report.py (architecture §8-M3) ────────────────────────

    def apply_report_py(self, report: Report, inputs: list[StampedData]) -> list[StampedData]:
        """Run report.py over the stamped inputs; stamp+carry its outputs.

        Adds one :class:`_PythonDerivedSection` per output to *report* (so the
        output fingerprint is backed by a section and ``verify --file`` can
        vouch for the embedded bytes) and returns the output
        :class:`StampedData` list — embedded after the inputs. The input
        carrier sections *report* already holds stay untouched: they remain
        query-reproducible in the receipt.
        """
        input_frames = {sd.name: sd.dataset.to_pandas() for sd in inputs}
        outputs_raw = self._run_report_py(input_frames)

        outputs: list[StampedData] = []
        for out_name, df in outputs_raw.items():
            if out_name in input_frames:
                raise ValueError(
                    f"report.py in package '{self.name}' returned an output named "
                    f"'{out_name}', which collides with a stamped input of the same "
                    f"name; give the output a distinct name."
                )
            sd = stamp_frame(df, name=out_name)
            outputs.append(sd)
            report.add(_PythonDerivedSection(
                title=out_name, dataset=sd.dataset, id=out_name))
        return outputs

    def _run_report_py(self, input_frames: dict) -> dict:
        """Import report.py, call ``build(inputs)``, and validate its return.

        Runs at *build* time only (never on a web request — the build step
        emits a static file). It is the analyst's own code, unsandboxed by
        design (architecture §6): its inputs are stamped, its output is not
        replay-proved. The contract is narrow: a module-level ``build`` that
        takes ``{name: DataFrame}`` and returns a non-empty ``{name:
        DataFrame}``.
        """
        mod_name = f"tracebi_report_py_{self.name}"
        spec = importlib.util.spec_from_file_location(mod_name, self.report_py_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load report.py: {self.report_py_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(mod_name, None)

        build_fn = getattr(module, "build", None)
        if not callable(build_fn):
            raise ValueError(
                f"report.py in package '{self.name}' must define a module-level "
                f"build(inputs) function that returns {{name: DataFrame}}."
            )
        result = build_fn(input_frames)
        if not isinstance(result, dict) or not result:
            raise ValueError(
                f"report.py build() in package '{self.name}' must return a "
                f"non-empty dict of {{name: DataFrame}}; got {type(result).__name__}."
            )
        for k, v in result.items():
            if not isinstance(k, str) or not isinstance(v, pd.DataFrame):
                raise ValueError(
                    f"report.py build() in package '{self.name}' must return "
                    f"{{str: DataFrame}}; output '{k}' is a "
                    f"{type(v).__name__}, not a DataFrame."
                )
        return result

    # ── Injection ───────────────────────────────────────────────────────────

    def _selection_blocks(self) -> str:
        """The selection marker: the report's authored selection, stated in
        the file. The page engine reads the same selection from the calc
        payload (``authored_selection``) and recomputes under it.
        """
        if not self.selection:
            return ""
        from tracebi.reports.embed import embed_json

        payload = {
            "report": self.package_id,
            "model": self.selection["model"],
            "filters": self.selection["filters"],
        }
        return embed_json(payload, "tracebi-selection") + "\n"

    def _slice_blocks(self, models: dict, manifest: ReportManifest,
                      outputs: list[str]) -> str:
        """The slice blocks and the calc payload, recorded in *manifest*.

        One Parquet block per fact (``tracebi-slice-<fact>``) and one JSON
        block (``tracebi-calc-plans``) with every binding's plan. The
        manifest's ``slice`` entry holds each block's ``payload_sha256``,
        the hash of the bytes shipped, from the one encoding that made the
        block. ``embed: none`` adds nothing, so the page is what it was
        before slices existed.
        """
        from tracebi.reports.slice import (
            CALC_PLANS_ID, binding_plans, build_slice, calc_plans_payload,
        )

        if self.embed == "none":
            return ""
        blocks = build_slice(self, models)
        plans = binding_plans(self, models, blocks, outputs)
        manifest.slice = {key: b.manifest_record(self.embed)
                          for key, b in blocks.items()}
        manifest.plans = plans
        html = "".join(b.block_html() + "\n" for b in blocks.values())
        return html + embed_json(
            calc_plans_payload(self, models, blocks, plans), CALC_PLANS_ID) + "\n"

    def _libs_for_page(self, page: str) -> list:
        """Declared ``libs``, plus D3 when *page* contains a chart figure.

        *page* is the one the reader gets: ``{{ figure() }}`` already
        expanded, and exploration already stripped on a final build. Dev
        and snapshot pass the page with exploration kept, so a chart there
        draws too. A report that lists ``echarts`` keeps the ECharts engine
        (its ``configureChart`` patches apply only there) and gets no D3
        added; each lib is inlined once.
        """
        from tracebi.reports.figures import FigureError, extract_figures

        libs: list[str] = []
        seen: set[str] = set()
        if self.app_source is not None:
            from tracebi.reports.app_lane import libs_for
            for lib in libs_for(self.app_imports):
                libs.append(lib)
                seen.add(lib)
        for lib in self.libs:
            if lib not in seen:
                libs.append(lib)
                seen.add(lib)
        if "echarts" in seen:
            return libs
        try:
            has_chart = any(fig.kind == "chart" for fig in extract_figures(page))
        except FigureError:
            has_chart = False
        if has_chart and "d3" not in seen:
            libs.append("d3")
        return libs

    def _inject(self, page: str, data_blocks: str, stage: Optional[str] = None,
                figures_cfg: Optional[dict] = None,
                extra_blocks_html: str = "") -> str:
        """Insert the full presentation stack (architecture v2 §2.4).

        Independent of any template placeholder (see the module docstring),
        via :mod:`tracebi.reports.stack` — the one injection order, which IS
        the override chain: CSP → stage meta → tracebi.css → the project's
        ``reports/_theme.css`` → this package's ``style.css`` into
        ``<head>``; charting libs → tracebi.js → the safe embedded-data
        blocks → the figures/provenance config → this package's
        ``script.js`` before ``</body>``. The author's layers run last, so
        they win. A pure fragment is already a document by this point; a page
        that still has no ``</head>`` or ``</body>`` is a hard error —
        dropping the injection would ship a page with no data and no warning.

        *extra_blocks_html* (the final build's semantic-contract blocks)
        rides in the same data-block slot, after the bindings.
        """
        from tracebi.reports.stack import apply_stack, project_theme_css

        if self.app_source is not None:
            from tracebi.reports.app_lane import app_blocks_html
            extra_blocks_html += app_blocks_html(self.app_source, self.app_icons)
        return apply_stack(
            page,
            libs=self._libs_for_page(page),
            # *data_blocks* arrives pre-built (the final build passes its
            # EmbedPlan's blocks so the manifest hashes the SAME bytes; the
            # dev snapshot builds blocks directly — it writes no manifest).
            data_blocks_html=(data_blocks + extra_blocks_html),
            stage=stage,
            project_css=project_theme_css(),
            report_css=self.style_css,
            figures_cfg=figures_cfg,
            report_js=self.script_js,
            app=self.app_source is not None,
            theme_css=self.theme_css,
        )


def _ensure_about_home(page: str) -> tuple[str, int]:
    """Return ``(page, insert_at)`` for the footer that ends the page.

    Prefer the author's ONE ``data-tb-methodology`` container. When the
    template left none, append a ``<footer class="tb-footer">`` before
    ``</body>`` so the footer is on by default. Its id lets an app place it
    (the kit's ``<Footer />``).
    """
    insert_at = methodology_insertion(page)
    if insert_at is not None:
        return page, insert_at
    footer = ('<footer class="tb-footer" id="tb-footer" data-tb-methodology>'
              "</footer>")
    close = page.lower().rfind("</body>")
    if close < 0:
        page = page + footer
    else:
        page = page[:close] + footer + page[close:]
    insert_at = methodology_insertion(page)
    assert insert_at is not None
    return page, insert_at


_MASTHEAD_OPEN = re.compile(
    r"<(header|div|section)\b[^>]*\bclass=\"[^\"]*\btb-masthead\b[^\"]*\"[^>]*>", re.I)


def _with_kicker(page: str, kicker: str, *, app: bool) -> str:
    """Give the masthead its default kicker, the model's label, when the
    author wrote none; a kicker the author wrote always wins.

    A template page gets a ``<p class="tb-kicker">`` before the masthead's
    ``<h1>``, so a reader without JavaScript sees it too. An app page's
    masthead is drawn by the kit, which reads the label from the app's
    mount point, ``<div id="tb-app" data-tb-kicker>``.
    """
    import html as _html

    if not kicker:
        return page
    text = _html.escape(kicker)
    if app:
        return page.replace('<div id="tb-app">',
                            f'<div id="tb-app" data-tb-kicker="{text}">', 1)
    head = _MASTHEAD_OPEN.search(page)
    if head is None:
        return page
    h1 = re.compile(r"<h1\b", re.I).search(page, head.end())
    if h1 is None:
        return page
    before = page[head.end():h1.start()]
    if "tb-kicker" in before or f"</{head.group(1).lower()}>" in before.lower():
        return page
    return (page[:h1.start()] + f'<p class="tb-kicker">{text}</p>\n'
            + page[h1.start():])


def _footer_html(manifest: ReportManifest, model_labels: list[str],
                 notes_html: str = "", app: bool = False) -> str:
    """The footer's build-written part: one visible line, then "How these
    numbers were made" behind a ``<details>``.

    The line says when the file was built, from which model (by its label),
    and that the page does not claim the numbers are right. Who built it
    is tooling provenance: the drawer's About this build carries it, not
    the page. The disclosure holds what the trace is for, the app note,
    and the stated methodology appendix; with the runtime the line's
    "How these numbers were made" opens the drawer and the disclosure
    hides (the drawer holds the same). Locked honesty: never says
    verified, reproduces, or correct.
    """
    import html as _html

    when = _about_when(manifest.rendered_at)
    parts = [f"Built {_html.escape(when)}"] if when else []
    parts += [_html.escape(label) for label in model_labels]
    line = (" · ".join(parts) + ". " if parts else "")
    line += "This page does not claim the numbers are right."

    inner = [
        '<p class="tb-footer-note">This file carries its trace: each '
        "figure names the query that produced it and a fingerprint of the "
        "result. <code>tracebi verify</code> re-runs those queries and "
        "checks whether the numbers still match the model.</p>"
    ]
    if app:
        inner.append(
            '<p class="tb-footer-note">This page is an app. The figures it '
            "shows through the TraceBi kit are traced; anything else "
            "it draws is the app's own presentation and is not checked.</p>"
        )
    return (f'<p class="tb-footer-line">{line}</p>'
            '<details class="tb-footer-details">'
            "<summary>How these numbers were made</summary>"
            + "".join(inner) + notes_html + "</details>")


def _about_when(rendered_at: str) -> str:
    """UTC calendar day from an ISO stamp ("18 Oct 2026"), or empty when
    unusable."""
    if not rendered_at:
        return ""
    try:
        # Accept trailing Z; date-only is enough for a reader.
        stamp = rendered_at.replace("Z", "+00:00")
        day = datetime.fromisoformat(stamp).date()
        return f"{day.day} {day.strftime('%b %Y')}"
    except ValueError:
        return rendered_at[:10] if len(rendered_at) >= 10 else ""


def _methodology_html(notes: dict, contracts: dict) -> str:
    """The stated-methodology entries as HTML — an appendix, never a claim.

    Wrapped in ``.tb-methodology`` with one ``.tb-note`` line per entry
    (muted, small; deliberately nowhere near a badge class). Every piece of
    text is escaped: notes and descriptions are the author's prose, carried
    verbatim but rendered inert. Locked language throughout: the transform
    STATES — nothing here is verified.
    """
    import html as _html

    # The manifest keys are table-keyed; the rendered line names the
    # transform, recovered from the contracts block (a table with a note
    # necessarily has a covering record there). Dedupe so a record covering
    # several loaded tables states itself once.
    transform_note_of: dict[str, str] = {}
    for table, note in (notes.get("transform_notes") or {}).items():
        transform = (contracts.get(table) or {}).get("transform")
        if transform:
            transform_note_of.setdefault(transform, note)
    check_notes = notes.get("check_notes") or []
    transforms = list(dict.fromkeys(
        list(transform_note_of) + [cn["transform"] for cn in check_notes]))

    lines: list[str] = []
    for transform in transforms:
        note = transform_note_of.get(transform)
        if note:
            lines.append(
                f'<p class="tb-note">the transform '
                f"'{_html.escape(str(transform))}' states: "
                f"{_html.escape(note)}</p>"
            )
        for cn in check_notes:
            if cn["transform"] == transform:
                lines.append(
                    f'<p class="tb-note">&middot; '
                    f"{_html.escape(str(cn['check']))}"
                    f"({_html.escape(str(cn['table']))}): "
                    f"{_html.escape(cn['note'])}</p>"
                )
    for measure, description in (notes.get("measure_notes") or {}).items():
        lines.append(
            f'<p class="tb-note">measure \'{_html.escape(str(measure))}\': '
            f"{_html.escape(description)}</p>"
        )
    return '<div class="tb-methodology">' + "".join(lines) + "</div>"


def _embedded_payload(block: str) -> str:
    """The exact JSON payload string between an :func:`embed_json` block's
    tags — the bytes the offline checker recovers and rehashes, taken from
    the block itself so the hash can never disagree with what shipped."""
    return block[block.index(">") + 1:block.rindex("</script>")]


def _receipt_payload(manifest: ReportManifest, figs: list[Figure],
                     fingerprints: dict, binding_models: dict,
                     contracts: dict, bindings: Optional[dict] = None,
                     app: bool = False) -> dict:
    """The ``tracebi-receipt`` block's payload — the receipt drawer's feed.

    Presentation feed only: it duplicates facts the manifest records so the
    built page can show its own provenance offline; the MANIFEST remains
    the receipt of record, and nothing in verify reads this block. Key
    order is fixed and every aggregate is sorted or in document order, so
    the payload is byte-stable across renders (the ``rendered_at`` stamp
    aside). ``transform_contracts`` is compacted to ``{table: status}`` —
    the drawer names the status; the full record stays in the manifest.
    ``bindings`` is per binding the query as run (the manifest's
    ``query_spec``), its row count, and how many of its ``order_by`` keys
    the author wrote (the rest is the engine's tie-break), so the drawer
    can state each query in one line without the page.
    """
    figures = []
    for f in figs:
        entry: dict = {"id": f.id, "kind": f.kind}
        if f.binding:
            entry["binding"] = f.binding
        if f.cell:
            entry["cell"] = f.cell
        if f.unverified:
            entry["unverified"] = True
        fp = fingerprints.get(f.binding) if f.binding else None
        if fp:
            entry["fingerprint"] = fp
        # Model names come from the bindings' DataRefs — a report.py
        # output has no DataRef, so its figure records no model.
        model = binding_models.get(f.binding) if f.binding else None
        if model:
            entry["model"] = model
        figures.append(entry)
    payload: dict = {
        "report": manifest.report_name,
        "rendered_at": manifest.rendered_at,
        "git_sha": manifest.git_sha,
        "figures": figures,
    }
    if bindings:
        payload["bindings"] = bindings
    if contracts:
        payload["transform_contracts"] = {
            table: contracts[table]["status"] for table in sorted(contracts)
        }
    if manifest.semantic_contract:
        payload["semantic_contract_models"] = sorted(manifest.semantic_contract)
    payload["methodology"] = manifest.methodology is not None
    # The footer's facts, for the drawer to show (DS-6): who built the file
    # and the stated methodology text, both copies of what the manifest
    # records.
    who = (manifest.rendered_by or "").strip()
    if who and who != "unknown":
        payload["rendered_by"] = who
    if manifest.methodology is not None:
        payload["stated_methodology"] = manifest.methodology
    # The footer's app note, which the drawer states once the runtime has
    # folded the footer's disclosure into it.
    if app:
        payload["app"] = True
    return payload


def _figure_record(f: Figure) -> dict:
    """One figure as its manifest claim — omitting empty fields, so the
    record stays diff-friendly and a claim's absence is meaningful."""
    d: dict = {"id": f.id, "kind": f.kind}
    if f.binding:
        d["binding"] = f.binding
    if f.cell:
        d["cell"] = f.cell
    if f.unverified:
        d["unverified"] = True
    if f.note:
        d["note"] = f.note
    if f.attrs.get("data-tb-totals"):
        d["totals"] = f.attrs["data-tb-totals"]
    return d


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _read_optional(path: str) -> str:
    return _read_text(path) if os.path.isfile(path) else ""
