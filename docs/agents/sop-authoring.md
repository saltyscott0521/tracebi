# SOP — Authoring a Report Through the Gateway (Analyst Agent)

Standard operating procedure for an AI analyst agent producing reports over
TraceBi's MCP gateway (`tracebi mcp`). Follow the steps in order. The
governing principle: **you never touch the warehouse — you speak the semantic
contract, every answer you receive is stamped, and every number you show a
human carries its receipt.**

**Where this sits in the three-phase workflow (see `WORKFLOW.md`).** This is
**phase ③ — DASHBOARD**, authoring over the model boundary. You are handed two
freeze points: a warehouse phase ① already sank (`data/warehouse.duckdb`)
and a model phase ② already declared over it (`models/*.py`, e.g.
`models/portfolio_model.py`). You do not re-run the phase-① pandas and you do not
see it — the model is the contract you author against, and everything below is
exactly how `reports/portfolio_dashboard.json` was written. **The trust
machinery in this SOP — stamped queries, validate-before-execute, `verify` —
governs from that model boundary onward. It says nothing about phase ①, which is
unconstrained pandas trusted as reviewed code, not by fingerprint.** If a number
you need is wrong or absent below the model, this SOP cannot fix it; escalate to
the engineer SOP (a model change) or, if the raw data was never sunk, to a
phase-① transform change.

The gateway exposes eight tools:

| Tool | Purpose |
|---|---|
| `get_context` | The semantic contract: full vocabulary, optionally plus one model's schema |
| `list_models` | Models this project exposes, with facts/dimensions/measures |
| `describe_model` | One model's full schema |
| `query_model` | Run a star-schema query; returns rows **plus a stamp** |
| `validate_report_spec` | Check a spec against the models without loading a row |
| `render_report_spec` | Validate, build and render a spec to HTML + manifest |
| `list_reports` | Reports the project already exposes |
| `verify_manifest` | Re-run every recorded query in a rendered manifest and classify each section (`reproduces` / `source_drift` / `model_changed` / `unexplained` / `unverifiable`) — the built-in replay for step 6 at L2/L3 |

Where you stand on the assurance ladder:

| Level | You do | The company can prove |
|---|---|---|
| L0 | Raw SQL, raw HTML | Nothing — **never operate here** |
| L1 | Query via gateway, render your own HTML | Every number traceable |
| L2 | Emit a ReportSpec; TraceBi renders | Artifact reproducible |
| L3 | L2 + signed manifest + re-verification | Attestable (future) |

Default to **L2**. Drop to L1 only when the six section types genuinely
cannot express the presentation — and then step 6 (self-audit) is mandatory,
because at L1 nothing machine-checks your transcription.

---

## Step 1 — Load the contract: `get_context`

Always the first call. Nothing outside what it returns will validate.

```json
{ "tool": "get_context", "arguments": { "model": "wealth_model" } }
```

The response contains, among other keys:

- `report_sections` — every section type (`text`, `table`, `chart`,
  `metrics`, `row`, `spacer`) with fields, defaults and allowed values
  (`chart_type`: `bar`, `barh`, `line`, `area`, `pie`, `scatter`;
  text `style`: `normal`, `heading1`, `heading2`, `note`, `callout`;
  table `style`: `default`, `striped`, `compact`)
- `semantic_model` — aggregations (`sum`, `count`, `mean`, `avg`, `min`,
  `max`, `nunique`), filter operators (`eq`, `ne`, `in`, `not_in`, `gt`,
  `gte`, `lt`, `lte`, `between`, `is_null`, `not_null`, `contains`), filter
  forms, and the measure kinds (`simple`, `expression`, `ratio`)
- `number_formats` — named formats (`currency`, `currency0`, `percent`,
  `comma`, `decimal`)
- `model` (because we passed `model=`) — that model's tables, relationships,
  facts, dimensions, and **named measures**

Use `list_models` first if you do not know which model to ask for;
`describe_model` (`{"model": "wealth_model"}`) re-fetches one schema later
without the full vocabulary.

**Rule: treat the contract as closed.** If a fact, dimension attribute or
measure is not in the response, it does not exist. Do not guess names —
validation will reject them, and inventing vocabulary is the exact failure
mode this gateway exists to prevent.

## Step 2 — Explore with `query_model`, and handle the stamp

Probe the data before deciding what to write. A query names a fact, measures,
and dimension attributes as `dim_name.attribute`:

```json
{
  "tool": "query_model",
  "arguments": {
    "model": "wealth_model",
    "fact": "fact_holdings",
    "measures": ["market_value", "cost_basis", "unrealized_gain", "gain_pct"],
    "dimensions": ["dim_product.asset_class"]
  }
}
```

`measures` accepts either a list of **named measures** the model declares, or
an inline `{column: agg}` dict such as `{"market_value": "sum"}`. `filters`
accepts equality (`{"dim_client.segment": "private"}`), lists meaning IN
(`{"region": ["NE", "SE"]}`), and operator dicts
(`{"market_value": {"gte": 1000}}`).

The response:

```json
{
  "model": "wealth_model",
  "query": {
    "fact": "fact_holdings",
    "measures": ["market_value", "cost_basis", "unrealized_gain", "gain_pct"],
    "dimensions": ["dim_product.asset_class"],
    "filters": {},
    "aggregate": true,
    "allow_fanout": false
  },
  "columns": ["dim_product.asset_class", "market_value", "cost_basis",
              "unrealized_gain", "gain_pct"],
  "row_count": 4,
  "rows": [ { "dim_product.asset_class": "equity", "market_value": 2215129.9, "...": "..." } ],
  "rows_returned": 4,
  "truncated": false,
  "fingerprint": "b3d614c1d264…<sha-256 hex>",
  "lineage": [ { "…": "operation nodes, connector to aggregate" } ],
  "actor": "mcp:agent"
}
```

**Stamp handling — non-negotiable:**

1. **Record `query` and `fingerprint` verbatim** for every query whose
   numbers you might later cite. The recorded pair is your working paper;
   step 6 replays it.
2. **The fingerprint covers the full result; `rows` is transport.** Row
   delivery is capped (`limit`, default 50, hard cap 500) but the SHA-256
   fingerprint always hashes the *uncapped* DataSet. If `truncated` is
   `true`, any number you compute from `rows` alone describes a preview, not
   the result — raise `limit` (≤ 500), narrow the query, or put the table in
   a report spec instead of paging rows through your context.
3. **Never re-derive a stamped number downstream.** If you need a total, ask
   the query for it (or use the section's `totals`); summing displayed rows
   yourself is how the $1 rounding error in
   `examples/agent_gateway/verify_report.py` happened.

## Step 3 — Author the spec

A report spec is JSON: `name` (required), plus optional `sections`, `author`,
`description`, `parameters`. Each data-bearing section (`table`, `chart`)
carries a `data` reference — `{"model": …, "query": …}` — where `query` has
exactly the fields `fact`, `measures`, `dimensions`, `filters`, `aggregate`,
`allow_fanout`. `tracebi spec schema` (or `GET /api/spec/schema`) publishes
the full JSON Schema.

Authoring rules:

- **Named measures beat inline aggs.** `"measures": ["market_value",
  "unrealized_gain"]` uses the model's shared definitions — "unrealized gain"
  means the same thing in every report, and the measure's declared format
  (`currency0`, `percent`, …) flows to the renderer with no formatting code
  in your spec. Fall back to `{column: agg}` only for a concept the model has
  no name for — and treat that as a signal (next rule).
- **A missing concept is an escalation, never a workaround.** A spec cannot
  express arbitrary computation — by design. If the analysis needs a measure,
  dimension attribute, or fact the contract does not declare, **stop and
  escalate to the engineer SOP** (this directory): the fix is a code-reviewed
  change in the definition plane (`models/*.py`, e.g.
  `model.add_measure("unrealized_gain", expr="market_value - cost_basis",
  agg="sum", format="currency0")`), after which a fresh gateway process's next call
  sees the new vocabulary. Do **not** compute the number yourself in a text
  section, do not approximate it with a different aggregation, do not
  transcribe hand-arithmetic into the page. Change the contract in git; use
  the contract over MCP.
- **Set `author`** so the artifact says who made it, e.g.
  `"claude (via mcp gateway)"`.
- Use `text` sections for narrative and a closing provenance note; use
  `column_labels`, `totals`, and `number_formats` on tables rather than
  reformatting data in the query.
- Leave `allow_fanout` false. If a query raises about a non-unique dimension
  key, that is the framework refusing to silently inflate additive measures —
  investigate or escalate; do not flip the flag to make an error go away.

## Step 4 — Validate, repair from the path, repeat

```json
{ "tool": "validate_report_spec", "arguments": { "spec": { "name": "…", "sections": [ "…" ] } } }
```

Returns `{"ok": bool, "errors": [...], "warnings": [...]}`. Every error
carries a path into the spec (top-level parse failures — malformed JSON,
missing `name` — return a plain message without one):

```
sections[1].data.query.fact: 'fact_hallucinated' is not a fact on model 'wealth_model'. Available: ['fact_activities', 'fact_holdings']
```

The loop: read the path, fix exactly that field (many errors include a
did-you-mean hint and the valid set), re-validate. Iterate until `ok` is
`true` **and** you have read every warning — a warning like *"no data
reference — this section cannot be rendered from the spec alone"* means the
section is presentation-only and will not carry a fingerprint. Validation
loads no data, so this loop is free; never skip it and let the renderer be
your first check.

## Step 5 — Render: `render_report_spec`

```json
{ "tool": "render_report_spec", "arguments": { "spec": { "…": "…" }, "output_dir": "output" } }
```

The gateway re-validates and **refuses an invalid spec** — an artifact from a
spec that failed validation is exactly the ungoverned output this surface
exists to prevent. On success:

```json
{
  "ok": true,
  "html_path": "output/book-of-business-review.html",
  "manifest_path": "output/book-of-business-review.manifest.json",
  "report_name": "Book of Business Review",
  "sections": 5,
  "dataset_fingerprints": ["b3d614c1…", "7d5f1ad1…", "3b6a4e88…"],
  "warnings": []
}
```

The manifest is the receipt: for every data-bearing section it records
`dataset_fingerprint`, `dataset_lineage` (connector → aggregate),
`dataset_name` and `dataset_shape`, plus the repo `git_sha` at render time.
Confirm that each fingerprint in `dataset_fingerprints` matches the
fingerprint of your corresponding step-2 exploratory query. A match proves
the rendered artifact contains the same data you analyzed — same hash,
provably the same data. A mismatch means the data moved between exploration
and render: re-run your exploratory queries and reconcile before publishing.

## Step 6 — Self-audit: replay the receipts

Before presenting anything, audit your own output. The pattern is
`examples/agent_gateway/verify_report.py`, which caught a real $1 error in a
page whose fingerprints all matched. Two independent checks, both required:

1. **Fingerprints** — re-run every recorded query through `query_model` and
   compare the returned `fingerprint` against the one you recorded (and, for
   L2, against the manifest's `dataset_fingerprint`). Match ⇒ the data has
   not drifted since authorship.
2. **Figures** — for every number displayed to the human, recompute it from
   the fresh query result and compare to what the artifact shows. Match ⇒
   you transcribed faithfully.

These catch different failure modes: a fingerprint match with a figure
mismatch localizes the fault to *your transcription* (the verify script's
first run: page said `+$523,045` — sum of rounded rows; truth was
`$523,044.32` — round-then-sum vs sum-then-round, invisible to any human
eye). A fingerprint mismatch means *source drift*, and every figure must be
re-derived. Encode the discipline the script encodes: round the true total,
never sum the rounded rows.

At L2, `verify_manifest` is the built-in that runs check 1 for you: point it at
the manifest `render_report_spec` just produced and read the per-section
`verdict`, not just `ok` — only `reproduces` means a number was re-run and
matched. TraceBi rendered the figures from the same query the manifest
fingerprints, so check 2 reduces to any numbers you quote in surrounding
narrative. At L1 — a page you wrote yourself — there is no manifest for
`verify_manifest` to read, so check every figure on the page with your own
replay script (`examples/agent_gateway/verify_report.py` is the template) and
keep it beside the artifact so anyone can re-run it.

## Step 7 — Presenting numbers to humans

**Never state a number without its citation.** Every figure you put in front
of a person traces to a stamped query; say so:

> Total book AUM is **$7,521,674** (query fingerprint `b3d614c1d264`,
> `fact_holdings` by `dim_product.asset_class`, wealth_model).

Conventions:

- Cite the fingerprint git-style — the first 12 hex characters are enough for
  a human page; keep the full hash in your working papers and the manifest.
- In an L1 page, include a "Working Papers" section listing each query
  (model, fact, measures, dimensions, filters) with its fingerprint, so an
  auditor can replay it without you.
- For an L2 artifact, point at the manifest: it already carries the exact
  query, lineage chain, and fingerprint per section.
- If a stakeholder asks "where does this number come from?", the answer is
  never prose — it is the recorded query and its fingerprint, re-runnable
  today.

---

## Worked minimal example (wealth_model)

The smallest complete pass through steps 1–7. The demo data is seeded, so
these queries reproduce.

**1. Contract.** `get_context` with `{"model": "wealth_model"}` →
`fact_holdings` (measure columns `units`, `market_value`, `cost_basis`), four
dimensions (`dim_client`, `dim_branch`, `dim_product`, `dim_account`), and
four named measures: `market_value`, `cost_basis`, `unrealized_gain`,
`gain_pct`.

**2. Explore.** One stamped query, shown above in step 2 — AUM, basis, gain
and gain% by asset class. Record: fingerprint `b3d614c1d264…`, `row_count`
4, `truncated` false. (Had we needed `unrealized_gain` and the model not
declared it, this is where we would have escalated to the engineer SOP
rather than computing `market_value - cost_basis` ourselves.)

**3–4. Author and validate.** A two-section spec using only named measures:

```json
{
  "name": "Asset Class Snapshot",
  "author": "analyst-agent (via mcp gateway)",
  "description": "AUM and unrealized gains by asset class, from the model's shared measure definitions.",
  "sections": [
    {
      "type": "table",
      "title": "AUM and gains by asset class",
      "column_labels": {
        "dim_product.asset_class": "Asset class",
        "market_value": "Market value",
        "cost_basis": "Cost basis",
        "unrealized_gain": "Unrealized gain",
        "gain_pct": "Gain %"
      },
      "totals": ["market_value", "cost_basis", "unrealized_gain"],
      "data": {
        "model": "wealth_model",
        "query": {
          "fact": "fact_holdings",
          "measures": ["market_value", "cost_basis", "unrealized_gain", "gain_pct"],
          "dimensions": ["dim_product.asset_class"]
        }
      }
    },
    {
      "type": "text",
      "title": "Provenance",
      "style": "note",
      "content": "Rendered from a validated report spec. The manifest beside this artifact records the exact query, full lineage, and a SHA-256 fingerprint for the table above."
    }
  ]
}
```

`validate_report_spec` → `{"ok": true, "errors": [], "warnings": []}`. (A
typo such as `"fact": "fact_holding"` would instead return
`sections[0].data.query.fact: 'fact_holding' is not a fact on model
'wealth_model'` — fix the pathed field and re-validate.)

**5. Render.** `render_report_spec` → `ok: true`,
`html_path: "output/asset-class-snapshot.html"`,
`manifest_path: "output/asset-class-snapshot.manifest.json"`, and
`dataset_fingerprints` containing one hash — which must equal the step-2
fingerprint `b3d614c1d264…`. It does: same hash, same data.

**6. Audit.** Re-run the recorded query; assert the fingerprint still starts
`b3d614c1d264` and that the totals you plan to quote equal the fresh sums
(round the true total — `round(sum(unrealized_gain rows))`, never the sum of
rounded rows).

**7. Present.**

> Unrealized gains across the book stand at **+$523,044** on
> **$6,998,630** of cost basis — a 7.5% return on basis
> (fingerprint `b3d614c1d264`, `fact_holdings` by asset class, wealth_model;
> manifest: `output/asset-class-snapshot.manifest.json`).

---

## Failure handling, in one place

| Situation | Action |
|---|---|
| Vocabulary you need is absent from `get_context` | Escalate to the engineer SOP. Never invent, approximate, or hand-compute. |
| `validate_report_spec` returns errors | Repair the exact pathed field; re-validate until `ok`. |
| `render_report_spec` returns `ok: false` | It refused an invalid spec — return to step 4; never route around the renderer. |
| Query raises on dimension fan-out | Investigate the join grain or escalate; do not set `allow_fanout: true` to silence it. |
| `truncated: true` on a query you need fully | Raise `limit` (≤ 500), narrow the query, or move the table into a spec. |
| Fingerprint mismatch on audit | Source drift: re-run every recorded query and re-derive every figure before publishing. |
| Figure mismatch with matching fingerprint | Your transcription is wrong: fix the artifact, re-run the audit to green. |
