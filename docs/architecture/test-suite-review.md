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

## The cull, 2026-10-18

The suite took about six minutes (5 min 54 s here; about seven on a
slower machine) and held 1,668 unit cases beside 232 journey cases. Most of the unit cases re-checked what a journey already drives,
or checked a private field, a printout or a sentence. The decision was a hard
cull: keep every journey, keep the unit tests in six categories, and delete the
rest.

**The rule.** Keep, whole: `tests/e2e/**`, `test_ui_smoke.py`, and unit tests
in six categories:

1. DataModel query semantics: the calculator (`test_phase2.py`,
   `test_phase25.py`, `test_measure_filters.py`, `test_binding_grammar.py`,
   `test_sql_calc.py`, and the calculator part of `test_knowledge.py`).
2. Number-format parity, SSR = JS (`test_presentation_js.py`,
   `test_engine_float_parity.py`, the scenario evaluator).
3. Verify and fingerprints (`test_verify.py`, `test_verify_v2.py`,
   `test_parquet_embed.py`, the fingerprint and `verify --file` tests).
4. Sink contracts (`test_contracts.py`).
5. Security: auth, roles, folder permissions, OAuth, CSRF, CSP, path guards,
   escaping, secrets kept out of output.
6. The honesty rules (`test_agent_guides.py`, `test_receipt_monotonicity.py`,
   "never green by itself", unverified and `verifiable: false` marks, the
   locked sentences, the typed-number refusal, exploration stripped at build).

A test outside the six went when a journey exercises its failure mode, or when
it checked a private field, "it didn't raise" or "the string appears". After
the cut, the coverage comparison below decided what came back: where a module
lost more than 10 points, or a security, verify, query or format module lost any
line, one unit test was restored, or the lost lines are named below as not
product behaviour.

### Per file

"Trimmed" keeps the named tests; everything else in the file went.

| File | Before → after | Decision |
| --- | --- | --- |
| `e2e/*` (19 journeys), `test_ui_smoke.py` | 232 → 232 | Kept whole. |
| `test_phase2.py`, `test_phase25.py`, `test_measure_filters.py`, `test_binding_grammar.py`, `test_sql_calc.py` | kept | Query semantics (1); the binding-grammar corpus also pins fingerprints (3). |
| `test_presentation_js.py`, `test_engine_float_parity.py` | kept | Format parity (2). |
| `test_verify.py`, `test_verify_v2.py`, `test_contracts.py` | kept | Verify (3), contracts (4). |
| `test_permissions.py`, `test_csrf.py`, `test_mcp_auth.py`, `test_drafts.py`, `test_ui_sandbox.py` | kept | Security (5). `test_drafts.py` is the drafts' security edges; the happy path is the web journey. |
| `test_agent_guides.py`, `test_receipt_monotonicity.py`, `test_custom_script_integrity.py` | kept | Honesty (6). |
| `test_docs_site.py` | kept | The only check that the committed site matches `docs/`. |
| `test_table_window.py`, `test_ui_build_mode.py` | kept | The only cover of table windowing; Build mode in a browser (gated, costs the default run nothing). |
| `test_knowledge.py` | 86 → 74 | Trimmed. Most of this file is the calculator (rate guards, median, percentiles, shares, rank, time grain, bins, period-end, OR filters, period-over-period, to-date), not lesson files: kept as (1). The 12 lesson-file and "documented in the vocabulary" tests went; `test_agent_guides.py` holds the vocabulary to the guides. |
| `test_parquet_embed.py` | 49 → 47 | Trimmed. Kept the fingerprint and verify tests (3) and the bounded decode (5); the two "which transport, how small" tests went. |
| `test_phase1.py` | 80 → 23 | Trimmed to DataSet fingerprints (3), repr escaping (5), Decimal writes landing exact (a wrong number), and, restored by coverage, the DataSet lineage and immutability tests, `DataModel.resolve`, and two DuckDB reader/writer tests. Connector and verb demos went. |
| `test_phase4.py` | 41 → 8 | Trimmed to audit attribution (actor never leaks; old databases gain the columns) and, restored by coverage, a Gold layer write, the per-layer run lock, schema persistence, per-dialect DDL and the advisory key. The pipeline journey covers the runner. |
| `test_phase5.py` | 187 → 73 | Trimmed to Basic/proxy auth, authorization and role-header trust (5), identifier quoting and SQL push-down (5, 1), star-schema query results (1), `verify --file` over the API and web/CLI parity (3), traceback hidden by default, docs path traversal, the one-renderer refusal, the enum/vocabulary match and the cheat-sheet kwargs, and the `TestPipelineRunEndpoint` isolation test that CLAUDE.md names. Restored by coverage: notebook source extraction, dev reload, docs guide, lineage join edges, concurrent registration, structured render error. `TestHomepageNeverSilently404s` went, and with it the ~120 MB `mkdtemp` copy of `tracebi/` it leaked per run; the slim-install and wheel tests went because CI's `base-install` and `wheel` jobs check the same things for real. |
| `test_report_generator.py` | 78 → 27 | Trimmed to the embed injection guard, fingerprints, `verify --file` verdicts, the typed-number gate, CSP, escape-hatch honesty (`verifiable: false`, never green), loopback preview and srcdoc escaping; restored by coverage: fragment wrapping and the missing-`</head>` refusal. |
| `test_artifact.py` | 36 → 17 | Trimmed to the figure parser `verify --file` shares (unverified marks, hostile markup fails loudly), the exploration strip, the methodology "states" language and escaping, and the footer's locked sentence; restored by coverage: id assignment, an unknown stage and an unclosed methodology container refused. |
| `test_presentation.py` | 28 → 10 | Trimmed to CSP and self-containment, provenance in the manifest without badges, the receipt's fingerprints, SSR never altering embedded data, and declared formats. Layer order went (not one of the six). |
| `test_selection.py` | 32 → 12 | Trimmed to the conjoined fingerprint, `connect-src` CSP, and the offline port matching the model; restored by coverage: keeping a cut, the selection endpoint's fingerprint, a longer value beating its prefix, a new grain that reproduces. |
| `test_mcp_gateway.py` | 45 → 9 | Trimmed to stamp re-verification, fingerprints unchanged by preview caps and tie-breaks, the path and output guards; restored by coverage: the schema-checking client and the XLSX build. The agent journey covers the rest. |
| `test_schedule.py` | 72 → 5 | Trimmed to the verdict gate: a schedule cannot force a bad receipt, a refused receipt is not uploaded; restored by coverage: an owner alert, per-value burst recipients, firing in the declared time zone. The schedule journey covers the rest. |
| `test_workbench.py` | 49 → 7 | Trimmed to markdown/frame escaping, CSPs, DNS-rebinding refusal, a session export that verify refuses; restored: the markdown export. The author and web journeys cover the workbench. |
| `test_compile_spec.py` | 36 → 7 | Trimmed to markdown/link escaping, the honestly unverified literal metric, the compiled package as a verify superset; restored: every section type compiles, the totals row. |
| `test_manifest_lineage.py` | 27 → 4 | Trimmed to: every rendered figure is fingerprinted, every dataset reaches the manifest, no unauditable artifact on failure, verify classifies from the last query node. |
| `test_report_folders.py` | 19 → 13 | Trimmed to names that cannot leave `reports/`, every read through `open_report`, mount label parsing; restored: two mounts each holding `weekly`. |
| `test_scenario.py` | 25 → 15 | Trimmed to the runtime evaluating like Python (2) and unsafe or bad formulas refused (5). |
| `test_model_spec.py` | 17 → 10 | Trimmed to the security refusals: credentials, a database outside the project, repeated keys, object tags. |
| `test_journey_fixes.py` | 13 → 5 | Trimmed to the dependency-confusion guards (kept by the 2026-09-22 review) and two real-bug pins: a commitless repo records `unknown`, and `.gitignore` really keeps manifests. |
| `test_warehouse_connectors.py` | 17 → 8 | Trimmed to identifier injection, parameterised filters and credentials kept out of `describe()`; restored: Snowflake push-down, BigQuery's unsupported filter type and missing driver. |
| `test_init_scaffold.py` | 12 → 4 | Trimmed to the MCP config never printing a token, `report send` refusing a failing verify, STARTTLS verification and no cleartext credentials. The analyst and author journeys run the scaffold. |
| `test_api_status.py` | 8 → 4 | Trimmed to the three "never echoes a secret" tests; restored: the route's checks. |
| `test_gateway_log.py` | 7 → 5 | Trimmed to argument names never values, masking, off by default; restored: the `agent log` summary. |
| `test_connect.py` | 13 → 3 | Trimmed to the secret never reaching stdout or the module; restored: a failing test writes nothing, an existing `.env` key is not overwritten. |
| `test_d3_charts.py` | 13 → 10 | Trimmed to tooltip, click → filter, legend toggle, arrow keys, brush, value labels, currency ticks, tooltip → receipt. Every-type, small-multiples and sparkline geometry went. The stacked-bars test stays because the brush test silently depends on it (see below). |
| `test_validate_gaps.py` | 22 → 3 | Restored by coverage: three pathed filter errors in `check_query_spec`. The agent journey covers validate wrong-then-right. |
| `test_live_discovery.py` | 8 → 2 | Restored by coverage: a deleted package is forgotten, a broken one retried only when it changes. |
| `test_desk.py` | 3 → 2 | Restored by coverage: the review desk lists and its endpoint. |
| `test_import_dbt.py` | 10 → 1 | Restored by coverage: the draft from a manifest. |
| `test_state_store.py` | 10 → 2 | Trimmed to an upgrade keeping history; restored: the legacy schedule-log import is idempotent. |
| `test_engine_assets.py` | 6 → 2 | Trimmed to the CSP granting WASM but never JS eval; restored: the engine ships only with Parquet. |
| `test_delivery.py` | 6 → 2 | Trimmed to the manifest's numbers beating the page's, and a Slack error without the token. |
| `test_pdf.py` | 4 → 2 | Trimmed to a script never reaching the network while printing (5); restored: printing a built chart package. |
| `test_runlog.py` | 5 → 2 | Trimmed to one thread's output never in another's capture, and a capped log. |
| `test_updates.py` | 12 → 2 | Trimmed to "off means no request"; restored: the update instructions per install kind. |
| `test_report_source.py` | 5 → 1 | Trimmed to a theme that cannot point outside `reports/`. |
| `test_react_app.py` | 6 → 1 | Trimmed to the dark-ground cascade (DS-8). The author journey builds and verifies an `app.jsx` report. |
| `test_agent_eval.py`, `test_chart_grouping.py`, `test_collect_changes.py`, `test_design_warnings.py`, `test_init_template.py`, `test_library_list.py`, `test_model_pipeline_scope.py`, `test_resolve_pin.py`, `test_spec_render.py`, `test_warehouse_tables.py` | → 0 | Deleted. The agent-eval scorer and changelog script are tooling; chart grouping is the legacy SVG renderer; design warnings, library columns and warehouse table listings are not among the six; templates (author journey), pin resolve (author journey), spec render (agent journey) and the pipeline scope stamp (web journey) are journey-covered. |

### Coverage

Measured with `pytest-cov`, line coverage of `tracebi/`:

| Run | Covered lines | Coverage |
| --- | --- | --- |
| The suite before the cull | 18,729 / 21,362 | 87.7% |
| The journeys alone (`tests/e2e`, `test_ui_smoke.py`) | 14,641 / 21,362 | 68.5% |
| The suite after the cull | 17,735 / 21,362 | 83.0% |

Modules still more than 10 points down after the restorations, and every line
lost in a security, verify, query or format module, with why the remainder is
not restored:

| Module | Before → after | Why it stays |
| --- | --- | --- |
| `_updates.py` | 90.6 → 60.2 | The release-check cache and its fallback key. One request when on, none when off; both are tested. |
| `web/register.py`, `registry.py` | 59.2 → 40.8, 96.9 → 80.8 | The `@register.scheduled` decorator and default-model helpers: the deprecated scheduled lane (CLAUDE.md, `TRACEBI_SCHEDULED_DIR`). |
| `connectors/memory_connector.py` | 100 → 81.8 | `write` and `add_table` replace a dict entry. |
| `schedule.py` | 93.1 → 75.0 | Slack upload branches, alert retries and the in-server scheduler's start and log lines. The verdict gate, burst recipients, owner alert and time zone are tested; the schedule and state-workers journeys run the rest. |
| `pipeline/runner.py` | 92.6 → 80.5 | `lineage()` and `status()` print to the terminal: notebook helpers, as the 2026-09-28 review already decided. |
| `reports/compile_spec.py` | 89.4 → 77.3 | Markdown subset branches (lists, emphasis) and the totals-under-a-limit warning. The escaping tests and the compiled-package verify stay. |
| `connectors/snowflake_connector.py` | 98.0 → 86.3 | `connect()` forwarding constructor arguments to a fake driver. |
| `cli.py` | 80.1 → 68.6 | Argument handling and printing for `migrate`, `session`, `new-model`, `update`, `list-pipelines`. What they call is tested; the journeys run `init`, `report build`, `verify`, `run-pipeline`, `schedule`, `dev`, `push`, `login`. |
| `web/api/routers/docs.py`, `status.py` | 94.3 → 82.9, 100 → 88.9 | The docs-dir resolution fallback and two status probes flipping. |
| `dbt_import.py` | 88.7 → 77.8 | The command wrapper's refusals (missing manifest, existing file). |
| `web/api/routers/reports.py` | 85.6 → 75.4 | The PDF route over the last build, stored-build listing and the selection route's error paths. PDF printing itself is tested from the CLI. |
| `model/dataset.py` | 91.6 → 82.8 | `cast`, `select` and column-check helpers, and `_repr_html_`. Lineage, immutability, join, aggregate and assign stay tested. |
| `connectors/bigquery_connector.py` | 98.1 → 94.3 | A `SELECT` source filtered in pandas. Quoting and parameterisation stay tested. |
| `reports/figures.py` | 97.8 → 95.2 | Seven `raise FigureError` lines: void-element and self-closing misuse of `data-tb-stage` / `data-tb-methodology`. The parser's other refusals are tested. |
| `report_paths.py` | 97.2 → 95.8 | The one-time notice that `TRACEBI_REPORTS_DIR` is ignored under mounts. |
| `model/model_spec.py` | 81.0 → 79.7 | The name-must-equal-the-file-stem refusal. |
| `model/data_model.py` | 90.9 → 90.0 | Thirteen lines of `check_query_spec`'s warnings (undeclared columns with a hint) and two `load` / `add_table` refusals. Query results lose no line. |
| `drafts.py` | 88.9 → 88.7 | The MCP listing's copy of the Python-model refusal that `start_draft` makes (tested). |

No line was lost in `web/api/auth.py`, `sso.py`, `mcp_oauth.py`,
`permissions.py`, `verify.py`, `contracts.py` or the format code.

### Count and runtime

1,900 collected cases → 1,180 (948 unit + 232 journey). The full run without
coverage went from 5 min 54 s to 4 min 18 s on the same machine.

The target was under three minutes, and the cull cannot reach it: the
journeys alone take 2 min 44 s (measured under coverage), and three kept
files cost about another 85 s by
themselves: the PDF network refusal waits out a 30-second print timeout
(security), the Parquet fingerprint corpus takes 38 s (verify) and the
format-parity browser tests 18 s (format parity). Getting under three minutes
needs a faster journey harness or a separate slow lane, not more deletion.

**A hidden order dependency.** `test_d3_charts.py` shares one browser page
across the module. `test_drag_zooms_to_a_range_and_reset_returns` passes only
after `test_stacked_bars_share_one_slot_and_end_where_their_rows_end` has run;
alone, the brush drag times out. The stacked test stays so the brush test keeps
passing; the dependency itself is a test bug worth fixing on its own.
