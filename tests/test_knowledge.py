"""The analyst knowledge base is well-formed AND actually delivered.

The failure mode this guards is the one the map found in docs/agents/sop-*.md:
genuine practice that no agent surface points at, so it rots unread. These tests
assert the lessons are well-formed and — the load-bearing part — that they reach
an agent through both consumption forms (the `tracebi context` payload and the
`tracebi-analyst` skill). If the delivery is ever silently dropped, CI fails.
"""

import re
from pathlib import Path

from tracebi.knowledge import get_lesson, index, list_lessons

_SKILL = (Path(__file__).resolve().parents[1]
          / "skills" / "tracebi-analyst" / "SKILL.md")


def test_lessons_parse_and_slugs_are_unique():
    lessons = list_lessons()
    assert lessons, "no lessons found — the curriculum is empty"
    slugs = [ls.slug for ls in lessons]
    assert len(slugs) == len(set(slugs)), f"duplicate lesson slugs: {slugs}"
    for ls in lessons:
        assert ls.title and ls.title != ls.slug, f"{ls.slug}: missing title"
        assert ls.when, f"{ls.slug}: missing 'when' trigger — an agent needs it"
        assert len(ls.body) > 100, f"{ls.slug}: body too thin to teach anything"


def test_cross_links_resolve():
    """Every [[slug]] reference points at a real lesson (link liberally, but not
    to nothing — a dead reference teaches the agent a lesson that isn't there)."""
    slugs = {ls.slug for ls in list_lessons()}
    for ls in list_lessons():
        for ref in re.findall(r"\[\[([a-z0-9-]+)\]\]", ls.body):
            assert ref in slugs, f"{ls.slug} links [[{ref}]] which does not exist"


def test_the_curriculum_is_delivered_in_context_both_tiers():
    """The lessons must appear in describe() — brief AND full — or a bring-your-
    own agent over MCP never learns the curriculum exists. This is the guard
    against the SOP-doc fate: a folder nobody's surface points at."""
    from tracebi.capabilities import describe

    for brief in (True, False):
        payload = describe(brief=brief)
        block = payload.get("analyst_knowledge")
        assert block, f"analyst_knowledge missing from context (brief={brief})"
        got = {l["slug"] for l in block["lessons"]}
        assert got == {ls.slug for ls in list_lessons()}, (
            f"context curriculum out of sync with the lessons (brief={brief})")
        assert "tracebi knowledge" in block["fetch"]


def test_context_index_matches_the_files():
    idx = index()
    assert {i["slug"] for i in idx} == {ls.slug for ls in list_lessons()}
    for i in idx:
        assert i["title"] and i["when"]


def test_skill_points_at_the_knowledge_base():
    """The skill must delegate to the lessons (single source of truth), not
    re-state the guidance where it can drift."""
    text = _SKILL.read_text(encoding="utf-8")
    assert "tracebi knowledge" in text, "skill does not reference the lessons"
    # The seed lessons the skill names by slug must exist.
    for slug in ("ratio-of-totals", "weighted-vs-plain-mean", "grain-and-fanout",
                 "verify-your-own-work"):
        assert slug in text, f"skill names '{slug}' in prose"
        assert get_lesson(slug) is not None, f"skill names missing lesson '{slug}'"


def test_reference_model_obeys_the_weighted_mean_lesson():
    """The 'would the agent do the analysis RIGHT' rot-guard the map asked for.
    A measure declared agg='mean' but described 'weighted' is the exact silent-
    wrong trap weighted-vs-plain-mean names — and the reference model shipped it
    once. If it ever comes back (or lands in the scaffold), fail here, because
    the canonical example teaches by being correct."""
    model_src = (Path(__file__).resolve().parents[1] / "examples"
                 / "portfolio_project" / "models" / "portfolio_model.py")
    src = model_src.read_text(encoding="utf-8")
    # Strip comments so a note ABOUT the trap ("previously agg=mean, 'weighted'")
    # doesn't trip the lint — only real declarations count.
    src = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
    for block in src.split(".add_measure(")[1:]:
        call = block.split(".add_measure(")[0]        # up to the next measure
        norm = call.replace("'", '"')
        is_mean = 'agg="mean"' in norm or 'agg="avg"' in norm
        says_weighted = re.search(r"weight", call, re.IGNORECASE)
        assert not (is_mean and says_weighted), (
            "portfolio_model declares a 'weighted' measure as a plain mean — "
            "see tracebi knowledge weighted-vs-plain-mean; use a ratio of "
            "sum(value*weight) / sum(weight) instead.")


# ── The guardrail that teaches — the fanout raise's sibling ────────────────────
# A guardrail is worth more than a paragraph of prose because it fires at the
# moment of the mistake and no model can skip it. This one refuses a mean of a
# rate/ratio and cites the lesson.

class TestMeanOfARatioGuard:
    def _model(self):
        from tracebi import DataModel
        return DataModel("t")

    def test_refuses_a_mean_of_a_rate_named_measure(self):
        import pytest
        for name, col in [("avg_margin_pct", "margin_pct"), ("yield", "y"),
                          ("avg_spread_bps", "spread_bps"), ("default_rate", "d")]:
            with pytest.raises(ValueError, match="rate or ratio"):
                self._model().add_measure(name, column=col, agg="mean")

    def test_refuses_a_weighted_mean_declared_as_a_plain_mean(self):
        import pytest
        with pytest.raises(ValueError, match="rate or ratio"):
            self._model().add_measure("wtd", column="spread", agg="mean",
                                      description="Weighted average spread")

    def test_the_refusal_teaches(self):
        import pytest
        with pytest.raises(ValueError) as exc:
            self._model().add_measure("avg_yield", column="yield", agg="mean")
        msg = str(exc.value)
        assert "ratio-of-totals" in msg          # cites the lesson
        assert "allow_mean=True" in msg          # names the escape hatch
        assert "sum(numerator)" in msg           # gives the correct pattern

    def test_does_not_false_positive_on_additive_means(self):
        # Legitimate means of additive quantities must still work.
        for name, col in [("avg_order_value", "revenue"), ("avg_age", "age"),
                          ("mean_qty", "quantity")]:
            self._model().add_measure(name, column=col, agg="mean")

    def test_allow_mean_is_the_escape_hatch(self):
        # Explicit opt-out, like allow_fanout — never blocks a deliberate choice.
        self._model().add_measure("avg_pct", column="p", agg="mean",
                                   allow_mean=True)

    def test_guard_is_documented_in_the_vocabulary(self):
        from tracebi.capabilities import describe
        constraints = describe()["semantic_model"]["constraints"]
        assert any("allow_mean" in c for c in constraints), (
            "the mean-of-a-ratio guard must be in the vocabulary so an agent "
            "knows it exists and knows the escape hatch")
