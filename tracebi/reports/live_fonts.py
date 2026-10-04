"""Live-view typefaces for reports served by the web UI or ``tracebi dev``.

Offline artifacts keep the ``system-ui`` stack in ``tracebi.css`` — no
font bytes in ``output/*.html``, so a downloaded file stays lean and
self-contained under the strict CSP. When the same HTML is *viewed* through
the server (Reports iframe, ``/r/<name>``, the dev preview), this module
injects Source Sans 3 / Source Code Pro as ``data:`` URIs (``font-src data:``
already allows them) and overrides the type tokens.

Never call this from the build path. Download and ``verify --file`` must
see the bytes on disk, without these faces.
"""

from __future__ import annotations

import base64
import functools
import os

from tracebi.reports.embed import insert_before

_FONTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "fonts",
)

# Lean latin set: body + emphasis + headings, plus one mono cut for receipts.
_FACES = (
    ("source-sans-3-latin-400-normal.woff2", "Source Sans 3", 400),
    ("source-sans-3-latin-600-normal.woff2", "Source Sans 3", 600),
    ("source-sans-3-latin-700-normal.woff2", "Source Sans 3", 700),
    ("source-code-pro-latin-400-normal.woff2", "Source Code Pro", 400),
)

_MARKER = "<!-- tracebi live fonts: server / preview only; not in the offline file -->"


@functools.lru_cache(maxsize=1)
def live_font_css() -> str:
    """``@font-face`` rules + token overrides, cached for the process."""
    rules = []
    for filename, family, weight in _FACES:
        path = os.path.join(_FONTS_DIR, filename)
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"shipped live-view font missing: {path} — packaging defect "
                f"(the wheel must carry tracebi/reports/assets/fonts)."
            )
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        rules.append(
            f"@font-face{{\n"
            f"  font-family:'{family}';\n"
            f"  font-style:normal;\n"
            f"  font-weight:{weight};\n"
            f"  font-display:swap;\n"
            f"  src:url(data:font/woff2;base64,{b64}) format('woff2');\n"
            f"}}"
        )
    rules.append(
        ":root{\n"
        "  --tb-font:'Source Sans 3',system-ui,-apple-system,'Segoe UI',"
        "Roboto,'Helvetica Neue',Arial,sans-serif;\n"
        "  --tb-mono:'Source Code Pro',ui-monospace,SFMono-Regular,Menlo,"
        "Consolas,monospace;\n"
        "}"
    )
    return "\n".join(rules)


def with_live_fonts(html: str) -> str:
    """Inject the live-view faces into a report HTML string (idempotent)."""
    if not html or _MARKER in html:
        return html
    block = (
        f"{_MARKER}\n"
        f"<style>\n{live_font_css()}\n</style>\n"
    )
    if "</head>" in html:
        return insert_before(html, "</head>", block)
    return block + html
