# Model — phase ②

**A declarative star schema over the warehouse: the grain, the keys, and the
[[measures]] — in a few dozen lines a reviewer reads in one screen.**

Lives in `models/`, one file per model: `models/<name>.yaml`.

---

## What it is

```yaml
# models/portfolio_model.yaml
name: portfolio_model
label: Direct Lending Portfolio

connectors:
  - name: warehouse
    type: warehouse          # the project's warehouse, wherever tracebi.yaml puts it

tables:
  - {name: fact_holdings, connector: warehouse, source: fact_holdings}
  - {name: dim_issuer,    connector: warehouse, source: dim_issuer}

dimensions:
  - name: dim_issuer
    table: dim_issuer
    key: issuer_id
    attributes: [issuer, sector]

facts:
  - name: fact_holdings
    table: fact_holdings
    measures: [fair_value, cost]
    foreign_keys: {dim_issuer: issuer_id}

measures:
  - {name: fair_value, column: fair_value, agg: sum, format: currency0}
```

That is the whole shape: connectors, tables, dimensions, facts, measures.
The file declares meaning; the connector says where the data is kept — see
[[models-and-connectors]].

A model is a declarative `models/<name>.yaml` by default (`.json` is the same schema, see [[model-json]]), with a `.py` file for anything exotic: the same connectors, tables, dimensions, facts and measures as builder calls on a `DataModel` held in a variable named `model` (`tracebi new-model --python`; `tracebi migrate model` converts one back to YAML). The reason is the remote case. An agent without access to the server can draft a YAML model and publish it through the gateway, because a YAML file runs no code. A Python model runs on the server with its connections, so it stays a file someone reviews and commits.

## Why it is only a declaration

The model is the second [[freeze-points|freeze point]] — the **semantic
contract** between the analysis and the reporting.

- It **reads the sink**. It never sees the [[transform]] that produced it.
- Reports speak only its vocabulary — measure names and dimension attributes,
  never raw SQL.

That constraint is what makes a figure re-runnable, and therefore what makes a
[[trace]] possible. A report cannot ask for something the model has
not declared, so anything the model *can* express is automatically replayable.

## The corollary worth internalising

**Every expressiveness gap in the model pushes work into ungoverned Python** —
a `report.py` whose outputs are stamped `verifiable: false` and never read
green.

So adding a measure kind is not only a convenience feature; it pulls a number
back into the verifiable lane. That is why the [[measures]] vocabulary is
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
