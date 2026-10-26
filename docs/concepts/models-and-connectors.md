# Models and connectors

A model says what the data means. A connector says where the data is. The
model file holds no data:

```yaml
connectors:
  - {name: warehouse, type: warehouse}                                  # where
tables:
  - {name: fact_holdings, connector: warehouse, source: fact_holdings}  # which table, from where
facts:                                                                  # what it means
  - {name: fact_holdings, table: fact_holdings, measures: [fair_value],
     foreign_keys: {dim_fund: fund_id}}
```

| Part | What it is | Where it is declared |
|---|---|---|
| Connector | A handle to a place that stores data: the project's warehouse, a DuckDB file, a database, a cloud warehouse | In the model file (`type: warehouse` for the project's warehouse), or once in `connections/<name>.yaml` |
| Table | A name the model uses for one source inside one connector | `{name: fact_holdings, connector: warehouse, source: fact_holdings}` |
| Model | The tables, which are facts and which are dimensions, how they join, and what each measure means | `models/<name>.yaml` |

## Find where a model's data is

**In the app:** open **Data › Models**, then the model
(`/data/models/<model>`). The header names the file that defines it, and its
Semantic layer the warehouse it reads. The page shows the model's tables, its
star schema, and an inspector for the table you select: its rows, who wrote
it, its joins and measures, and **Open table** for its columns and rows. With
nothing selected, the **Storage** fold says whether the warehouse file
exists, how big it is, and which tables each connector serves.

Two Data folders cover the whole project. **Warehouse** (`/data/warehouse`)
shows every table, grouped by the transform that wrote it, each with a page
at `/data/warehouse/<table>`. **Sources** (`/data/sources`) lists every
connection and input file, and what reads each (`/data/sources/<name>`).

**In code:** `model.info()["connector_details"]` gives the same answer.
`connector.storage()` says where a connector's data lives, never a credential.

## A model, its reports and its pipeline

Reports are grouped by model: the folder name is the model's name.

```
models/portfolio_model.yaml            what the data means
reports/portfolio_model/…              every report that reads it
pipelines/portfolio_model.yaml         rebuild its data, then those reports
```

The pipeline file is a few lines: `transform: holdings_transform`,
`models: [portfolio_model]`, `reports: all`. It runs the transform, then
builds every report in `reports/portfolio_model/` with its trace. It appears on
the transform's page (Data › Transforms › `holdings_transform`), where
**Refresh data** runs it, and from the
terminal as `tracebi run-pipeline portfolio_model`. If the transform fails,
the reports are not rebuilt.

## "Not built yet"

A file connector points at a path that exists only after the transform has
run. Until then the app shows **not built yet** beside it.

## Why it works this way

- The model fits on one screen for review, because it holds meaning only.
- The data can be rebuilt without touching the model. The transform rewrites
  the warehouse; the model keeps reading the same table names.
- Every query records which connector and table it read, with a fingerprint
  of that table, so a trace can name its source.

## Next

- Declare a database connection: [[connections-yaml]]
- See how a number is traced to its table: [[lineage]]
