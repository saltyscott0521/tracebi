"""The shipped design system asset: tracebi/reports/assets/tracebi.css.

Checks the asset exists, stays lean, seeds its chart tokens exactly from
ChartSpec's DEFAULT_PALETTE, and defines the components the figure grammar
relies on (table variants, provenance badges, exploration treatment).
"""

import re
from pathlib import Path

from tracebi.reports.chart import DEFAULT_PALETTE

CSS_PATH = Path(__file__).resolve().parents[1] / "tracebi" / "reports" / "assets" / "tracebi.css"


def test_asset_exists_and_is_lean():
    assert CSS_PATH.is_file()
    assert CSS_PATH.stat().st_size < 20 * 1024


def test_chart_tokens_match_default_palette():
    css = CSS_PATH.read_text()
    tokens = dict(re.findall(r"--tb-chart-(\d+):\s*(#[0-9A-Fa-f]{6})", css))
    assert len(tokens) == len(DEFAULT_PALETTE)
    for i, color in enumerate(DEFAULT_PALETTE, start=1):
        assert tokens[str(i)].lower() == color.lower(), f"--tb-chart-{i}"


def test_components_present():
    css = CSS_PATH.read_text()
    for needle in (
        ".tb-table--striped",
        ".tb-table--compact",
        ".tb-badge--verified",
        ".tb-badge--derived",
        ".tb-badge--unverified",
        ".tb-badge-anchor",
        '[data-tb-stage="exploration"]',
    ):
        assert needle in css, needle


def test_value_card_treatment_scoped_to_kpi_class():
    """The card is the .tb-kpi CLASS's opt-in, never the attribute's.

    A bare ``[data-tb-figure="value"]`` is an inline span bound in prose —
    the hydrator writes into the element itself when there is no
    .tb-kpi-value child — so no selector may style the attribute without
    requiring .tb-kpi in the same compound, or the span becomes a
    sentence-breaking card.
    """
    css = re.sub(r"/\*.*?\*/", "", CSS_PATH.read_text(), flags=re.S)
    needle = '[data-tb-figure="value"]'
    for m in re.finditer(re.escape(needle), css):
        # Walk back to the start of the compound selector the match sits in.
        j = m.start()
        while j > 0 and css[j - 1] not in " \t\n,>+~{}":
            j -= 1
        compound = css[j:m.end()]
        assert ".tb-kpi" in compound, (
            f"selector styles a bare value figure: {compound!r}"
        )
    # The card itself still exists, scoped to the class.
    kpi = re.search(r"\.tb-kpi\s*\{([^}]*)\}", css)
    assert kpi is not None and "display: flex" in kpi.group(1)
    assert "position: relative" in kpi.group(1)  # anchors its badge
