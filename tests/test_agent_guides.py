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
                "a figure's number is only ever a query result",
                "the sink satisfied its contract",
                "data-tb-unverified",
            ):
                assert phrase in text, f"{name} lost the locked line {phrase!r}"
        # The control grammar's law is the vocabulary's too.
        assert "a figure's number is only ever a query result" in json.dumps(describe())

    def test_the_word_receipt_stays_retired(self):
        """What every number carries is its trace (2026-10-18). The old word
        survives only inside identifiers the artifact contract fixes; any
        other use is drift back into retired vocabulary."""
        internal = re.compile(r"tracebi-receipt|\.?tb-receipt[\w-]*|"
                              r"data-tb-receipt-[\w-]*|renderReceipt|"
                              r"receiptFileName|receipt_drawer")
        surfaces = dict(_guides())
        surfaces["tracebi context"] = json.dumps(describe())
        for name, text in surfaces.items():
            left = re.findall(r".{0,30}receipt.{0,30}", internal.sub("", text), re.I)
            assert not left, f"{name} still says receipt: {left[:3]}"

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
        # rglob, not glob: docs/ is a tree (concepts/, guides/, reference/,
        # architecture/), so a flat scan would miss the very pages that
        # document a command and let an undocumented one pass.
        parts += [
            p.read_text(encoding="utf-8") for p in (_REPO / "docs").rglob("*.md")
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
        from tracebi.cli import _INIT_SAMPLE_APP_JSX

        for marker in ("<Kpi lead", "<Value", "<Chart", "<Table", "<Filter",
                       "<Search", "<Download", "<Masthead", "<Footer",
                       "tb-span-8", "deltaBinding="):
            assert marker in _INIT_SAMPLE_APP_JSX, (
                f"the scaffold sample no longer demonstrates {marker}"
            )

    def test_the_showcase_carries_the_template_grammar(self):
        """The HTML grammar (template.html) is taught by the showcase now that
        the scaffold sample is an app."""
        from pathlib import Path

        showcase = (Path(__file__).parents[1] / "examples" / "portfolio_project" / "reports"
                    / "portfolio_model" / "portfolio_showcase" / "template.html").read_text()
        for marker in ("data-tb-filter", "data-tb-search",
                       "data-tb-download", "data-tb-figure",
                       "data-tb-stage", "data-tb-methodology",
                       "tb-masthead", "data-tb-period", "tb-footer",
                       "tb-kpi-delta", "tb-kicker", "tb-standfirst",
                       "tb-kpi--lead", "tb-span-8", "tb-span-4", "tb-span-6",
                       "data-tb-direction", "data-tb-bars", "data-tb-sort",
                       "data-tb-totals", "data-tb-facet", "data-tb-mark",
                       "data-tb-scenario", "data-tb-unverified", "tb-tabs",
                       *(f'data-tb-type="{t}"' for t in ("bar", "barh", "line",
                                                          "area", "scatter"))):
            assert marker in showcase, f"the showcase no longer demonstrates {marker}"


class TestTheDesignSystemIsTaught:
    """The report design system (the frame, the KPI signal, the grid) is the
    vocabulary every page is built from. A component the guides do not name
    is one an agent rebuilds by hand, in a look of its own."""

    _FRAME = ("tb-masthead", "tb-kicker", "tb-standfirst", "tb-masthead-meta",
              "tb-verdict", "data-tb-verdict", "tb-footer", "tb-kpi--lead",
              "tb-kpi-delta", "tb-span-8", "tb-span-4", "<Masthead", "<Footer",
              "deltaBinding")

    def test_the_vocabulary_and_both_guides_name_the_system(self):
        payload = json.dumps(describe(brief=True)["presentation"])
        for name in self._FRAME:
            assert name in payload, f"the vocabulary does not name {name}"
        for guide, text in _guides().items():
            missing = [n for n in self._FRAME if n not in text]
            assert not missing, f"{guide} does not teach {missing}"

    def test_every_scaffold_and_bundle_is_framed(self):
        """What a new project copies opens with the masthead and ends with
        the footer: the init sample, the new-report and new-dashboard
        templates, and both init --template bundles."""
        from tracebi.cli import _INIT_SAMPLE_APP_JSX, _report_template_html

        pages = {"init sample": _INIT_SAMPLE_APP_JSX}
        for layout in ("editorial", "brief", "dashboard", "tabbed"):
            pages[layout] = _report_template_html(
                "T", "revenue", "dim_region.region", layout)
        bundles = _REPO / "tracebi" / "_scaffold" / "templates"
        for path in sorted(bundles.rglob("reports/*/*/*")):
            if path.name in ("app.jsx", "template.html"):
                pages[str(path.relative_to(bundles))] = path.read_text(encoding="utf-8")
        assert len(pages) >= 8
        for name, page in pages.items():
            opens = "<Masthead" in page or "tb-masthead" in page
            ends = "<Footer" in page or "tb-footer" in page
            assert opens and ends, f"{name} is not on the frame (masthead and footer)"


class TestDescriptionsAreForTheReader:
    """A report's description is the library's second line, the first thing a
    reader scans. It was written for agents once ("an app (app.jsx) whose every
    number is a kit figure"); this keeps how a page is built out of it."""

    # Each of these once stood in a shipped description.
    _BUILD_TALK = re.compile(
        r"app\.jsx|template\.html|\bkit\b|bound figure|house CSS|receipt names it|"
        r"editorial report|stamped binding|React lane|as an app\b|scaffolded by|"
        r"re-runs the pandas|kitchen-sink|\w+_model\b", re.I)

    def test_no_shipped_description_says_how_the_page_is_built(self):
        from tracebi.cli import _report_json_text

        found = {}
        roots = [_REPO / "examples", _REPO / "tracebi" / "_scaffold",
                 _REPO / "tracebi" / "web" / "demo_app"]
        for root in roots:
            for path in [*root.rglob("report.json"), *root.rglob("init_sample_report.json")]:
                found[str(path.relative_to(_REPO))] = json.loads(
                    path.read_text(encoding="utf-8")).get("description", "")
        query = {"fact": "f", "measures": ["revenue"], "dimensions": ["dim_region.region"]}
        for look in (None, {}):
            found[f"new-report (look={look})"] = json.loads(
                _report_json_text("T", "sales_model", query, look=look))["description"]
        assert len(found) >= 15
        for where, text in found.items():
            hit = self._BUILD_TALK.search(text)
            assert not hit, f"{where}: the description says {hit.group(0)!r}"


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

    def test_draw_api_is_in_the_vocabulary_and_both_guides(self):
        from tracebi.capabilities import describe

        payload = json.dumps(describe())
        assert "tracebi.draw(" in payload and "tracebi.theme()" in payload, (
            "the vocabulary must document tracebi.draw and tracebi.theme — "
            "without them an agent draws once from tracebi.data and the "
            "figure ignores the page's filters and theme"
        )
        for name, text in _guides().items():
            assert "tracebi.draw(" in text, f"{name} does not teach tracebi.draw"

    def test_the_size_chosen_embed_format_is_explained_in_both_guides(self):
        for name, text in _guides().items():
            assert "Parquet" in text, f"{name} never mentions the Parquet embed"
            assert "PyArrow" in text or "pyarrow" in text, (
                f"{name} does not name the dependency the Parquet form needs"
            )

    def test_the_embed_keys_are_in_the_vocabulary_and_both_guides(self):
        note = " ".join(describe(brief=True)["presentation"]["report_json"]["embed"].values())
        for name, text in {"tracebi context": note, **_guides()}.items():
            for phrase in ('"embed"', "embed_budget_mb", "tracebi-slice-",
                           "tracebi-calc-plans"):
                assert phrase in text, f"{name} does not teach {phrase}"

    def test_the_project_settings_file_is_in_the_vocabulary_and_both_guides(self):
        settings = next(d for d in describe(brief=True)["conventions"]["directories"]
                        if d["path"] == "tracebi.yaml")
        for name, text in {"tracebi context": settings["note"], **_guides()}.items():
            for phrase in ("tracebi init", "query_timeout_s", "memory_limit",
                           "docs/reference/tracebi-yaml.md", "warehouse:",
                           "type: warehouse", "sink_target()", "${ENV_VAR}"):
                assert phrase in text, f"{name} does not teach {phrase}"


    def test_the_source_directive_is_in_the_vocabulary_and_both_guides(self):
        # A transform that reads a database without the directive reaches for
        # pandas and a hand-rolled connection, and the certificate never
        # learns which inputs the sink was checked against.
        transforms = next(d for d in describe(brief=True)["conventions"]["directories"]
                          if d["path"] == "transforms/")
        for name, text in {"tracebi context": transforms["note"], **_guides()}.items():
            for phrase in ("-- source:", "fallback:", "source_fallback", "load_source(",
                           "sources"):
                assert phrase in text, f"{name} does not teach {phrase}"


def test_a_value_figure_is_taught_as_a_one_row_binding():
    """data-tb-cell reads one row. A multi-row binding is a build error,
    and a text cell (the top sector's name) is shown as text."""
    from tracebi.mcp_server import authoring_guide

    cell = describe(brief=True)["presentation"]["figure_attributes"]["data-tb-cell"]
    assert "one-row" in cell
    assert "row 0" not in cell
    assert "top sector" in cell
    kinds = describe(brief=True)["presentation"]["figure_helper"]["kinds"]
    assert "one-row binding" in kinds
    for name, text in _guides().items():
        assert "one-row binding" in text, name
        assert "top sector" in text, name
    guide = authoring_guide()
    assert "one-row binding" in guide
    assert "top sector" in guide


def test_d3_is_taught_as_automatic_when_the_page_has_a_chart():
    """A chart figure needs no ``libs``: both guides and the gateway guide
    say the build adds D3, and how to keep ECharts."""
    from tracebi.mcp_server import authoring_guide

    note = describe(brief=True)["presentation"]["report_json"]["libs"]
    assert "optional" in note and "automatically" in note
    assert "inlines D3 automatically" in authoring_guide()
    for name, text in _guides().items():
        assert "inlines D3 automatically" in text, name
        assert '"echarts"' in text, f"{name} does not say how to keep ECharts"
