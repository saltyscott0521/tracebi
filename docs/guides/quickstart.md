# Quickstart

**Install, scaffold a project, and build one verified report — about five
minutes.**

---

## 1. Install

```bash
pip install -e ".[all]"
```

The minimum working set is pandas + duckdb + jinja2. `[all]` covers it plus the
web UI and Excel export.

## 2. Scaffold

```bash
tracebi init my_project
cd my_project
git init && git commit --allow-empty -m "init"
```

Commit early: every manifest stamps the current commit as `git_sha`, so a
report built in a repo with no commits records `unknown` and warns.

You get the three-phase layout from [[the-three-phase-workflow]]:

```
inputs/       ⓪ raw pulls
transforms/   ① pandas that lands clean tables
models/       ② the star-schema contract
reports/      ③ the report packages
data/         the warehouse lives here
output/       built artifacts + receipts
```

## 3. Run the transform — phase ①

```bash
tracebi run-transform sample_transform
```

Reads `inputs/orders.csv`, cleans it, and sinks star-schema tables into
`data/warehouse.duckdb`. That file is the first [[freeze-points|freeze point]].

→ [[transform]]

## 4. Look at the model — phase ②

Open `models/sample_model.py`. A few dozen lines: tables, keys, and
[[measures]]. Nothing to run — it is a declaration.

```bash
tracebi validate
```

Checks the model loads and its dimension keys are unique. A non-unique key
silently inflates every additive measure, so this is worth running.

→ [[model]]

## 5. Build the report — phase ③

```bash
tracebi report build sample_dashboard
```

Writes two files:

```
output/sample_dashboard.html                   the artifact
output/sample_dashboard.html.manifest.json     the receipt
```

The HTML is fully self-contained — no CDN, no network. Open it directly.

→ [[report]]

## 6. Verify

```bash
tracebi verify output/sample_dashboard.html.manifest.json
```

Re-runs every recorded query and compares fingerprints. You should see
`✓ REPRODUCES` per figure.

Then the offline check — no database, no model, just the file:

```bash
tracebi verify --file output/sample_dashboard.html
```

Edit a number inside the HTML by hand and run it again: it reports
`FILE ALTERED` and names the binding.

→ [[receipts]]

---

## Now iterate

```bash
tracebi dev sample_dashboard
```

The live loop. Edit `reports/sample_dashboard/template.html` and the page
reloads. The workbench at `/__workbench` shows what each figure is bound to and
what it has earned.

**Because the model is materialized, editing a report never re-runs the
pandas** — that is the whole point of [[freeze-points]].

## Where to go next

| You want to… | Go to |
| --- | --- |
| Author a report properly | [[your-first-report]] |
| Add a figure without writing markup | [[figure-helper]] |
| Understand the `data-tb-*` attributes | [[template-html]] |
| Add a measure | [[measures]] |
| Filter, sort, or limit | [[queries]] |
| Style the page | [[styling-a-report]] |
| See every command | [[cli]] |
