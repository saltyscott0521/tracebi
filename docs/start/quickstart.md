# Get started

In five minutes you will install TraceBi, create a workspace, build a report and
open it in the app.

## Before you begin

- Python 3.10 or later
- Git
- Node.js 22, to build the web app (skip it if you only need the command line)

## 1. Install

TraceBi is not on PyPI yet. Install it from a clone:

```bash
git clone https://github.com/saltyscott0521/tracebi
cd tracebi
pip install -e ".[all]"
(cd web/ui && npm ci && npm run build)
```

The last line builds the web app. A release wheel and the Docker image ship it
already built. `pip install "tracebi[analyst] @ git+https://github.com/saltyscott0521/tracebi"`
installs without cloning, but has no web app.

## 2. Create a workspace

```bash
tracebi init my_workspace && cd my_workspace
git init && git add . && git commit -m "init"
```

Commit now. Each build records the commit it was made from. A build in a
repository with no commits records `unknown` and warns.

The workspace has one folder per stage:

```
tracebi.yaml  settings: where the warehouse is, and the query engine's limits
inputs/       raw files
connections/  the databases a transform reads, one YAML file each
transforms/   the code that cleans the inputs and writes warehouse tables
models/       the model: tables, joins and measures
reports/      report packages, one project (a folder) per model
pipelines/    one per model: run its transform, then build its reports
data/         the warehouse (created on the first run)
output/       built reports and their traces (created on the first build)
```

## 3. Run the transform

```bash
tracebi run-transform sample_transform
```

This reads `inputs/orders.csv`, cleans it, and writes star-schema tables to
`data/warehouse.duckdb`. The sample is written in pandas. New transforms are
SQL by default (`tracebi new-transform`).

Then check the model:

```bash
tracebi validate
```

It loads `models/sample_model.yaml` and checks that every dimension key is
unique. A repeated key would inflate every total.

## 4. Build the report

```bash
tracebi report build sample_model/sample_dashboard
```

The report lives in `reports/sample_model/sample_dashboard/` and is named by
that path. The build writes two files:

```
output/sample_model/sample_dashboard.html                 the report
output/sample_model/sample_dashboard.html.manifest.json   its trace
```

The HTML file is self-contained and works offline. Check it:

```bash
tracebi verify output/sample_model/sample_dashboard.html.manifest.json
```

Every figure should read `REPRODUCES`: its query ran again and returned the
same data.

## 5. Open the app

```bash
tracebi serve
```

Open `http://127.0.0.1:8000`. The library lists **Sample Dashboard** under
**Sample Orders**. Open it, then click **Trace** under the title to see how
each number was made.

## What you have now

- A warehouse file with clean tables, written by a transform.
- A model that names those tables, their joins and their measures.
- A report whose every number is a query against the model, with a trace
  beside it.

`tracebi run-pipeline sample_model` runs steps 3 and 4 in one command. It is
what **Refresh data** runs in the app.

To work on the report with live reload, run `tracebi dev sample_model/sample_dashboard`
and edit `reports/sample_model/sample_dashboard/app.jsx`. The page reloads on
each save. Editing a report never re-runs the transform.

## Next

| To | Read |
| --- | --- |
| Change a number and rebuild | [[your-first-report]] |
| Understand the three stages | [[the-three-phase-workflow]] |
| Add a measure | [[measures]] |
| Filter, sort or limit a query | [[queries]] |
| Check a report file someone sent you | [[trace]] |
| See every command | [[cli]] |
