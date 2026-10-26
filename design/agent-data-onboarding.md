# Agent-driven data onboarding

Decided 2026-10-26 with the owner. One note, six decisions. Each package below
cites the section it implements. Dated in NOTES.md.

## 1. What is locked: the logic, not the data

The product's promise is that an agent cannot make a number up. Until now the
mechanism was a frozen sink: a transform wrote tables once, and everything
downstream read that copy. The owner's direction is to move the lock up a
level: **what is locked is the logic and the queries** (the model, each
figure's query, their fingerprints), and **the data may be live**. A frozen
copy is then a choice a person makes when they want to keep a set of numbers,
not the only way the system works.

What this changes and what it does not:

- A built report is already a snapshot: the page embeds the slice it read and
  the manifest records every query and fingerprint. That is the "lock in the
  Q3 numbers" the owner described. It gets a name in the product: **a kept
  build** (a build the person marks as kept, listed by name, never overwritten
  by a refresh). Today every rebuild overwrites `output/<name>.html`; a kept
  build is copied aside with its manifest and cover under
  `output/<name>.kept/<label>/` and served by `/api/reports/{name}/kept`.
- `verify` keeps its job. It re-runs the recorded queries and says whether the
  logic reproduces the recorded result. Under live data the answer "the data
  moved, the logic did not" is a normal outcome, not a failure; the verdict
  vocabulary already separates source drift from a model change and that
  distinction becomes the headline, not the footnote.
- The sink view rule ("a view may read only what is frozen") relaxes
  accordingly: a view may read what the model's query connection can reach.
  Today that is the warehouse; with §2 it includes attached sources, read-only.
  The refusal for files and TEMP objects stays.
- The certificate stays what it is: evidence that the sink's checks passed when
  a run wrote it. Under live reads it also records the source watermark it saw.

This is a re-framing of the trust story, so the words change first: in the
docs and the app, "frozen" is replaced by "locked logic" and "kept build". The
phrases that stay word for word: "the sink satisfied its contract", "a figure's
number is only ever a query result", and what `verify` does not claim.

## 2. How data comes in: the way everyone does it

Today a `-- source:` line reads the whole table through SQLAlchemy into pandas
and hands the frame to DuckDB. That is the slow path. The method the field
settled on (dbt's adapters, Tableau extracts, DuckDB users generally) is:
query where the data lives when you can, and when you copy, copy in bulk,
columnar, with pushdown.

- **Native scanners first.** Postgres, MySQL and SQLite attach into the
  transform's DuckDB connection through DuckDB's own extensions
  (`postgres`, `mysql`, `sqlite`), read-only. The transform's SQL reads
  `crm.issuer_ratings` as before; DuckDB pushes projections and filters down
  and moves rows as Arrow, with no pandas in between. The fingerprint the
  certificate records is computed in DuckDB over the sorted rows, so it equals
  today's.
- **Arrow where there is no scanner.** Snowflake and BigQuery through their
  Arrow result APIs (BigQuery's Storage API); any other SQLAlchemy URL through
  ADBC when a driver exists, else `read_sql` in chunks as the floor.
- **The model may read a source live.** The query connection attaches the
  allowlisted sources the same way, READ_ONLY, before the lock; the lock then
  allows exactly those catalogs. A model table may name `crm.issuer_ratings`
  directly. The connection's own credentials are resolved at attach time and
  never stored.
- **Incremental loads** (`since: <column>`) come after, with their own note:
  a watermark in the certificate and a merge rule.

## 3. Saving back: tables and views to a database or a bucket

A result may leave the warehouse. Two forms, one vocabulary:

- In a transform: `-- sink: <connection>` on a `CREATE TABLE` or `CREATE VIEW`
  line's statement sends that table to the named connection instead of (or as
  well as) the warehouse; `COPY (…) TO 's3://…/x.parquet'` already works for a
  bucket through the warehouse's object credentials.
- From the app and the gateway: **Export to…** on a warehouse table or view
  writes it to a chosen connection (a table, through the connector's `write`)
  or to an object prefix (Parquet). Recorded as a run row; an admin action.

## 4. Connections are set up by a person, in the app

The Sources page gains **Add a connection**: pick a type (Postgres, MySQL,
SQLite, DuckDB, Snowflake, BigQuery, an S3 or GCS prefix, an uploaded CSV or
Parquet), fill the form, the secret goes to the encrypted store, Test, and the
app writes `connections/<name>.yaml` as a person would. A connection then lists
its tables with row estimates, and the person ticks **which tables agents may
read**: `agents: {tables: [a, b]}` in the YAML (`*` for all, absent for none).
That allowlist is what the gateway and the model's live attach may see.
Editing a connection edits the file; deleting one removes it when nothing
reads it, and says what does otherwise.

## 5. The agent takes it from there

Five gateway tools, each inside the gates that already exist:

| Tool | Does | Gate |
|---|---|---|
| `list_connections` | connections, their type, their allowlisted tables | viewer |
| `list_source_tables(connection)` | the allowlisted tables with row estimates and columns | viewer |
| `describe_source_table(connection, table)` | columns, types, a profile, a 20-row sample | viewer |
| `propose_transform(name, sql, contract)` | writes `transforms/<name>.sql` + `.contract.yaml` as a code request | analyst; an admin approves, it runs once |
| `export_table(table, to)` | §3's Export to… | admin |

`start_draft(kind="model")` already exists; the SOP for agents becomes:
explore → propose a transform → (approval) → draft the model → build the
report → publish (approval). `author_report`'s prompt gains the first steps.

## 6. The model is the semantic layer, and it says so

The model page's summary becomes **Semantic layer**: the grain in one
sentence; every measure with its label, description, expression, format and
the questions it answers; every dimension's attributes with descriptions;
synonyms. The same text is what `get_context --model` and `describe_model`
hand an agent, shown on the page under **What an agent sees**, so a person
curating the model is curating the agent's vocabulary. The spec gains
`description` and `synonyms` on dimensions, attributes and measures where it
lacks them, and `questions: [..]` on a model (example questions, used by Ask
and by the agent prompt). Nothing computes from these fields; they are words.
