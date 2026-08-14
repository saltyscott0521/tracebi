"""
Template-package renderer (architecture §2 lane B, §8-M1).

A *freeform package* is a directory ``reports/<name>/`` in which the analyst
draws the whole page — the built-in section renderers are not involved:

    report.json    declarative data bindings (model + query per name)
    template.html  a Jinja2 page shell the analyst controls
    style.css      the page's stylesheet
    script.js      client-side code that reads the embedded data and draws

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

import json
import os
from typing import Optional

from tracebi.reports.embed import embed_block, embedded_record, stamp
from tracebi.reports.html_renderer import HTMLRenderer
from tracebi.reports.report import Report, ReportManifest, TableSection
from tracebi.spec import DataRef

#: Files that make up a package. ``report.json`` and ``template.html`` are
#: required; the stylesheet and script are read when present.
REPORT_JSON = "report.json"
TEMPLATE_HTML = "template.html"
STYLE_CSS = "style.css"
SCRIPT_JS = "script.js"


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
        report, stamped = self.build(models)

        manifest = report.build_manifest("html", output_path)
        manifest.embedded_data = [embedded_record(sd) for sd in stamped]

        renderer = HTMLRenderer(
            template=self.template_html,
            template_context={"bindings": list(self.bindings)},
        )
        page = renderer.to_html(report)
        page = self._inject(page, stamped)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(page)
        if save_manifest:
            manifest.save(manifest_path or output_path + ".manifest.json")
        return manifest

    # ── Injection ───────────────────────────────────────────────────────────

    def _inject(self, page: str, stamped) -> str:
        """Insert style, data blocks, and script into the rendered HTML.

        Independent of any template placeholder (see the module docstring): the
        stylesheet lands before ``</head>``; the safe embedded-data blocks and
        the app script land before ``</body>``. A missing ``</head>`` or
        ``</body>`` is a hard error — dropping the injection would ship a page
        with no data and no warning.
        """
        if self.style_css.strip():
            page = _insert_before(
                page, "</head>", f"<style>\n{self.style_css}\n</style>\n"
            )

        # Data first, then the script that reads it — so the blocks are already
        # in the DOM if the script runs immediately.
        tail = "".join(embed_block(sd) + "\n" for sd in stamped)
        if self.script_js.strip():
            tail += f"<script>\n{self.script_js}\n</script>\n"
        if tail:
            page = _insert_before(page, "</body>", tail)
        return page


def _insert_before(html: str, tag: str, snippet: str) -> str:
    """Insert *snippet* immediately before *tag*, matched case-insensitively.

    Fails loudly when the tag is absent: the whole point of string injection is
    that a forgotten placeholder cannot silently swallow the data.
    """
    idx = html.lower().find(tag)
    if idx == -1:
        raise ValueError(
            f"The rendered template has no {tag} — cannot inject the report's "
            f"data/style/script. A template package's template.html must be a "
            f"complete HTML document with <head> and <body>."
        )
    return html[:idx] + snippet + html[idx:]


def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _read_optional(path: str) -> str:
    return _read_text(path) if os.path.isfile(path) else ""
