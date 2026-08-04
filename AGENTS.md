# AGENTS.md — Working with TraceBi as an AI Agent

Read this before touching a TraceBi project. Deeper references: `CLAUDE.md`
(codebase rules), `NOTES.md` (design decisions), `examples/agent_gateway/`
(a complete recorded agent session).

## What TraceBi is

TraceBi is a **trust layer for AI-generated analytics**. AI made producing
reports nearly free; believing them is the expensive part. So agents never
touch the warehouse: they speak a semantic contract (models, facts,
dimensions, named measures) through a gateway, and every answer comes back
**stamped** — the resolved query, the full lineage chain, and a SHA-256
fingerprint of the complete result. Reports are authored as declarative specs
that validate *before* execution and render to artifacts with a lineage
manifest. Any number an agent puts in front of a person is traceable back to
exactly which query produced it.

## The two planes rule

**Change the contract in git. Use the contract over MCP.**

- **Definition plane** (git): `models/*.py`, `pipelines/*.py`, `reports/*`.
  Missing a measure? The fix is a code-reviewed edit to the model file
  (e.g. `model.add_measure(...)` in `models/wealth_model.py`) — never a
  workaround in the report layer. A fresh gateway process sees the new
  vocabulary on its next call (stdio one-shot clients get this for free; a
  long-running server must be restarted — Python module caching keeps the
  old model loaded).
- **Access plane** (MCP): read-and-compute only. Queries, validation, and
  spec rendering persist nothing beyond an output file. Pipeline execution
  writes to the warehouse and is deliberately absent from this surface.

## Assurance ladder

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
| `verify_manifest` | Re-run every recorded query in a rendered manifest and classify: `reproduces` / `source_drift` / `model_changed` / `unexplained` / `unverifiable`. Anything but reproduces is not an ok receipt |

### The canonical loop

1. **Discover** — `get_context`, then `list_models` / `describe_model`.
2. **Explore** — `query_model` to probe the data before deciding what to write.
3. **Author** — write a ReportSpec using only vocabulary the gateway showed you.
4. **Validate** — `validate_report_spec`; fix pathed errors until clean.
5. **Render** — `render_report_spec`; keep the manifest with the HTML.
6. **Verify** — `verify_manifest` on the manifest you just produced; anything
   but REPRODUCES needs explaining before a human sees the number.
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
