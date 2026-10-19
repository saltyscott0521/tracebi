# SQL transforms

**A phase ① transform is a `.sql` file by default: DuckDB statements, run top
to bottom in one fresh connection to the warehouse. Python is the escape hatch.
The sink contract sits beside it as a `.contract.yaml`.**

```
transforms/
  holdings_transform.sql             # the transform
  holdings_transform.contract.yaml   # what the tables it lands must satisfy
```

```bash
tracebi new-transform "Holdings"      # → transforms/holdings.sql + holdings.contract.yaml
tracebi run-transform holdings        # runs it, then the contract; prints form: sql
```

The reference is
`examples/portfolio_project/transforms/holdings_transform.sql`; the same work
in pandas, `holdings_transform_pandas.py`, sinks identical tables (every
table's fingerprint equal, row order included).

---

## How it runs

`tracebi run-transform <name>` (and the `transform` step of a
[[pipeline-yaml|pipeline]], and a report's `refresh`) finds
`transforms/<name>.sql`, `.py` or `.ipynb`, runs it and prints
`form: sql | python | notebook`; a pipeline run records the form, and
`tracebi run-pipeline <name> --status` and the model's Transform tab show it.

A SQL transform:

1. has its two placeholders substituted (below);
2. runs statement by statement, in order, in **one** fresh read-write DuckDB
   connection to the warehouse `tracebi.yaml` names, with the project's
   `engine` limits. A failing statement stops the run with its number and
   line: `transforms/x.sql: statement 6 (line 60) failed: Catalog Error: …`;
3. on the object tier, lands every table it created (below);
4. closes the connection, then runs `<name>.contract.yaml` if there is one.

Nothing persists between runs but the tables that landed: `TEMP` tables and
`TEMP MACRO`s are scratch and vanish with the connection. Keep it idempotent
with `CREATE OR REPLACE`, so a rerun replaces the tables.

The connection is not locked like a model's query connection: it may read
files and, on the object tier, load `httpfs`. It runs only from the CLI, the
scheduler and an approved code request, never to answer a reader.

## Where a table lands, per tier

A table the script creates (`CREATE OR REPLACE TABLE fact_x AS …`, not `TEMP`)
is a **sink table**.

| Tier (`tracebi.yaml` `warehouse.tier`) | `CREATE OR REPLACE TABLE fact_x` lands | `{{ sink }}` is |
|---|---|---|
| `file` (default) | in `data/warehouse.duckdb` itself | the `.duckdb` path |
| `object` | as `<location>/fact_x.parquet`, written after the script | the prefix (`s3://bucket/project`, or a directory) |
| `remote` | in the attached database (`USE`d for the run) | the attach string |

On the object tier a script may also write a table itself, which is the idiom
`tracebi new-transform` scaffolds there:

```sql
CREATE OR REPLACE TEMP TABLE dim_x AS SELECT …;
COPY dim_x TO '{{ sink }}/dim_x.parquet' (FORMAT PARQUET);
```

Use one or the other for a table: a `CREATE`d table that is also `COPY`'d is
written twice.

## Placeholders

Exactly two, substituted as text with any single quote doubled, so each
belongs inside a `'…'` literal:

| Placeholder | Becomes |
|---|---|
| `{{ sink }}` | `str(sink_target(root))`: the warehouse address on its tier |
| `{{ root }}` | the project root, absolute |

Anything else between `{{` and `}}` is an error naming it:
`transforms/x.sql: {{ warehouse }} is not a placeholder; a SQL transform has
two, {{ sink }} and {{ root }}`. There are no loops, conditionals or
`ref()`s: one transform file per pipeline, statements in order.

## Relative paths

A **read** with a relative path, `read_csv('inputs/holdings.csv')`, resolves
against the project root: the connection's `file_search_path` is set to it, so
the transform reads the same file whichever directory it was started from. A
**write** names its destination with `{{ sink }}` or `{{ root }}`.

## Cells

`-- %% [markdown]` and `-- %%` lines mark cells, as `# %%` does in a Python
transform, so an editor that understands percent cells folds them. They are
comments: the run ignores them.

## The contract file

`<name>.contract.yaml` beside the transform declares the
[[sink-contracts|sink contract]] in the same closed vocabulary as
`with contract(...)` in Python, through the same parser, and writes the same
certificate. It is honoured beside a `.py` or `.ipynb` transform too (run after
the script).

```yaml
name: holdings          # the certificate's record; default: the transform's file name
note: >-                # the STATED methodology, recorded verbatim, never verified
  rows with no keyable issuer dropped and counted
checks:
  - rows: fact_holdings          # the check, with its table as the value
    at_least: 10                 # its parameters beside it
    note: under 10 means a truncated pull
  - unique: dim_issuer
    columns: [issuer_id]
  - foreign_key: fact_holdings
    column: issuer_id
    refers_to: [dim_issuer, issuer_id]
```

| Check | Parameters |
|---|---|
| `rows` | `at_least`, `at_most`, `exactly` (whole numbers, any of them) |
| `unique` | `columns` (a list) |
| `not_null` | `columns` (a list) |
| `foreign_key` | `column`, `refers_to: [table, column]` |
| `values` | `column`, `within` (a list) |
| `reconcile` | `column`, `against: [table, column]`, `by`, `tolerance` (default 0) |

Every check takes a `note`. The top level holds only `name`, `note` and
`checks`; an unknown key, a check outside the vocabulary or a parameter it
does not take is an error naming the file and the entry
(`checks[0] must name exactly one check …`). No checks, or all of them
commented out, declares nothing and writes nothing.

The checks run after the transform's connection is closed, through the
warehouse's own reader, so they check what landed (on the object tier the
transform's connection also holds in-memory tables that are not the sink).
A failed check raises and no certificate is written; the claim is **the sink
satisfied its contract**, never that the transform was verified.

## The escape hatch: Python

`tracebi new-transform "Name" --python` scaffolds `transforms/<name>.py`,
notebook-shaped pandas that ends by writing frames:
`DuckDBConnector("warehouse", database=sink_target(ROOT)).write(df, "table")`.
A literal `.ipynb` runs too. Either runs top to bottom in a fresh namespace.
Nothing is converted: a pandas transform keeps working until its author
rewrites it. The trace line is drawn at the sink, so a Python transform is as
traceable as a SQL one.

## One file per name

A transform is one file. `x.sql` beside `x.py` (or `x.ipynb`) is refused by
`run-transform`, naming both, and `new-transform` will not create the second.

## Related

- [[transform]] — the phase, and why it is unconstrained
- [[sink-contracts]] — what a certificate says, and what it does not
- [[pipeline-yaml]] — the pipeline that runs a transform, then the reports
- [[tracebi-yaml]] — the warehouse block that decides the tier
