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

## Recommended for removal (not yet removed)

| Test | Why | Suggested action |
| --- | --- | --- |
| `test_presentation_js.py::TestAssetHygiene::test_asset_exists_and_under_size_budget` | Caps `tracebi.js` at a byte size. See [[#Why is there a KB limit?]] | Remove. Keep `test_no_eval`, `test_no_innerhtml` and `test_public_api_defined` in the same class; those are security and API checks. |
| `test_engine_assets.py::test_parquet_wasm_is_gzipped_and_substantial` | Asserts the WebAssembly file is "substantial" (a size check). | Keep the gzip check, drop the size assertion. |
| `test_journey_fixes.py::test_readme_uses_git_url_install_form`, `test_readme_has_no_bare_pypi_install_line`, `test_missing_uvicorn_message_uses_git_url_form` | Pin the README's install wording to "install from git". They will fail the day TraceBi is published on PyPI, which is the plan. | Remove when 0.6 ships to PyPI (or now). |
| `test_phase1.py::test_dataset_help_prints`, `test_datamodel_help_prints`; `test_phase2.py::test_report_help_prints`; `test_phase5.py::test_help_text_returns_the_string`, `test_help_still_prints_the_same_text` | Assert that `help()` prints some text containing a few method names. Nothing breaks for a user if the cheat sheet is reworded. | Remove, or keep one smoke test. |
| `test_phase1.py::test_dataset_repr_html`, `test_datamodel_repr_html`; `test_phase2.py::test_report_repr_html_is_iframe` | Pin the notebook display markup. | Remove. **Keep** `test_dataset_repr_html_escapes` and `test_dataset_repr_html_caps_preview`: one is an HTML-injection guard, the other stops a huge frame freezing a notebook. |
| `test_phase2.py` checks of `os.path.getsize(path) > 1000` | "The file isn't tiny" says little. | Replace with an assertion about the content, or remove. |
| `test_docs_site.py::test_regenerating_produces_no_diff` | Forces the generated docs HTML to be committed and rebuilt by hand after every docs edit. | Build the docs site during deploy instead, then remove the committed HTML and this test. |

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

**Recommendation:** remove the test. If size ever becomes a real complaint, add
a line to `tracebi report build` output ("report.html: 862 KB") and let people
decide.

## The rule for new tests

Before adding a test, answer: *what bug would this catch?* If the answer is
"someone changed a colour, a size, or a sentence", don't add it. See
[[pitfalls]] for the bugs that did happen, and the checks that would have
caught them.
