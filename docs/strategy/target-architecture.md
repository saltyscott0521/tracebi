# Architecture

**Files the customer owns hold every definition, report and schedule. One engine does all the
computing, in the CLI, the server and the agent gateway. Queries run in the
customer's warehouse. The server adds state, identity and scheduling, and
never a second way to compute a number.**

This is the target architecture for the next 12 months. The engine design is
in [[report-architecture-v2]] and [[production-plan]].

---

## The picture

```
┌──────── Customer's report library: folders, share or source control (source of truth) ────┐
│ models/        the definitions: facts, dimensions, measures                         │
│ reports/<name>/  report.json (bindings, schedule, recipients) + template.html        │
│ transforms/    optional pandas for teams without a warehouse pipeline                │
└───────────▲──────────────────────────────────────────────────────────▲───────────────┘
            │ agent writes drafts                                       │ read on publish
┌───────────┴──────────────┐                     ┌───────────────────────┴────────────────┐
│ AGENT GATEWAY (MCP)      │                     │ TRACEBI SERVER                          │
│ get_context  query_model │                     │ API + web app: Desk, Reports, Ask,      │
│ describe_model           │◀── same engine ───▶│   Requests, Review, Admin               │
│ build_report  verify     │                     │ Scheduler + workers (report runs)       │
│ workbench_state  (+ new: │                     │ Delivery: email, Slack, Teams, webhook  │
│ request, run, status)    │                     │ Identity: SSO/OIDC, roles, row policies │
└───────────┬──────────────┘                     └──────┬──────────────────────┬──────────┘
            │                                            │                      │
┌───────────▼────────────────────────────────────────────▼──┐        ┌──────────▼─────────┐
│ ENGINE (the tracebi library, MIT)                          │        │ STATE (Postgres)   │
│ DataModel → query compiler → SQL per warehouse dialect     │        │ runs, schedules,   │
│ report build → self-contained HTML + manifest (receipt)    │        │ requests, users,   │
│ validation, lint guards, verify                            │        │ audit log, cache   │
└───────────┬────────────────────────────────────────────────┘        │ index              │
            │ read-only                                                └────────────────────┘
┌───────────▼─────────────────────────────────────────────────┐
│ CUSTOMER DATA: Postgres · Snowflake · BigQuery · Databricks │
│ · Redshift · DuckDB files · dbt marts                        │
└──────────────────────────────────────────────────────────────┘
```

## Components

| Component | Responsibility | Today | Change |
| --- | --- | --- | --- |
| **Engine** | Models, queries, report build, validation, receipts | ✅ `tracebi` package | Add a query compiler (below). |
| **CLI** | Author, build, verify, schedule, serve | ✅ ~20 commands | Add refresh and retries to `schedule`. Add `init --template`. |
| **Agent gateway** | MCP tools for agents | ✅ 11 tools, bearer auth on HTTP | Add request, run and status tools. Per-agent identity. |
| **Server** | API, web app, auth, roles | ✅ FastAPI + React | Add scheduler workers, requests, review, admin. |
| **Scheduler + workers** | Run reports on schedule | ✅ `tracebi schedule serve` (one process) | Move into the server as workers. State in Postgres. |
| **State store** | Runs, schedules, requests, users, audit | Partial: SQLite/Postgres for pipeline runs, a JSONL run log | Postgres for everything multi-process. SQLite for local only. |
| **Report library** | Browse folders, permissions, drafts, publish with approval, version history | ❌ | Folders and permissions first; a source-control adapter (git on any host) after. See [[report-library]]. |
| **Delivery** | Email, chat, links | ✅ SMTP email, Slack ping | Slack/Teams files, links, webhooks. |

## Decisions

### 1. Files are the source of truth; source control is optional
Every definition, report, schedule and recipient list is a file in a folder
the customer owns: on the server, a network share, or a source control
checkout. Published changes, from people or agents, are approved before they
go live, through TraceBi's own publish step or, where a team uses one, their
source control's review. **Why:** reviewable, versioned, portable, and
agent-friendly. It's the line between TraceBi and GUI BI tools. **Cost:**
TraceBi keeps its own version history for folders without source control.
See [[report-library]].

### 2. Queries run in the warehouse
Today `DataModel.query` loads the fact table into the Python process and
aggregates it locally. Simple filters already run in the source, but that
isn't enough for warehouse-scale tables. The query compiler turns a model
query into one SQL statement in the warehouse's dialect (joins, filters,
measures, window measures) and runs it where the data lives. It uses
SQLAlchemy dialects, with DuckDB SQL as the reference implementation.
**Rule:** the compiled SQL must match the in-process result byte for byte on
a pinned test corpus before a warehouse is marked supported. Otherwise the
fingerprints fork.

### 3. The model can sit on existing tables
Phase ① (`transforms/`) becomes optional. A model can point straight at
warehouse tables or dbt marts. A `tracebi import dbt` step reads a dbt
project's `manifest.json` and drafts a model for review. **Why:** most
horizontal customers already have clean tables. Asking them to rewrite
pipelines is a lost sale.

### 4. Schedules live next to the report
The `schedule` block in `report.json` (shipped) grows to cover refresh steps,
parameters and channels. The server reads it. Nothing about when or to whom
is configured by clicking.

### 5. Parameters are the filter grammar
A report declares parameters (for example `region`) using the same filter
grammar as bindings and selections. Delivery fans out one build per value,
with its own recipients. Row-level security uses the same mechanism, keyed on
the viewer's identity instead of a recipient list.

### 6. One engine, three runtimes
The CLI, the server's workers and the gateway all call the same library
functions. The server adds persistence, identity and scheduling. There is no
server-only query path and no browser calculator.

### 7. Stateless web, stateful workers
Web processes serve the API and UI and scale horizontally. Workers run builds
and deliveries. Postgres coordinates them (advisory locks per report run, the
same pattern pipelines use). **SQLite means one process only.**

### 8. Tenancy: single-tenant first
Cloud starts single-tenant: one isolated deployment per customer, created
from the same Docker image. It's simpler to secure and to operate.
Multi-tenant comes when the number of customers makes per-customer
deployments too costly to operate.

## Security model

| Concern | Approach |
| --- | --- |
| Warehouse credentials | Customer-provided read-only credentials. Secrets in environment variables or the platform's secret store, never in the repo. |
| Agent access | Gateway only. No warehouse writes. Bearer tokens today, per-agent identities later. |
| Human access | Roles today (viewer, analyst, admin). SSO/OIDC and SCIM in Q4. |
| Data leaving the warehouse | Only query results needed for a report, embedded in the artifact. Cloud stores results and receipts, not raw tables. |
| Audit | Every run and request records actor, role, time and outcome. |
| Delivery | TLS-verified SMTP (already enforced). Signed links for web delivery. |

## Technical debt to clear first

These block the plan and are cheaper to fix now. Items 1, 4 and 5 are in
[[epics]] E4 and E1; item 2 is E5.

1. **`registry.scheduled()` is unread.** Remove it or route it to the new
   runner, so there's one way to schedule.
2. **Run history is split** between pipeline tables and `schedule_runs.jsonl`.
   Unify them in the state store.
3. ~~**The web download re-renders.**~~ Done: the HTML download is the last
   build, the same bytes its receipt describes.
4. **Version shown in the UI is hard-coded.** Serve it from the API.
5. **Tests write to the repo's `output/`.** Point them at temporary folders.
