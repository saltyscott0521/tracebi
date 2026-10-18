"""
Tests for manifest lineage capture on custom section types.

The audit manifest must record dataset lineage for EVERY section that
carries a dataset — including custom/user-defined section types with a
plain-string section_type — and the built-in sections' manifest output
must remain exactly as it was (regression pins below).
"""

import json
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import pytest

from tracebi.model.dataset import DataSet, LineageNode
from tracebi.reports.report import (
    Report, ReportSection, RowSection, TableSection, ChartSection,
)


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


# ─────────────────────────────────────────────


@dataclass
class TabsSection(ReportSection):
    """A custom container: children live in `panes`, wrapped in tuples."""
    panes: list = field(default_factory=list)   # [(label, ReportSection)]

    def __post_init__(self):
        self.section_type = "tabs"


@dataclass
class PanelSection(ReportSection):
    """A custom container keyed by name rather than ordered."""
    panels: dict = field(default_factory=dict)

    def __post_init__(self):
        self.section_type = "panels"


def render_tabs(section) -> str:
    """A project's own renderer for its own container — public API only."""
    return "".join(f"<div>{label}{t.dataset.to_pandas().to_html(index=False)}</div>"
                   for label, t in section.panes)


def all_fingerprints(sections) -> set:
    """Every dataset_fingerprint anywhere in a manifest's section tree."""
    found = set()
    for s in sections or []:
        if s.get("dataset_fingerprint"):
            found.add(s["dataset_fingerprint"])
        found |= all_fingerprints(s.get("sections") or [])
    return found


def distinct_ds(i: int) -> DataSet:
    """A dataset whose *content* is unique to *i*.

    fingerprint() is derived from content, so datasets that merely differ by
    name collapse to one fingerprint — and a coverage assertion over them
    would then hold even if every nested section were dropped.
    """
    node = LineageNode(
        operation="load", description=f"Load d{i}",
        connector={"connector_name": "test", "connector_type": "CSV"},
        source=f"d{i}.csv",
    )
    return DataSet(df=pd.DataFrame({"region": ["North"], "orders": [100 + i]}),
                   name=f"d{i}", lineage=[node])


class TestContainerSectionsCannotForfeitLineage:
    """A page of real figures must never produce a manifest with nothing in
    it. Custom containers are the case that used to: only RowSection knew how
    to descend, so any other container dropped every dataset it held and
    `tracebi verify` then passed the artifact as having no data at all."""

    def test_rendered_figure_is_covered_by_a_manifest_fingerprint(self, tmp_path):
        from tracebi.reports.html_renderer import HTMLRenderer

        df = pd.DataFrame({"cut": ["North"], "market_value": [523044.32]})
        ds = DataSet(df=df, name="holdings", lineage=[LineageNode(
            operation="load", description="Load holdings",
            connector={"connector_name": "t", "connector_type": "CSV"},
            source="holdings.csv")])
        report = Report("Holdings Review").add(TabsSection(
            title="Holdings by cut",
            panes=[("By region", TableSection(dataset=ds))],
        ))

        out = tmp_path / "holdings.html"
        HTMLRenderer(section_renderers={"tabs": render_tabs}).render(report, str(out))
        html = out.read_text()
        manifest = json.loads((tmp_path / "holdings.html.manifest.json").read_text())

        assert "523044.32" in html, "the figure under test must reach the page"
        fps = all_fingerprints(manifest["sections"])
        assert fps, "a report whose only data sits in a custom container " \
                    "produced a manifest with no fingerprint at all"
        assert ds.fingerprint() in fps, (
            "the number rendered in the HTML is not covered by any fingerprint "
            "in the manifest"
        )
        # …and the same descent must feed the on-page lineage appendix, so the
        # manifest and what a reader sees cannot disagree about one report.
        assert "holdings.csv" in html, (
            "the nested dataset is missing from the HTML lineage appendix"
        )

    def test_every_dataset_in_the_report_reaches_the_manifest(self):
        datasets = [distinct_ds(i) for i in range(5)]
        assert len({d.fingerprint() for d in datasets}) == 5, \
            "the datasets must be distinguishable or this test proves nothing"
        report = (
            Report("Mixed")
            .add(TableSection(title="flat", dataset=datasets[0]))
            .add(RowSection(sections=[
                TableSection(dataset=datasets[1]),
                RowSection(sections=[TableSection(dataset=datasets[2])]),
            ]))
            .add(TabsSection(panes=[("a", TableSection(dataset=datasets[3]))]))
            .add(PanelSection(panels={"left": MapSection(dataset=datasets[4])}))
        )
        m = report.build_manifest("html", "/dev/null").to_dict()
        assert all_fingerprints(m["sections"]) == {d.fingerprint() for d in datasets}


    def test_a_manifest_failure_leaves_no_unauditable_artifact(self, tmp_path):
        """The receipt is built before the artifact: an artifact on disk that
        nothing can audit is the state this whole mechanism exists to
        prevent, so it must not be reachable by failing halfway."""
        from tracebi.reports.excel_renderer import ExcelRenderer
        from tracebi.reports.html_renderer import HTMLRenderer

        @dataclass
        class UnserialisableSection(TableSection):
            def to_manifest_dict(self):
                raise RuntimeError("manifest boom")

        report = Report("R").add(UnserialisableSection(dataset=make_ds("x")))
        for renderer, name in ((HTMLRenderer(), "r.html"), (ExcelRenderer(), "r.xlsx")):
            out = tmp_path / name
            with pytest.raises(RuntimeError, match="manifest boom"):
                renderer.render(report, str(out))
            assert not out.exists(), f"{name} was written despite having no receipt"


# ─────────────────────────────────────────────

def query_node(model: str) -> LineageNode:
    """A lineage node shaped like the one ``DataModel.execute`` stamps."""
    return LineageNode(
        operation="query",
        description=f"Query {model}",
        metadata={"model": model,
                  "query_spec": {"fact": f"fact_{model}",
                                 "measures": ["revenue"]}},
    )


class TestRewiredSitesUnchanged:
    """One regression per call site rewired onto last_query_node."""


    def test_verify_section_classifies_from_last_query_node(self):
        """verify._query_node: model/query_spec come from the LAST query node,
        and the node-identity check (transformed after the query) still holds."""
        from tracebi.verify import ERROR, UNVERIFIABLE, _verify_section

        lineage = [query_node("first").to_dict(), query_node("ghost").to_dict()]
        section = {"section_type": "table", "dataset_fingerprint": "f" * 64,
                   "dataset_lineage": lineage}
        out = _verify_section(section, models={}, label="s1")
        assert out["status"] == ERROR                # model 'ghost' not found
        assert out["model"] == "ghost"
        assert out["query_spec"]["fact"] == "fact_ghost"

        # No query node at all → unverifiable, same wording as before.
        section["dataset_lineage"] = make_ds().lineage_to_dict()
        out = _verify_section(section, models={}, label="s1")
        assert out["status"] == UNVERIFIABLE
        assert "no recorded query" in out["detail"]

        # Transformed after the query → the query node is not last.
        section["dataset_lineage"] = lineage + [
            LineageNode(operation="filter", description="post-query").to_dict()]
        out = _verify_section(section, models={}, label="s1")
        assert out["status"] == UNVERIFIABLE
        assert "transformed after" in out["detail"]
