"""
Tests for manifest lineage capture on custom section types.

The audit manifest must record dataset lineage for EVERY section that
carries a dataset — including custom/user-defined section types with a
plain-string section_type — and the built-in sections' manifest output
must remain exactly as it was (regression pins below).
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from tracebi.model.dataset import DataSet, LineageNode
from tracebi.reports.report import (
    Report, ReportSection, TableSection, ChartSection,
)


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


@dataclass
class MapSection(ReportSection):
    """A custom section type: string section_type, carries a dataset."""
    dataset: Optional[DataSet] = None

    def __post_init__(self):
        self.section_type = "map"


@dataclass
class BadgeSection(ReportSection):
    """A custom section type with no dataset field."""
    label: str = ""

    def __post_init__(self):
        self.section_type = "badge"


# ─────────────────────────────────────────────
# Custom sections in the manifest
# ─────────────────────────────────────────────

class TestCustomSectionManifest:

    def test_custom_section_with_dataset_records_lineage(self):
        ds = make_ds("points").filter("orders > 90", description="High volume")
        section = MapSection(title="Map", dataset=ds)
        d = section.to_manifest_dict()
        assert d["section_type"] == "map"
        assert d["dataset_name"] == "points"
        assert d["dataset_shape"] == list(ds.shape)
        assert d["dataset_fingerprint"] == ds.fingerprint()
        assert d["dataset_lineage"] == ds.lineage_to_dict()
        assert len(d["dataset_lineage"]) > 0

    def test_custom_section_with_dataset_via_report_manifest(self):
        ds = make_ds("points")
        manifest = (
            Report("Custom Report")
            .add(MapSection(title="Map", dataset=ds))
            .build_manifest("html", "/tmp/custom.html")
        )
        entry = manifest.sections[0]
        for key in ("dataset_name", "dataset_shape",
                    "dataset_lineage", "dataset_fingerprint"):
            assert key in entry

    def test_custom_section_without_dataset(self):
        section = BadgeSection(title="Badge", label="OK")
        d = section.to_manifest_dict()
        assert d["section_type"] == "badge"
        assert "dataset_name" not in d
        assert "dataset_shape" not in d
        assert "dataset_lineage" not in d
        assert "dataset_fingerprint" not in d

    def test_custom_section_dataset_none(self):
        section = MapSection(title="Empty Map", dataset=None)
        d = section.to_manifest_dict()
        assert "dataset_name" not in d
        assert "dataset_fingerprint" not in d


# ─────────────────────────────────────────────
# Built-in sections: regression pins
# ─────────────────────────────────────────────

class TestBuiltinManifestUnchanged:

    def test_table_section_manifest_keys_unchanged(self):
        ds = make_ds("sales")
        section = TableSection(
            title="Sales", dataset=ds, id="t1",
            columns=["region", "revenue"], max_rows=5,
        )
        d = section.to_manifest_dict()
        assert list(d.keys()) == [
            "section_type", "title", "id",
            "dataset_name", "dataset_shape",
            "dataset_lineage", "dataset_fingerprint",
            "columns", "max_rows",
        ]
        assert d["section_type"] == "table"
        assert d["title"] == "Sales"
        assert d["id"] == "t1"
        assert d["dataset_name"] == "sales"
        assert d["dataset_shape"] == [3, 3]
        assert d["dataset_lineage"] == ds.lineage_to_dict()
        assert d["dataset_fingerprint"] == ds.fingerprint()
        assert d["columns"] == ["region", "revenue"]
        assert d["max_rows"] == 5

    def test_chart_section_manifest_keys_unchanged(self):
        ds = make_ds("sales")
        section = ChartSection(
            title="Chart", dataset=ds, chart_type="bar",
            x="region", y="revenue",
        )
        d = section.to_manifest_dict()
        assert list(d.keys()) == [
            "section_type", "title",
            "dataset_name", "dataset_shape",
            "dataset_lineage", "dataset_fingerprint",
            "chart_type", "x", "y", "color", "xlabel", "ylabel",
            "figsize", "style", "palette", "show_values",
        ]
        assert d["section_type"] == "chart"
        assert d["dataset_name"] == "sales"
        assert d["dataset_shape"] == [3, 3]
        assert d["dataset_lineage"] == ds.lineage_to_dict()
        assert d["dataset_fingerprint"] == ds.fingerprint()
        assert d["chart_type"] == "bar"
        assert d["x"] == "region"
        assert d["y"] == ["revenue"]

    def test_table_without_dataset_omits_dataset_keys(self):
        d = TableSection(title="Empty").to_manifest_dict()
        assert "dataset_name" not in d
        assert d["columns"] is None
        assert d["max_rows"] is None


# ─────────────────────────────────────────────
# describe() with custom string section types
# ─────────────────────────────────────────────

class TestDescribeCustomSections:

    def test_describe_does_not_raise(self, capsys):
        report = (
            Report("Mixed Report")
            .add(TableSection(title="Table", dataset=make_ds("sales")))
            .add(MapSection(title="Map", dataset=make_ds("points")))
        )
        report.describe()
        out = capsys.readouterr().out
        assert "[TABLE]" in out
        assert "[MAP]" in out


# ─────────────────────────────────────────────
# Review-pass fixes (adversarial findings)
# ─────────────────────────────────────────────

@dataclass
class ForeignPayloadSection(ReportSection):
    """A custom section whose 'dataset' field holds a non-DataSet."""
    dataset: object = None

    def __post_init__(self):
        self.section_type = "foreign"


class TestForeignDatasetPayloads:
    """A field *named* dataset is not necessarily a DataSet. Foreign types
    must not crash the manifest — they are simply not lineage-bearing."""

    def test_raw_dataframe_payload_omits_keys_no_crash(self):
        s = ForeignPayloadSection(title="df", dataset=pd.DataFrame({"a": [1]}))
        d = s.to_manifest_dict()
        assert "dataset_fingerprint" not in d
        assert "dataset_lineage" not in d

    def test_string_payload_omits_keys_no_crash(self):
        d = ForeignPayloadSection(title="s", dataset="not-a-dataset").to_manifest_dict()
        assert "dataset_fingerprint" not in d

    def test_render_with_foreign_payload_still_builds_manifest(self):
        report = Report(name="foreign")
        report.add(ForeignPayloadSection(title="odd",
                                         dataset=pd.DataFrame({"a": [1]})))
        report.add(TableSection(title="real", dataset=make_ds()))
        m = report.build_manifest("html", "/dev/null").to_dict()
        assert len(m["sections"]) == 2
        assert m["sections"][1]["dataset_fingerprint"]


class TestEmptyDatasetRecordsLineage:
    """A present-but-0-row DataSet is data with provenance, not absence of
    data. The old truthiness guard silently skipped it (DataSet defines
    __len__); the is-not-None semantics are pinned here."""

    def test_empty_dataset_emits_all_four_keys(self):
        empty = DataSet(df=pd.DataFrame({"region": [], "revenue": []}),
                        name="empty")
        d = TableSection(title="t", dataset=empty).to_manifest_dict()
        assert d["dataset_name"] == "empty"
        assert d["dataset_shape"] == [0, 2]
        assert d["dataset_fingerprint"] == empty.fingerprint()

    def test_empty_dataset_on_custom_section(self):
        empty = DataSet(df=pd.DataFrame({"a": []}), name="empty")
        d = MapSection(title="m", dataset=empty).to_manifest_dict()
        assert d["dataset_shape"] == [0, 1]


class TestSpecExportToleratesCustomSections:
    """from_report() is best-effort by design; a custom string section_type
    must export (as its string), not crash with AttributeError."""

    def test_from_report_with_custom_section_does_not_raise(self):
        from tracebi.spec import ReportSpec

        report = Report(name="mixed")
        report.add(MapSection(title="map", dataset=make_ds()))
        report.add(TableSection(title="tbl", dataset=make_ds()))
        rspec = ReportSpec.from_report(report)
        types = [s.get("type") for s in rspec.to_dict()["sections"]]
        assert "map" in types
