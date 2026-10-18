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


# ── markdown, escaped first ────────────────────────────────────────────────

class TestMarkdown:

    def test_content_cannot_smuggle_markup(self):
        html = md_to_html("<script>alert(1)</script> & **fine**")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<strong>fine</strong>" in html

    @pytest.mark.parametrize("quote", ['"', "'"])
    def test_link_url_cannot_break_out_of_the_href_attribute(self, quote):
        # A URL is captured up to ')' or whitespace, which permits a bare
        # quote; leaving quotes unescaped let the link close href and inject a
        # live event handler. The escaped quote must stay inside the attribute.
        payload = f"[c](http://x{quote}onmouseover={quote}alert(1))"
        html = md_to_html(payload)
        assert 'onmouseover="' not in html and "onmouseover='" not in html, html
        assert f'{quote}onmouseover' not in html, (
            "a bare quote survived into the href — attribute breakout"
        )


# ── figures and bindings ───────────────────────────────────────────────────

class TestFigures:


    def test_literal_metric_is_honestly_unverified(self):
        compiled = compile_spec(_spec([
            {"type": "metrics",
             "metrics": [{"label": "Headcount", "value": 42}]},
        ]))
        page = compiled.files["template.html"]
        assert "data-tb-unverified" in page
        assert ">42<" in page


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


# ── table labels / formats and row layout ──────────────────────────────────

def _write_package(tmp_path, compiled):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    for fname, content in compiled.files.items():
        (pkg / fname).write_text(content, encoding="utf-8")
    return pkg


class TestTotalsRows:
    """A spec's ``totals`` become a one-row query the model computes."""


    def test_build_renders_the_totals_row_and_records_it(self, cs_model, tmp_path):
        from tracebi.reports.template_package import TemplatePackage
        from tracebi.verify import verify_file
        compiled = compile_spec(_spec([
            {"type": "table", "title": "By region", "id": "by_region",
             "data": _DATA, "totals": ["revenue"],
             "number_formats": {"revenue": "currency0"}},
        ]))
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(_write_package(tmp_path, compiled))).render(
            {"cs_model": cs_model}, str(out))
        html = out.read_text(encoding="utf-8")
        assert ('<tfoot><tr class="tb-total"><td>Total</td>'
                '<td class="tb-num">$425</td></tr></tfoot>') in html
        fig = next(f for f in manifest.figures if f.get("binding") == "by_region")
        assert fig["totals"] == "by_region_totals"
        result = verify_file(html, manifest.to_dict())
        assert result["ok"], result["verdict_detail"]
        # Unhooking the totals row from its binding is an edit verify catches.
        edited = html.replace(' data-tb-totals="by_region_totals"', "")
        assert not verify_file(edited, manifest.to_dict())["ok"]
