# Sink contracts

**Closed, declarative checks a [[transform]]'s tables must satisfy before the
data counts. The narrowest honest claim about phase ①.**

---

## Why they exist

[[lineage]] deliberately stops at the sink. Everything above it is arbitrary
pandas, which nothing machine-checks — see
[[the-three-phase-workflow#Where trust starts]].

A sink contract does not close that gap. It narrows it: it lets you state, in a
form a machine can re-run, what the tables you just wrote must be true of.

## Declaring one

After the writes, in the same transform:

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

The vocabulary is **closed**. Every check also takes an optional `note=`, which
the report's methodology appendix shows beside it:

| Check | Signature |
|---|---|
| row count | `c.rows(table, at_least=…, at_most=…, exactly=…)` |
| unique key | `c.unique(table, columns=[…])` |
| no NULLs | `c.not_null(table, columns=[…])` |
| foreign key | `c.foreign_key(table, column, refers_to=(dim_table, dim_col))` |
| value domain | `c.values(table, column, within=[…])` |
| reconciliation | `c.reconcile(table, column, against=(other_table, other_col), by=key_col, tolerance=0.0)` |

No callables, for the same reason [[measures]] rejects them: a check that cannot
be serialized cannot be re-run by someone else. The reference declaration is
`examples/portfolio_project/transforms/holdings_transform.py`.

The checks run as read-only SQL against the tables you just sank.

## What happens

- **A failed check raises at sink time.** The transform stops; bad data does not
  become a [[freeze-points|freeze point]].
- **Success records a certificate** — `data/warehouse.contracts.json` — carrying
  per-table fingerprints.

Report manifests join against that certificate, so a built report can say what
the warehouse certified about itself at build time.

## Statuses

| Status | Meaning |
| --- | --- |
| `satisfied` | the checks passed, and the data still matches the fingerprint |
| `stale` | the tables were re-sunk after the transform checked them — the certificate no longer describes this data |
| `no_contract` | the transform declared none |

**`stale` never reads green.** A certificate that describes different data is
not evidence.

## Re-running them

```bash
tracebi verify output/report.html.manifest.json --contracts
```

Re-runs the recorded contracts against the *current* warehouse **and** compares
the certified fingerprints to the data now — catching an out-of-band change that
would still pass the declared checks.

## The locked language

> **"the sink satisfied its contract"** — never *"the transform was verified"*.

A contract checks what you thought to check. It says nothing about the pandas
that produced the numbers, and nothing about whether the numbers are right.
Contract status **never colours a figure status**; it is reported in its own
block.

That wording is fixed for the same reason as the rest of the vocabulary in
[[receipts#The locked language]]: paraphrasing is how an honest guarantee
becomes an overclaim.

## Related

- [[transform]] — where contracts are declared
- [[receipts]] — the separate, downstream claim
- [[cli]] — `tracebi verify --contracts`
