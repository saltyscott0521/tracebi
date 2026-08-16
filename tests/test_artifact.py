"""
The artifact layer — figure extraction, id assignment, exploration strip.

figures.py is the ONE parser for data-tb-* markup (architecture v2 §2.1,
flaw 1): build validation, the exploration strip, and verify --file all
share it, so these tests are the trust tests for all three. Hostile and
malformed markup must fail LOUDLY — a figure silently missed here would
vanish from the build check and the offline check at once.
"""

import pytest

from tracebi.reports.figures import (
    Figure,
    FigureError,
    assign_figure_ids,
    extract_figures,
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
