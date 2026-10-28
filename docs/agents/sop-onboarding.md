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
  secrets, so you never run one. You propose it; an admin reads it in the app
  and approves it, and approving runs it once.
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
you get a `request_id` and a `review_url`.

## 4. Wait for the approval

Tell the person the request id and the `review_url` (the app's Review page),
and that an admin approves it there. Nothing has run yet, and the tables do
not exist until it does: do not draft a model or a report over them before
then.

When the admin approves, the files go into `transforms/` and the transform
runs once. If it fails (its SQL, or a contract check), the request says so
and the admin tells you; propose a corrected transform under a new name.

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
| The approved run failed | Read the error on the request, then propose a corrected transform under a new name. |
| A number is wrong below the model | It is the transform's logic. Propose a change; the checks from the model onward cannot see it. |
