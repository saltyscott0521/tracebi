# Transform — phase ①

**Unconstrained pandas that ends by landing clean star-schema tables in the
warehouse.**

Lives in `transforms/`. This is the one phase the framework does not constrain.

---

## The contract

The contract is **not how you clean**. Window functions, prose parsing, fuzzy
dedupe, three APIs and a spreadsheet — whatever the data needs.

The contract is **what lands**: the named tables at the end of the script.

```python
from tracebi import DuckDBConnector

# … whatever pandas the data needs …

DuckDBConnector("warehouse", database=WAREHOUSE).write(dim_issuer, "dim_issuer")
DuckDBConnector("warehouse", database=WAREHOUSE).write(fact_holdings, "fact_holdings")
```

Those table names are the [[freeze-points|freeze point]]. Nothing downstream
imports this file.

## Notebook-shaped by default

Scaffolded transforms use `# %%` percent cells with `# %% [markdown]` prose, so
every notebook editor — VS Code, Cursor, PyCharm, Jupyter via jupytext — opens
the file **as a notebook**: collapse cells, run cell by cell, markdown beside
code.

It stays plain, reviewable Python that runs top to bottom.

Literal `.ipynb` transforms work too. Either form runs the same way:

```bash
tracebi run-transform holdings
```

which executes it **top to bottom in a fresh namespace** — the sink never comes
from out-of-order kernel state.

## Keep it idempotent

A rerun replaces the warehouse tables rather than appending. This is what makes
refreshing a [[freeze-points|freeze point]] safe to do at any time.

## Declare a sink contract

After the writes, state what the tables must satisfy:

```python
with contract("holdings", warehouse=WAREHOUSE) as c:
    c.rows("fact_holdings", min=1)
    c.not_null("fact_holdings", "issuer_id")
    c.foreign_key("fact_holdings", "issuer_id", "dim_issuer", "issuer_id")
```

A failed check raises at sink time. Success records a certificate the report
manifests join against. See [[sink-contracts]].

## What this phase is *not*

Lineage is **not** traced through this code, deliberately. The trust boundary
starts at the sink — see [[receipts]] and
[[the-three-phase-workflow#Where trust starts]].

Phase ① is trusted the way you trust reviewed code in git.

## Related

- [[sink-contracts]] — checks at the boundary
- [[model]] — what reads the tables you land
- [[cli]] — `tracebi new-transform`, `tracebi run-transform`
