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


def stack_head(stage: Optional[str] = None, project_css: str = "",
               report_css: str = "", include_csp: bool = True) -> str:
    """The head injection, in override order (later wins)."""
    head = csp_meta() if include_csp else ""
    if stage:
        head += f'<meta name="tracebi-stage" content="{stage}">\n'
    head += f"<style>\n{read_asset('tracebi.css')}\n</style>\n"
    if project_css.strip():
        head += f"<style>\n{project_css}\n</style>\n"
    if report_css.strip():
        head += f"<style>\n{report_css}\n</style>\n"
    return head


def stack_tail(libs, data_blocks_html: str, figures_cfg: Optional[dict] = None,
               report_js: str = "") -> str:
    """The body-end injection: libs → runtime → engine → data → config → author."""
    tail = ""
    for lib in libs or ():
        tail += f"<script>\n{read_lib(lib)}\n</script>\n"
    tail += f"<script>\n{read_asset('tracebi.js')}\n</script>\n"
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
        tail += f"<script>\n{report_js}\n</script>\n"
    return tail


def apply_stack(page: str, *, libs, data_blocks_html: str,
                stage: Optional[str] = None, project_css: str = "",
                report_css: str = "", figures_cfg: Optional[dict] = None,
                report_js: str = "") -> str:
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
                   include_csp=csp_meta().strip() not in page))
    page = insert_before(page, "</body>",
                         stack_tail(libs, data_blocks_html, figures_cfg,
                                    report_js))
    return page
