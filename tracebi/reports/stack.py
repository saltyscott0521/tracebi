"""
The presentation stack (architecture v2 §2.4).

One function pair builds every artifact page's head and tail, and the
injection order IS the override chain — ``Theme.with_overrides``'s
append-so-later-wins semantic, promoted to page scale:

    <head>:  CSP → stage meta → tracebi.css (shipped) →
             reports/_theme.css (project) → style.css (report)
    </body>: charting libs → tracebi.js (shipped runtime) → data blocks →
             tracebi-figures config → script.js (report)

The agent (or analyst) adopts, overrides, or ignores; it never forks. The
author's layers run LAST so their rules and scripts win — and the runtime
hydrates at DOM-ready, after an author script has had the chance to
register chart patches.

The figures config block carries per-figure PROVENANCE (verified /
derived / unverified), decided here at build time from what was actually
embedded — the runtime chooses badge classes from it, so a stylesheet can
restyle a badge but never re-color honesty.
"""

from __future__ import annotations

import functools
import os
from typing import Optional

from tracebi.reports.embed import (
    csp_meta, embed_json, engine_blocks_html, insert_before, read_lib,
)

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def read_asset(name: str) -> str:
    """A shipped presentation asset (tracebi.css / tracebi.js), loudly."""
    path = os.path.join(_ASSETS_DIR, name)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"shipped presentation asset missing: {path} — this is a "
            f"packaging defect (the wheel must carry tracebi/reports/assets)."
        )
    with open(path, encoding="utf-8") as f:
        return f.read()


#: What the shipped Hanken Grotesk subset covers (Latin, punctuation, currency, arrows).
#: Anything outside it falls through to the system face, as a bad glyph would.
_FONT_RANGE = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,"
                "U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,"
                "U+2212,U+2215,U+FEFF,U+FFFD")


@functools.lru_cache(maxsize=1)
def font_face_css() -> str:
    """Hanken Grotesk as an inlined ``@font-face``: the one face a report carries.

    A shipped report is one file under a strict CSP (``font-src data:``), so the
    face travels inside it, base64, rather than being fetched or installed. It is
    the same face as the web app, so a report reads as part of the product. The
    licence (SIL OFL 1.1) is in NOTICE.
    """
    import base64
    path = os.path.join(_ASSETS_DIR, "hanken-grotesk-latin-wght-normal.woff2")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"shipped presentation asset missing: {path} — this is a "
            f"packaging defect (the wheel must carry tracebi/reports/assets)."
        )
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return ('@font-face{font-family:"Hanken Grotesk";font-style:normal;font-display:swap;'
            f'font-weight:100 900;src:url("data:font/woff2;base64,{data}") '
            f'format("woff2");unicode-range:{_FONT_RANGE}}}')


def project_theme_css(root: Optional[str] = None) -> str:
    """The project brand layer: ``reports/_theme.css`` when it exists.

    Underscore-prefixed, so discovery already skips it; one file restyles
    every report the project builds.
    """
    reports_dir = os.environ.get("TRACEBI_REPORTS_DIR", "reports")
    path = os.path.join(root or os.getcwd(), reports_dir, "_theme.css")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def figures_config(figures, output_names, badges: bool = True) -> list[dict]:
    """Per-figure provenance for the runtime's badge rendering.

    verified — a declarative query binding (green-eligible under replay);
    derived — a ``report.py`` output (python-derived, never green);
    unverified — the author's explicit mark. Decided from what the build
    actually embedded, never from markup alone.
    """
    out = []
    for f in figures:
        if f.unverified:
            provenance = "unverified"
        elif f.binding in output_names:
            provenance = "derived"
        else:
            provenance = "verified"
        entry = {"id": f.id, "provenance": provenance}
        if f.note:
            entry["note"] = f.note
        out.append(entry)
    return out


_LIB_ROLE = {
    "react": "runs this page's app (app.jsx), compiled in the page",
    "recharts": "the app's own charts",
    "tailwind": "the app's utility classes, generated in the page",
}

#: Before Tailwind's browser build: the TraceBi tokens as Tailwind theme
#: colours (bg-card, text-ink, border-rule, …), so an app follows the page's
#: mode and the project theme; and its "not for production" console notice
#: muted — the page is offline by design, and that is the build it needs.
_TAILWIND_PRELUDE = '''<style type="text/tailwindcss">
@theme inline {
  --font-sans: var(--tb-font);
  --font-mono: var(--tb-mono);
  --color-ink: var(--tb-ink);
  --color-muted: var(--tb-muted);
  --color-page: var(--tb-page);
  --color-card: var(--tb-bg);
  --color-surface: var(--tb-surface);
  --color-rule: var(--tb-rule);
  --color-accent: var(--tb-accent);
  --color-accent-text: var(--tb-accent-text);
  --color-good: var(--tb-good);
  --color-bad: var(--tb-bad);
  --color-chart-1: var(--tb-chart-1);
  --color-chart-2: var(--tb-chart-2);
  --color-chart-3: var(--tb-chart-3);
  --color-chart-4: var(--tb-chart-4);
  --color-chart-5: var(--tb-chart-5);
  --color-chart-6: var(--tb-chart-6);
  --color-chart-7: var(--tb-chart-7);
  --color-chart-8: var(--tb-chart-8);
  --radius-panel: var(--tb-radius);
}
</style>
<script>(function(){var w=console.warn;console.warn=function(m){
if(typeof m==="string"&&m.indexOf("browser build of Tailwind")!==-1)return;
return w.apply(console,arguments);};})();</script>
'''


@functools.lru_cache(maxsize=None)
def _lib_credit(lib: str) -> str:
    """"Apache ECharts 6.1.0 (Apache-2.0)" or "D3 7.9.0 (ISC)" from the
    vendored file's own header, so the credit can never drift from the
    bundled version."""
    import re
    head = read_lib(lib)[:2000]
    m = re.search(r"TraceBi-credit: ([^*]+?) \*/", head)
    if m:
        return m.group(1)
    m = re.search(r"Apache ECharts ([0-9][0-9.]*)", head)
    if m:
        return f"Apache ECharts {m.group(1)} (Apache-2.0)"
    m = re.search(r"D3 ([0-9][0-9.]*)", head)
    return f"D3 {m.group(1)} (ISC)" if m else lib


def libraries_comment(libs) -> str:
    """An HTML comment at the top of every report naming what is inlined in
    it, and under which licence — a reader who opens the source learns what
    the file contains without leaving it."""
    from tracebi._version import __version__
    lines = [
        f"Built with TraceBi {__version__}. Everything below is inlined: no "
        "script, style, font or image is fetched from a CDN or the web.",
        "  tracebi.css  TraceBi design system (MIT)",
        "  Hanken Grotesk  the typeface, Latin subset (SIL OFL 1.1): inlined, no font fetched",
        "  tracebi.js   TraceBi runtime (MIT): fills each figure from the "
        "embedded, fingerprinted data; tabs, filters, receipt drawer",
    ]
    for lib in libs or ():
        lines.append(f"  {_lib_credit(lib)}: {_LIB_ROLE.get(lib, 'draws the charts')}")
    lines.append("  Report files: style.css and script.js when present; "
                 "fonts and images from the package's assets/ folder")
    return "<!--\n" + "\n".join(lines) + "\n-->\n"


def stack_head(stage: Optional[str] = None, project_css: str = "",
               report_css: str = "", include_csp: bool = True,
               libs=None, app: bool = False) -> str:
    """The head injection, in override order (later wins).

    On an app page (app.jsx) tracebi.css goes in a cascade layer between
    Tailwind's reset and its utilities, so a utility class (text-2xl) wins
    over a TraceBi default while the kit's tb-* classes still style the
    figures. The project theme and style.css stay unlayered: they win."""
    head = csp_meta() if include_csp else ""
    head += libraries_comment(libs)
    if stage:
        head += f'<meta name="tracebi-stage" content="{stage}">\n'
    css = read_asset("tracebi.css")
    if app:
        css = ("@layer theme, base, tracebi, components, utilities;\n"
               f"@layer tracebi {{\n{css}\n}}")
    head += ("<!-- tracebi.css: the TraceBi design system -->\n"
             f"<style>\n{font_face_css()}\n{css}\n</style>\n")
    if project_css.strip():
        head += ("<!-- reports/_theme.css: the project theme -->\n"
                 f"<style>\n{project_css}\n</style>\n")
    if report_css.strip():
        head += ("<!-- style.css: this report's own styles -->\n"
                 f"<style>\n{report_css}\n</style>\n")
    return head


def stack_tail(libs, data_blocks_html: str, figures_cfg: Optional[dict] = None,
               report_js: str = "") -> str:
    """The body-end injection: libs → runtime → engine → data → config → author."""
    tail = ""
    for lib in libs or ():
        if lib == "tailwind":
            tail += _TAILWIND_PRELUDE
        tail += (f"<!-- {_lib_credit(lib)} -->\n"
                 f"<script>\n{read_lib(lib)}\n</script>\n")
    # The selection worker is a few kilobytes and ships only with a sealed
    # grain. A report that did not opt in stays byte-for-byte as before.
    if 'id="tracebi-grain"' in data_blocks_html:
        tail += f"<script>\n{read_asset('selection_eval.js')}\n</script>\n"
    tail += ("<!-- tracebi.js: the TraceBi runtime -->\n"
             f"<script>\n{read_asset('tracebi.js')}\n</script>\n")
    # The worker engine ships ONLY when a binding is embedded as Parquet — a
    # CSV artifact would otherwise pay megabytes for an engine it never starts.
    # Test the DATA BLOCKS, never the assembled tail: the runtime source itself
    # mentions parquet (in comments), so scanning `tail` ships the engine always.
    if '"format": "parquet"' in data_blocks_html or \
            '"format":"parquet"' in data_blocks_html:
        tail += engine_blocks_html()
    tail += data_blocks_html
    if figures_cfg is not None:
        tail += embed_json(figures_cfg, "tracebi-figures") + "\n"
    if report_js.strip():
        tail += ("<!-- script.js: this report's own script -->\n"
                 f"<script>\n{report_js}\n</script>\n")
    return tail


def apply_stack(page: str, *, libs, data_blocks_html: str,
                stage: Optional[str] = None, project_css: str = "",
                report_css: str = "", figures_cfg: Optional[dict] = None,
                report_js: str = "", app: bool = False) -> str:
    """Inject the full stack into *page* (loud on missing head/body tags)."""
    # The carrier render may already carry the framework CSP meta
    # (html_renderer inserts the same one); a second identical tag is just
    # noise, so skip it — but ONLY when the EXACT framework meta is present.
    # The old loose substring check let any "Content-Security-Policy" text in a
    # template (a comment, an author's weaker policy) suppress the strict CSP
    # entirely, which is exactly the markup an injection would smuggle.
    page = insert_before(
        page, "</head>",
        stack_head(stage, project_css, report_css,
                   include_csp=csp_meta().strip() not in page, libs=libs, app=app))
    page = insert_before(page, "</body>",
                         stack_tail(libs, data_blocks_html, figures_cfg,
                                    report_js))
    return page
