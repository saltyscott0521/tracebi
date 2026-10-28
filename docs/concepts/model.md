# Models

A model is the semantic layer: the one place that says what the data means.
It is a YAML file in `models/` that names the warehouse tables a report may
read, how they join, the measures it can compute, and the words people use
for them. Here is the one the reference workspace ships, shortened:

```yaml
# models/portfolio_model.yaml
name: portfolio_model
label: Direct Lending Portfolio
description: A direct-lending book, marked at fair value.
questions:
  - Which sectors hold the most fair value?

connectors:
  - name: warehouse
    type: warehouse          # the workspace's warehouse, wherever tracebi.yaml puts it

tables:
  - {name: fact_holdings, connector: warehouse, source: fact_holdings}
  - {name: dim_issuer,    connector: warehouse, source: dim_issuer}

dimensions:
  - name: dim_issuer
    table: dim_issuer
    key: issuer_id
    description: The borrower a loan is made to, and its industry
    attributes:
      - issuer
      - {name: sector, synonyms: [industry]}

facts:
  - name: fact_holdings
    table: fact_holdings
    measures: [fair_value, cost]
    foreign_keys: {dim_issuer: issuer_id}

measures:
  - name: fair_value
    column: fair_value
    agg: sum
    format: currency0
    description: Total fair value
    synonyms: [market value, FV]
```

A model has five parts: connectors, tables, dimensions, facts and measures.
The connector says where the data is kept; the rest says what it means. See
[[models-and-connectors]].

## The words are part of the model

`description` and `synonyms` on the model, a dimension, an attribute and a
measure, and `questions` on the model, are words for people and agents.
Nothing computes from them: a query still names `fair_value`, never "market
value". They are what makes the model a vocabulary rather than a list of
columns.

- The model's page in the app opens on **Semantic layer**: the grain, every
  measure with its definition, description, synonyms and the questions it
  answers, every dimension's attributes, and the example questions.
- **Ask** offers the questions as starting chips, and matches typed words to
  synonyms as well as labels.
- An agent receives the same text: `tracebi context --model <name>`, the
  gateway's `get_context` and `describe_model`, and the page's **What an
  agent sees** all come from one function. Curating the words on the model
  curates what an agent knows.

An attribute is a column name, or an object when it needs words:
`{name, label, description, synonyms}`. Either way a query names it
`dim_issuer.sector`.

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
