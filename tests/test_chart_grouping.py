"""
Tests for ChartSection.color grouping and compact show_values labels.

ChartSection.color pivots rows on the color column so each distinct value
becomes its own series (grouped bars, one line/area per group, per-group
scatter points). Before this existed, color= was silently ignored and a
query with a group column drew one bar per row under repeated x labels —
a confident-looking wrong chart.
"""

import hashlib
import json

import pandas as pd
import pytest

from tracebi.model.dataset import DataSet
from tracebi.reports.chart import ChartSpec
from tracebi.reports.report import ChartSection


def grouped_ds() -> DataSet:
    df = pd.DataFrame({
        "region":  ["North", "North", "South", "South", "East", "East"],
        "segment": ["Retail", "Wholesale", "Retail", "Wholesale",
                    "Retail", "Wholesale"],
        "revenue": [5000.0, 3000.0, 4250.0, 2100.0, 6100.0, 900.0],
    })
    return DataSet(df=df, name="grouped")


def plain_ds() -> DataSet:
    df = pd.DataFrame({
        "region":  ["North", "South", "East", "West"],
        "revenue": [5000.0, -1200.0, 6100.0, 300.0],
        "cost":    [3000.0, 900.0, 4000.0, 100.0],
    })
    return DataSet(df=df, name="plain")


def spec(**kw) -> ChartSpec:
    return ChartSpec.from_section(ChartSection(**kw))


# ─────────────────────────────────────────────
# color= grouping
# ─────────────────────────────────────────────

class TestColorGrouping:

    def test_bar_color_pivots_groups_into_series(self):
        s = spec(dataset=grouped_ds(), chart_type="bar",
                 x="region", y="revenue", color="segment")
        assert s.series == ("Retail", "Wholesale")     # N groups → N series
        assert len(s.rows) == 3                         # distinct x values
        svg = s.to_svg()
        # bars per x = group count → 3 x values × 2 groups = 6 bars
        assert svg.count('class="tb-bar"') == 6
        # legend present, one swatch per group
        assert svg.count('class="tb-legend-swatch"') == 2
        assert "Retail" in svg and "Wholesale" in svg
        # successive palette colours
        assert 'fill="#2E74B5"' in svg and 'fill="#ED7D31"' in svg

    def test_bar_color_differs_from_no_color(self):
        with_colour = spec(dataset=grouped_ds(), chart_type="bar",
                           x="region", y="revenue", color="segment").to_svg()
        without = spec(dataset=grouped_ds(), chart_type="bar",
                       x="region", y="revenue").to_svg()
        assert with_colour != without   # color= was a silent no-op before

    def test_line_color_draws_one_path_per_group(self):
        svg = spec(dataset=grouped_ds(), chart_type="line",
                   x="region", y="revenue", color="segment").to_svg()
        assert svg.count('class="tb-line"') == 2

    def test_scatter_color_gives_per_group_point_colours(self):
        df = pd.DataFrame({
            "x": [1.0, 2.0, 3.0, 4.0],
            "g": ["A", "A", "B", "B"],
            "y": [5.0, 6.0, 7.0, 8.0],
        })
        s = spec(dataset=DataSet(df=df, name="s"), chart_type="scatter",
                 x="x", y="y", color="g")
        assert s.series == ("A", "B")
        svg = s.to_svg()
        # Every data point survives — no merging of points across groups.
        assert svg.count('class="tb-point"') == 4
        # Two points per group colour.
        assert svg.count('fill="#2E74B5"') >= 2
        assert svg.count('fill="#ED7D31"') >= 2

    def test_group_with_missing_x_draws_nothing_not_zero(self):
        # Wholesale has no East row: no phantom zero-height bar for it.
        df = grouped_ds().to_pandas().iloc[:-1]     # drop East/Wholesale
        s = spec(dataset=DataSet(df=df, name="gap"), chart_type="bar",
                 x="region", y="revenue", color="segment")
        assert s.to_svg().count('class="tb-bar"') == 5

    def test_pie_color_raises(self):
        with pytest.raises(ValueError, match="pie"):
            spec(dataset=grouped_ds(), chart_type="pie",
                 x="region", y="revenue", color="segment")

    def test_missing_color_column_raises_with_did_you_mean(self):
        with pytest.raises(ValueError, match="did you mean 'segment'"):
            spec(dataset=grouped_ds(), chart_type="bar",
                 x="region", y="revenue", color="segmnt")

    def test_color_with_multiple_y_columns_raises(self):
        with pytest.raises(ValueError, match="exactly one y column"):
            spec(dataset=plain_ds(), chart_type="bar",
                 x="region", y=["revenue", "cost"], color="region")

    def test_grouped_spec_round_trips_through_json(self):
        s = spec(dataset=grouped_ds(), chart_type="bar",
                 x="region", y="revenue", color="segment")
        again = ChartSpec.from_dict(json.loads(json.dumps(s.to_dict())))
        assert again == s
        assert again.color == "segment"
        assert again.to_svg() == s.to_svg()


# ─────────────────────────────────────────────
# show_values compact labels
# ─────────────────────────────────────────────

class TestShowValuesCompact:

    def test_labels_are_compact_not_raw_floats(self):
        df = pd.DataFrame({"r": ["a", "b"], "v": [2400240.38, 523900.0]})
        svg = spec(dataset=DataSet(df=df, name="v"), chart_type="bar",
                   x="r", y="v", show_values=True).to_svg()
        assert ">2.4M</text>" in svg
        assert ">523.9K</text>" in svg
        assert "2,400,240.38</text>" not in svg

    def test_small_values_keep_up_to_two_decimals(self):
        df = pd.DataFrame({"r": ["a", "b"], "v": [12.345, 999.0]})
        svg = spec(dataset=DataSet(df=df, name="v"), chart_type="bar",
                   x="r", y="v", show_values=True).to_svg()
        assert ">12.35</text>" in svg
        assert ">999</text>" in svg

    def test_axis_ticks_are_not_compacted(self):
        # One formatting voice per surface: labels compact, ticks unchanged.
        df = pd.DataFrame({"r": ["a", "b"], "v": [2400240.38, 523900.0]})
        svg = spec(dataset=DataSet(df=df, name="v"), chart_type="bar",
                   x="r", y="v", show_values=True).to_svg()
        assert 'class="tb-tick"' in svg
        assert "2,000,000" in svg   # tick formatter untouched


# ─────────────────────────────────────────────
# Byte-identical regression for color-less charts
# ─────────────────────────────────────────────

class TestNoColorByteIdentical:
    """
    Charts that do not use color= must render exactly the SVG they rendered
    before grouping existed (show_values labels excepted, by design). The
    hashes were captured from the pre-change implementation.
    """

    def test_plain_bar_chart_is_byte_identical(self):
        svg = spec(dataset=plain_ds(), chart_type="bar",
                   x="region", y="revenue").to_svg()
        assert hashlib.sha256(svg.encode()).hexdigest() == (
            "9c982ce1c952208dfc060ab3de1da0974027d03a04ba00fbc2821b9ad734c729"
        )

    def test_multi_series_line_chart_is_byte_identical(self):
        svg = spec(dataset=plain_ds(), chart_type="line",
                   x="region", y=["revenue", "cost"]).to_svg()
        assert hashlib.sha256(svg.encode()).hexdigest() == (
            "b98cd632dd15a3b05e9f804b0db3d73c650abeb92701355c25075835b63bd855"
        )
