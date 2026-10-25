# Transforms

A transform is a file in `transforms/` that reads raw data, cleans it, and
writes star-schema tables into the warehouse. Here is the shape of the
reference project's transform:

```sql
-- transforms/holdings.sql: DuckDB, top to bottom, one fresh connection
CREATE OR REPLACE TEMP TABLE raw AS
SELECT * FROM read_csv('inputs/holdings.csv', all_varchar = true);

-- whatever the data needs: regexp_replace, TRY_CAST, QUALIFY row_number() …

CREATE OR REPLACE TABLE dim_issuer AS
SELECT row_number() OVER (ORDER BY issuer) AS issuer_id, issuer, sector
FROM (SELECT DISTINCT issuer, sector FROM keyed);
CREATE OR REPLACE TABLE fact_holdings AS SELECT …;
```

`TEMP` tables are scratch. The tables created without `TEMP` (`dim_issuer`,
`fact_holdings`) land in the warehouse. Those table names are what the model
reads. See [[transform-sql]] for the placeholders `{{ sink }}` and `{{ root }}`
and where tables land on each warehouse tier.

## Create and run one

```bash
tracebi new-transform "Holdings"     # transforms/holdings.sql + holdings.contract.yaml
tracebi run-transform holdings       # prints form: sql
```

`tracebi run-transform` runs the file top to bottom in a fresh state: a SQL
file in one new connection, a Python file in a new namespace. It prints which
form ran, and a pipeline run records it.

## Write it in pandas or polars instead

```bash
tracebi new-transform "Holdings" --python
```

This writes `transforms/holdings.py` as a notebook-shaped file: `# %%` cells
and `# %% [markdown]` prose that VS Code, Cursor, PyCharm and Jupyter (with
jupytext) open as a notebook. It ends by writing frames:

```python
from tracebi import DuckDBConnector
from tracebi.project_config import sink_target

wh = DuckDBConnector("warehouse", database=sink_target(ROOT))
wh.write(dim_issuer, "dim_issuer")
wh.write(fact_holdings, "fact_holdings")
```

A `.ipynb` notebook works too. The reference project keeps
`holdings_transform_pandas.py` beside `holdings_transform.sql`; both write
identical tables.

## Add a sink contract

Put the checks the tables must pass in a file beside the transform:

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

A Python transform can declare the same checks in code:
`with contract("holdings", warehouse=sink_target(ROOT)) as c: c.rows("fact_holdings", at_least=1)`.
A failed check stops the run. See [[sink-contracts]].

## Rules

- **One file per name.** `x.sql` beside `x.py` is refused, naming both.
- **Rerunnable.** A rerun replaces the warehouse tables (`CREATE OR REPLACE`
  in SQL, `write()` in Python). It never appends.
- **Nothing downstream reads the transform file.** Models read only the
  tables it wrote.
- **Lineage is traced from the sink, not through the transform.** Review a
  transform as you review any code in git.

## Why it works this way

Cleaning real data takes whatever tools the data needs, so TraceBi leaves this
stage open. What it checks is the result: the tables that land and the
contract they satisfy.

## Next

- Write a SQL transform: [[transform-sql]]
- Run it with its reports: [[pipeline-yaml]]
