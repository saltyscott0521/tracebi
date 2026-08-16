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
        '[data-tb-stage="exploration"]',
    ):
        assert needle in css, needle
