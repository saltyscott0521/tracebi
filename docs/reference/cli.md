# CLI reference

**Every `tracebi` command.** Start with [[#The everyday loop]] — it is five
commands, and most days you use only those.

```bash
tracebi [--models-dir DIR] [--pipelines-dir DIR] <command> [...]
```

Global flags come **before** the subcommand. Directory defaults come from the
environment — see [[environment-variables]].

---

## The everyday loop

```bash
tracebi dev                      # the live surface (no name = discovery mode)
tracebi run-transform holdings   # ① clean + sink to the warehouse
tracebi report build my_report   # ③ render one self-contained .html + receipt
tracebi report status my_report  # what the artifact has actually earned
tracebi verify output/my_report.html.manifest.json
```

Everything else is scaffolding, serving, or one-time migration.

---

## Authoring

### `tracebi init`

```bash
tracebi init <project> [--force]
```

Scaffolds a complete three-phase project whose sample loop ends in
`tracebi verify` printing REPRODUCES.

Creates `inputs/ transforms/ models/ pipelines/ reports/ scheduled/ data/
output/`, plus a sample transform, model and report package, `.gitignore`,
`.env.example`, `README.md` and `AGENTS.md`.

- `--force` — overwrite existing files, and required to init into a non-empty
  directory. Without it, an existing file is skipped with a note and the run
  still succeeds.

### `tracebi new-transform "Title"` · `new-model` · `new-report` · `new-pipeline`

```bash
tracebi new-transform "Orders Clean"  [--force] [--transforms-dir DIR]
tracebi new-model     "Sales Model"   [--force]
tracebi new-report    "Portfolio Book"[--force] [--reports-dir DIR]
tracebi new-pipeline  "Sales ETL"     [--force]
```

Each scaffolds one file (or, for `new-report`, a package directory) with the
title slugified: `"Portfolio Book"` → `portfolio_book`.

All refuse to overwrite without `--force`.

`new-report` deliberately writes **no** `script.js` or `style.css` — the
runtime draws every figure from the stamped bytes, so hand-rolling a CSV parser
and a chart is a trap. Its `template.html` teaches the grammar instead: bound
prose, a KPI, a chart, and a filter/search/download table.
See [[template-html]].

---

## Building and checking

### `tracebi report build`

```bash
tracebi report build <name> [--output PATH] [--badges] [--reports-dir DIR]
```

Renders to one self-contained, offline `.html` plus a sibling
`<output>.html.manifest.json`. Default output is `output/<name>.html`.

- `--badges` — draw per-figure provenance badges on the page. Off by default;
  the receipt drawer already carries provenance in one place. **The manifest is
  identical either way.**

A `.json` spec target is compiled to a package first, then rendered like a
hand-authored one — one report form.

### `tracebi report status`

```bash
tracebi report status <name> [--json]
```

The earned state of an artifact — what a driving agent or CI calls between
edits. Prints a per-figure line (`✓` verified, `·` derived or unverified,
`✗` otherwise), then unused and failing bindings.

**Exits 1** if any binding errors. Packages only.

### `tracebi verify`

```bash
tracebi verify <manifest.json> [--strict] [--contracts]
tracebi verify --file <report.html> [--manifest PATH] [--strict]
```

Two deliberately separate checks. See [[receipts]] for what each proves.

**Mode 1 — query → model.** Re-runs every recorded query and classifies each
section: `REPRODUCES`, `SOURCE DRIFT`, `MODEL CHANGED`, `UNEXPLAINED`, or
`UNVERIFIABLE`.

| Exit | Meaning |
| --- | --- |
| `0` | all reproduce or are unverifiable |
| `2` | diagnosed drift only |
| `1` | anything unexplained or errored — **or a manifest with nothing to verify** |

**Mode 2 — `--file`.** Rehashes the bytes embedded in the shipped HTML against
the manifest. No model, no database, fully offline. Catches a number edited in
the file after the fact.

- `--strict` — fail unless **every figure** reproduces. The CI gate.
- `--contracts` — also re-run the warehouse's recorded [[sink-contracts]] and
  compare certified fingerprints to the data now. Reported separately; it never
  colours a figure status.

Verify is read-only and refuses a review snapshot by name rather than printing
a check that looks like it ran.

### `tracebi validate`

```bash
tracebi validate
```

Cheap pre-flight: checks the project layout, reports any discovery import that
failed, and runs `DataModel.validate()` on every model — chiefly that dimension
keys are unique, since a non-unique key silently inflates every additive
measure. Exits 1 on any problem.

---

## Working live

### `tracebi dev`

```bash
tracebi dev [name] [--port 8001] [--no-browser]
```

The live-preview loop, and **the everyday surface**.

With a package name, serves `reports/<name>/` with the exploration render plus
the workbench at `/__workbench`. With **no name** it enters *discovery mode*:
warehouse tables, sink contracts, models and packages — the live surface before
any report exists.

### `tracebi report preview`

```bash
tracebi report preview <name> [--port 8080] [--no-browser]
```

Builds, then serves the built static file. Bound to `127.0.0.1` only, because
it serves a directory of rendered reports unauthenticated.

### `tracebi serve`

```bash
tracebi serve [--host 127.0.0.1] [--port 8000] [--reload]
```

Serves the project's web UI. Refuses with an actionable message if there is no
project in the current directory, or if `uvicorn` is not installed.

### `tracebi session`

```bash
tracebi session export [name] [-o PATH] [--format {html,md}] [--title T]
tracebi session clear  [name]
```

Saves or resets the workbench exhibit feed that `tracebi dev` writes (stored
under `.tracebi/workbench/<name>/`). Omit `name` for the discovery session.

`export` writes **one living record per session** — re-exporting overwrites the
same file so git carries the timeline as a readable diff. The `md` format is
the pull-request twin. It is a lab notebook: **no manifest**, and `verify`
refuses it by name.

`clear` refuses while a dev-server heartbeat is fresh (15s), since the live
watcher would post straight over the reset.

---

## Sharing

### `tracebi report send`

```bash
tracebi report send <name> --to a@b.com[,c@d.com] [--subject S] [--force]
```

Builds, **verifies the fresh manifest in-process**, then emails the HTML and
its receipt together.

**It refuses to send when the receipt does not verify** — distribution never
outruns verification. `--force` sends anyway with the failing verdict pasted
into the body, so the red flag travels *with* the report.

Requires `TRACEBI_SMTP_URL` and `TRACEBI_SMTP_FROM`; optional
`TRACEBI_SLACK_WEBHOOK` pings after a successful send.

**Scheduling is plain cron** — no daemon ships:

```bash
0 7 * * MON cd /path/to/project && tracebi report send weekly --to team@example.com
```

### `tracebi report snapshot`

```bash
tracebi report snapshot <name> [--output PATH]
```

Writes the sendable **working state** — exploration blocks kept, a self-banner,
a read-only code appendix, and deliberately **no manifest**, because a
weaker-looking receipt is worse than none. `verify --file` refuses it by name.

---

## Agent surfaces

### `tracebi context`

```bash
tracebi context [--model NAME] [--brief] [--compact]
```

The framework's vocabulary as JSON — generated from the code, so it cannot
drift. This is what an agent reads first.

- `--brief` — the token-lean tier: semantic model, figure grammar, contracts,
  conventions
- `--model NAME` — also include that model's schema

### `tracebi knowledge`

```bash
tracebi knowledge [slug]
```

Analyst good-practice lessons. No argument lists the curriculum; a slug prints
that lesson in full.

### `tracebi mcp`

```bash
tracebi mcp [--transport {stdio,http}] [--port 8765] [--insecure]
```

Serves the agent gateway over MCP. **The http transport refuses to start until
an auth decision is made** — set `TRACEBI_MCP_TOKEN`, or pass `--insecure`
deliberately.

---

## Pipelines

### `tracebi run-pipeline`

```bash
tracebi run-pipeline <name> [--layer LAYER] [--refresh] [--status]
```

Runs a pipeline's layers, upstream first. Any external scheduler can drive it.

- `--layer` — run only this layer; add `--refresh` to run its upstream chain
- `--status` — show each layer's last run, executing nothing

**It does not stop at the first failure** — downstream layers read what upstream
wrote, so every failure is reported, then a summary and exit 1.

Records the OS user as the audit actor, so "who ran this" answers for cron and
CI runs too.

### `tracebi list-models` · `tracebi list-pipelines`

List definition files. Never fail: a missing or empty directory prints a note
and exits 0.

---

## Legacy

### `tracebi spec`

```bash
tracebi spec {schema|validate|render} [file] [--theme CSS] [--output PATH]
```

Works with the JSON `ReportSpec` form: print its JSON Schema, validate without
running, or compile and render.

It **refuses a package `report.json` by name** and points you at
`tracebi report build` rather than emitting confusing "unknown field" errors.

### `tracebi migrate spec`

```bash
tracebi migrate spec reports/<name>.json [--force]
```

Compiles a spec into `reports/<name>/` **alongside** the original — it emits,
never replaces. At discovery the directory shadows the same-named spec, so the
cutover is the directory existing and the rollback is deleting it.

---

## Related

- [[environment-variables]] — every `TRACEBI_*` variable
- [[quickstart]] — these commands in order, once
- [[receipts]] — what `verify` proves
