# SOP: Author a report through the gateway

The procedure an AI analyst agent follows to produce a report over TraceBi's
MCP gateway (`tracebi mcp`). Follow the steps in order.

Read `AGENTS.md` first. It is the brief every agent reads before working in a
TraceBi project (`tracebi init` writes one into each). This SOP is one job
from it.

## Before you begin

- **You work at the report stage.** A transform has already written the
  warehouse (`data/warehouse.duckdb` by default), and a model is declared over
  it (`models/<name>.yaml`, such as `models/portfolio_model.yaml`). You don't
  run or see the transform; the model is what you author against. The reports
  in `reports/portfolio_model/` were written this way. See
  [[the-three-phase-workflow]].
- **You never touch the warehouse.** You use the model's names, every answer
  you get is stamped, and every number you show a person carries its trace.
- **The checks cover the model onward.** Stamped queries, validation and
  `verify` say nothing about the transform, which is reviewed as code. If a
  number is wrong or missing below the model, this SOP cannot fix it: escalate
  to a model change ([[sop-model-changes]]), or to a transform change if the
  data was never written.
- **No model yet?** When the data sits in a connection and nothing has been
  sunk or modelled, start with step 0 below, then come back to step 1.

### The tools

The gateway has twenty-eight tools and three prompts (`author_report`,
`answer_question`, `address_pins`) that run this procedure for you. The MCP
`tools/list` call is the source of truth if this table drifts. This SOP walks
the spec path. A report package is the same loop with `build_report`. Over a
hosted connection, the draft tools are how a package reaches the server
([[push-from-a-laptop]], [[connect-chatgpt-and-claude]]).

| Tool | Purpose |
|---|---|
| `get_context` | The full vocabulary, optionally with one model's schema. Pass `brief` for the smaller version. |
| `list_models` | The project's models, with facts, dimensions and measures |
| `describe_model` | One model's full schema |
| `describe_table` | Columns and types of a raw warehouse table, before a model exists |
| `query_model` | Run a star-schema query; returns rows and a stamp |
| `validate_report_spec` | Check a spec against the models without loading a row; also returns `design` warnings |
| `render_report_spec` | Validate, build and render a spec to HTML and a manifest |
| `build_report` | Build a report package under `reports/` to one HTML file and a manifest |
| `fetch_artifact` | Read back a built HTML or manifest, so a remote agent can deliver it |
| `list_reports` | Reports the project already has |
| `workbench_state` | What the `tracebi dev` workbench shows, including a reviewer's pins |
| `resolve_pin` | Mark a reviewer's pin as addressed, with a note |
| `verify_manifest` | Re-run every recorded query in a manifest and classify each figure (`reproduces`, `source_drift`, `model_changed`, `unexplained`, `unverifiable`) |
| `list_drafts` · `start_draft` · `read_draft` · `write_draft_file` | Your drafts on the server: start one (empty, or a copy of a published report or model), read it, write one allowed file |
| `preview_draft` | Validate and render a draft in memory; returns errors, warnings and its address in the app |
| `model_impact` | For a model draft: each published report that reads the model, unchanged, moves or breaks |
| `publish_draft` | Publish a draft, or open a publish request where the folder asks for one |
| `list_publish_requests` · `decide_publish_request` | Requests into folders where you hold Publish; approve or reject one |
| `describe_project` | The project as a graph: every source, transform, table, model and report, what feeds what, and what you may read |
| `list_connections` | The project's connections, each with the tables a person allowed agents to read |
| `list_source_tables` | One connection's allowed tables, with columns and row estimates |
| `describe_source_table` | One allowed table's columns, profile and a sample of rows (`sample`, at most 500) |
| `propose_transform` | Store `transforms/<name>.sql` and its `.contract.yaml` as a code request; an admin approves it and it runs once |
| `export_table` | Admin: write a warehouse table or view to a connection or an object prefix |

### Assurance levels

| Level | You do | The company can prove |
|---|---|---|
| L0 | Raw SQL, raw HTML | Nothing. Never work here. |
| L1 | Query through the gateway, write your own HTML | Every number traceable |
| L2 | Emit a report package or a ReportSpec; TraceBi builds it | The artifact reproduces |
| L3 | L2 plus a signed manifest and re-verification | Attestable (future) |

Work at L2. Drop to L1 only when the six section types cannot express the
page, and then step 6 is mandatory, because nothing checks your
transcription.

## 0. No model yet: start from the data

Skip this step when a model already answers the question. Otherwise, in
order ([[sop-onboarding]] walks it in full):

1. **Explore what you may read.** `list_connections`, then
   `list_source_tables(connection)` and
   `describe_source_table(connection, table)`. Only the tables a person
   allowed agents to read are there; any other answers "not found".
2. **Propose a transform.** `propose_transform(name, sql, contract_yaml,
   note)`: SQL that reads those tables through `-- source:` lines and sinks
   clean star-schema tables, with a contract of checks on them.
3. **Wait for the approval.** Give the person the request id and its
   `review_url`. Nothing has run: an admin approves it and it runs once.
   Until then its tables do not exist.
4. **Draft the model.** `start_draft(kind="models", path=<name>)` over the
   sunk tables (`describe_table` gives their columns), `preview_draft`, then
   `publish_draft` once the person agrees. Then go on to step 1.

## 1. Load the contract with `get_context`

Always the first call. Nothing outside what it returns will validate.

```json
{ "tool": "get_context", "arguments": { "model": "wealth_model" } }
```

The response includes:

| Key | Holds |
|---|---|
| `report_sections` | Every section type (`text`, `table`, `chart`, `metrics`, `row`, `spacer`) with fields, defaults and allowed values: `chart_type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`), text `style` (`normal`, `heading1`, `heading2`, `note`, `callout`), table `style` (`default`, `striped`, `compact`) |
| `semantic_model` | Aggregations (`sum`, `count`, `mean`, `avg`, `min`, `max`, `nunique`), filter operators (`eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, `between`, `is_null`, `not_null`, `contains`), filter forms, and measure kinds |
| `number_formats` | `currency`, `currency0`, `percent`, `comma`, `decimal` |
| `model` | With `model=`: that model's tables, relationships, facts, dimensions and named measures |

Use `list_models` first if you don't know which model to ask for.
`describe_model` (`{"model": "wealth_model"}`) re-fetches one schema later.

**Treat the contract as closed.** A fact, attribute or measure not in the
response does not exist. Don't guess names: validation rejects them, and
invented vocabulary is the failure this gateway exists to prevent.

## 2. Explore with `query_model` and keep the stamp

Probe the data before you decide what to write. A query names a fact,
measures, and dimension attributes as `dim_name.attribute`:

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

`measures` takes declared names, or an inline `{column: agg}` dict such as
`{"market_value": "sum"}`. `filters` takes equality
(`{"dim_client.segment": "private"}`), lists meaning IN
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

Handle the stamp this way, every time:

1. **Record `query` and `fingerprint` exactly** for every query whose numbers
   you might cite. Step 6 replays them.
2. **The fingerprint covers the full result; `rows` is only delivery.** Rows
   are capped (`limit`, default 50, at most 500), but the fingerprint hashes
   the uncapped result. If `truncated` is `true`, a number computed from
   `rows` describes a preview. Raise `limit` (up to 500), narrow the query, or
   put the table in a spec.
3. **Never re-derive a stamped number.** Ask the query for a total, or use a
   section's `totals`. Summing displayed rows yourself is how the $1 rounding
   error in `examples/agent_gateway/verify_report.py` happened.

## 3. Write the spec

### First, the house theme

Offer the house theme once, for a new report or dashboard only: when the
project sets no brand.theme and the person has not named a theme, offer the
three in one short line each (Ledger: calm, institutional, the default;
Nightdesk: dark, dense, monospaced numbers, for a desk or ops screen; Signal:
bold, big numbers, for a board pack or a wall screen), recommend one for what
the report is for, and use Ledger if the person does not choose. If the
project sets a theme, use it and say so in one line instead of asking. Never
ask again for an existing report. The person's choice goes in the package's
`report.json` `"theme"` (`start_draft(kind="reports", path=…,
theme="nightdesk")` starts the draft with it; keep that key when you write
`report.json`). Pick a theme or use the project's brand; never hard-code a
colour ([[chart-style]]).

### The spec

A spec is JSON: `name` (required), plus optional `sections`, `author`,
`description` and `parameters`. Each `table` or `chart` section carries a
`data` reference, `{"model": …, "query": …}`, where `query` has exactly
`fact`, `measures`, `dimensions`, `filters`, `aggregate` and `allow_fanout`.
`tracebi spec schema` (or `GET /api/spec/schema`) prints the JSON Schema.

- **Use named measures.** `"measures": ["market_value", "unrealized_gain"]`
  uses the model's shared definitions, so "unrealized gain" means the same in
  every report, and each measure's declared format reaches the page with no
  formatting in your spec. Use `{column: agg}` only for a concept the model
  has no name for, and treat that as a signal (next rule).
- **A missing concept is an escalation.** A spec cannot express arbitrary
  computation. If you need a measure, attribute or fact the contract lacks,
  stop and follow [[sop-model-changes]]: the fix is a reviewed change to the
  model file (a `measures:` entry in `models/<name>.yaml`, such as
  `{name: unrealized_gain, expr: market_value - cost_basis, agg: sum, format: currency0}`),
  after which a fresh gateway process sees it. Don't compute the number in a
  text section, approximate it with another aggregation, or type
  hand arithmetic into the page. Change the contract in git; use it over MCP.
- **Set `author`**, e.g. `"claude (via mcp gateway)"`, so the artifact says
  who made it.
- Use `text` sections for narrative and a closing provenance note. Use
  `column_labels`, `totals` and `number_formats` on tables rather than
  reformatting in the query.
- **Leave `allow_fanout` false.** An error about a non-unique dimension key is
  TraceBi refusing to inflate sums. Investigate or escalate; don't flip the
  flag.

## 4. Validate and repair

```json
{ "tool": "validate_report_spec", "arguments": { "spec": { "name": "…", "sections": [ "…" ] } } }
```

It returns `{"ok": bool, "errors": [...], "warnings": [...]}`. Every error
carries a path into the spec (malformed JSON or a missing `name` return a
plain message):

```
sections[1].data.query.fact: 'fact_hallucinated' is not a fact on model 'wealth_model'. Available: ['fact_activities', 'fact_holdings']
```

1. Read the path.
2. Fix exactly that field. Many errors include a did-you-mean hint and the
   valid set.
3. Validate again.
4. Repeat until `ok` is `true` and you have read every warning. A warning
   that a section has *no data reference* means it carries no fingerprint.

Validation loads no data, so the loop is free. Never let the renderer be your
first check.

## 5. Render with `render_report_spec`

```json
{ "tool": "render_report_spec", "arguments": { "spec": { "…": "…" }, "output_dir": "output" } }
```

The gateway validates again and refuses an invalid spec. On success:

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

The manifest is the trace. For each data section it records
`dataset_fingerprint`, `dataset_lineage` (connector to aggregate),
`dataset_name` and `dataset_shape`, plus the repository's `git_sha`.

Check that each fingerprint in `dataset_fingerprints` matches the one from
your step 2 query. A match proves the artifact holds the data you analysed. A
mismatch means the data moved between exploration and render: re-run your
queries and reconcile before you publish.

## 6. Audit your own output

Before you present anything, run both checks.
`examples/agent_gateway/verify_report.py` is the pattern; it caught a real $1
error on a page whose fingerprints all matched.

1. **Fingerprints.** Re-run every recorded query with `query_model` and
   compare its `fingerprint` to the one you recorded (and, at L2, to the
   manifest's `dataset_fingerprint`). A match means the data has not drifted.
2. **Figures.** Recompute every number you show from the fresh result and
   compare it to the artifact. A match means you transcribed it correctly.

The two catch different faults. A matching fingerprint with a mismatched
figure is your transcription: the script's first run found a page saying
`+$523,045` (the sum of rounded rows) where the truth was `$523,044.32`.
Round the true total; never sum rounded rows. A fingerprint mismatch is source
drift, and every figure must be re-derived.

At L2, `verify_manifest` runs check 1 for you. Point it at the manifest from
step 5 and read each section's `verdict`, not just `ok`: only `reproduces`
means a number was re-run and matched. TraceBi drew the figures from the
queries the manifest fingerprints, so check 2 covers only numbers you quote in
your own text. At L1 there is no manifest: check every figure with your own
replay script (`verify_report.py` is the template) and keep it beside the
artifact.

## 7. Present numbers with their citation

Never state a number without its citation:

> Total book AUM is **$7,521,674** (query fingerprint `b3d614c1d264`,
> `fact_holdings` by `dim_product.asset_class`, wealth_model).

- Cite the first 12 hex characters of the fingerprint on a page for people.
  Keep the full hash in your working papers and the manifest.
- On an L1 page, add a "Working Papers" section listing each query (model,
  fact, measures, dimensions, filters) with its fingerprint.
- For an L2 artifact, point at the manifest.
- When someone asks where a number came from, answer with the recorded query
  and its fingerprint, which can be re-run today.

## Worked example (wealth_model)

The smallest complete pass. The demo data is seeded, so these queries
reproduce.

1. **Contract.** `get_context` with `{"model": "wealth_model"}` returns
   `fact_holdings` (columns `units`, `market_value`, `cost_basis`), four
   dimensions (`dim_client`, `dim_branch`, `dim_product`, `dim_account`) and
   four named measures: `market_value`, `cost_basis`, `unrealized_gain`,
   `gain_pct`.
2. **Explore.** The step 2 query: AUM, basis, gain and gain % by asset class.
   Record fingerprint `b3d614c1d264…`, `row_count` 4, `truncated` false. Had
   the model lacked `unrealized_gain`, you would escalate here instead of
   computing `market_value - cost_basis`.
3. **Write and validate.** A two-section spec using named measures only:

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

   `validate_report_spec` returns `{"ok": true, "errors": [], "warnings": []}`.
   A typo such as `"fact": "fact_holding"` would return
   `sections[0].data.query.fact: 'fact_holding' is not a fact on model 'wealth_model'`.
4. **Render.** `render_report_spec` returns `ok: true`,
   `html_path: "output/asset-class-snapshot.html"`,
   `manifest_path: "output/asset-class-snapshot.manifest.json"`, and one
   fingerprint in `dataset_fingerprints`, equal to step 2's `b3d614c1d264…`.
5. **Audit.** Re-run the query; the fingerprint still starts `b3d614c1d264`,
   and the totals you will quote equal the fresh sums
   (`round(sum(unrealized_gain rows))`, never a sum of rounded rows).
6. **Present.**

   > Unrealized gains across the book stand at **+$523,044** on
   > **$6,998,630** of cost basis, a 7.5% return on basis
   > (fingerprint `b3d614c1d264`, `fact_holdings` by asset class,
   > wealth_model; manifest: `output/asset-class-snapshot.manifest.json`).

## When something goes wrong

| Situation | Action |
|---|---|
| The vocabulary you need is not in `get_context` | Follow [[sop-model-changes]]. Never invent, approximate or hand-compute. |
| `validate_report_spec` returns errors | Fix the field at each path; validate until `ok`. |
| `render_report_spec` returns `ok: false` | It refused an invalid spec. Go back to step 4; never route around the renderer. |
| A query fails on dimension fan-out | Investigate the join grain or escalate. Don't set `allow_fanout: true`. |
| `truncated: true` on a query you need in full | Raise `limit` (up to 500), narrow the query, or move the table into a spec. |
| Fingerprint mismatch on audit | Source drift: re-run every query and re-derive every figure before publishing. |
| Figure mismatch with a matching fingerprint | Your transcription is wrong. Fix the artifact and audit again. |
