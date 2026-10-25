# Models

A model is a YAML file in `models/` that names the warehouse tables a report
may read, how they join, and the measures it can compute. Here is the one the
reference project ships, shortened:

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

A model has five parts: connectors, tables, dimensions, facts and measures.
The connector says where the data is kept; the rest says what it means. See
[[models-and-connectors]].

## Create one

```bash
tracebi new-model "Sales Model"            # models/sales_model.yaml
tracebi validate                           # load every model, check its keys
```

`.json` uses the same schema ([[model-json]]). For anything YAML cannot say,
`tracebi new-model --python` writes a `.py` that builds a `DataModel` in a
variable named `model`. `tracebi migrate model` converts one back to YAML.

## Use it from Python

```python
from tracebi.model_registry import get_model
model = get_model("portfolio_model")
```

No web server is needed. The CLI, notebooks and the app read models through
the same registry.

## Rules

- **A model reads the warehouse and never sees the transform.**
- **Reports ask only for what the model declares**: measure names and
  dimension attributes, never SQL. That is what lets every figure be re-run.
- **Dimension keys must be unique.** A repeated key multiplies the fact rows
  and inflates every sum. `tracebi validate` checks this.
- **YAML runs no code.** An agent without access to the server can draft a
  YAML model and publish it through the gateway. A Python model runs on the
  server with its connections, so it stays a file someone reviews and
  commits.

## Why it works this way

A number the model cannot express ends up in a `report.py`, whose outputs are
stamped `verifiable: false` and never read green. So each new measure kind
brings more numbers back into the checkable path. The [[measures]] list is
broad, so real analysis fits, and closed, so nothing arbitrary gets in.

## Next

- Declare measures: [[measures]]
- Every key of a model file: [[model-json]]
