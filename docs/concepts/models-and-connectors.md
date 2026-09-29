# Models and connectors

**A model says what the data means. A connector says where the data is. The
model file holds no data.**

---

## The three things

| | What it is | Where it lives |
|---|---|---|
| **Connector** | A handle to a place that stores data: a DuckDB file, a folder of CSVs, a database URL, a cloud warehouse | Built in the model file (or registered in an app module) |
| **Table** | A name the model uses, pointing at *one source inside one connector* | `add_table("fact_holdings", connector="warehouse", source="fact_holdings")` |
| **Model** | The tables, which are facts and which are dimensions, how they join, and what every measure means | `models/<name>.py`: code, a few dozen lines |

Reading a model file, then, tells you the *shape* of the data and the *name* of
the place it is kept, never the data itself.

```python
model = DataModel("portfolio_model")
model.add_connector(DuckDBConnector("warehouse", database="data/warehouse.duckdb"))   # where
model.add_table("fact_holdings", connector="warehouse", source="fact_holdings")       # which table, from where
model.add_fact("fact_holdings", table_name="fact_holdings",                           # what it means
               foreign_keys={"dim_fund": "fund_id"}, measures=["fair_value"])
```

## Finding where the data is

- **In the app**, open **Data model**, pick a model: the header says
  *Defined in* `models/portfolio_model.py` and *Data in*
  `data/warehouse.duckdb`, and whether the file is there yet and how big it is.
  The **Storage** tab lists each connector, what kind of place it is, and
  exactly which tables it serves. The **Connectors** page is the same list
  across all models, with the models that use each one.
- **In code**, `model.info()["connector_details"]` gives the same answer, and
  `connector.storage()` says where any connector's data lives (never a
  credential).

## Why it is split this way

- **The model can be reviewed on one screen**, because it holds meaning, not
  data or plumbing.
- **The data can be rebuilt without touching the model.** A [[transform]]
  writes the warehouse file; the model keeps reading the same table names.
- **A [[receipts|receipt]] can name its source.** Every query records which
  connector and which table it read, plus a fingerprint of that table, so a
  number can be traced to stored data.

## When the data is "not built yet"

A file connector points at a path that exists only after phase ① has run. The
app shows **not built yet** beside the location until the [[transform]] (or
the model's pipeline) has written it.

See also [[model]] and [[lineage]].
