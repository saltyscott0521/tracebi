"""
The agent guides can never drift from the product again.

Round 2's biggest finding: everything built in M1–M5 was invisible to the
file agents read first — the guides described the previous product. The
durable fix has three layers: generate what drifts (``tracebi context`` is
generated from code), hand-write only what is stable, and BIND the two
with these tests — every ``data-tb-*`` attribute the generated vocabulary
documents must be *named* in both agent guides, and the load-bearing
commands must appear where agents look for them. Add a feature without
teaching it and CI fails: "would the agent know?" is a test now, not a
hope.
"""

import json

import re
from pathlib import Path

from tracebi.capabilities import describe

_REPO = Path(__file__).parent.parent


def _guides() -> dict[str, str]:
    from tracebi.cli import _INIT_AGENTS_MD

    # Whitespace-normalized: markdown wraps lines, and the LOCKED LINE is
    # what must survive, not its wrapping.
    return {
        "repo AGENTS.md": re.sub(
            r"\s+", " ", (_REPO / "AGENTS.md").read_text(encoding="utf-8")),
        "scaffolded AGENTS.md": re.sub(r"\s+", " ", _INIT_AGENTS_MD),
    }


def _vocabulary_attributes() -> set[str]:
    """Every data-tb-* attribute the generated vocabulary documents."""
    pres = describe(brief=True)["presentation"]
    text = str(pres)
    return set(re.findall(r"data-tb-[a-z-]+", text))


class TestGuidesCoverTheVocabulary:
    def test_every_documented_attribute_is_named_in_both_guides(self):
        attrs = _vocabulary_attributes()
        assert attrs, "the vocabulary must document data-tb-* attributes"
        for name, text in _guides().items():
            missing = sorted(a for a in attrs if a not in text)
            assert not missing, (
                f"{name} does not name {missing} — a feature the guides "
                f"don't teach effectively does not exist (round-2 lesson). "
                f"Name it in the guide, or remove it from the vocabulary."
            )

    def test_the_honesty_rules_travel_verbatim(self):
        """The locked lines must appear in both guides — vocabulary is
        load-bearing and must not be paraphrased into drift."""
        for name, text in _guides().items():
            for phrase in (
                "never compute new numbers",
                "the sink satisfied its contract",
                "data-tb-unverified",
            ):
                assert phrase in text, f"{name} lost the locked line {phrase!r}"

    def test_the_loop_commands_are_taught(self):
        """The commands an agent must run appear in both guides."""
        for name, text in _guides().items():
            for cmd in ("tracebi dev", "tracebi report build",
                        "tracebi verify", "tracebi context"):
                assert cmd in text, f"{name} does not teach {cmd}"


class TestCLISurfaceIsDocumented:
    """Every user-facing ``tracebi <cmd>`` must be named in at least one
    doc surface an operator or agent actually reads. This closes the gap
    that let ``report send`` ship with zero documentation: a command the
    docs never mention is a command nobody discovers."""

    def _subcommands(self) -> set[str]:
        from tracebi.cli import build_parser

        parser = build_parser()
        subs: set[str] = set()
        for action in parser._subparsers._group_actions:
            subs |= set(getattr(action, "choices", {}).keys())
        return subs

    def _doc_corpus(self) -> str:
        parts = [
            (_REPO / "README.md").read_text(encoding="utf-8"),
            (_REPO / "AGENTS.md").read_text(encoding="utf-8"),
        ]
        parts += [
            p.read_text(encoding="utf-8") for p in (_REPO / "docs").glob("*.md")
        ]
        return "\n".join(parts)

    def test_every_subcommand_is_named_in_the_docs(self):
        subs = self._subcommands()
        assert subs, "the CLI must expose subcommands"
        corpus = self._doc_corpus()
        missing = sorted(c for c in subs if f"tracebi {c}" not in corpus)
        assert not missing, (
            f"these CLI subcommands are undocumented: {missing}. Name each "
            f"as `tracebi <cmd>` in README.md, AGENTS.md, or a docs/ guide — "
            f"a command the docs never mention is one nobody discovers "
            f"(the `report send` lesson)."
        )


class TestScaffoldDemonstratesTheProduct:
    def test_scaffold_template_carries_the_interactive_grammar(self):
        """The first page a new project renders must demonstrate the
        current product — the scaffold is a teaching surface, and round 2
        proved a scaffold teaching the old lane orphans every feature."""
        from tracebi.cli import _INIT_SAMPLE_TEMPLATE_HTML

        for marker in ("data-tb-filter", "data-tb-search",
                       "data-tb-download", "data-tb-figure",
                       "data-tb-stage", "data-tb-methodology"):
            assert marker in _INIT_SAMPLE_TEMPLATE_HTML, (
                f"the scaffold sample no longer demonstrates {marker}"
            )


class TestLargeDetailArtifactIsTaught:
    """The discoverability definition of done for the Parquet embed.

    A feature agents should use is not done when it works — it is done when an
    agent WOULD use it. The size-chosen embed format changes how an author must
    write script.js (a bare tracebi.data() call returns [] on a Parquet
    artifact), so both guides and the generated vocabulary must say so.
    """

    def test_ready_api_is_in_the_vocabulary_and_both_guides(self):
        from tracebi.capabilities import describe

        payload = json.dumps(describe())
        assert "tracebi.ready(" in payload, (
            "the vocabulary must document tracebi.ready — without it an agent "
            "writes a top-level tracebi.data() call that silently returns []"
        )
        for name, text in _guides().items():
            assert "tracebi.ready(" in text, f"{name} does not teach tracebi.ready"

    def test_the_size_chosen_embed_format_is_explained_in_both_guides(self):
        for name, text in _guides().items():
            assert "Parquet" in text, f"{name} never mentions the Parquet embed"
            assert "PyArrow" in text or "pyarrow" in text, (
                f"{name} does not name the dependency the Parquet form needs"
            )
