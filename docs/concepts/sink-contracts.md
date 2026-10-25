# Sink contracts

A sink contract is a list of checks a transform's tables must pass before the
data counts. It sits beside the transform in `transforms/<name>.contract.yaml`:

```yaml
name: holdings
checks:
  - rows: fact_holdings
    at_least: 10
  - unique: dim_issuer
    columns: [issuer_id]
  - foreign_key: fact_holdings
    column: issuer_id
    refers_to: [dim_issuer, issuer_id]
```

A Python transform can declare the same checks after it writes its tables:

```python
from tracebi.contracts import contract

with contract("holdings", warehouse=WAREHOUSE) as c:
    c.rows("fact_holdings", at_least=10)
    c.unique("dim_issuer", ["issuer_id"])
    c.not_null("fact_holdings", ["fund_id", "issuer_id", "fair_value"])
    c.foreign_key("fact_holdings", "issuer_id",
                  refers_to=("dim_issuer", "issuer_id"))
    c.values("dim_issuer", "sector", within=["Software", "Energy", "Consumer"])
    c.reconcile("fact_holdings", "fair_value",
                against=("raw_holdings", "fair_value"), by="position_id")
```

The reference is
`examples/portfolio_project/transforms/holdings_transform.contract.yaml`.

## The checks

Both forms use the same six checks. Each also takes an optional `note`, which
the report's methodology shows beside it.

| Check | Signature |
|---|---|
| Row count | `c.rows(table, at_least=…, at_most=…, exactly=…)` |
| Unique key | `c.unique(table, columns=[…])` |
| No nulls | `c.not_null(table, columns=[…])` |
| Foreign key | `c.foreign_key(table, column, refers_to=(dim_table, dim_col))` |
| Value domain | `c.values(table, column, within=[…])` |
| Reconciliation | `c.reconcile(table, column, against=(other_table, other_col), by=key_col, tolerance=0.0)` |

The list is closed and takes no functions. A check that cannot be written
down cannot be re-run by someone else. The YAML form is in [[transform-sql]].

## What happens when it runs

The checks run as read-only SQL against the tables just written.

- **A failed check stops the run.** Bad data never becomes the warehouse the
  model reads.
- **Success writes a certificate**, `data/warehouse.contracts.json`, with a
  fingerprint per table.

Each report manifest records the certificate's status for the tables it read:

| Status | Meaning |
| --- | --- |
| `satisfied` | The checks passed, and the data still matches the fingerprint. |
| `stale` | The tables were rewritten after the checks ran. The certificate no longer describes this data, and never shows green. |
| `no_contract` | The transform declares no checks. |

## Re-run the checks

```bash
tracebi verify output/report.html.manifest.json --contracts
```

This re-runs the recorded checks against the current warehouse and compares
the certified fingerprints to the data now. It catches a change made outside
the transform that would still pass the checks.

## What to call it

When the checks pass, say "the sink satisfied its contract". Do not say the
transform was verified. A contract checks what you thought to check. It says
nothing about the code that produced the tables or whether the numbers are
right. Its status is reported on its own and never changes a figure's status.

## Next

- Add a contract to a transform: [[transform-sql]]
- See how it appears in a report's trace: [[trace]]
