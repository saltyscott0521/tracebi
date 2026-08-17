"""
The artifact layer — figure extraction, id assignment, exploration strip.

figures.py is the ONE parser for data-tb-* markup (architecture v2 §2.1,
flaw 1): build validation, the exploration strip, and verify --file all
share it, so these tests are the trust tests for all three. Hostile and
malformed markup must fail LOUDLY — a figure silently missed here would
vanish from the build check and the offline check at once.
"""

import json

import pandas as pd
import pytest

from tracebi.reports.figures import (
    Figure,
    FigureError,
    assign_figure_ids,
    extract_figures,
    methodology_insertion,
    read_stage_meta,
    strip_stage,
)


PAGE = """<!doctype html>
<html><head><title>p</title>
<meta name="tracebi-stage" content="final">
</head><body>
<div class="tb-kpi" data-tb-figure="value" data-tb-binding="kpi"
     data-tb-cell="book_fv" id="fig-book"><span>x</span></div>
<div data-tb-figure="chart" data-tb-binding="bands" id="fig-bands"></div>
<table data-tb-figure="table" data-tb-binding="top10" id="fig-top10"></table>
<div data-tb-figure="custom" data-tb-binding="bands" id="fig-heat"></div>
<div data-tb-figure="value" data-tb-unverified
     data-tb-note="analyst estimate" id="fig-est">42</div>
<section data-tb-stage="exploration">
  <p>working note</p>
  <table data-tb-figure="table" data-tb-binding="nulls" id="fig-nulls"></table>
</section>
</body></html>"""


class TestExtract:
    def test_extracts_every_figure_in_document_order(self):
        figs = extract_figures(PAGE)
        assert [f.id for f in figs] == [
            "fig-book", "fig-bands", "fig-top10", "fig-heat", "fig-est",
            "fig-nulls",
        ]
        book = figs[0]
        assert book.kind == "value" and book.binding == "kpi"
        assert book.cell == "book_fv" and not book.unverified
        est = figs[4]
        assert est.unverified and est.binding is None
        assert est.note == "analyst estimate"

    def test_unknown_kind_is_refused(self):
        with pytest.raises(FigureError, match="unknown figure kind"):
            extract_figures('<div data-tb-figure="kpi" id="x"></div>')

    def test_binding_and_unverified_together_are_refused(self):
        with pytest.raises(FigureError, match="never both"):
            extract_figures(
                '<div data-tb-figure="value" data-tb-binding="b" '
                'data-tb-unverified id="x"></div>'
            )

    def test_duplicate_ids_are_refused(self):
        with pytest.raises(FigureError, match="duplicate figure id"):
            extract_figures(
                '<div data-tb-figure="chart" data-tb-binding="a" id="f"></div>'
                '<div data-tb-figure="chart" data-tb-binding="b" id="f"></div>'
            )

    def test_misnested_markup_fails_loudly(self):
        with pytest.raises(FigureError, match="mis-nested|closes nothing"):
            extract_figures("<div><section></div></section>")

    def test_stray_close_fails_loudly(self):
        with pytest.raises(FigureError, match="closes nothing"):
            extract_figures("</div><div data-tb-figure='chart' id='x'></div>")

    def test_uppercase_and_whitespace_attrs_still_parse(self):
        figs = extract_figures(
            '<DIV DATA-TB-FIGURE="chart"\n  data-tb-binding = "b"\n'
            '  ID="f1"></DIV>'
        )
        assert figs == [Figure(kind="chart", id="f1", binding="b", tag="div",
                               attrs=figs[0].attrs)]

    def test_figure_attr_hidden_in_text_or_comment_is_not_a_figure(self):
        # The classic regex traps: markup-looking bytes in places that are
        # not markup. A real tokenizer must not see figures here.
        figs = extract_figures(
            "<pre>&lt;div data-tb-figure=\"chart\" id=\"fake\"&gt;</pre>"
            "<!-- <div data-tb-figure='table' id='ghost'></div> -->"
            "<div data-tb-figure=\"chart\" data-tb-binding=\"b\" id=\"real\">"
            "</div>"
        )
        assert [f.id for f in figs] == ["real"]


class TestAssignIds:
    def test_missing_ids_are_assigned_with_warnings(self):
        html = ('<div data-tb-figure="chart" data-tb-binding="a"></div>'
                '<div data-tb-figure="table" data-tb-binding="b" id="mine">'
                '</div>')
        out, warnings = assign_figure_ids(html)
        figs = extract_figures(out)
        assert [f.id for f in figs] == ["fig-1", "mine"]
        assert len(warnings) == 1 and "fig-1" in warnings[0]

    def test_assignment_skips_taken_ids(self):
        html = ('<div data-tb-figure="chart" data-tb-binding="a" id="fig-1">'
                '</div><div data-tb-figure="chart" data-tb-binding="b"></div>')
        out, _ = assign_figure_ids(html)
        assert [f.id for f in extract_figures(out)] == ["fig-1", "fig-2"]

    def test_page_with_all_ids_is_returned_unchanged(self):
        out, warnings = assign_figure_ids(PAGE)
        assert out == PAGE and warnings == []


class TestStripStage:
    def test_exploration_blocks_are_removed_whole(self):
        out = strip_stage(PAGE)
        assert "working note" not in out
        assert "fig-nulls" not in out
        # Everything else survives byte-for-byte around the cut.
        assert "fig-book" in out and "fig-est" in out

    def test_nested_exploration_blocks_remove_as_one_outermost_range(self):
        html = ('<div>keep</div>'
                '<section data-tb-stage="exploration">outer'
                '<div data-tb-stage="exploration">inner</div>'
                '</section><p>after</p>')
        out = strip_stage(html)
        assert out == "<div>keep</div><p>after</p>"

    def test_unclosed_stage_block_fails_loudly(self):
        with pytest.raises(FigureError, match="never closed"):
            strip_stage('<section data-tb-stage="exploration"><p>x</p>')

    def test_unknown_stage_is_refused(self):
        with pytest.raises(FigureError, match="unknown stage"):
            strip_stage('<div data-tb-stage="draft"></div>')

    def test_void_element_cannot_be_staged(self):
        with pytest.raises(FigureError, match="void element"):
            strip_stage('<img data-tb-stage="exploration">')


class TestStageMeta:
    def test_reads_the_stage_meta(self):
        assert read_stage_meta(PAGE) == "final"

    def test_absent_meta_is_none(self):
        assert read_stage_meta("<html><body></body></html>") is None


# ── the stated-methodology appendix ─────────────────────────────────────────
# The container is the template's opt-in; the build appends the pipeline's
# STATED methodology after the author's own children. Prose, never a
# verified claim — no badge, no status, and nothing injected without the
# container.

# Deliberately markup-shaped prose: the appendix must render it inert.
TRANSFORM_NOTE = "dropped the 9 unkeyed rows & <b>counted</b> them"
CHECK_NOTE = "an empty fact means the pull failed"
MEASURE_NOTE = "Book fair value: sum of revenue over kept rows"

CONTAINER = ('<section data-tb-methodology><h2>Method</h2>'
             '<p id="authors-own">The author\'s prose stays first.</p>'
             '</section>')


def _noted_warehouse(tmp_path):
    from tracebi.connectors.duckdb_connector import DuckDBConnector
    from tracebi.contracts import contract

    wh_path = str(tmp_path / "warehouse.duckdb")
    wh = DuckDBConnector("wh", database=wh_path)
    wh.write(pd.DataFrame({"region_id": [1, 2], "region": ["NE", "SE"]}),
             "dim_region")
    wh.write(pd.DataFrame({"order_id": [1, 2, 3], "region_id": [1, 2, 1],
                           "revenue": [100.0, 250.0, 75.0]}), "fact_orders")
    wh.disconnect()
    with contract("orders", warehouse=wh_path, note=TRANSFORM_NOTE) as c:
        c.rows("fact_orders", at_least=1, note=CHECK_NOTE)
        c.unique("fact_orders", ["order_id"])
    return wh_path


def _noted_model(wh_path):
    from tracebi import DataModel
    from tracebi.connectors.duckdb_connector import DuckDBConnector

    m = DataModel("wh_model")
    m.add_connector(DuckDBConnector("wh", database=wh_path))
    m.add_table("fact_orders", connector="wh", source="fact_orders")
    m.add_table("dim_region", connector="wh", source="dim_region")
    m.add_relationship("o2r", left_table="fact_orders",
                       right_table="dim_region", left_key="region_id")
    m.add_dimension("dim_r", table_name="dim_region",
                    key_col="region_id", attributes=["region"])
    m.add_fact("f", table_name="fact_orders", measures=["revenue"],
               foreign_keys={"dim_r": "region_id"})
    m.add_measure("total", column="revenue", agg="sum",
                  description=MEASURE_NOTE)
    m.connect()
    return m


def _render_package(tmp_path, extra_body=""):
    from tracebi.reports.template_package import TemplatePackage

    wh_path = _noted_warehouse(tmp_path)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "report.json").write_text(json.dumps({
        "name": "pkg",
        "data": {"kpi": {"model": "wh_model",
                         "query": {"fact": "f", "measures": ["total"]}}},
    }))
    (pkg / "template.html").write_text(
        "<html><head><title>x</title></head><body>"
        '<div data-tb-figure="value" data-tb-binding="kpi" '
        'data-tb-cell="total" id="fig-kpi"></div>'
        + extra_body +
        "</body></html>"
    )
    out = tmp_path / "out.html"
    manifest = TemplatePackage(str(pkg)).render(
        {"wh_model": _noted_model(wh_path)}, str(out))
    return out.read_text(encoding="utf-8"), manifest.to_dict()


#: The appendix div's own marker — tracebi.css (inlined into every page's
#: head) also contains the bare string "tb-methodology", so tests anchor on
#: the class attribute.
APPENDIX = 'class="tb-methodology"'


class TestMethodologyAppendix:
    def test_appendix_is_appended_after_the_authors_own_children(
            self, tmp_path):
        page, _ = _render_package(tmp_path, CONTAINER)
        assert APPENDIX in page
        # The author's prose stays theirs, and stays FIRST.
        assert 'id="authors-own"' in page
        assert page.index('id="authors-own"') < page.index(APPENDIX)
        # The appendix still sits inside the container.
        assert page.index(APPENDIX) < page.index("</section>")

    def test_appendix_states_transform_check_and_measure_notes(
            self, tmp_path):
        page, _ = _render_package(tmp_path, CONTAINER)
        # Locked language: the transform STATES — never "verified".
        assert "the transform 'orders' states:" in page
        assert f"rows(fact_orders): {CHECK_NOTE}" in page
        assert f"measure 'total': {MEASURE_NOTE}" in page
        # No badge anywhere near it: stated methodology is never green.
        appendix = page[page.index(APPENDIX):page.index("</section>")]
        assert "tb-badge" not in appendix
        assert "verified" not in appendix.lower()

    def test_every_note_is_escaped(self, tmp_path):
        page, _ = _render_package(tmp_path, CONTAINER)
        assert "dropped the 9 unkeyed rows &amp; &lt;b&gt;counted&lt;/b&gt; them" in page
        assert TRANSFORM_NOTE not in page       # the raw markup never ships

    def test_manifest_records_what_stated_methodology_shipped(self, tmp_path):
        _, manifest = _render_package(tmp_path, CONTAINER)
        assert manifest["methodology"] == {
            "transform_notes": {"fact_orders": TRANSFORM_NOTE},
            "check_notes": [{"transform": "orders", "check": "rows",
                             "table": "fact_orders", "note": CHECK_NOTE}],
            "measure_notes": {"total": MEASURE_NOTE},
        }
        # A separate claim: it colors nothing, and the contracts block is
        # unchanged beside it.
        assert manifest["transform_contracts"]["fact_orders"]["status"] \
            == "satisfied"

    def test_without_the_container_nothing_is_injected_and_manifest_omits_it(
            self, tmp_path):
        page, manifest = _render_package(tmp_path, extra_body="")
        assert APPENDIX not in page
        assert "methodology" not in manifest

    def test_two_containers_error_loudly(self, tmp_path):
        with pytest.raises(FigureError, match="ONE home"):
            _render_package(
                tmp_path,
                '<div data-tb-methodology></div><p data-tb-methodology></p>',
            )


class TestMethodologyContainerParsing:
    def test_insertion_point_is_the_containers_closing_tag(self):
        html = '<div>x</div><section data-tb-methodology><p>mine</p></section>'
        pos = methodology_insertion(html)
        assert html[pos:].startswith("</section>")

    def test_no_container_is_none(self):
        assert methodology_insertion("<div>x</div>") is None

    def test_two_containers_are_refused(self):
        with pytest.raises(FigureError, match="ONE home"):
            methodology_insertion(
                '<div data-tb-methodology></div>'
                '<p data-tb-methodology></p>'
            )

    def test_void_element_cannot_be_the_container(self):
        with pytest.raises(FigureError, match="void element"):
            methodology_insertion('<img data-tb-methodology>')

    def test_self_closing_container_is_refused(self):
        with pytest.raises(FigureError, match="closing tag"):
            methodology_insertion('<div data-tb-methodology/>')

    def test_unclosed_container_fails_loudly(self):
        with pytest.raises(FigureError, match="never closed"):
            methodology_insertion('<div data-tb-methodology><p>x</p>')
