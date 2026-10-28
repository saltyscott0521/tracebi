# SOP: Onboard a source, from a connection to a report

The procedure an AI agent follows over the gateway (`tracebi mcp`) when a
person has connected a database and nothing has been built from it yet: no
transform, no model. Follow the steps in order.

Read `AGENTS.md` first. It is the brief every agent reads before working in a
TraceBi workspace. This SOP ends where [[sop-authoring]] begins.

## Before you begin

- **A person sets up the connection, not you.** They add it in the app
  (Data › Sources) or with `tracebi connect`, and its credential goes to the
  workspace's encrypted store. You never see a password or a URL that carries
  one.
- **A person decides what you may read.** On the connection they tick the
  tables agents may read: `agents: {tables: [orders, customers]}` in
  `connections/<name>.yaml` (`"*"` for every table; no `agents:` means none).
  A table outside that list answers "not found", exactly as a missing one
  does. Do not look for it another way.
- **What you write is a proposal.** A transform runs on the server with its
  secrets, so you never run one for real. You propose it, and it is dry-run
  at once against a throwaway copy, so you and the reviewer see what it
  would make; an admin reads it in the app and approves it, and approving
  runs it once.

The loop: `describe_workspace` → `read_transform` for what exists →
`describe_source_table` → `propose_transform` (new or a change) → read the
dry run, fix and propose again until it passes → an admin approves → draft
the model.
- **The checks start at the model.** The transform's contract records that
  the sink satisfied its contract when it ran. Stamped queries and `verify`
  cover the model onward; they say nothing about the transform's logic.

## 1. See the workspace, then find the connection

Your first call on a workspace you have not seen:

```json
{ "tool": "describe_project", "arguments": {} }
```

It returns the workspace as one graph, the same one the app's Data › Lineage
map draws: every source (connections, the files under `inputs/`, a connection's
tables), transform, warehouse table, model and report, with `edges` saying
what feeds what. Each node's `passport.agents` says whether you may read it
(`ok` for a source table on the allowlist), and `gap` marks what is wired on
one side only, such as a file no transform reads or a table no model reads.
It tells you what already exists, so you build only what is missing.
(`describe_workspace` is the same tool under the workspace's word.)

Read each transform that exists before you write a new one; one may already
sink what you need, or need only a change:

```json
{ "tool": "read_transform", "arguments": { "name": "shop_orders" } }
```

It returns the file's `text` and its `contract_yaml`, its `form` (`sql`,
`python`, `notebook`), the `tables` it writes, `last_run` (when its sink last
satisfied its contract, and the `sources` that run read, each with `method`
and `snapshot` when a committed snapshot stood in) and `lineage`, per table
and column the columns DuckDB's parse proves it is computed from. It reads
code, never rows. A transform node's `passport.agents.tools` in the graph
names the tools that take its name.

Then the connections themselves:

```json
{ "tool": "list_connections", "arguments": {} }
```

Each connection has its `type` and `agent_tables`, the tables you may read
(`"*"` for all, `[]` for none). If every list is empty, stop and tell the
person: nothing has been opened to agents yet, and they tick the tables on
the Sources page.

## 2. Read the tables you may read

```json
{ "tool": "list_source_tables", "arguments": { "connection": "shop" } }
```

Each table comes with its columns (`{name, type}`) and `rows`: exact for
DuckDB, the database's own estimate (`rows_exact: false`) where it keeps one,
else `null`. A connection that cannot be reached answers `ok: false` with a
`reason`, and `variable` when an unset `${VAR}` is why: tell the person which
one to set.

Then look at each table you will use:

```json
{ "tool": "describe_source_table",
  "arguments": { "connection": "shop", "table": "orders", "sample": 20 } }
```

It returns the columns, a profile of each (nulls, distinct values, range,
mean, commonest values) and `sample` rows (at most 500) with the `total`.
Find the grain (what one row is), the keys, and the columns that need
cleaning before you write a line of SQL.

## 3. Propose the transform

Write one SQL transform: a `-- source:` header line per table it reads, then
DuckDB statements that clean the data and sink star-schema tables with
`CREATE OR REPLACE TABLE`. Name the tables by role (`fact_*`, `dim_*`).
[[transform-sql]] is the reference.

```sql
-- source: shop.orders
-- source: shop.customers
CREATE OR REPLACE TABLE dim_customer AS
SELECT customer_id, region FROM shop.customers;
CREATE OR REPLACE TABLE fact_orders AS
SELECT order_id, customer_id, amount FROM shop.orders;
```

Write its contract: checks on the tables it sinks, from the closed
vocabulary (`rows`, `unique`, `not_null`, `foreign_key`, `values`,
`reconcile`), at least one.

```yaml
note: Orders and customers from the shop database, as they are.
checks:
  - rows: fact_orders
    at_least: 1
  - unique: dim_customer
    columns: [customer_id]
  - foreign_key: fact_orders
    column: customer_id
    refers_to: [dim_customer, customer_id]
```

Then propose both, with a note that tells the reviewer why:

```json
{ "tool": "propose_transform",
  "arguments": { "name": "shop_orders", "sql": "…", "contract_yaml": "…",
                 "note": "Orders by customer, for a sales model" } }
```

The proposal is checked before it is stored: the name is new, the SQL parses
in DuckDB, every `-- source:` is a table you may read, and the contract is
valid. A refusal lists every reason; fix them and propose again. On success
you get a `request_id`, a `review_url` and a `dry_run`.

**To change a transform that exists**, read it (`read_transform`), edit its
SQL and contract, and propose them under its name with `change: true`. The
reviewer sees the diff against the published files. The change must keep
writing every table a model reads today; one that drops such a table is
refused, naming the model and the table: change the model first, as a draft
(step 5), and propose the transform once that is published. Only a SQL
transform is yours to change: a Python one is refused, and a person changes
it from a laptop with `tracebi push`.

## 4. Read the dry run, then wait for the approval

Every proposal, new or a change, runs once at once against a throwaway copy:
a scratch DuckDB with the warehouse attached READ_ONLY, the `-- source:`
tables loaded the way the real run loads them, and external access locked,
so it reads only what you may read and writes nothing real. A `-- sink:`
line is not sent and a `COPY` is not run; `not_executed` names each. The run
is bounded by the workspace's statement timeout.

`dry_run` holds, per table the SQL created, its `columns`, `rows` and the
first 20 rows (`sample`); per check, `passed` and `failing_rows`; the
`lineage` DuckDB's parse proves; `elapsed_ms`; and any `error`, with the
`statement` and `line` it failed on. `summary` says it in one line ("Dry run:
2 tables, checks 3 of 3 passed").

If `dry_run.ok` is false, the request is stored but cannot be approved. Read
the error and the failed checks, fix the SQL or the contract, and propose
again (with `change: true` for a change); the newer proposal is the one the
admin approves.

When it passes, tell the person the request id and the `review_url` (the
app's Review page, where the admin sees the diff beside the dry run), and
that an admin approves it there. Nothing real has run yet, and the tables do
not exist until it does: do not draft a model or a report over them before
then.

When the admin approves, the files go into `transforms/` and the transform
runs once. When the workspace is a git repository, the approval also commits
exactly those files (you as author, the admin as committer, a
`TraceBi-Request: <id>` trailer; it never pushes); otherwise the request says
why it made no commit. If the run fails (its SQL, or a contract check), the
request says so and the admin tells you; propose a corrected transform.

## 5. Draft the model

Once the tables exist, `describe_table` gives their columns. Draft a
declarative model over them:

1. `start_draft(kind="models", path="shop_model")`.
2. `write_draft_file(kind="models", path="shop_model", file="shop_model.yaml",
   content=…)`: a `type: warehouse` connector, the tables, the relationships,
   the facts, the dimensions and the named measures ([[model-json]]).
3. `preview_draft(kind="models", path="shop_model")` until it validates.
4. `publish_draft(kind="models", path="shop_model", note=…)` once the person
   agrees.

## 6. Build the report

Follow [[sop-authoring]] from step 1, against the model you just published.

## When something goes wrong

| Situation | Action |
|---|---|
| Every `agent_tables` is empty | Stop. Ask the person to tick the tables agents may read on the Sources page. |
| A table you need is "not found" | It is not one you may read, or it is not there. Ask the person; do not look for it another way. |
| `list_source_tables` answers `ok: false` with `variable` | The connection's credential is not set. Tell the person which variable. |
| `propose_transform` refuses | Read every error, fix each, and propose again. |
| A change is refused: a model reads a table it drops | Keep writing the table, or change the model first as a draft and propose the transform after it is published. |
| A change to a Python transform is refused | It is a person's to change, with `tracebi push`. Tell them what you would change. |
| `dry_run.ok` is false | Read `dry_run.error` and the checks that did not pass, fix the SQL or the contract, and propose again. |
| The approved run failed | Read the error on the request, then propose a corrected transform. |
| A number is wrong below the model | It is the transform's logic. Propose a change; the checks from the model onward cannot see it. |
