"""
Tests for TraceBi Phase 2: Report Engine
"""

import os
import json
import tempfile
import pytest
import pandas as pd

from tracebi.model.dataset import DataSet, LineageNode
from tracebi.reports.report import (
    Report, TextSection, TableSection, ChartSection,
    SpacerSection, SectionType, ReportManifest,
)
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

def make_ds(name: str = "test") -> DataSet:
    df = pd.DataFrame({
        "region":  ["North", "South", "East"],
        "orders":  [100, 85, 120],
        "revenue": [5000.0, 4250.0, 6100.0],
    })
    node = LineageNode(
        operation="load", description=f"Load {name}",
        connector={"connector_name": "test", "connector_type": "CSV"},
        source=f"{name}.csv",
    )
    return DataSet(df=df, name=name, lineage=[node])


@pytest.fixture
def sample_report():
    ds = make_ds("sales")
    filtered_ds = ds.filter("orders > 90", description="High volume regions")
    return (
        Report("Test Report")
        .author("Test Author")
        .description("A test report.")
        .parameter("period", "Q1 2024")
        .add(TextSection(title="Summary", content="Summary heading", style="heading1"))
        .add(TextSection(content="Some body text.", style="normal"))
        .add(TextSection(content="A note here.", style="note"))
        .add(TableSection(
            title="Sales Table",
            dataset=filtered_ds,
            columns=["region", "orders", "revenue"],
            column_labels={"revenue": "Revenue ($)"},
            totals=["orders", "Revenue ($)"],
            number_formats={"revenue": "{:,.2f}"},
        ))
        .add(ChartSection(
            title="Revenue Chart",
            dataset=ds,
            chart_type="bar",
            x="region",
            y="revenue",
        ))
        .spacer()
    )


# ─────────────────────────────────────────────
# Report structure tests
# ─────────────────────────────────────────────

class TestReport:

    def test_fluent_builder(self, sample_report):
        assert sample_report.name == "Test Report"
        assert sample_report._author == "Test Author"
        assert sample_report._parameters == {"period": "Q1 2024"}
        assert len(sample_report.sections) == 6

    def test_section_types(self, sample_report):
        types = [s.section_type for s in sample_report.sections]
        assert SectionType.TEXT in types
        assert SectionType.TABLE in types
        assert SectionType.CHART in types
        assert SectionType.SPACER in types

    def test_build_manifest(self, sample_report):
        manifest = sample_report.build_manifest("excel", "/tmp/test.xlsx")
        assert manifest.report_name == "Test Report"
        assert manifest.format == "excel"
        assert manifest.output_path == "/tmp/test.xlsx"
        assert len(manifest.sections) == 6
        assert manifest.parameters == {"period": "Q1 2024"}

    def test_manifest_records_git_sha(self, sample_report):
        manifest = sample_report.build_manifest("excel", "/tmp/test.xlsx")
        # In a git checkout this is the HEAD SHA; outside one it's 'unknown'.
        assert manifest.git_sha
        assert manifest.git_sha == "unknown" or len(manifest.git_sha) == 40
        assert manifest.to_dict()["git_sha"] == manifest.git_sha

    def test_manifest_contains_lineage(self, sample_report):
        manifest = sample_report.build_manifest("html", "/tmp/test.html")
        # Find the table section manifest entry
        table_entry = next(
            (s for s in manifest.sections if s["section_type"] == "table"), None
        )
        assert table_entry is not None
        assert "dataset_lineage" in table_entry
        # The filtered_ds has 2 lineage nodes: load + filter
        assert len(table_entry["dataset_lineage"]) == 2

    def test_manifest_to_json(self, sample_report):
        manifest = sample_report.build_manifest("excel", "/tmp/test.xlsx")
        j = manifest.to_json()
        parsed = json.loads(j)
        assert parsed["report_name"] == "Test Report"
        assert isinstance(parsed["sections"], list)

    def test_table_section_get_display_df(self):
        ds = make_ds()
        section = TableSection(
            dataset=ds,
            columns=["region", "revenue"],
            column_labels={"revenue": "Rev"},
            max_rows=2,
        )
        df = section.get_display_df()
        assert list(df.columns) == ["region", "Rev"]
        assert len(df) == 2

    def test_describe_runs(self, sample_report, capsys):
        sample_report.describe()
        out = capsys.readouterr().out
        assert "Test Report" in out
        assert "Test Author" in out


# ─────────────────────────────────────────────
# Excel renderer tests
# ─────────────────────────────────────────────

class TestExcelRenderer:

    def test_renders_file(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.xlsx")
            ExcelRenderer().render(report=sample_report, output_path=path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 1000

    def test_manifest_saved(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.xlsx")
            ExcelRenderer().render(report=sample_report, output_path=path)
            manifest_path = path + ".manifest.json"
            assert os.path.exists(manifest_path)
            with open(manifest_path) as f:
                data = json.load(f)
            assert data["report_name"] == "Test Report"

    def test_manifest_returned(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.xlsx")
            manifest = ExcelRenderer().render(report=sample_report, output_path=path)
            assert isinstance(manifest, ReportManifest)
            assert manifest.format == "excel"

    def test_renders_pie_chart(self):
        # Regression: PieChart has no x/y axes — setting axis titles crashed.
        report = Report("Pie Report").add(ChartSection(
            title="Revenue Share", dataset=make_ds("pie"),
            chart_type="pie", x="region", y="revenue",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pie.xlsx")
            ExcelRenderer().render(report=report, output_path=path)
            assert os.path.getsize(path) > 1000

    def test_excel_has_sheets(self, sample_report):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.xlsx")
            ExcelRenderer(include_cover=True, include_lineage_sheet=True).render(
                report=sample_report, output_path=path
            )
            wb = openpyxl.load_workbook(path)
            assert "Cover" in wb.sheetnames
            assert "Report" in wb.sheetnames
            assert "Lineage" in wb.sheetnames

    def test_no_cover_option(self, sample_report):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.xlsx")
            ExcelRenderer(include_cover=False, include_lineage_sheet=False).render(
                report=sample_report, output_path=path
            )
            wb = openpyxl.load_workbook(path)
            assert "Cover" not in wb.sheetnames
            assert "Lineage" not in wb.sheetnames
            assert "Report" in wb.sheetnames

    def test_no_manifest_option(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.xlsx")
            ExcelRenderer().render(report=sample_report, output_path=path,
                                   save_manifest=False)
            assert not os.path.exists(path + ".manifest.json")


# ─────────────────────────────────────────────
# HTML renderer tests
# ─────────────────────────────────────────────

class TestHTMLRenderer:

    def test_renders_file(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            HTMLRenderer().render(report=sample_report, output_path=path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 2000

    def test_html_is_valid(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            HTMLRenderer().render(report=sample_report, output_path=path)
            with open(path) as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
            assert "Test Report" in content
            assert "Test Author" in content
            assert "Q1 2024" in content

    def test_html_contains_table_data(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            HTMLRenderer().render(report=sample_report, output_path=path)
            with open(path) as f:
                content = f.read()
            assert "Sales Table" in content
            assert "North" in content   # data from the dataset

    def test_html_contains_lineage(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            HTMLRenderer().render(report=sample_report, output_path=path)
            with open(path) as f:
                content = f.read()
            assert "Data Lineage" in content
            assert "filter" in content

    def test_manifest_saved(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            HTMLRenderer().render(report=sample_report, output_path=path)
            assert os.path.exists(path + ".manifest.json")

    def test_manifest_returned(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            manifest = HTMLRenderer().render(report=sample_report, output_path=path)
            assert isinstance(manifest, ReportManifest)
            assert manifest.format == "html"

    def test_empty_report(self):
        report = Report("Empty")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.html")
            HTMLRenderer().render(report=report, output_path=path)
            assert os.path.exists(path)

    def test_custom_manifest_path(self, sample_report):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.html")
            custom_mp = os.path.join(tmp, "custom_manifest.json")
            HTMLRenderer().render(
                report=sample_report, output_path=path,
                manifest_path=custom_mp
            )
            assert os.path.exists(custom_mp)


# ─────────────────────────────────────────────
# Formatting & layout tests
# ─────────────────────────────────────────────

class TestMetricSection:

    def make_metrics_report(self):
        from tracebi.reports.report import Metric, MetricSection
        return Report("Metrics Report").add(MetricSection(
            title="Key Metrics",
            metrics=[
                Metric("Total Revenue", 1250000, format="currency0", delta=0.12),
                Metric("Error Rate", 0.034, format="percent", delta=0.01,
                       good_when_up=False),
            ],
        ))

    def test_html_renders_cards(self):
        html = HTMLRenderer().to_html(self.make_metrics_report())
        assert "metric-card" in html
        assert "$1,250,000" in html
        assert "3.4%" in html
        # Positive delta on a good_when_up metric is good (green)…
        assert 'metric-delta good">▲ +12.0%' in html
        # …but on a good_when_up=False metric it is bad (red)
        assert 'metric-delta bad">▲ +1.0%' in html

    def test_excel_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "metrics.xlsx")
            ExcelRenderer().render(self.make_metrics_report(), path,
                                   save_manifest=False)
            from openpyxl import load_workbook
            ws = load_workbook(path)["Report"]
            values = [c.value for row in ws.iter_rows() for c in row if c.value]
            assert "Total Revenue" in values
            assert "$1,250,000" in values

    def test_manifest_records_metrics(self):
        manifest = self.make_metrics_report().build_manifest("html", "x.html")
        assert manifest.sections[0]["metrics"][0]["label"] == "Total Revenue"

    def test_fluent_shortcut(self):
        from tracebi.reports.report import Metric
        report = Report("R").metrics([Metric("Orders", 10)], title="KPIs")
        assert report.sections[0].section_type == SectionType.METRICS


class TestRowSection:

    def make_row_report(self):
        from tracebi.reports.report import RowSection
        ds = make_ds("sales")
        return Report("Row Report").add(RowSection(sections=[
            TableSection(title="Left Table", dataset=ds),
            ChartSection(title="Right Chart", dataset=ds,
                         chart_type="bar", x="region", y="revenue"),
        ]))

    def test_html_side_by_side(self):
        html = HTMLRenderer().to_html(self.make_row_report())
        assert "layout-row" in html
        assert "Left Table" in html
        assert "Right Chart" in html

    def test_nested_lineage_in_html(self):
        html = HTMLRenderer().to_html(self.make_row_report())
        assert "Data Lineage" in html
        assert "Load sales" in html

    def test_data_sections_flattens(self):
        report = self.make_row_report()
        types = [s.section_type for s in report.data_sections()]
        assert types == [SectionType.TABLE, SectionType.CHART]

    def test_excel_renders_stacked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "row.xlsx")
            ExcelRenderer().render(self.make_row_report(), path,
                                   save_manifest=False)
            from openpyxl import load_workbook
            wb = load_workbook(path)
            values = [c.value for row in wb["Report"].iter_rows()
                      for c in row if c.value]
            assert "Left Table" in values
            # Nested dataset lineage reaches the Lineage sheet
            lineage_vals = [c.value for row in wb["Lineage"].iter_rows()
                            for c in row if c.value]
            assert "Load sales" in lineage_vals

    def test_fluent_shortcut(self):
        ds = make_ds()
        report = Report("R").row(TableSection(dataset=ds), widths=[2, 1])
        assert report.sections[0].section_type == SectionType.ROW


class TestTableStyling:

    def make_styled_ds(self):
        df = pd.DataFrame({
            "region": ["North", "South", "East"],
            "margin": [120.0, -45.0, 300.0],
        })
        return DataSet(df=df, name="margins",
                       lineage=[LineageNode(operation="load", description="Load")])

    def test_named_number_format_html(self):
        report = Report("R").add(TableSection(
            dataset=make_ds(), number_formats={"revenue": "currency"}))
        html = HTMLRenderer().to_html(report)
        assert "$5,000.00" in html

    def test_highlight_negatives_html(self):
        report = Report("R").add(TableSection(
            dataset=self.make_styled_ds(), highlight_negatives=["margin"]))
        html = HTMLRenderer().to_html(report)
        assert 'class="num neg"' in html
        # Only the one negative value is highlighted
        assert html.count('class="num neg"') == 1

    def test_color_scale_html(self):
        report = Report("R").add(TableSection(
            dataset=self.make_styled_ds(), color_scale={"margin": "#2E74B5"}))
        html = HTMLRenderer().to_html(report)
        # Max value gets the full color, min gets white
        assert "background:rgb(46,116,181)" in html
        assert "background:rgb(255,255,255)" in html

    def test_column_widths_html(self):
        report = Report("R").add(TableSection(
            dataset=make_ds(), column_widths={"region": 20}))
        html = HTMLRenderer().to_html(report)
        assert "min-width:140px" in html

    def test_excel_styling(self):
        report = Report("R").add(TableSection(
            dataset=self.make_styled_ds(),
            highlight_negatives=["margin"],
            color_scale={"margin": "#2E74B5"},
            column_widths={"region": 30},
            number_formats={"margin": "currency"},
        ))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "styled.xlsx")
            ExcelRenderer().render(report, path, save_manifest=False)
            from openpyxl import load_workbook
            ws = load_workbook(path)["Report"]
            # column_widths override autosize
            assert ws.column_dimensions["A"].width == 30
            # negative value in red font
            cells = {c.value: c for row in ws.iter_rows() for c in row}
            assert "C62828" in str(cells[-45.0].font.color.rgb)
            assert cells[-45.0].number_format == "$#,##0.00"
            # conditional formatting registered for the margin column
            assert len(ws.conditional_formatting._cf_rules) == 1

    def test_excel_named_format_mapping(self):
        fmt = ExcelRenderer._excel_number_format
        assert fmt("currency") == "$#,##0.00"
        assert fmt("currency0") == "$#,##0"
        assert fmt("percent") == "0.0%"
        assert fmt("comma") == "#,##0"
        assert fmt("{:,.2f}") == "#,##0.00"


class TestChartEnhancements:

    def test_area_chart_html(self):
        report = Report("R").add(ChartSection(
            dataset=make_ds(), chart_type="area", x="region", y="revenue"))
        html = HTMLRenderer().to_html(report)
        assert "data:image/png;base64," in html

    def test_show_values_bar(self):
        report = Report("R").add(ChartSection(
            dataset=make_ds(), chart_type="bar", x="region", y="revenue",
            show_values=True))
        html = HTMLRenderer().to_html(report)
        assert "data:image/png;base64," in html


class TestReportNotebookIntegration:

    def test_report_repr_html_is_iframe(self, sample_report):
        html = sample_report._repr_html_()
        assert html.strip().startswith("<iframe srcdoc=")
        # Report content is embedded (entity-escaped)
        assert "Test Report" in html

    def test_report_help_prints(self, capsys):
        Report("R").help()
        out = capsys.readouterr().out
        assert ".table(" in out
        assert ".metrics(" in out
        assert ".row(" in out
