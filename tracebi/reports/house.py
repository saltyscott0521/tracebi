"""The house themes: a report's whole look, chosen by name.

``report.json`` ``"theme": "ledger" | "nightdesk" | "signal"``, else the
project's ``tracebi.yaml`` ``brand: {theme: …}``, else Ledger. A house theme
is tokens (ground, card surface and border, the card's shadow stack, radius,
type sizes and weights, the numeral face, the chart tokens, the lead KPI's
tile, an accent and an eight-colour palette, each for the light ground and the
dark one) plus a few rules, stacked right after ``tracebi.css`` and before the
project's brand, so a brand's accent, palette, font and logo win over the
theme's colours while the theme keeps its surfaces, depth, density, radius
and numerals.

Ledger is ``tracebi.css`` itself (its values are the sheet's own tokens), so
it adds nothing here. The six accent presets in ``themes/`` (graphite, indigo,
…) are deprecated: a report that names one renders in the house theme with
that accent pair, and its build says so once.

Presentation only: a theme changes how a page looks, never a number.
Reference: ``docs/reference/chart-style.md``.
"""

from __future__ import annotations

import base64
import functools
import os
from typing import Optional

DEFAULT = "ledger"

#: What an agent says when a person starts a new report or dashboard, word
#: for word in the gateway's author_report prompt, docs/agents/sop-authoring.md
#: and both agent guides (tests/test_agent_guides.py holds it there).
OFFER = (
    "Offer the house theme once, for a new report or dashboard only: when the "
    "project sets no brand.theme and the person has not named a theme, offer "
    "the three in one short line each (Ledger: calm, institutional, the "
    "default; Nightdesk: dark, dense, monospaced numbers, for a desk or ops "
    "screen; Signal: bold, big numbers, for a board pack or a wall screen), "
    "recommend one for what the report is for, and use Ledger if the person "
    "does not choose. If the project sets a theme, use it and say so in one "
    "line instead of asking. Never ask again for an existing report."
)

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

#: Per theme: what it is (``about``) and for (``for``), the mode a page opens
#: in when neither the report nor the brand names one, its density, the dark
#: card a brand's dark-ground colours are lifted against, the mode-independent
#: tokens and the light ground (``root``), the dark ground (``dark``), and
#: whether the KPI strip is separate tiles, and any rules of its own.
THEMES: dict[str, dict] = {
    "ledger": {
        "about": "calm, institutional: paper ground, white cards on soft layered "
                 "shadows, one ink-blue accent",
        "for": "a report to read, a monthly pack, anything that should look well kept",
        "mode": "auto", "density": None, "dark_card": "#141417",
        "root": {}, "dark": {}, "tiles": False, "rules": "",
    },
    "nightdesk": {
        "about": "dark first and dense: monospaced numerals, lines that glow faintly "
                 "on a near-black ground",
        "for": "a desk or an operations screen, read all day",
        "mode": "dark", "density": "compact", "dark_card": "#0f141b",
        "root": {
            "--tb-font-num": '"Geist Mono", var(--tb-mono)',
            "--tb-num-weight": "500", "--tb-num-tracking": "-0.03em",
            "--tb-kpi-size": "26px", "--tb-kpi-lead-size": "32px", "--tb-title-size": "24px",
            "--tb-radius": "6px", "--tb-chart-tooltip-radius": "4px",
            "--tb-chart-grid-dash": "1 3", "--tb-chart-dim": "0.22",
            "--tb-accent": "#0e7490", "--tb-accent-text": "#0b5f76",
            "--tb-surface-accent": "#ebf4f6", "--tb-on-accent": "#ffffff",
            "--tb-dark-accent": "#22d3ee", "--tb-dark-accent-text": "#5ee3f5",
            "--tb-page": "#eef1f4", "--tb-bg": "#ffffff", "--tb-ink": "#0f1720",
            "--tb-muted": "#5b6878", "--tb-rule": "#d9dfe6", "--tb-surface": "#eef2f6",
            "--tb-good": "#047857", "--tb-bad": "#be123c",
            "--tb-card-shadow": "none",
            "--tb-chart-grid": "#e3e8ee", "--tb-chart-axis": "#9aa6b4",
            "--tb-chart-tooltip-bg": "#0f1720", "--tb-chart-tooltip-border": "#0f1720",
            "--tb-chart-tooltip-shadow": "0 8px 22px -6px rgba(15, 23, 32, .4)",
            "--tb-chart-tooltip-ink": "#a9b6c4", "--tb-chart-tooltip-title": "#e3e9f0",
            "--tb-chart-tooltip-link": "var(--tb-dark-accent-text)",
            "--tb-chart-glow": "0",
            "--tb-lead-bg": "var(--tb-bg)", "--tb-lead-ink": "var(--tb-accent-text)",
            "--tb-lead-muted": "var(--tb-muted)",
            "--tb-lead-border": "color-mix(in srgb, var(--tb-accent) 33%, transparent)",
            "--tb-chart-2": "#d97706", "--tb-chart-3": "#7c3aed", "--tb-chart-4": "#047857",
            "--tb-chart-5": "#e11d48", "--tb-chart-6": "#2563eb", "--tb-chart-7": "#a21caf",
            "--tb-chart-8": "#4d7c0f",
        },
        "dark": {
            "--tb-page": "#090c11", "--tb-bg": "#0f141b", "--tb-ink": "#e3e9f0",
            "--tb-muted": "#8593a3", "--tb-rule": "#1c242e", "--tb-surface": "#141b24",
            "--tb-on-accent": "#04131a", "--tb-good": "#34d399", "--tb-bad": "#fb7185",
            "--tb-card-shadow": "0 0 0 1px rgba(255, 255, 255, .015)",
            "--tb-chart-grid": "#1d2631", "--tb-chart-axis": "#3a4655",
            "--tb-chart-tooltip-bg": "#0b1016",
            "--tb-chart-tooltip-border": "color-mix(in srgb, var(--tb-accent) 33%, transparent)",
            "--tb-chart-tooltip-shadow": "0 0 0 1px color-mix(in srgb, var(--tb-accent) 15%, "
                                         "transparent), 0 0 24px -6px color-mix(in srgb, "
                                         "var(--tb-accent) 35%, transparent)",
            "--tb-chart-tooltip-ink": "var(--tb-muted)",
            "--tb-chart-tooltip-title": "var(--tb-ink)",
            "--tb-chart-tooltip-link": "var(--tb-accent-text)",
            "--tb-chart-glow": "6",
            "--tb-chart-2": "#f59e0b", "--tb-chart-3": "#a78bfa", "--tb-chart-4": "#34d399",
            "--tb-chart-5": "#fb7185", "--tb-chart-6": "#60a5fa", "--tb-chart-7": "#e879f9",
            "--tb-chart-8": "#a3e635",
        },
        "tiles": True, "rules": "",
    },
    "signal": {
        "about": "bold and editorial: big heavy numerals, the lead KPI a solid accent "
                 "tile, borderless cards on large soft shadows, inverted tooltips",
        "for": "a board pack or a screen on the wall",
        "mode": "auto", "density": None, "dark_card": "#19191c",
        "root": {
            "--tb-radius": "20px", "--tb-chart-tooltip-radius": "12px",
            "--tb-title-size": "36px", "--tb-title-weight": "700",
            "--tb-kpi-size": "34px", "--tb-kpi-lead-size": "46px",
            "--tb-num-weight": "700", "--tb-num-tracking": "-0.035em",
            "--tb-accent": "#1f3fff", "--tb-accent-text": "#1a35d6",
            "--tb-surface-accent": "#eef1ff", "--tb-on-accent": "#ffffff",
            "--tb-dark-accent": "#5c74ff", "--tb-dark-accent-text": "#8d9dff",
            "--tb-accent-fill": "#1f3fff", "--tb-on-accent-fill": "#ffffff",
            "--tb-page": "#fafaf9", "--tb-bg": "#ffffff", "--tb-ink": "#111113",
            "--tb-muted": "#6c6c72", "--tb-rule": "#ebebea", "--tb-surface": "#f2f2f0",
            "--tb-card-border": "transparent",
            "--tb-card-shadow": "0 2px 4px rgba(17, 17, 19, .03), "
                                "0 20px 44px -24px rgba(17, 17, 19, .22)",
            "--tb-chart-grid": "rgba(17, 17, 19, .07)",
            "--tb-chart-axis": "rgba(17, 17, 19, .5)",
            "--tb-chart-tooltip-bg": "#111113", "--tb-chart-tooltip-border": "#111113",
            "--tb-chart-tooltip-shadow": "0 16px 36px -10px rgba(17, 17, 19, .45)",
            "--tb-chart-tooltip-ink": "#b4b4ba", "--tb-chart-tooltip-title": "#fafaf9",
            "--tb-chart-tooltip-link": "var(--tb-dark-accent-text)",
            "--tb-lead-bg": "var(--tb-accent-fill)", "--tb-lead-ink": "var(--tb-on-accent-fill)",
            "--tb-lead-muted": "color-mix(in srgb, var(--tb-on-accent-fill) 78%, transparent)",
            "--tb-lead-border": "transparent",
            "--tb-chart-2": "#ff6b2b", "--tb-chart-3": "#00a676", "--tb-chart-4": "#ffb000",
            "--tb-chart-5": "#8b5cf6", "--tb-chart-6": "#e2366b", "--tb-chart-7": "#0891b2",
            "--tb-chart-8": "#65a30d",
        },
        "dark": {
            "--tb-page": "#0e0e10", "--tb-bg": "#19191c", "--tb-ink": "#f4f4f5",
            "--tb-muted": "#a1a1a8", "--tb-rule": "#2a2a2e", "--tb-surface": "#232327",
            "--tb-good": "#2ed3a0", "--tb-bad": "#ff5c8a",
            "--tb-accent-fill": "#3d58ff", "--tb-on-accent-fill": "#ffffff",
            "--tb-card-shadow": "0 24px 50px -26px rgba(0, 0, 0, .9)",
            "--tb-chart-grid": "rgba(255, 255, 255, .07)",
            "--tb-chart-axis": "rgba(255, 255, 255, .5)",
            "--tb-chart-tooltip-bg": "#f4f4f5", "--tb-chart-tooltip-border": "#f4f4f5",
            "--tb-chart-tooltip-shadow": "0 16px 36px -10px rgba(0, 0, 0, .7)",
            "--tb-chart-tooltip-ink": "#52525b", "--tb-chart-tooltip-title": "#111113",
            "--tb-chart-tooltip-link": "var(--tb-chart-tooltip-title)",
            "--tb-chart-2": "#ff7d45", "--tb-chart-3": "#2ed3a0", "--tb-chart-4": "#ffc233",
            "--tb-chart-5": "#a78bfa", "--tb-chart-6": "#ff5c8a", "--tb-chart-7": "#22d3ee",
            "--tb-chart-8": "#a3e635",
        },
        "tiles": True,
        # The lead tile is the accent: a sparkline on it is drawn in the tile's ink.
        "rules": ".tb-kpi--lead .tb-spark :is(.tb-line, .tb-dot) { stroke: var(--tb-lead-ink); }\n"
                 ".tb-kpi--lead .tb-spark :is(.tb-area, .tb-dot) { fill: var(--tb-lead-ink); }\n",
    },
}

#: The KPI strip as separate tiles (Nightdesk, Signal) instead of Ledger's one
#: panel of hairline-joined cells. A direction arrow on the lead's tile takes
#: the tile's own ink, as its sign already says the direction.
_KPI_TILES = """\
.tb-grid:has(> .tb-kpi) { gap: var(--tb-space-3); background: none; border: 0;
  border-radius: 0; box-shadow: none; overflow: visible; }
.tb-grid > .tb-kpi { border: 1px solid var(--tb-card-border); border-radius: var(--tb-radius);
  box-shadow: var(--tb-card-shadow); }
.tb-grid > .tb-kpi.tb-kpi--lead { border-color: var(--tb-lead-border); }
.tb-kpi--lead :is(.tb-up, .tb-down, .tb-good, .tb-bad) { color: inherit; }
"""


def names() -> list[str]:
    """The house themes, the default first."""
    return list(THEMES)


def deprecated_names() -> list[str]:
    """The six accent presets a report.json may still name."""
    from tracebi.reports.stack import named_themes
    return named_themes()


def _block(selector: str, tokens: dict[str, str], indent: str = "") -> str:
    body = "".join(f"{indent}  {k}: {v};\n" for k, v in tokens.items())
    return f"{indent}{selector} {{\n{body}{indent}}}\n"


@functools.lru_cache(maxsize=1)
def mono_face_css() -> str:
    """Geist Mono (Latin subset, SIL OFL 1.1, NOTICE) as an inlined
    ``@font-face``: Nightdesk's numerals, carried in the page like Geist."""
    from tracebi.reports.stack import _FONT_RANGE
    path = os.path.join(_ASSETS_DIR, "geist-mono-latin-wght-normal.woff2")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"shipped presentation asset missing: {path} — this is a "
            f"packaging defect (the wheel must carry tracebi/reports/assets)."
        )
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return ('@font-face{font-family:"Geist Mono";font-style:normal;font-display:swap;'
            f'font-weight:100 900;src:url("data:font/woff2;base64,{data}") '
            f'format("woff2");unicode-range:{_FONT_RANGE}}}\n')


@functools.lru_cache(maxsize=None)
def css(name: str) -> str:
    """The theme's CSS, stacked right after tracebi.css: ``""`` for Ledger,
    which is that sheet's own tokens."""
    theme = THEMES[name]
    if not theme["root"]:
        return ""
    out = [f"/* {name}: {theme['about']} */\n"]
    if "Geist Mono" in theme["root"].get("--tb-font-num", ""):
        out.append(mono_face_css())
    out.append(_block(":root", theme["root"]))
    out.append(_block(':root[data-tb-mode="dark"]', theme["dark"]))
    out.append("@media (prefers-color-scheme: dark) {\n"
               + _block(':root[data-tb-mode="auto"]', theme["dark"], "  ") + "}\n")
    if theme["tiles"]:
        out.append(_KPI_TILES)
    return "".join(out) + theme["rules"]


def check(name, where: str) -> str:
    """*name* as a theme a report may name: a house theme, or a deprecated
    accent preset. Anything else fails naming the three."""
    if isinstance(name, str) and (name in THEMES or name in deprecated_names()):
        return name
    raise ValueError(f"{where}: unknown theme {name!r}; the house themes are "
                     f"{', '.join(THEMES)} (no theme is {DEFAULT}).")


def resolve(report_theme: Optional[str],
            project_theme: Optional[str]) -> tuple[str, Optional[str]]:
    """``(house, accent)``: the house theme a page takes, and the deprecated
    accent preset it names, if any. A report's own house theme wins over the
    project's; a deprecated preset keeps the project's house theme (Ledger
    when none) under that accent pair."""
    if report_theme in THEMES:
        return report_theme, None
    house = project_theme if project_theme in THEMES else DEFAULT
    return house, report_theme or None


def deprecation(accent: str, house: str) -> str:
    """The one line a build prints for a report that names an accent preset."""
    return (f"theme {accent!r} is deprecated: name a house theme "
            f"({', '.join(THEMES)}) or set the accent in tracebi.yaml "
            f"brand: {{accent: …}}. It renders as {house} with {accent}'s accent.")
