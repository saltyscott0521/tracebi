# Model files (YAML or JSON)

A model file declares a star schema: the same model as a Python `DataModel`,
written as data that runs no code.

```yaml
# models/sales_model.yaml
name: sales_model
label: Sales Orders
description: Every order, by the region it ships to.
questions:
  - Which regions bring in the most revenue?

connectors:
  - name: warehouse
    type: warehouse

tables:
  - {name: fact_orders, connector: warehouse, source: fact_orders}
  - {name: dim_region, connector: warehouse, source: dim_region}

dimensions:
  - name: dim_region
    table: dim_region
    key: region_id
    description: The sales region an order ships to
    attributes:
      - {name: region, synonyms: [territory]}

facts:
  - name: fact_orders
    table: fact_orders
    measures: [amount]
    foreign_keys: {dim_region: region_id}

# Derived attributes you can group by
time_grains:
  - {dimension: dim_date, name: order_month, source: order_date, grain: month}
value_bins:
  - dimension: dim_customer
    name: score_band
    source: credit_score
    edges: [600, 700, 800]      # 3 edges make 4 bands

measures:
  - name: revenue
    column: amount
    agg: sum
    format: currency0
    description: Order amounts, summed
    synonyms: [sales, turnover]
```

The same model as JSON:

```json
{
  "name": "sales_model",
  "connectors": [{"name": "warehouse", "type": "duckdb", "database": "data/warehouse.duckdb"}],
  "tables": [
    {"name": "fact_orders", "connector": "warehouse", "source": "fact_orders"},
    {"name": "dim_region", "connector": "warehouse", "source": "dim_region"}
  ],
  "dimensions": [{"name": "dim_region", "table": "dim_region", "key": "region_id", "attributes": ["region"]}],
  "facts": [{"name": "fact_orders", "table": "fact_orders", "measures": ["amount"],
             "foreign_keys": {"dim_region": "region_id"}}],
  "measures": [{"name": "revenue", "column": "amount", "agg": "sum", "format": "currency0"}]
}
```

- `models/<name>.yaml`, `.yml` and `.json` share one schema, validator and
  builder. YAML can carry comments explaining a measure.
- Each key maps to one builder call. Loading the file reads no rows; a query
  opens the warehouse.
- `tracebi new-model "Sales"` writes a commented `models/sales.yaml`.

## Keys

The schema is closed: an unknown key is an error naming the closest key.
Errors start with their path, e.g. `measures[2].agg`.

| Key | Builder call | Fields |
|---|---|---|
| `name` | `DataModel(name)` | Required. Equals the file name without its extension. Queries, bindings and commands use it. |
| `label` | `DataModel(name, label=)` | Optional. What people read where the model is listed (`Direct Lending Portfolio`). Unset: the name title-cased (`portfolio_model` → `Portfolio Model`). `GET /api/models`, `describe_model` and `tracebi list-models` carry it. |
| `description` | `DataModel(name, description=)` | Optional. What the model is about, in a sentence or two. Words only: nothing computes from it. The model's Semantic layer page, `describe_model` and `get_context` carry it. |
| `synonyms` | `DataModel(name, synonyms=)` | Optional list of other names for what the model covers (`loan book`). |
| `questions` | `DataModel(name, questions=)` | Optional list of example questions the model answers, as plain sentences. Ask offers them as starting chips, filling its builder as far as their words name a measure and a dimension (by label, identifier or synonym); an agent receives them in its context. |
| `owners` | `DataModel(name, owners=)` | Optional list of sign-in names. Only an owner or an admin may publish a change to this model; others can still draft it and run the impact check. Read from the published file, so a draft cannot grant itself ownership. No `owners`, or a new model: any analyst may publish. Names only, not groups. |
| `connectors` | `add_connector` | `{name, type: warehouse}`, `{name, type: "duckdb", database}` or `{name, connection}` |
| `tables` | `add_table` | `name`, `connector`, `source` |
| `relationships` | `add_relationship` | `name`, `left_table`, `right_table`, `left_key`, optional `right_key`, `how` |
| `dimensions` | `add_dimension` | `name`, `table`, `key`, optional `attributes`, `description`, `synonyms`. An attribute is a column name or `{name, label, description, synonyms}`; a query names it `dimension.name` either way. |
| `facts` | `add_fact` | `name`, `table`, `measures`, optional `foreign_keys` |
| `time_grains` | `add_time_grain` | `dimension`, `name`, `source`, `grain` (`month`, `quarter`, ...) |
| `value_bins` | `add_value_bins` | `dimension`, `name`, `source`, `edges`, optional `labels` (one more than `edges`) |
| `measures` | `add_measure` | `name` plus any keyword in [[measures]]: `column`, `agg`, `expr`, `ratio`, `share`, `rank`, `running`, `partition_by`, `period_end`, `offset`, `growth`, `to_date`, `label`, `description`, `synonyms`, `format`, `allow_rate_agg`, `allow_additive`. Pairs and triples are lists. |

`description`, `synonyms` and `questions` are the semantic layer's words
([[model]]): they change no query, and `tracebi migrate model` carries them.
`time_grains` and `value_bins` call the dimension `dimension` (the builder's
`dim`). A publish by someone who is not an owner is refused (HTTP 403, MCP
`ok: false`), naming the owners. The model's page in the app shows them.

## Connectors

| Form | Meaning |
|---|---|
| `type: warehouse` | The workspace's warehouse, wherever `tracebi.yaml` puts it ([[tracebi-yaml]]): a DuckDB file (default `data/warehouse.duckdb`), Parquet on object storage, or a remote engine. |
| `type: duckdb`, `database: data/warehouse.duckdb` | A DuckDB file inside the workspace. An absolute path or `..` is refused. |
| `{name: crm, connection: crm}` | A declared connection: `connections/crm.yaml` ([[connections-yaml]]), else the older `models/_connections/crm.py`. Its own `name` must match. |

There is no key for a URL, password or token, so a model file cannot carry
one. Secrets stay as `${NAME}` in the connection file ([[credentials]]).

## YAML rules

- The file is read with a safe loader. No YAML tag can build an object;
  `!!python/object` is refused.
- A repeated key is an error, so a second `agg:` cannot quietly replace the
  first.
- YAML reads `no`, `on` and `null` as non-strings. Quote them when you mean
  text.

## One model, one file

Model files are found at startup and by live discovery, checked for shape,
and loaded on first use. A bad file is a **failed** entry in `/api/discovery`
and `tracebi validate`, with the path of the problem; other models still load.

| Files present | Result |
|---|---|
| `x.py` and any `x.yaml`/`x.yml`/`x.json` | The Python file wins. The other is reported as failed ("`x.yaml` refused: `x.py` exists"). |
| More than one of `x.yaml`, `x.yml`, `x.json` | All are refused, each naming the others. Delete all but one. |

## Convert a Python model

```
tracebi migrate model models/sales.py            # print the YAML
tracebi migrate model models/sales.py --write    # write models/sales.yaml beside it
```

The YAML is built from the loaded model, compiled again and compared with the
original. A model YAML cannot express is refused with the reason: a connector
that is not a DuckDB file inside the workspace, a name that differs from the
file name, or a measure that needed `allow_additive`. Comments are not
carried over. Nothing is renamed or deleted: the `.py` wins until you delete
it, and a query through the YAML fingerprints the same.

## Drafts over the gateway

| Rule | Detail |
|---|---|
| Location | One file, `<name>.yaml` or `<name>.json`, under `drafts/<owner>/models/`. |
| New draft | Starts as YAML. |
| Switching form | Writing the other form replaces the draft's file; the two never coexist. |
| Publishing | Copies the file to `models/`, replacing any other declarative form of that name. The previous one is kept under `.tracebi/history/`. |
| `.yml` | Can be drafted (it opens as `.yaml`); a draft is never written as `.yml`. |
