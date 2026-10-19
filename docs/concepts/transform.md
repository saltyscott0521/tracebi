# Transform — phase ①

**Unconstrained work that ends by landing clean star-schema tables in the
warehouse. SQL by default; Python is the escape hatch.**

Lives in `transforms/`. This is the one phase the framework does not constrain.

---

## The contract

The contract is **not how you clean**. Window functions, prose parsing, fuzzy
dedupe, three APIs and a spreadsheet — whatever the data needs.

The contract is **what lands**: the named tables at the end of the script.

```sql
-- transforms/holdings.sql — DuckDB, top to bottom, one fresh connection
CREATE OR REPLACE TEMP TABLE raw AS
SELECT * FROM read_csv('inputs/holdings.csv', all_varchar = true);

-- … whatever the data needs: regexp_replace, TRY_CAST, QUALIFY row_number() …

CREATE OR REPLACE TABLE dim_issuer AS
SELECT row_number() OVER (ORDER BY issuer) AS issuer_id, issuer, sector
FROM (SELECT DISTINCT issuer, sector FROM keyed);
CREATE OR REPLACE TABLE fact_holdings AS SELECT …;
```

Those table names are the [[freeze-points|freeze point]]. Nothing downstream
reads this file. Where a created table lands follows the project's warehouse
tier (`tracebi.yaml`), and two placeholders, `{{ sink }}` and `{{ root }}`,
cover the rest: see [[transform-sql]].

## Run it

```bash
tracebi new-transform "Holdings"     # transforms/holdings.sql + holdings.contract.yaml
tracebi run-transform holdings       # prints form: sql
```

`run-transform` executes the file **top to bottom, fresh** — a SQL file in one
new connection, a Python file in a new namespace — so the sink never comes
from out-of-order state. It reports which form ran, and a pipeline run records
it.

## The escape hatch: pandas or polars

When the cleaning outgrows SQL, write Python:
`tracebi new-transform "Holdings" --python` scaffolds a notebook-shaped `.py`
(`# %%` percent cells with `# %% [markdown]` prose, so VS Code, Cursor,
PyCharm and Jupyter via jupytext open it as a notebook) that ends by writing
frames:

```python
from tracebi import DuckDBConnector
from tracebi.project_config import sink_target

wh = DuckDBConnector("warehouse", database=sink_target(ROOT))
wh.write(dim_issuer, "dim_issuer")
wh.write(fact_holdings, "fact_holdings")
```

A literal `.ipynb` works too. The reference project keeps
`holdings_transform_pandas.py` beside `holdings_transform.sql` as the example:
both sink identical tables. A transform is one file: `x.sql` beside `x.py` is
refused, naming both.

## Keep it idempotent

A rerun replaces the warehouse tables rather than appending
(`CREATE OR REPLACE` in SQL, `write()` in Python). This is what makes
refreshing a [[freeze-points|freeze point]] safe to do at any time.

## Declare a sink contract

Beside the transform, state what the tables must satisfy:

```yaml
# transforms/holdings.contract.yaml
name: holdings
checks:
  - rows: fact_holdings
    at_least: 1
  - not_null: fact_holdings
    columns: [issuer_id]
  - foreign_key: fact_holdings
    column: issuer_id
    refers_to: [dim_issuer, issuer_id]
```

A Python transform may instead end with the same checks in code,
`with contract("holdings", warehouse=sink_target(ROOT)) as c: c.rows("fact_holdings", at_least=1)`.
A failed check raises at sink time. Success records a certificate the report
manifests join against. See [[sink-contracts]].

## What this phase is *not*

Lineage is **not** traced through this code, deliberately. The trust boundary
starts at the sink — see [[trace]] and
[[the-three-phase-workflow#Where trust starts]].

Phase ① is trusted the way you trust reviewed code in git.

## Related

- [[transform-sql]] — the SQL form, the tiers, the placeholders, the contract file
- [[sink-contracts]] — checks at the boundary
- [[model]] — what reads the tables you land
- [[cli]] — `tracebi new-transform`, `tracebi run-transform`
