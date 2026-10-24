# Models and connectors

**A model says what the data means. A connector says where the data is. The
model file holds no data.**

---

## The three things

| | What it is | Where it lives |
|---|---|---|
| **Connector** | A handle to a place that stores data: the project's warehouse, a DuckDB file, a database URL, a cloud warehouse | Named in the model file (`type: warehouse` for the project's warehouse), or declared once in `connections/<name>.yaml` |
| **Table** | A name the model uses, pointing at *one source inside one connector* | `{name: fact_holdings, connector: warehouse, source: fact_holdings}` |
| **Model** | The tables, which are facts and which are dimensions, how they join, and what every measure means | `models/<name>.yaml`: a few dozen declarative lines |

Reading a model file, then, tells you the *shape* of the data and the *name* of
the place it is kept, never the data itself.

```yaml
connectors:
  - {name: warehouse, type: warehouse}                                  # where
tables:
  - {name: fact_holdings, connector: warehouse, source: fact_holdings}  # which table, from where
facts:                                                                  # what it means
  - {name: fact_holdings, table: fact_holdings, measures: [fair_value],
     foreign_keys: {dim_fund: fund_id}}
```

## Finding where the data is

- **In the app**, open **Data**, then the model: the header says
  *Defined in* `models/portfolio_model.yaml` · *reads*
  `data/warehouse.duckdb`. The Model tab's **Storage** view says whether the
  file is there yet and how big it is, and lists each connector, what kind of
  place it is, and exactly which tables it serves. Data's **Warehouse** tab
  (`/data/warehouse`) lists every table with the transform that wrote it and
  the models that read it, and **Sources** (`/data/sources`) every connection
  and input file the transforms read, with what reads each.
- **In code**, `model.info()["connector_details"]` gives the same answer, and
  `connector.storage()` says where any connector's data lives (never a
  credential).

## Why it is split this way

- **The model can be reviewed on one screen**, because it holds meaning, not
  data or plumbing.
- **The data can be rebuilt without touching the model.** A [[transform]]
  writes the warehouse file; the model keeps reading the same table names.
- **A [[trace]] can name its source.** Every query records which
  connector and which table it read, plus a fingerprint of that table, so a
  number can be traced to stored data.

## A model, its reports and its pipeline

Reports are organised **by model**: the folder is the model's name.

```
models/portfolio_model.yaml            what the data means
reports/portfolio_model/…            every report that reads it
pipelines/portfolio_model.yaml         rebuild its data, then those reports
```

A few lines make the pipeline (`pipelines/portfolio_model.yaml`:
`transform: holdings_transform`, `models: [portfolio_model]`, `reports: all`):
a **transform** step (the phase ① script that fills the warehouse) and a
**build** step (every report in `reports/portfolio_model/`, each with its
trace). It shows on the model's Transform tab, where **Refresh data** runs it,
and runs with `tracebi run-pipeline portfolio_model`. The build step
refuses to run after a transform that failed, so a report is never rebuilt on
data the transform did not refresh.

## When the data is "not built yet"

A file connector points at a path that exists only after phase ① has run. The
app shows **not built yet** beside the location until the [[transform]] (or
the model's pipeline) has written it.

See also [[model]] and [[lineage]].
