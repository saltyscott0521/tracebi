# AGENTS.md — Working with TraceBi as an AI Agent

Read this before touching a TraceBi project. Deeper references: `WORKFLOW.md`
(the three-phase workflow, end to end), `CLAUDE.md` (codebase rules), `NOTES.md`
(design decisions), `examples/agent_gateway/` (a complete recorded agent
session).

## What TraceBi is

TraceBi is a code-first BI framework built around a **three-phase workflow**
that carries data from messy to reportable. Each phase is a project-root folder
with its own cadence, decoupled from the next by a **freeze point** — a
materialized artifact handed across the boundary:

| Phase | Folder | You write | Freeze it hands on |
|---|---|---|---|
| ① **Manipulate** | `transforms/` | ordinary, unconstrained pandas — pull queries, clean, parse, key, dedupe, then **sink** clean star-schema tables | `workflow_data/warehouse.duckdb` (materialized tables) |
| ② **Model** | `models/` | a declarative `DataModel` over the warehouse — grain, keys, measures, in a few dozen lines a reviewer reads without opening the pandas above it | the model (the semantic contract) |
| ③ **Dashboard** | `dashboards/` | a `ReportSpec` (JSON) pointed at the model — KPI cards, charts, tables, every figure a live query | the rendered page + its lineage manifest |

Reference implementation, end to end: `transforms/holdings_transform.py` →
`models/portfolio_model.py` → `dashboards/portfolio_dashboard.json`, wired by
`run_workflow.py`. `WORKFLOW.md` is the full tour; read it first.

The split earns its keep at the freeze points: the slow, unconstrained analysis
(①) and the fast, iterated reporting (③) never block each other, because the
model (②) is a frozen contract between them. Editing the dashboard never re-runs
the pandas. As an agent (or analyst) you author each phase in turn: write the
phase-① transform, declare the phase-② model, author the phase-③ dashboard spec.

## Where the trust machinery applies — and where it does not

TraceBi is also a **trust layer for AI-generated analytics**: AI made producing
reports nearly free; believing them is the expensive part. But be exact about
the boundary. **The trust machinery governs from the model boundary onward — it
covers phases ② and ③, not ①.**

- **Phase ① (`transforms/`) is unconstrained and unverified by design.** It is
  ordinary pandas that writes the warehouse. The framework draws the line at the
  **sink**, where the numbers become a contract you can report against. Lineage
  is *not* traced through the raw analysis, and nothing machine-checks that the
  transform's numbers are right. Phase ① is trusted the way reviewed code is
  trusted — in git — not the way a fingerprint is trusted.
- **From the model boundary onward, every answer is stamped.** Agents never
  touch the warehouse over the gateway: they speak the semantic contract
  (facts, dimensions, named measures), and every result comes back with its
  resolved query, full lineage chain, and a SHA-256 fingerprint of the complete
  result. Dashboards are declarative specs that validate *before* execution and
  render to artifacts with a lineage manifest. `tracebi verify` re-runs a
  manifest's recorded queries and compares fingerprints — it does **not** read a
  transform and does **not** assert that a number is correct; it proves the
  reported figures still match the warehouse they were drawn from.

So any number a dashboard puts in front of a person is traceable back to the
query that produced it and re-runnable against the sink. What produced the sink
is phase ① — believed the way you believe reviewed code, not the way you believe
a hash.

## The two planes rule

**Change the contract in git. Use the contract over MCP.**

- **Definition plane** (git): `transforms/*.py`, `models/*.py`,
  `dashboards/*.json` (and `pipelines/*.py`, `reports/*`). Every phase is
  authored and code-reviewed here. Missing a measure? The fix is a code-reviewed
  edit to the model file (e.g. `model.add_measure(...)` in
  `models/portfolio_model.py`) — never a workaround in the dashboard layer.
  Missing a *column the measure needs*? That is a phase-① change: sink it in the
  transform. A fresh gateway process sees new vocabulary on its next call (stdio
  one-shot clients get this for free; a long-running server must be restarted —
  Python module caching keeps the old model loaded).
- **Access plane** (MCP): read-and-compute only, and only from the model
  boundary onward. Queries, validation, and spec rendering persist nothing
  beyond an output file. Phase ① never runs over the gateway — it writes the
  warehouse, and the gateway has no write surface, on purpose. Pipeline
  execution (the older warehouse-writing path) is likewise absent from this
  surface.

## Assurance ladder

These levels grade how you author the reporting side (phase ③) once the model is
frozen; they say nothing about phase ①, which the ladder does not reach.

| Level | Agent does | Requires today |
|---|---|---|
| L0 | Raw SQL, raw HTML | Nothing — and proves nothing. Avoid. |
| L1 | Queries via gateway, renders its own HTML | Every number from `query_model`; cite its fingerprint alongside the figure |
| L2 | Emits a ReportSpec; TraceBi renders | Spec passes `validate_report_spec`; artifact + manifest come from `render_report_spec` |
| L3 | L2 + signed manifest + re-verification | Re-verification exists (`verify_manifest` / `tracebi verify`, drift-aware via input fingerprints recorded at render); **signing not yet built** |

Prefer L2. Use L1 when you need presentation freedom the spec grammar lacks —
governed data, ungoverned presentation.

## The gateway

Start it with `tracebi mcp` (stdio, local agent) or
`tracebi mcp --transport http --port 8765` (remote). Needs
`pip install 'tracebi[mcp]'`. Register with Claude Code:
`claude mcp add tracebi -- tracebi mcp`. Work is attributed as
`mcp:<TRACEBI_MCP_ACTOR>` (default `mcp:agent`).
The http transport requires `TRACEBI_MCP_TOKEN` (send
`Authorization: Bearer <token>`) — it refuses to start without it unless
`--insecure` is passed explicitly.

Eight tools (`tracebi/mcp_server.py`):

| Tool | Purpose |
|---|---|
| `get_context` | Full vocabulary: section/chart types, DataSet verbs, measure kinds, filter operators; `model=<name>` adds that model's schema. **Call first.** |
| `list_models` | Project models with tables, facts, dimensions, measures |
| `describe_model` | One model's full schema |
| `query_model` | Star-schema query → stamped result. `measures` is `{column: agg}` (`sum, count, mean, min, max, nunique`); dimensions are `dim_name.attribute`; filters take equality, lists (IN), or operator dicts (`gte`, `between`, `contains`, …) |
| `validate_report_spec` | Check a spec against the models without loading a row; errors carry a path like `sections[0].data.query.fact` — repair and retry |
| `render_report_spec` | Validate, build, render to self-contained HTML + lineage manifest; **refuses invalid specs** |
| `list_reports` | Per-file discovery status (note: a bare `tracebi mcp` process has not run web discovery, so this may be empty — models and queries are unaffected) |
| `verify_manifest` | Re-run every recorded query in a rendered manifest and classify: `reproduces` / `source_drift` / `model_changed` / `unexplained` / `unverifiable`. Read the receipt-level `verdict`, not just `ok`: only `reproduces` means a number was re-run and matched — and it names any sections it could not check, so read `verdict_detail` too. `nothing_to_verify` (no data-bearing section — a broken receipt) and `refused_newer_schema` (written by a newer tracebi; not read at all) are not ok; `unverifiable` (every section hand-transformed) is ok but proves nothing |

### The canonical loop

1. **Discover** — `get_context`, then `list_models` / `describe_model`.
2. **Explore** — `query_model` to probe the data before deciding what to write.
3. **Author** — write a ReportSpec using only vocabulary the gateway showed you.
4. **Validate** — `validate_report_spec`; fix pathed errors until clean.
5. **Render** — `render_report_spec`; keep the manifest with the HTML.
6. **Verify** — `verify_manifest` on the manifest you just produced; any
   verdict but `reproduces` needs explaining before a human sees the number —
   including the two that check nothing at all (`nothing_to_verify`,
   `unverifiable`), which is why `ok` alone is not the question to ask.
7. **Cite** — every number you quote anywhere carries its fingerprint.

Rows are transport; the stamp is the truth. `query_model` caps rows (default
50, hard cap 500) but fingerprints the *uncapped* result, so a figure beyond
the cap is still verifiable: re-run the recorded query, compare fingerprints.

CLI equivalents (no MCP needed): `tracebi context [--model NAME]`,
`tracebi spec schema`, `tracebi spec validate report.json`,
`tracebi spec render report.json`, `tracebi verify out.manifest.json`.

## Audit your own transcription

At L1 you transcribe numbers into your own page, and nothing machine-checks
the transcription — so write and run a verifier that re-runs the recorded
queries, compares fingerprints, and checks every displayed figure
(`examples/agent_gateway/verify_report.py` is the template).

The cautionary tale: the gateway's first agent session produced a page whose
fingerprints all matched yet whose total read `+$523,045` when the truth was
`$523,044.32` — it had summed rounded per-row gains instead of rounding the
sum. The matching fingerprints proved the data hadn't drifted, localizing the
fault to transcription instantly; no human eye would have caught one dollar in
seven and a half million.

## Never

- **Never invent vocabulary.** Only facts, dimensions, measures, section
  types, and operators returned by `get_context` / `describe_model` exist.
  Nothing outside the contract will validate.
- **Never render or ship an unvalidated spec.** `render_report_spec` refuses
  invalid specs by design; do not route around it with hand-built artifacts
  pretending to be governed.
- **Never quote a number without its fingerprint.** An uncited figure is
  exactly the untraceable output this system exists to prevent.
- **Never mutate models, measures, or pipelines at runtime.** Contract
  changes belong in `models/*.py` (and friends) through git — the definition
  plane. The gateway has no write surface, on purpose.
- **Never page raw rows to dodge the cap.** More than 500 rows means you are
  building a table; do it through a report spec.
