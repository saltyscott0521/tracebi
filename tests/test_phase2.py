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
