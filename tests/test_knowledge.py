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

    def test_refuses_additive_aggregation_of_a_rate(self):
        import pytest
        # mean AND sum of a rate are both refused; min/max are not.
        for agg in ("mean", "avg", "sum"):
            for name, col in [("avg_margin_pct", "margin_pct"), ("yield", "y"),
                              ("total_spread_bps", "spread_bps")]:
                with pytest.raises(ValueError, match="aggregates a rate"):
                    self._model().add_measure(name, column=col, agg=agg)

    def test_min_max_of_a_rate_are_allowed(self):
        # The widest spread / lowest yield are legitimate.
        self._model().add_measure("max_spread_bps", column="spread_bps", agg="max")
        self._model().add_measure("min_yield", column="yield", agg="min")

    def test_summing_a_weighted_numerator_is_allowed(self):
        # Σ(value × weight) is the CORRECT building block of a weighted average —
        # "weighted" in the description must NOT refuse a sum (only a mean).
        self._model().add_measure(
            "spread_x_par", expr="spread_bps * par", agg="sum",
            description="Σ(spread × par) — par-weighted-spread numerator")

    def test_refuses_a_weighted_mean_declared_as_a_plain_mean(self):
        import pytest
        with pytest.raises(ValueError, match="aggregates a rate"):
            self._model().add_measure("wtd", column="spread", agg="mean",
                                      description="Weighted average spread")

    def test_the_refusal_teaches(self):
        import pytest
        with pytest.raises(ValueError) as exc:
            self._model().add_measure("avg_yield", column="yield", agg="mean")
        msg = str(exc.value)
        assert "ratio-of-totals" in msg          # cites the lesson
        assert "allow_rate_agg=True" in msg      # names the escape hatch
        assert "sum(numerator)" in msg           # gives the correct pattern

    def test_does_not_false_positive_on_additive_means(self):
        # Legitimate means of additive quantities must still work.
        for name, col in [("avg_order_value", "revenue"), ("avg_age", "age"),
                          ("mean_qty", "quantity")]:
            self._model().add_measure(name, column=col, agg="mean")

    def test_allow_rate_agg_is_the_escape_hatch(self):
        # Explicit opt-out, like allow_fanout — never blocks a deliberate choice.
        self._model().add_measure("avg_pct", column="p", agg="mean",
                                   allow_rate_agg=True)
        self._model().add_measure("sum_pct", column="p2", agg="sum",
                                   allow_rate_agg=True)

    def test_guard_is_documented_in_the_vocabulary(self):
        from tracebi.capabilities import describe
        constraints = describe()["semantic_model"]["constraints"]
        assert any("allow_rate_agg" in c for c in constraints), (
            "the mean-of-a-ratio guard must be in the vocabulary so an agent "
            "knows it exists and knows the escape hatch")


# ── Expressiveness pulled back into the governed lane: distribution aggs ───────
# A mean hides skew; median/stddev used to force report.py (ungoverned, no
# receipt, no guard). Now they are declarative measures — governed, verifiable,
# deterministic — paired with the summarize-a-distribution lesson.

class TestDistributionAggregations:
    def _model(self):
        import pandas as pd
        from tracebi import DataModel, MemoryConnector
        fact = pd.DataFrame({"desk_id": [1, 1, 1, 1, 2, 2, 2, 2],
                             "pnl": [10, 12, 11, 500, 9, 11, 10, 12]})
        dim = pd.DataFrame({"desk_id": [1, 2], "desk": ["A", "B"]})
        m = DataModel("risk")
        m.add_connector(MemoryConnector("mem", tables={"fact": fact, "dim_desk": dim}))
        m.add_table("fact", connector="mem", source="fact")
        m.add_table("dim_desk", connector="mem", source="dim_desk")
        m.add_dimension("dim_desk", table_name="dim_desk", key_col="desk_id",
                        attributes=["desk"])
        m.add_fact("f", table_name="fact", measures=["pnl"],
                   foreign_keys={"dim_desk": "desk_id"})
        m.add_measure("mean_pnl", column="pnl", agg="mean")
        m.add_measure("median_pnl", column="pnl", agg="median")
        m.add_measure("stddev_pnl", column="pnl", agg="stddev")
        m.connect()
        return m

    def _run(self, m):
        from tracebi.model.data_model import QuerySpec
        return m.execute(QuerySpec.from_dict(
            {"fact": "f", "measures": ["mean_pnl", "median_pnl", "stddev_pnl"],
             "dimensions": ["dim_desk.desk"]})).to_pandas()

    def test_median_is_robust_where_the_mean_is_dragged_by_an_outlier(self):
        row = self._run(self._model()).set_index("dim_desk.desk").loc["A"]
        assert row["mean_pnl"] > 100        # dragged by the 500 outlier
        assert 11 <= row["median_pnl"] <= 12   # the honest centre
        assert row["stddev_pnl"] > 100      # the spread flags the skew

    def test_distribution_aggs_are_deterministic(self):
        m = self._model()
        assert self._run(m).equals(self._run(m))

    def test_median_and_stddev_are_in_the_vocabulary(self):
        from tracebi.capabilities import describe
        aggs = describe()["semantic_model"]["aggregations"]
        assert "median" in aggs and "stddev" in aggs

    def test_the_lesson_exists_and_is_delivered(self):
        assert get_lesson("summarize-a-distribution") is not None
        slugs = {ls["slug"] for ls in index()}
        assert "summarize-a-distribution" in slugs

    def test_median_of_a_rate_is_not_refused(self):
        # The rate guard targets ADDITIVE aggs (sum/mean); a median or stddev of
        # a rate is a legitimate summary and must stay allowed.
        from tracebi import DataModel
        DataModel("t").add_measure("median_spread_bps", column="spread_bps",
                                   agg="median")


# ── Share-of-total: a report.py computation pulled into the governed lane ──────

class TestShareMeasure:
    def _model(self):
        import pandas as pd
        from tracebi import DataModel, MemoryConnector
        fact = pd.DataFrame({"region_id": [1, 2, 3], "rev": [600.0, 300.0, 100.0]})
        dim = pd.DataFrame({"region_id": [1, 2, 3],
                            "region": ["West", "East", "North"]})
        m = DataModel("s")
        m.add_connector(MemoryConnector("mem", tables={"fact": fact, "dim_region": dim}))
        m.add_table("fact", connector="mem", source="fact")
        m.add_table("dim_region", connector="mem", source="dim_region")
        m.add_dimension("dim_region", table_name="dim_region", key_col="region_id",
                        attributes=["region"])
        m.add_fact("f", table_name="fact", measures=["rev"],
                   foreign_keys={"dim_region": "region_id"})
        m.add_measure("revenue", column="rev", agg="sum")
        m.add_measure("revenue_share", share="revenue", format="percent")
        m.connect()
        return m

    def _run(self, m, **extra):
        from tracebi.model.data_model import QuerySpec
        q = {"fact": "f", "measures": ["revenue", "revenue_share"],
             "dimensions": ["dim_region.region"], **extra}
        return m.execute(QuerySpec.from_dict(q))

    def test_shares_are_the_fraction_of_the_total(self):
        df = self._run(self._model()).to_pandas().set_index("dim_region.region")
        assert df.loc["West", "revenue_share"] == 0.6
        assert df.loc["East", "revenue_share"] == 0.3
        assert round(df["revenue_share"].sum(), 6) == 1.0

    def test_share_is_deterministic_and_a_known_result_column(self):
        m = self._model()
        assert self._run(m).fingerprint() == self._run(m).fingerprint()
        from tracebi.model.data_model import QuerySpec
        cols = m.spec_result_columns(QuerySpec.from_dict(
            {"fact": "f", "measures": ["revenue", "revenue_share"],
             "dimensions": ["dim_region.region"]}))
        assert "revenue_share" in cols

    def test_share_takes_no_agg(self):
        import pytest
        from tracebi import DataModel
        with pytest.raises(ValueError, match="take no agg"):
            DataModel("t").add_measure("s", share="revenue", agg="sum")

    def test_share_is_in_the_vocabulary(self):
        from tracebi.capabilities import describe
        kinds = {k["kind"] for k in describe()["semantic_model"]["measure_kinds"]}
        assert "share" in kinds

    def test_the_lesson_exists_and_is_delivered(self):
        slugs = {ls["slug"] for ls in index()}
        assert "share-of-total" in slugs
        assert get_lesson("share-of-total") is not None
