# Test suite review, 2026-09-22

**Test what the product does, not what it looks like.** A test earns its
place when it would catch a real bug: a wrong number, a broken receipt, a
security hole, two implementations drifting apart. A test that pins a colour, a
CSS rule, a file size or a sentence in the README catches nothing. It just
makes every design or wording change also a test change.

This review applied that rule to all 36 test files.

---

## Removed in this change

| Test | Why it went |
| --- | --- |
| `tests/test_presentation_css.py` (whole file, 6 tests) | Read `tracebi.css` as text and asserted selectors, property values, a 20 KB size cap, and that the chart colours matched `DEFAULT_PALETTE`. Every restyle broke it; no behaviour depended on it. |
| `test_chart_grouping.py::TestNoColorByteIdentical` (2 tests) | SHA-256 hashes of rendered SVG charts. Any colour or spacing change failed them. The grouping *behaviour* is still covered by the other tests in that file. |
| `test_phase25.py::test_to_mermaid_colors` | Asserted two hex colours in the lineage diagram. |
| `test_docs_site.py::test_the_palette_comes_from_the_landing_page` | Asserted the docs site and the marketing page share colour tokens. |
| `test_presentation_js.py::TestChartThemeColors` (3 tests) | Asserted chart axis colours follow CSS tokens. Theme mechanics, not behaviour. |
| Two assertions in `TestTableOverridesAndChartPolish` | Pinned bar corner radius and tick text. The test now asserts only that chart styling never changes the data. |

13 tests removed. The suite is 1,414 passing after this change, plus the tests
added for the new features.

## Removed in the follow-up change

| Test | Why it went |
| --- | --- |
| The size cap in `test_presentation_js.py::TestAssetHygiene` | Capped `tracebi.js` at a byte size. See [[#Why is there a KB limit?]] The test now only checks the asset exists; `test_no_eval`, `test_no_innerhtml` and `test_public_api_defined` stay. |
| The size assertion in `test_engine_assets.py::test_parquet_wasm_is_gzipped` | Asserted the WebAssembly file was "substantial". The gzip check stays. |
| `test_phase1.py::test_dataset_help_prints`, `test_datamodel_help_prints`; `test_phase2.py::test_report_help_prints`; `test_phase5.py::test_help_text_returns_the_string`, `test_help_still_prints_the_same_text` | Asserted `help()` prints text with a few method names in it. `test_cheat_sheet_kwargs_are_real_parameters` still checks the cheat sheets name real parameters, which is the bug that actually shipped. |
| `test_phase1.py::test_dataset_repr_html`, `test_datamodel_repr_html`; `test_phase2.py::test_report_repr_html_is_iframe` | Pinned the notebook display markup. `test_dataset_repr_html_escapes` (HTML injection) and `test_dataset_repr_html_caps_preview` (a huge frame can't freeze a notebook) stay. |
| `os.path.getsize(path) > 1000` / `> 2000` in `test_phase2.py` | "The file isn't tiny" said little. The tests still check the file is written, and the neighbouring tests check its sheets and markup. |

8 tests and 5 size assertions removed.

## Kept after a second look

| Test | Why it stays |
| --- | --- |
| `test_journey_fixes.py::test_readme_uses_git_url_install_form`, `test_readme_has_no_bare_pypi_install_line`, `test_missing_uvicorn_message_uses_git_url_form` | These looked like wording tests, but they are a **security guard**. A package named `tracebi` exists on PyPI (0.5.0–0.5.3). If that package isn't ours, a bare `pip install tracebi` installs someone else's code (dependency confusion). If it is ours, the tests go when 0.6 is published and the README switches to `pip install tracebi`. Confirm ownership before removing them. |
| `test_docs_site.py::test_regenerating_produces_no_diff` | The site deploys with no build step (`site/README.md`), so the generated HTML has to be committed, and this test is what keeps it current. Remove it only after the deploy runs `python site/build_docs.py` itself. |

## Keep, even though they look presentational

These touch presentation but guard behaviour:

- **Style injection order** (`test_presentation.py::test_later_wins_layer_order`):
  the override chain is a feature authors rely on.
- **Security:** no `eval`, no `innerHTML`, CSP present and not suppressible,
  escaping of labels and prose.
- **Parity between two implementations:** the Python and JavaScript number
  formatters must produce the same text, or a number flickers on load. Same for
  the worker engine's float spelling.
- **Honesty rules:** provenance badges, unverified marks, exploration stripped
  at build, receipts and fingerprints.
- **Agent guides** (`test_agent_guides.py`): documentation *is* the agent
  interface here. A feature the guides don't name doesn't get used.

## Why is there a KB limit?

`tracebi.js` is inlined into every report, so every byte ships in every file.
The limit was meant to stop the runtime growing unnoticed. It has been raised
five times, each with a note ("Behavior, not bloat"), which shows it never
stopped a change. It only added a step.

It also guards the wrong thing. A report with charts is around 700–860 KB. Of
that, the bundled ECharts is 620 KB and `tracebi.js` is 70 KB, under a tenth
of the file. If file size matters, measure the **built report**,
and report it in the build output rather than failing a test.

**Done:** the test is removed. If size ever becomes a real complaint, add
a line to `tracebi report build` output ("report.html: 862 KB") and let people
decide.

## End-to-end first, 2026-09-28

The first two passes removed tests that pinned *presentation*. This one went
after *volume*: the suite had grown the way generated suites do — hundreds of
tiny tests (a third were four lines or fewer), look-alikes that differ only in
the input, asserts on private fields, and "it didn't raise" or "the text
appears" checks — while only a handful of tests used the product the way a
person does.

**Added: seven journeys in `tests/e2e/`**, each driving the real entry points
in-process (so coverage sees them) against a project on disk:

| Journey | What it walks |
| --- | --- |
| analyst | `init` → `run-transform` → `validate` → `report build` → `verify --strict --contracts` → `verify --file`; then a number edited in the file, and the warehouse changing under the report |
| reference project | both transforms, then every report in `examples/portfolio_project` builds, reproduces and is intact; the showcase's affordances; a control recomputing on the model; the housing scenario never receipted |
| web | the app over a live-discovered project: status, report list, run, background run, built page, share link, HTML/XLSX download, source, lineage, model browser, an Explore query and its error |
| agent | the MCP tools: context → models → a stamped query → validate (wrong, then right) → render → verify → build → fetch; the path guards |
| schedule | a `schedule` block → `schedule run` builds, verifies, emails (only smtplib faked) and records; no mail server says what to set |
| pipeline | `new-pipeline`, filled in, run from the CLI and the Refresh API, history read back |
| author | `tracebi dev` on a spare port: preview, workbench state, a pin left and resolved from the CLI; status; the review snapshot verify refuses |

**Removed: 247 tests net** (1,524 test functions → 1,277 unit tests plus 21
end-to-end tests; 1,602 collected cases → 1,381) — the journeys' duplicates (`test_showcase.py` and
`test_housing_report.py` went whole), look-alikes, private-field and repr
checks, weak assertions, and restated defaults. Look-alike vocabulary and
"lesson exists" tests for nine analytics features became one test that
derives the measure kinds and aggregations from the code.

**Coverage went up, 85% → 86%** (11,029 → 11,242 lines), because the journeys
reach code no unit test did. What the old suite covered and the new one
doesn't is deliberate: `__repr__`, `describe()` and `print_lineage()` (notebook
print helpers), and the legacy renderer's colour scale and cell styling —
presentation, per the rule above.

**It found two real bugs.** The dev server's file watcher never stopped when
the server did (its stop event was never set); a test that ran after it in the
same process saw the old watcher open the new project's warehouse. And
`TestPipelineRunEndpoint` only isolated itself if the router hadn't been
imported yet — the no-op-isolation trap CLAUDE.md describes; it now swaps the
router's own binding.

## The rule for new tests

Before adding a test, answer: *what bug would this catch?* If the answer is
"someone changed a colour, a size, or a sentence", don't add it.

Prefer a step in a journey (`tests/e2e/`) over a new unit test. Write a unit
test when a journey can't pin the thing precisely: query semantics,
Python/JavaScript formatting parity, fingerprints and verify verdicts,
contracts, security, the honesty rules. Never a look-alike (parametrize, or
pick the one case that matters), never an assert on a private field, never
"it didn't raise" or "the string appears" on its own. See
[[pitfalls]] for the bugs that did happen, and the checks that would have
caught them.
