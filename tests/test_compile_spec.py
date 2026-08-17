"""
M5 — the spec → artifact compiler (``tracebi migrate spec``).

The claims under test:

- EVERY SectionType compiles (pinned to the enum, so a new section type
  cannot be added without teaching the compiler);
- markdown TextSections are honored — escaped first, converted second;
- data-bearing sections compile to default-component figures bound to the
  SAME DataRefs (the queries move verbatim into report.json);
- a metric naming a query column compiles LIVE; a literal metric compiles
  honestly unverified — nothing is inlined as dead text that reads governed;
- dropped presentation knobs are warned about, never swallowed;
- the compiled package BUILDS through the ordinary artifact gate, and its
  verify output is a superset of the spec render's (receipt monotonicity —
  nothing that was green goes dark);
- at discovery, an artifact directory shadows a same-named spec, loudly.
"""

import json

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.reports.compile_spec import compile_spec, md_to_html
from tracebi.reports.report import SectionType
from tracebi.spec import ReportSpec

_DATA = {"model": "cs_model",
         "query": {"fact": "f", "measures": {"revenue": "sum"},
                   "dimensions": ["dim_r.region"]}}
_KPI_DATA = {"model": "cs_model", "query": {"fact": "f", "measures": ["total"]}}


def _spec(sections):
    return ReportSpec.from_dict({"name": "Compiled", "sections": sections})


@pytest.fixture()
def cs_model():
    df = pd.DataFrame({"region": ["NE", "SE", "MW"],
                       "revenue": [100.0, 250.0, 75.0]})
    m = DataModel("cs_model")
    m.add_connector(MemoryConnector("cs_mem", tables={"t": df}))
    m.add_table("t", connector="cs_mem", source="t")
    m.add_dimension("dim_r", table_name="t", key_col="region",
                    attributes=["region"])
    m.add_fact("f", table_name="t", measures=["revenue"], foreign_keys={})
    m.add_measure("total", column="revenue", agg="sum")
    m.connect()
    return m


# ── coverage is pinned to the enum ─────────────────────────────────────────

def test_every_section_type_compiles():
    sections = [
        {"type": "text", "content": "hello"},
        {"type": "table", "title": "T", "data": _DATA},
        {"type": "chart", "title": "C", "chart_type": "bar",
         "x": "dim_r.region", "y": "revenue", "data": _DATA},
        {"type": "metrics", "metrics": [{"label": "Total", "value": "total"}],
         "data": _KPI_DATA},
        {"type": "row", "sections": [{"type": "text", "content": "in a row"}]},
        {"type": "spacer", "height": 2},
    ]
    used = {s["type"] for s in sections}
    assert used == {t.value for t in SectionType}, \
        "this test must exercise every SectionType — update it with the enum"
    compiled = compile_spec(_spec(sections))
    assert set(compiled.files) == {"report.json", "template.html"}


def test_unknown_section_type_is_refused():
    with pytest.raises(ValueError, match="unknown section type"):
        compile_spec(_spec([{"type": "hologram"}]))


# ── markdown, escaped first ────────────────────────────────────────────────

class TestMarkdown:
    def test_subset_converts(self):
        html = md_to_html("## Findings\n\n- **bold** point\n- with *em*\n\n"
                          "See [docs](https://example.com) and `code`.")
        assert "<h3>Findings</h3>" in html
        assert "<li><strong>bold</strong> point</li>" in html
        assert "<em>em</em>" in html
        assert '<a href="https://example.com">docs</a>' in html
        assert "<code>code</code>" in html

    def test_ordered_lists(self):
        html = md_to_html("1. first\n2. second")
        assert html == "<ol><li>first</li><li>second</li></ol>"

    def test_content_cannot_smuggle_markup(self):
        html = md_to_html("<script>alert(1)</script> & **fine**")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<strong>fine</strong>" in html

    def test_text_section_carries_the_converted_markdown(self):
        compiled = compile_spec(_spec([
            {"type": "text", "content": "# Head\n\nA **strong** point."},
        ]))
        page = compiled.files["template.html"]
        assert "<h2>Head</h2>" in page
        assert "<strong>strong</strong>" in page


# ── figures and bindings ───────────────────────────────────────────────────

class TestFigures:
    def test_table_compiles_to_a_bound_figure(self):
        compiled = compile_spec(_spec([
            {"type": "table", "title": "By region", "id": "by_region",
             "style": "striped", "columns": ["region", "revenue"],
             "data": _DATA},
        ]))
        page = compiled.files["template.html"]
        assert 'data-tb-figure="table"' in page
        assert 'data-tb-binding="by_region"' in page
        assert 'data-tb-columns="region,revenue"' in page
        assert 'class="tb-table--striped"' in page
        report = json.loads(compiled.files["report.json"])
        assert report["data"]["by_region"] == _DATA

    def test_chart_compiles_axes_and_series(self):
        compiled = compile_spec(_spec([
            {"type": "chart", "chart_type": "line", "x": "dim_r.region",
             "y": ["revenue", "cost"], "color": "dim_r.region",
             "data": _DATA},
        ]))
        page = compiled.files["template.html"]
        assert 'data-tb-type="line"' in page
        assert 'data-tb-x="dim_r.region"' in page
        assert 'data-tb-y="revenue,cost"' in page
        assert 'data-tb-color="dim_r.region"' in page

    def test_live_metric_binds_a_cell(self):
        compiled = compile_spec(_spec([
            {"type": "metrics", "data": _KPI_DATA,
             "metrics": [{"label": "Total", "value": "total",
                          "format": "currency"}]},
        ]))
        page = compiled.files["template.html"]
        assert 'data-tb-cell="total"' in page
        assert 'data-tb-format="currency"' in page
        assert "data-tb-unverified" not in page

    def test_literal_metric_is_honestly_unverified(self):
        compiled = compile_spec(_spec([
            {"type": "metrics",
             "metrics": [{"label": "Headcount", "value": 42}]},
        ]))
        page = compiled.files["template.html"]
        assert "data-tb-unverified" in page
        assert ">42<" in page

    def test_dropped_knobs_are_warned_never_swallowed(self):
        compiled = compile_spec(_spec([
            {"type": "table", "data": _DATA, "totals": ["revenue"],
             "color_scale": {"revenue": "#ff0000"}},
            {"type": "metrics", "data": _KPI_DATA,
             "metrics": [{"label": "T", "value": "total", "delta": 0.12}]},
        ]))
        text = "\n".join(compiled.warnings)
        assert "totals" in text and "color_scale" in text
        assert "delta" in text

    def test_a_chart_section_opts_the_package_into_echarts(self):
        """Charts hydrate through the vendored ECharts, which packages opt
        into per report — a compiled spec with a chart but no libs would
        render a permanently blank panel (round-2 review, finding 7)."""
        with_chart = compile_spec(_spec([
            {"type": "row", "sections": [
                {"type": "chart", "chart_type": "bar", "x": "dim_r.region",
                 "y": "revenue", "data": _DATA}]},
        ]))
        assert json.loads(with_chart.files["report.json"])["libs"] == ["echarts"]
        without = compile_spec(_spec([
            {"type": "table", "title": "T", "data": _DATA},
        ]))
        assert "libs" not in json.loads(without.files["report.json"])

    def test_duplicate_titles_get_distinct_bindings(self):
        other = {"model": "cs_model",
                 "query": {"fact": "f", "measures": {"revenue": "mean"}}}
        compiled = compile_spec(_spec([
            {"type": "table", "title": "Same", "data": _DATA},
            {"type": "table", "title": "Same", "data": other},
        ]))
        report = json.loads(compiled.files["report.json"])
        assert len(report["data"]) == 2
        assert _DATA in report["data"].values()
        assert other in report["data"].values()


# ── the monotonicity gate: compiled artifact ⊇ spec render ─────────────────

class TestCompiledArtifactBuilds:
    def _full_spec(self):
        return ReportSpec.from_dict({
            "name": "Migrated",
            "sections": [
                {"type": "text", "content": "## Notes\n\nProse survives."},
                {"type": "metrics", "data": _KPI_DATA, "id": "kpis",
                 "metrics": [{"label": "Total", "value": "total",
                              "format": "currency"}]},
                {"type": "table", "title": "By region", "id": "by_region",
                 "data": _DATA},
                {"type": "chart", "title": "Chart", "id": "trend",
                 "chart_type": "bar", "x": "dim_r.region", "y": "revenue",
                 "data": _DATA},
            ],
        })

    def test_compiled_package_builds_and_verifies_as_a_superset(
            self, cs_model, tmp_path):
        from tracebi.reports.template_package import TemplatePackage
        from tracebi.verify import REPRODUCES, verify_manifest

        spec = self._full_spec()
        models = {"cs_model": cs_model}

        # The original spec render's receipt: its set of verifiable,
        # fingerprinted claims.
        spec_manifest = spec.build(models).build_manifest(
            "html", str(tmp_path / "spec.html")).to_dict()
        spec_fps = {s["dataset_fingerprint"]
                    for s in spec_manifest["sections"]
                    if s.get("dataset_fingerprint")}
        assert spec_fps, "the spec render must fingerprint something"

        # Compile → write the package → build through the ordinary gate.
        compiled = compile_spec(spec)
        pkg = tmp_path / "migrated"
        pkg.mkdir()
        for fname, content in compiled.files.items():
            (pkg / fname).write_text(content, encoding="utf-8")
        manifest = TemplatePackage(str(pkg)).render(
            models, str(tmp_path / "out.html")).to_dict()

        # Monotonicity: every fingerprinted claim the spec receipt carried
        # is present in the artifact receipt — nothing green goes dark.
        artifact_fps = {e["embedded_sha256"]
                        for e in manifest.get("embedded_data", [])}
        assert spec_fps <= artifact_fps

        # And the artifact's figure claims verify green.
        result = verify_manifest(manifest, models, strict=True)
        assert result["exit_code"] == 0, result["verdict_detail"]
        assert all(f["status"] == REPRODUCES for f in result["figures"])


# ── the CLI and the shadowing rule ─────────────────────────────────────────

class TestMigrateCli:
    def _write_spec(self, tmp_path):
        spec_path = tmp_path / "reports" / "sales.json"
        spec_path.parent.mkdir(exist_ok=True)
        spec_path.write_text(json.dumps({
            "name": "Sales",
            "sections": [{"type": "table", "title": "T", "data": _DATA}],
        }))
        return spec_path

    def test_migrate_emits_alongside(self, tmp_path):
        from tracebi import cli
        spec_path = self._write_spec(tmp_path)
        assert cli.main(["migrate", "spec", str(spec_path)]) == 0
        pkg = tmp_path / "reports" / "sales"
        assert (pkg / "report.json").is_file()
        assert (pkg / "template.html").is_file()
        assert spec_path.is_file(), "the original spec is never touched"

    def test_migrate_refuses_an_existing_target_without_force(self, tmp_path):
        from tracebi import cli
        spec_path = self._write_spec(tmp_path)
        (tmp_path / "reports" / "sales").mkdir()
        assert cli.main(["migrate", "spec", str(spec_path)]) == 1
        assert cli.main(["migrate", "spec", str(spec_path), "--force"]) == 0

    def test_migrate_compiles_theme_and_script_files(self, tmp_path):
        from tracebi import cli
        spec_path = tmp_path / "reports" / "themed.json"
        spec_path.parent.mkdir(exist_ok=True)
        spec_path.write_text(json.dumps({
            "name": "Themed", "theme": "brand.css", "script": "extra.js",
            "sections": [{"type": "table", "title": "T", "data": _DATA}],
        }))
        (tmp_path / "reports" / "brand.css").write_text("h1{color:teal}")
        (tmp_path / "reports" / "extra.js").write_text("console.log(1)")
        assert cli.main(["migrate", "spec", str(spec_path)]) == 0
        pkg = tmp_path / "reports" / "themed"
        assert (pkg / "style.css").read_text() == "h1{color:teal}"
        assert (pkg / "script.js").read_text() == "console.log(1)"


class TestDiscoveryShadowing:
    def test_artifact_directory_shadows_a_same_named_spec(
            self, tmp_path, capsys):
        from tracebi.web import discovery

        reports = tmp_path / "reports"
        (reports / "sales").mkdir(parents=True)
        (reports / "sales" / "report.json").write_text(json.dumps(
            {"name": "sales", "data": {"rows": _DATA}}))
        (reports / "sales" / "template.html").write_text(
            "<html><head><title>s</title></head><body></body></html>")
        (reports / "sales.json").write_text(json.dumps(
            {"name": "Sales", "sections": []}))

        discovery.clear_discovery_report()
        discovery.auto_discover(str(reports))
        outcomes = {o["file"]: o for o in discovery.discovery_report()
                    if o["directory"] == str(reports)}
        assert outcomes["sales.json"]["status"] == "skipped"
        assert "shadowed by artifact package" in outcomes["sales.json"]["reason"]
        assert outcomes["sales"]["status"] == "registered"
        err = capsys.readouterr().err
        assert "shadows spec" in err and "sales.json" in err
