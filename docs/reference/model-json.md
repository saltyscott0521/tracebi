# Model files (YAML or JSON)

**A model as data: the same star schema as a Python `DataModel`, written as a
document a person reviews and a remote agent can draft without the server
running anyone's code.**

`models/<name>.yaml` is the human form (comments say why a measure is weighted
and which trap it avoids); `.yml` and `.json` are the same schema and load
through the same validator and builder. The document mirrors the builder calls
one to one. Loading it reads no rows; a query is what opens the warehouse,
exactly as with `models/<name>.py`. `tracebi new-model "Sales"` writes a
commented `models/sales.yaml`.

---

## Example

```yaml
# models/sales_model.yaml
name: sales_model

connectors:
  - name: warehouse
    type: duckdb
    database: data/warehouse.duckdb

tables:
  - {name: fact_orders, connector: warehouse, source: fact_orders}
  - {name: dim_region, connector: warehouse, source: dim_region}

dimensions:
  - name: dim_region
    table: dim_region
    key: region_id
    attributes: [region]

facts:
  - name: fact_orders
    table: fact_orders
    measures: [amount]
    foreign_keys: {dim_region: region_id}

# Derived, groupable attributes: declared once, not re-cut in every report.
time_grains:
  - {dimension: dim_date, name: order_month, source: order_date, grain: month}
value_bins:
  - dimension: dim_customer
    name: score_band
    source: credit_score
    edges: [600, 700, 800]      # N edges make N+1 bands

measures:
  - name: revenue
    column: amount
    agg: sum
    format: currency0
```

The same model as JSON, for a tool that writes JSON:

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

## Keys

The schema is closed: an unknown key is an error that names the closest key.
Errors lead with their path, e.g. `measures[2].agg`.

| Key | Builder call | Fields |
|---|---|---|
| `name` | `DataModel(name)` | **Required.** Must equal the file name without its extension. |
| `connectors` | `add_connector` | `{name, type: "duckdb", database}` or `{name, connection}` |
| `tables` | `add_table` | `name`, `connector`, `source` |
| `relationships` | `add_relationship` | `name`, `left_table`, `right_table`, `left_key`, optional `right_key`, `how` |
| `dimensions` | `add_dimension` | `name`, `table`, `key`, optional `attributes` |
| `facts` | `add_fact` | `name`, `table`, `measures`, optional `foreign_keys` |
| `time_grains` | `add_time_grain` | `dimension`, `name`, `source`, `grain` (`month`, `quarter`, ...) |
| `value_bins` | `add_value_bins` | `dimension`, `name`, `source`, `edges`, optional `labels` (one more than `edges`) |
| `measures` | `add_measure` | `name` plus any keyword of [[measures]]: `column`, `agg`, `expr`, `ratio`, `share`, `rank`, `running`, `partition_by`, `period_end`, `offset`, `growth`, `to_date`, `description`, `format`, `allow_rate_agg`, `allow_additive`. Pairs and triples are lists. |

`time_grains` and `value_bins` name the dimension as `dimension` (the builder's
`dim`); the other fields are the builder's own keyword arguments.

### YAML specifics

- The file is read with a safe loader only: no YAML tag can construct an
  object, so `!!python/object` is refused.
- **A repeated key is an error**, not last-wins: a second `agg:` in one measure
  would otherwise quietly replace the first.
- Beware YAML's own scalars when a value is text: `no`, `on` and `null` are not
  strings. Quote them.

### Connectors, and no credentials

- `type: duckdb` with `database: data/warehouse.duckdb` is a DuckDB file
  **inside the project**. An absolute path or one with `..` is refused.
- `{name: warehouse, connection: warehouse}` reuses the connector in
  `models/_connections/warehouse.py` (written by `tracebi connect`). Its own
  `name` must match.

There is no key for a URL, password or token, so a file cannot carry one. The
secret stays in `.env`, read by the connection module.

## One model, one file

`models/<name>.yaml`, `.yml` and `.json` are discovered beside `models/*.py` at
startup and by live discovery, validated structurally, and loaded on first
use. A bad file is a **failed** entry in `/api/discovery` (and `tracebi
validate`) with the path of the problem; the other models keep loading.

- If `x.py` and any declarative `x.*` both exist, **the Python file wins** and
  the declarative one is reported as failed ("`x.yaml` refused: `x.py`
  exists").
- If more than one declarative form exists (`x.yaml` and `x.json`), **all of
  them are refused**, each with a reason naming the others, because nothing
  says which is current. Delete all but one.

## Converting a Python model

```
tracebi migrate model models/sales.py            # print the YAML
tracebi migrate model models/sales.py --write    # write models/sales.yaml beside it
```

The YAML is built from the loaded model, compiled again, and compared with the
original; a model that cannot be expressed is refused with the reason (a
connector that is not a DuckDB file inside the project, a name that differs
from the file name, a measure that needed `allow_additive`). Comments in the
Python file are not carried over. Nothing is renamed or deleted: the `.py`
keeps winning until you delete it, and a query through the YAML fingerprints
the same as through the Python.

## Drafts over the gateway

A model draft is one file, `<name>.yaml` or `<name>.json`, under
`drafts/<owner>/models/`. A new draft starts as YAML. Writing the other form
replaces the draft's file, so the two never coexist. Publishing copies the file
as it is to `models/`, replacing any other declarative form of that name there
(the previous one is kept under `.tracebi/history/`). A `.yml` model can be
drafted (it opens as `.yaml`) but a draft is never written as `.yml`.
