# `models/<name>.json`

**A model as data: the same star schema as a Python `DataModel`, written as a
document a remote agent can draft without the server running anyone's code.**

The JSON mirrors the builder calls one to one. Loading it reads no rows; a
query is what opens the warehouse, exactly as with `models/<name>.py`.

---

## Example

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

| Key | Builder call | Fields |
|---|---|---|
| `name` | `DataModel(name)` | **Required.** Must equal the file name without `.json`. |
| `connectors` | `add_connector` | `{name, type: "duckdb", database}` or `{name, connection}` |
| `tables` | `add_table` | `name`, `connector`, `source` |
| `relationships` | `add_relationship` | `name`, `left_table`, `right_table`, `left_key`, optional `right_key`, `how` |
| `dimensions` | `add_dimension` | `name`, `table`, `key`, optional `attributes` |
| `facts` | `add_fact` | `name`, `table`, `measures`, optional `foreign_keys` |
| `measures` | `add_measure` | `name` plus any keyword of [[measures]]: `column`, `agg`, `expr`, `ratio`, `share`, `rank`, `running`, `partition_by`, `period_end`, `offset`, `growth`, `to_date`, `description`, `format`, `allow_rate_agg`, `allow_additive`. Pairs and triples are JSON arrays. |

Time grains and value bins have no JSON form yet; use a Python model for them.

### Connectors, and no credentials

- `{"type": "duckdb", "database": "data/warehouse.duckdb"}` is a DuckDB file
  **inside the project**. An absolute path or one with `..` is refused.
- `{"name": "warehouse", "connection": "warehouse"}` reuses the connector in
  `models/_connections/warehouse.py` (written by `tracebi connect`). Its own
  `name` must match.

There is no key for a URL, password or token, so a file cannot carry one. The
secret stays in `.env`, read by the connection module.

## Discovery

`models/<name>.json` is discovered beside `models/*.py` at startup and by live
discovery, validated structurally, and loaded on first use. A bad file is a
**failed** entry in `/api/discovery` (and `tracebi validate`) with the path of
the problem, e.g. `measures[2].agg`; the other models keep loading.

If `x.py` and `x.json` both exist, **the Python file wins** and the JSON is
reported as failed ("`x.json` refused: `x.py` exists"). A model is one or the
other.
