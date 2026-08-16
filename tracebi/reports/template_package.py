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
``</body>`` of the *rendered* HTML, and a missing ``</head>`` or ``</body>``
fails loudly rather than dropping the injection on the floor.

The embedded data carries the M0 canonical triple, so ``tracebi verify --file``
works on the output.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from typing import Optional

import pandas as pd

from tracebi.reports.embed import (
    KNOWN_LIBS, StampedData, csp_meta, embed_block, embedded_record,
    insert_before, read_lib, stamp, stamp_frame,
)
from tracebi.reports.figures import (
    Figure, FigureError, assign_figure_ids, extract_figures, strip_stage,
)
from tracebi.reports.html_renderer import HTMLRenderer
from tracebi.reports.report import (
    ARTIFACT_MANIFEST_SCHEMA_VERSION, Report, ReportManifest, TableSection,
)
from tracebi.spec import DataRef

#: Files that make up a package. ``report.json`` and ``template.html`` are
#: required; the stylesheet and script are read when present. ``report.py`` is
#: the optional escape hatch (architecture §8-M3).

REPORT_JSON = "report.json"
TEMPLATE_HTML = "template.html"
STYLE_CSS = "style.css"
SCRIPT_JS = "script.js"
REPORT_PY = "report.py"


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
        self.name = os.path.basename(os.path.normpath(directory))

        report_json_path = os.path.join(directory, REPORT_JSON)
        template_path = os.path.join(directory, TEMPLATE_HTML)
        if not os.path.isfile(report_json_path):
            raise FileNotFoundError(
                f"Template package '{directory}' has no {REPORT_JSON}."
            )
        if not os.path.isfile(template_path):
            raise FileNotFoundError(
                f"Template package '{directory}' has no {TEMPLATE_HTML}."
            )

        with open(report_json_path, encoding="utf-8") as f:
            declaration = json.load(f)
        if not isinstance(declaration, dict):
            raise ValueError(
                f"{report_json_path}: the top level must be an object."
            )

        self.name = declaration.get("name") or self.name
        self.author = declaration.get("author", "")
        self.description = declaration.get("description", "")

        data = declaration.get("data")
        if not isinstance(data, dict) or not data:
            raise ValueError(
                f"{report_json_path}: needs a non-empty 'data' object mapping "
                f"each binding name to {{'model': ..., 'query': ...}}."
            )
        # Reuse DataRef's structural validation for every binding.
        self.bindings: dict[str, DataRef] = {}
        for binding_name, ref_raw in data.items():
            if not isinstance(ref_raw, dict):
                raise ValueError(
                    f"{report_json_path}: data binding '{binding_name}' must be "
                    f"an object with 'model' and 'query'."
                )
            self.bindings[binding_name] = DataRef.from_dict(ref_raw)

        self.template_html = _read_text(template_path)
        self.style_css = _read_optional(os.path.join(directory, STYLE_CSS))
        self.script_js = _read_optional(os.path.join(directory, SCRIPT_JS))

        # Charting libraries to inline into the self-contained file (offline, no
        # CDN). ``"echarts"`` is the default engine; a package opts in per report
        # so a data-only report stays small. Unknown libs fail loudly.
        libs = declaration.get("libs", [])
        if not isinstance(libs, list) or any(lib not in KNOWN_LIBS for lib in libs):
            raise ValueError(
                f"{report_json_path}: 'libs' must be a list drawn from "
                f"{sorted(KNOWN_LIBS)}."
            )
        self.libs = libs

        # The escape hatch (architecture §8-M3). When present, the ``data``
        # bindings above are the *stamped inputs* to report.py's ``build``;
        # the page embeds its python-derived *outputs* beside them.
        report_py = os.path.join(directory, REPORT_PY)
        self.report_py_path: Optional[str] = (
            report_py if os.path.isfile(report_py) else None
        )

    # ── Build + render ──────────────────────────────────────────────────────

    def build(self, models: dict):
        """Resolve every binding and assemble the carrier :class:`Report`.

        Returns ``(report, stamped)`` where *stamped* is the list of
        :class:`~tracebi.reports.embed.StampedData`, one per binding, in
        declaration order.
        """
        report = Report(self.name)
        if self.author:
            report.author(self.author)
        if self.description:
            report.description(self.description)

        stamped = []
        for binding_name, ref in self.bindings.items():
            model = (models or {}).get(ref.model)
            if model is None:
                raise ValueError(
                    f"Cannot render package '{self.name}': binding "
                    f"'{binding_name}' names model '{ref.model}', which was not "
                    f"supplied. Available: {sorted(models or {})}."
                )
            sd = stamp(model, ref.query, name=binding_name)
            stamped.append(sd)
            # A synthetic carrier: it exists only so the manifest-first receipt
            # fingerprints this binding through the ordinary to_manifest_dict
            # path. The analyst's template decides what is actually drawn.
            report.add(TableSection(title=binding_name, dataset=sd.dataset,
                                    id=binding_name))
        return report, stamped

    def render(
        self,
        models: dict,
        output_path: str,
        save_manifest: bool = True,
        manifest_path: Optional[str] = None,
    ) -> ReportManifest:
        """Render the package to one self-contained ``.html`` (+ manifest).

        Manifest first, artifact second — the receipt is built and the embedded
        fingerprints recorded before a byte of the page is written, so a render
        that half-fails cannot leave a page without a receipt.
        """
        report, inputs = self.build(models)

        # Verifiability is carried per binding, never per package
        # (report-architecture-v2 §2.1). Every declared ``data`` binding is
        # query-reproducible and embeds ``verifiable: true`` — a report.py
        # beside it no longer flattens it to false. Every report.py output
        # embeds ``verifiable: false``, hardcoded: a python-derived number
        # never reads as query-reproducible, whatever sits next to it.
        outputs: list[StampedData] = []
        if self.report_py_path is not None:
            outputs = self._apply_report_py(report, inputs)
        embed_items = inputs + outputs

        renderer = HTMLRenderer(
            template=self.template_html,
            template_context={"bindings": list(self.bindings)},
        )
        page = renderer.to_html(report)
        # Final build: exploration blocks are DELETED by the build, not by a
        # rewrite (v2 §2.1) — then ids are assigned and the figure claims
        # validated against what is actually embedded. Extraction, the strip,
        # and verify --file all share the one tokenizer in figures.py.
        page = strip_stage(page, "exploration")
        page, id_warnings = assign_figure_ids(page)
        for w in id_warnings:
            print(f"[tracebi] {self.name}: {w}", file=sys.stderr)
        figs = extract_figures(page)
        self._validate_figures(figs, inputs, outputs)

        # Manifest first, artifact second — and the figure claims layer rides
        # in it (schema v2: the refuse-newer-schema path in verify is the
        # compatibility mechanism it was reserved for).
        manifest = report.build_manifest("html", output_path)
        manifest.embedded_data = (
            [embedded_record(sd, verifiable=True) for sd in inputs]
            + [embedded_record(sd, verifiable=False) for sd in outputs]
        )
        manifest.schema_version = ARTIFACT_MANIFEST_SCHEMA_VERSION
        manifest.stage = "final"
        manifest.figures = [_figure_record(f) for f in figs]

        page = self._inject(page, embed_items, stage="final")

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(page)
        if save_manifest:
            manifest.save(manifest_path or output_path + ".manifest.json")
        return manifest

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

    # ── Escape hatch: report.py (architecture §8-M3) ────────────────────────

    def _apply_report_py(self, report: Report, inputs: list[StampedData]) -> list[StampedData]:
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

    def _inject(self, page: str, stamped, stage: Optional[str] = None) -> str:
        """Insert the CSP, stage meta, style, charting libs, data blocks, script.

        Independent of any template placeholder (see the module docstring). Into
        ``<head>``: a strict CSP (architecture §5), the page's stage meta, and
        the stylesheet. Before ``</body>``, in order: any inlined charting
        library, the safe embedded-data blocks, then the app script that reads
        them. A missing ``</head>`` or ``</body>`` is a hard error — dropping
        the injection would ship a page with no data and no warning.
        """
        head = csp_meta()
        if stage:
            head += f'<meta name="tracebi-stage" content="{stage}">\n'
        if self.style_css.strip():
            head += f"<style>\n{self.style_css}\n</style>\n"
        page = insert_before(page, "</head>", head)

        # Library first (so its global exists), then data (so the blocks are in
        # the DOM), then the app script that draws from them.
        tail = ""
        for lib in self.libs:
            tail += f"<script>\n{read_lib(lib)}\n</script>\n"
        tail += "".join(embed_block(sd) + "\n" for sd in stamped)
        if self.script_js.strip():
            tail += f"<script>\n{self.script_js}\n</script>\n"
        if tail:
            page = insert_before(page, "</body>", tail)
        return page


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
    return d


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _read_optional(path: str) -> str:
    return _read_text(path) if os.path.isfile(path) else ""
