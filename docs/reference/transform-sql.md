# SQL transforms

A transform is a `.sql` file of DuckDB statements, run top to bottom in one
fresh connection to the warehouse, with its sink contract beside it in a
`.contract.yaml`.

```
transforms/
  holdings_transform.sql             # the transform
  holdings_transform.contract.yaml   # what the tables it writes must satisfy
```

```bash
tracebi new-transform "Holdings"      # transforms/holdings.sql + holdings.contract.yaml
tracebi run-transform holdings        # runs it, then the contract; prints form: sql
```

The reference is `examples/portfolio_project/transforms/holdings_transform.sql`.
The pandas version, `holdings_transform_pandas.py`, writes identical tables:
every fingerprint equal, row order included.

## How it runs

`tracebi run-transform <name>`, a pipeline's `transform` step and a schedule's
`refresh` all find `transforms/<name>.sql`, `.py` or `.ipynb`, run it, and
print `form: sql | python | notebook`. A pipeline run records the form, and
`tracebi run-pipeline <name> --status` and the model's Transform tab show it.

A SQL transform runs in five steps:

1. Its two placeholders are substituted.
2. Each table its `-- source:` lines name is loaded through its connection.
3. Its statements run in order in one fresh read-write DuckDB connection to
   the warehouse `tracebi.yaml` names, with the project's `engine` limits. A
   failing statement stops the run with its number and line:
   `transforms/x.sql: statement 6 (line 60) failed: Catalog Error: …`.
4. On the object tier, every table it created is written out.
5. The connection closes, then `<name>.contract.yaml` runs if there is one.

`TEMP` tables and `TEMP MACRO`s vanish with the connection. Use
`CREATE OR REPLACE` so a rerun replaces the tables.

This connection may read files and, on the object tier, load `httpfs`. It runs
only from the CLI, the scheduler and an approved code request, never to answer
a reader.

## Where a table lands

A table the script creates without `TEMP` (`CREATE OR REPLACE TABLE fact_x AS
…`) is a sink table.

| Tier (`warehouse.tier`) | `CREATE OR REPLACE TABLE fact_x` lands | `{{ sink }}` is |
|---|---|---|
| `file` (default) | In `data/warehouse.duckdb` | The `.duckdb` path |
| `object` | As `<location>/fact_x.parquet`, written after the script | The prefix (`s3://bucket/project`, or a directory) |
| `remote` | In the attached database (`USE`d for the run) | The attach string |

On the object tier a script may write a table itself instead, which is what
`tracebi new-transform` scaffolds there:

```sql
CREATE OR REPLACE TEMP TABLE dim_x AS SELECT …;
COPY dim_x TO '{{ sink }}/dim_x.parquet' (FORMAT PARQUET);
```

Use one way or the other for a table. A table that is both created and
copied is written twice.

## Views

```sql
CREATE OR REPLACE VIEW fact_holdings_by_sector AS
SELECT i.sector, count(*) AS positions, round(sum(h.fair_value), 2) AS fair_value
FROM fact_holdings h
JOIN dim_issuer i USING (issuer_id)
GROUP BY i.sector;
```

A view the script creates without `TEMP` is a sink view. It lands in the
warehouse as a definition, not as rows. A model table can name it
(`source: fact_holdings_by_sector`) and reads it as it reads a table. A
contract check runs against it as against a table, and `tracebi verify
--contracts` re-runs that check the same way.

Materialize the facts you aggregate. View the derivations. When the facts
outgrow a file, move the warehouse to another tier, not the design.

**What a view may read.** Only the warehouse's own tables and views, by their
plain names. The run checks each view it created. A view that reads anything
else fails the run and is dropped, and the message names the view, what it
read and the fix:

```
transforms/x.sql: view v_ratings reads crm.issuer_ratings, a -- source: table,
which is attached for the run only and never lands in the warehouse. A sink
view may read only the warehouse's own tables and views; materialize it:
CREATE OR REPLACE TABLE v_ratings AS …, or move the read into a table the view
selects from
```

| Refused | Why |
|---|---|
| A `-- source:` table (`crm.issuer_ratings`) | It is attached for the run only. A model's query connection cannot reach it. |
| A file or URL (`read_csv(…)`, `read_parquet(…)`, `'inputs/x.csv'`, `https://…`) | The query connection is locked: no files, no network. |
| A `TEMP` table or a `TEMP MACRO` | It is gone when the connection closes. |
| A table named with its database (`warehouse.main.x`) | The model attaches the warehouse under another name. |

There is a second reason. A view runs its query each time it is read. A view
over a source would read the source again at read time, so the certificate's
claim that the sink satisfied its contract would describe data that has since
changed, and `tracebi verify` would compare against something new.

**On each tier.**

| Tier | A view |
|---|---|
| `file` | Kept in `data/warehouse.duckdb` |
| `remote` | Kept in the attached database |
| `object` | Refused. The tier keeps one Parquet file per table and no definitions. Materialize it with `CREATE OR REPLACE TABLE`. |

**What the certificate records.** With a contract beside the transform, the
certificate lists the views the run created under the transform's `views`:

```json
"views": [
  {"name": "fact_holdings_by_sector", "bases": ["dim_issuer", "fact_holdings"],
   "definition_sha256": "fc7a…"}
]
```

`bases` are the tables and views the definition names. A view a check
touches also has a fingerprint under `tables`, read like a table. The app
marks a view with its own glyph and says which transform defined it over
which tables.

A Python transform's `write()` always materializes. The reference project's
`holdings_transform_pandas.py` writes the same rows as a table.

## Placeholders

There are two. Each is substituted as text with any single quote doubled, so
put it inside a `'…'` literal.

| Placeholder | Becomes |
|---|---|
| `{{ sink }}` | `str(sink_target(root))`: the warehouse address on its tier |
| `{{ root }}` | The project root, absolute |

Anything else between `{{` and `}}` is an error naming it:
`transforms/x.sql: {{ warehouse }} is not a placeholder; a SQL transform has
two, {{ sink }} and {{ root }}`. There are no loops, conditionals or `ref()`s.

## Relative paths

A relative read, `read_csv('inputs/holdings.csv')`, resolves against the
project root (the connection's `file_search_path`), whatever directory the run
started from. A write names its destination with `{{ sink }}` or `{{ root }}`.

## Read a table from a database

Declare the database as a connection ([[connections-yaml]]), then name each
table in a `-- source:` line in the header, above the first statement:

```sql
-- source: crm.issuer_ratings fallback: inputs/issuer_ratings.csv

CREATE OR REPLACE TABLE dim_rating AS
SELECT … FROM crm.issuer_ratings …;
```

```
-- source: <connection>.<table> [fallback: <path>.csv]
```

| Part | Meaning |
|---|---|
| `<connection>` | `connections/<connection>.yaml`, any type (`tracebi connect crm --kind postgres` writes one). Letters, digits and underscores. |
| `<table>` | A table that connection's connector loads. |
| `fallback:` | A committed CSV snapshot inside the project, read only when the connection's `${VAR}` is unset (a fresh clone, CI). Any other failure (server down, table missing, wrong password) stops the run. With no fallback, an unset variable stops the run, naming it. |

- Before the first statement, each table loads in full through the
  connection's connector, with nothing pushed down. The SQL reads it as
  `<connection>.<table>`, from an in-memory database attached for this run
  only, so none of it lands in the warehouse.
- The loaded rows are sorted by every column, because a database table has no
  row order.
- Refused, naming the line: `-- source: crm` with no table, a table named
  twice, a `-- source:` line below the first statement, and anything after the
  table except `fallback: <path>`.

A source is a name the SQL reads, not a placeholder.

### What the certificate records

With a `<name>.contract.yaml` beside the transform, the certificate
(`data/warehouse.contracts.json`) records each load under the transform's
`sources`:

```json
"sources": {
  "crm.issuer_ratings": {
    "connection": "crm", "table": "issuer_ratings",
    "rows": 12, "fingerprint": "5840…", "loaded_at": "2026-10-20T…Z"
  }
}
```

When the snapshot stood in, it also records `"source_fallback": "csv"`,
`"fallback": "inputs/issuer_ratings.csv"` and the `reason` (the unset
variable). The claim is then exact: the sink satisfied its contract against
those inputs. Each report manifest's `transform_contracts` entry carries the
same `sources` (without the reason), so a report's trace says where the data
came from, including when the CRM was not reached. It never changes the
contract's status.

`tracebi verify <manifest> --contracts` re-reads each recorded source (a
snapshot load from the snapshot again) and compares fingerprints:

| Result | Meaning |
|---|---|
| `unchanged` | The source returns the same data. |
| `CHANGED` | A re-run of the transform would write different tables. Exit 1. The figures may still reproduce, because the warehouse did not move. |
| `not checked` | The source cannot be read now (variable unset, server down). Neither green nor a failure. |

**In Python:** `tracebi.transforms.load_source(ref, root, fallback=None)`
returns `(frame, record)`, the same load and record. Pass the records to
`contract(name, warehouse=..., sources={ref: record})` and the certificate
says the same thing. `holdings_transform_pandas.py` does this.

## Cells

`-- %% [markdown]` and `-- %%` lines mark cells, like `# %%` in Python, so an
editor that understands percent cells can fold them. The run ignores them.

## The contract file

`<name>.contract.yaml` declares the [[sink-contracts|sink contract]]. It uses
the same checks and parser as `with contract(...)` in Python and writes the
same certificate. It also runs beside a `.py` or `.ipynb` transform.

```yaml
name: holdings          # the certificate's record; default: the transform's file name
note: >-                # the stated methodology, recorded as written, never checked
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

- Every check takes a `note`.
- The top level holds only `name`, `note` and `checks`. An unknown key, check
  or parameter is an error naming the file and entry
  (`checks[0] must name exactly one check …`).
- No checks, or all commented out, declares nothing and writes nothing.
- The checks run after the transform's connection closes, through the
  warehouse's own reader, so they check what landed.
- A failed check raises and writes no certificate. Passing means the sink
  satisfied its contract, never that the transform was verified.

## Python transforms

`tracebi new-transform "Name" --python` writes `transforms/<name>.py`:
notebook-shaped pandas that ends with
`DuckDBConnector("warehouse", database=sink_target(ROOT)).write(df, "table")`.
A `.ipynb` runs too. Either runs top to bottom in a fresh namespace. A pandas
transform keeps working until you rewrite it; nothing converts it. Lineage
starts at the sink, so a Python transform is as traceable as a SQL one.

## One file per name

`x.sql` beside `x.py` or `x.ipynb` is refused by `run-transform`, naming both,
and `new-transform` will not create the second.
