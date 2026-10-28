# `report.json`

`report.json` declares a report package's data: the queries it runs, and the
figures TraceBi builds for it.

```json
{
  "name": "Portfolio Overview",
  "data": {
    "by_sector": {
      "model": "portfolio_model",
      "query": {
        "fact": "fact_holdings",
        "measures": ["fair_value"],
        "dimensions": ["dim_issuer.sector"],
        "order_by": ["-fair_value"]
      }
    }
  }
}
```

It sits in the package folder:

```
reports/my_report/
  report.json      this file
  template.html    the page you write     → [[template-html]]
  app.jsx          or a dashboard         → [[app-jsx]]
  style.css        optional
  script.js        optional
  report.py        optional: numbers the model cannot express (never read green)
```

## Keys

| Key | Type | Meaning |
|---|---|---|
| `name` | string | The display name in every list and title. The path (`portfolio_model/portfolio_overview`) stays the identifier commands and URLs take. `GET /api/reports` returns it as `display_name`; unset, the folder name title-cased. |
| `author` | string | Recorded in the manifest as `rendered_by` and shown in the trace's About this build. |
| `description` | string | One sentence for the reader: what the page shows (measures, breakdowns, period), e.g. `"Ending MRR, customers and logo churn, month by month and by plan."`. Shown under the name in the library. How the page is built goes in `notes`. |
| `notes` | string | For people and agents who edit the package: how the page is built. Nothing renders it. |
| `data` | object, required | Binding name → `{"model": …, "query": …}` ([[queries]]). Each binding runs once, is fingerprinted, embedded and recorded in the trace. Must be non-empty; each entry needs `model` and `query`. A binding may name a SQL calculation instead: `{"model": …, "sql": "<name>"}`. |
| `figures` | object | Figures TraceBi builds for you, placed with `{{ figure("name") }}` ([[figure-helper]]). Leave it out if you write the markup yourself. |
| `measures` | object | This report's own calculations: `{"<model>": {"<name>": {<add_measure keywords>}}}`, plus `filters` and `measure_expr`. A binding lists one by name. The model is unchanged, a name the model declares is refused, and the trace labels them "calculated in this report". |
| `sql_calculations` | object | `{"<model>": {"<name>": "SELECT ..."}}`: one read-only `SELECT` or `WITH` over the warehouse's own tables. Writes, `ATTACH`, `COPY`, `PRAGMA`, `SET`, `INSTALL`, `LOAD` or a second statement are refused at discovery. `{{ measure('name') }}` expands a simple model measure. A selection cannot reach a SQL binding yet. |
| `libs` | array | Charting libraries to inline: `"d3"`, `"echarts"`. Optional (see below). |
| `theme` | string | The house theme ([[chart-style]]): `ledger` (calm, institutional; the default), `nightdesk` (dark, dense, monospaced numerals) or `signal` (bold, big numbers, the lead KPI a solid accent tile). Over the project's `tracebi.yaml` `brand.theme`; the brand's colours, font and logo layer on top. Any other name fails the build naming the three. The six accent presets (`graphite`, `indigo`, `midnight`, `ocean`, `plum`, `sand`) are deprecated: the page renders in the house theme with that accent pair and the build says so once; set `brand: {accent: …}` instead. `tracebi theme list`. |
| `look` | object | `app.jsx` only: `"mode"` (`light`, `dark`, or `auto`, the default; Nightdesk opens `dark` unless this or the brand says otherwise) and `"density"` (`comfortable` or `compact`; Nightdesk is `compact` unless this says `comfortable`). |
| `embed` | string | What the page carries to recompute under filters: `"required"` (default), `"model"` or `"none"` (see below). |
| `embed_budget_mb` | number | The limit for that data. Default 25. |
| `schedule` | object | When the report runs and who gets it (see below). The build ignores it. |

```json
"figures": {
  "total":  {"kind": "value", "binding": "totals", "cell": "revenue",
             "label": "Revenue", "format": "currency"},
  "detail": {"kind": "table", "binding": "by_sector"}
}
```

```json
"measures": {"wealth_model": {
  "purchases": {"column": "amount", "agg": "sum", "filters": {"activity_type": "purchase"}},
  "sales": {"column": "amount", "agg": "sum", "filters": {"activity_type": "sale"}},
  "net_new_assets": {"measure_expr": "purchases - sales", "format": "currency0"}
}}
```

## `libs`

The build inlines D3 automatically when the page contains a chart figure (a
hand-written `data-tb-figure="chart"`, a `{{ figure("…") }}` chart, or a chart
compiled from a spec), and leaves it out otherwise. A final build decides
after exploration blocks are removed; `tracebi dev` and a snapshot decide from
the page they render.

| Value | When to list it |
|---|---|
| `"d3"` | For a `custom` figure drawn with `tracebi.draw`. |
| `"echarts"` | To keep the older ECharts engine for the page's charts. `tracebi.configureChart` applies only there. |

Each library is inlined once. An unknown value is refused at load.

## `embed`

Besides each binding's rows, a live page carries a **slice**: per fact, one
Parquet block (`tracebi-slice-<fact>`) at the coarsest grain that answers
every figure and filter, plus a `tracebi-calc-plans` block with each binding's
calc plan.

| Value | The page carries |
|---|---|
| `"required"` (default) | That grain. Base grain when a measure is `nunique`, a percentile or a row expression; a mean is stored as its sum and count. |
| `"model"` | Every fact at base grain, with every dimension attribute it reaches. |
| `"none"` | Nothing extra. Filters subset the stamped rows and value figures stay as built. |

- Past `embed_budget_mb` the build fails and names the fix: remove a control
  or a grouping, raise the budget, or use `"none"`.
- A slice holds numbers, booleans, strings and naive datetimes. Any other type
  in a needed column fails the build by name.
- A SQL binding and a `report.py` output are never in a slice; they stay as
  built.
- The manifest records each block's `payload_sha256` under `slice` and every
  plan under `plans`.

## `schedule`

```json
"schedule": {
  "cron": "0 9 * * MON",
  "timezone": "America/New_York",
  "to": ["cfo@example.com"],
  "refresh": {"transforms": ["holdings_transform"]}
}
```

Read by `tracebi schedule` ([[cli]]).

| Field | Meaning |
| --- | --- |
| `cron` | Required. Five fields: minute, hour, day, month, day of week. |
| `timezone` | An IANA name. Default `UTC`. |
| `to` | Email addresses. Without it, a run sends no email. With `TRACEBI_SLACK_BOT_TOKEN` and `TRACEBI_SLACK_CHANNEL` set, a successful run still uploads the HTML and manifest to Slack. |
| `refresh` | `{"transforms": [...], "pipelines": [...]}` to run before the build: transforms first, then pipelines, each in a fresh process (`tracebi run-transform`, `tracebi run-pipeline`). A failed step, including a sink contract that refuses the data, fails the run; nothing is built or sent. |
| `retries` | 0 to 5. Default 2. A failed refresh or build is retried after 1 minute, then 5, then 5 again. A trace that does not verify and a delivery failure are not retried. |
| `owner` | One email address. A run recorded `failed`, `refused` or `empty` alerts it in plain text and is not sent to `to`. |
| `burst` | One build per filter value, each with its own recipients (below). |

```json
"burst": {
  "filter": {"dim_region.region": {"in": ["EMEA", "APAC", "AMER"]}},
  "to": {
    "EMEA": ["emea@example.com"],
    "APAC": ["apac@example.com"],
    "AMER": ["amer@example.com"]
  }
}
```

- `filter` is one dimension key mapped to a list or `{"in": [...]}`. `to`
  maps each value to addresses. A value missing from `to` is skipped and
  recorded, not sent to the top-level `to`. `burst` without `to` is refused at
  load.
- Each value gets its own HTML and manifest under `output/`. The filter
  applies at build to every binding whose model has that dimension, the same
  way a selection does. Each slice is verified on its own; a refused, empty or
  failed slice is not sent, and the others still are.
- The run is one record with a `slices` list (value, status, recipients,
  output path). Any slice that failed, came back empty or was refused is named
  in one owner alert.

A run where a figure's binding returns zero rows is recorded `empty` and not
sent. A binding no figure uses does not count.

Refused at load: any other field, a cron that isn't five fields, an unknown
time zone, an address without `@` (in `to` or `owner`), a malformed `refresh`,
or `retries` outside 0 to 5. A `refresh` name that doesn't exist fails the
run, not the load.

## When it is checked

When the package loads, before any query runs:

| Rule | Refusal |
| --- | --- |
| The top level is an object | `the top level must be an object` |
| `data` is a non-empty object | `needs a non-empty 'data' object mapping…` |
| Each binding is an object with `model` and `query` | `data binding 'x' must be an object…` |
| `libs` uses known libraries | `'libs' must be a list drawn from ['echarts']` |
| `figures` is an object | `'figures' must be an object mapping…` |
| A figure's `kind` is known | `has kind 'x'; expected one of [...]` |
| A figure's `binding` is in `data` | `names binding 'x', which is not declared in 'data'` |
| A `value` figure has `cell` | `is a value figure and needs 'cell'` |

When the report builds:

- every declared figure is placed in `template.html` exactly once;
- every binding resolves against a registered model;
- every query is valid against the model ([[measures]]).

**Known gap.** Unknown keys in `report.json` are ignored, not refused. A typo
like `"figure"` for `"figures"` loads with no figures, and a typo inside a
figure falls back to a default. The `.json` spec format does refuse unknown
keys.
