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


def test_interaction_components_present():
    """The control grammar's presentation: scroll wrap, columns, tabs,
    and the receipt drawer chrome all ship in the one stylesheet."""
    css = CSS_PATH.read_text()
    for needle in (
        ".tb-scroll",
        ".tb-cols-2",
        ".tb-cols-3",
        ".tb-tabs",
        ".tb-tab-bar",
        ".tb-tab-active",
        ".tb-receipt-btn",
        ".tb-receipt-drawer",
        ".tb-receipt-open",
        ".tb-receipt-fp",
    ):
        assert needle in css, needle
    # Sticky header inside the scroll container.
    sticky = re.search(r"\.tb-scroll thead th\s*\{([^}]*)\}", css)
    assert sticky is not None and "position: sticky" in sticky.group(1)
    # Columns collapse to one under 720px.
    mobile = re.search(r"@media \(max-width: 720px\)\s*\{(.*?)\}\s*\}", css, re.S)
    assert mobile is not None
    assert ".tb-cols-2" in mobile.group(1) and ".tb-cols-3" in mobile.group(1)
    assert "grid-template-columns: 1fr" in mobile.group(1)
    # Tab sections hide only behind the runtime-inserted bar (sibling
    # combinator) — a page whose script never ran shows every section.
    assert ".tb-tab-bar ~ [data-tb-tab]" in css


def test_drawer_never_recolors_badges():
    """The drawer is provenance DISPLAY: no drawer rule may re-color a
    badge. A badge's tone is chosen from the recorded provenance by the
    runtime; the drawer may only re-lay it out (position, margin)."""
    css = re.sub(r"/\*.*?\*/", "", CSS_PATH.read_text(), flags=re.S)
    found_layout_rule = False
    for m in re.finditer(r"([^{}]+)\{([^}]*)\}", css):
        selector, body = m.group(1), m.group(2)
        if "tb-receipt" not in selector or "tb-badge" not in selector:
            continue
        found_layout_rule = True
        for prop in ("color", "background", "border"):
            assert not re.search(rf"(?<![-\w]){prop}", body), (
                f"drawer rule re-colors a badge: {selector.strip()!r} "
                f"sets {prop}"
            )
    # The layout rule itself must exist (position: static inside the
    # drawer, or the absolute badge would pin to the viewport corner).
    assert found_layout_rule


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
