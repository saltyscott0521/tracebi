# Model — phase ②

**A declarative star schema over the warehouse: the grain, the keys, and the
[[measures]] — in a few dozen lines a reviewer reads in one screen.**

Lives in `models/`. Each file exposes a variable named `model`.

---

## What it is

```python
from tracebi import DataModel, DuckDBConnector

model = DataModel("portfolio_model")
model.add_connector(DuckDBConnector("warehouse", database="data/warehouse.duckdb"))

model.add_table("fact_holdings", connector="warehouse", source="fact_holdings")
model.add_table("dim_issuer",    connector="warehouse", source="dim_issuer")

model.add_dimension("dim_issuer", table_name="dim_issuer",
                    key_col="issuer_id", attributes=["issuer", "sector"])

model.add_fact("fact_holdings", table_name="fact_holdings",
               measures=["fair_value", "cost_basis"],
               foreign_keys={"dim_issuer": "issuer_id"})

model.add_measure("fair_value", column="fair_value", agg="sum")
```

That is the whole shape: connectors, tables, dimensions, facts, measures.

## Why it is only a declaration

The model is the second [[freeze-points|freeze point]] — the **semantic
contract** between the analysis and the reporting.

- It **reads the sink**. It never sees the [[transform]] that produced it.
- Reports speak only its vocabulary — measure names and dimension attributes,
  never raw SQL.

That constraint is what makes a figure re-runnable, and therefore what makes a
[[receipts|receipt]] possible. A report cannot ask for something the model has
not declared, so anything the model *can* express is automatically replayable.

## The corollary worth internalising

**Every expressiveness gap in the model pushes work into ungoverned Python** —
a `report.py` whose outputs are stamped `verifiable: false` and never read
green.

So adding a measure kind is not only a convenience feature; it pulls a number
back into the receipted lane. That is why the [[measures]] vocabulary is
deliberately broad and deliberately closed: broad, so real analysis fits; closed,
so nothing arbitrary slips in.

## Validate it

```bash
tracebi validate
```

Chiefly checks that dimension keys are **unique**. A non-unique key silently
inflates every additive measure — it is the failure most worth catching early,
and the one hardest to notice in a finished report.

## Use it anywhere

```python
from tracebi.model_registry import get_model
model = get_model("portfolio_model")
```

No web server required. The same registry backs the CLI, notebooks, and the
served UI.

## Related

- [[measures]] — every measure kind
- [[queries]] — what a report may ask it
- [[freeze-points]] — why it is frozen
- [[report]] — what reads it
