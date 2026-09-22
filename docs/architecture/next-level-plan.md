# Next-level plan: agents build the BI

**Status: plan (2026-09-22).** TraceBi's next goal: be the framework
agents use to build **repeatable reports**, and replace the BI tool for
recurring reporting.

This plan sets the product direction. [[production-plan]] still sequences
the report-engine work inside it. Where this plan disagrees with
[[ROADMAP]] on positioning, this plan wins. The ROADMAP's line "don't pitch
a Tableau replacement" is deliberately reversed, and narrowed to recurring
reporting.

---

## 1. Positioning

> **Your BI tool, written by agents and approved by people.** Ask for a report
> in plain words. An agent builds it as code against your definitions. A person
> approves it. It then refreshes and delivers itself on schedule.

- **What it replaces:** the recurring layer of BI. That's the weekly KPI pack,
  the monthly investor report, the board deck numbers, the dashboard that's
  rebuilt by hand every quarter. Most BI seats exist to maintain these.
- **Why agents change the math:** BI tools are built on the assumption that
  authoring is expensive, so they offer drag-and-drop for humans. Agents make
  authoring cheap. What stays scarce is **consistency** (the same definitions
  everywhere), **review** (someone approved this), and **repeatability** (it
  runs itself next month). TraceBi is built on those three.
- **What it doesn't replace:** drag-and-drop exploration by humans. The Ask
  box, backed by an agent, answers the ad hoc question. It doesn't draw charts
  by hand.

## 2. User types

| User | Job | Main surface | Must have (❌ = not built yet) |
| --- | --- | --- | --- |
| **Requester** (business user) | "I need a weekly view of X." | Web app: request form, Ask | ❌ request inbox that turns a sentence into an agent task |
| **Reader** (exec, client, LP) | Reads the numbers, often by email | Delivered HTML, Slack, the web viewer | ✅ scheduled email (`tracebi schedule`). ❌ per-recipient versions |
| **Approver** (data owner) | Signs off on definitions and new reports | Pull request, Desk | ❌ review in the app, not only on GitHub |
| **Builder** (analytics engineer) | Owns the warehouse link, the models, the hard cases | Repo, CLI, `tracebi dev` | ✅ largely built |
| **Agent** | Authors and maintains reports | MCP gateway, `AGENTS.md`, skills | ✅ authoring loop. ❌ can't fix a failing scheduled run on its own |
| **Admin** | Deploys, connects data, sets access | Config, CLI, admin page | ❌ SSO, row-level security, secrets management |

**The agent is a user type, not a feature.** Every surface is designed for
two readers: the person, and the agent acting for them.

## 3. The repeatable-report loop

This is the product. Every step must work without the builder in the loop.

```
 REQUEST ──▶ AUTHOR ──▶ REVIEW ──▶ PUBLISH ──▶ RUN ──▶ DELIVER ──▶ MONITOR
 requester   agent      approver   merge       schedule  email/     failure or
 in plain    writes     reads the  to main     refresh + Slack/     drift → agent
 words       model +    diff                   build     web        opens a fix PR
             report
```

| Step | Today | Gap to close |
| --- | --- | --- |
| Request | Ask on one report | Request inbox. Each request becomes an agent task tied to a branch. |
| Author | MCP gateway, `build_report`, `workbench_state`, model hot-reload | Report templates to start from. Agent can scaffold a model from warehouse metadata. |
| Review | Git pull request, Desk pins | GitHub App: agent opens the PR, and the app shows the rendered preview and model diff in plain language. |
| Publish | Discovery at server startup | Publish on merge: server pulls `main` and reloads. No restart. |
| Run | ✅ `schedule` block in `report.json` + `tracebi schedule run`/`serve` (build → check → record). `registry.scheduled()` is still unread. | Refresh the source before the build. Run history in Postgres and the app. |
| Deliver | ✅ scheduled email to the block's `to` list, plus the Slack ping | More channels (Slack files, Teams, webhook), formats, and per-recipient parameters ("bursting"). |
| Monitor | `tracebi verify`, run history for pipelines | Report run history, alerts on failure, empty data or threshold breach. Agent gets the failure and proposes a fix PR. |

## 4. Architecture

```
┌──────────────────────── Git repo (source of truth) ────────────────────────┐
│ transforms/  models/  reports/<name>/{report.json, template.html, schedule} │
└──────────────▲──────────────────────────────────────────────▲──────────────┘
               │ PRs (agent via GitHub App)                    │ pull on merge
┌──────────────┴──────────┐   ┌───────────────────────────────┴──────────────┐
│ Agent gateway (MCP)     │   │ TraceBi server                                │
│ context · query · build │◀─▶│ API + web app: Desk, Reports, Ask, Requests   │
│ validate · run · status │   │ Runner/scheduler workers (report jobs)        │
└──────────────┬──────────┘   │ Delivery: email · Slack · Teams · webhook     │
               │              │ Auth: SSO/OIDC · roles · row-level policies   │
               ▼              └───────┬───────────────────────────┬──────────┘
┌──────────────────────────┐          │                           │
│ Engine (the library)     │◀─────────┘                   ┌───────▼────────┐
│ DataModel · query compiler│                             │ State store     │
│ report build · receipts   │                             │ Postgres: runs, │
└──────────────┬───────────┘                              │ schedules, users│
               │ read-only SQL                            │ requests, audit │
┌──────────────▼───────────────────────────────────────┐  └────────────────┘
│ Customer data: Snowflake · BigQuery · Postgres ·      │
│ Databricks · DuckDB file · dbt marts                  │
└───────────────────────────────────────────────────────┘
```

**Decisions**

1. **Git is the source of truth. The server never edits a report in
   place.** Every change, from an agent or from a person, arrives as a
   PR. This is what makes reports repeatable and reviewable, and it's the line
   against BI tools, where the logic lives inside the tool.
2. **Push queries down to the warehouse.** Today a model query loads the fact
   table into Python (simple filters are pushed down, aggregation isn't), and
   that doesn't scale to a warehouse. Add a **query compiler**: `DataModel`
   query → SQL in the warehouse's dialect, run where the data lives, with
   results cached per run. Keep in-process DuckDB for local projects.
3. **Phase ① is optional.** Most teams already have dbt or warehouse tables.
   A model can point at existing tables directly, or import dbt marts as the
   sink. `transforms/` stays available for teams without a warehouse.
4. **Schedules and delivery live in the repo.** A `schedule` block in
   `report.json` (shipped: cron, time zone, recipients) means a reviewer approves *when* and *to whom*
   along with *what*. The runner reads them. Nothing is configured by
   clicking.
5. **Parameters are the existing filter grammar.** A report declares
   parameters (for example `fund`, `region`, `period`). Delivery fans out one
   build per recipient value. Row-level policies use the same grammar, keyed
   on the viewer's identity.
6. **One engine, three runtimes.** The same library runs in the CLI, the
   server's workers, and the gateway. The server adds state, identity and
   schedules. It adds no second query path.
7. **Postgres for anything with more than one process.** SQLite remains for
   local use only (see "Running More Than One Worker" in `CLAUDE.md`).

## 5. Deployment

| Tier | For | Shape | Status |
| --- | --- | --- | --- |
| **Local** | Builder, evaluation | `pip install tracebi` → `tracebi init` → `tracebi serve` | ✅ works, not on PyPI yet |
| **Self-hosted team** | First production users | One Docker image (web + workers) + Postgres + a git checkout. Docker Compose, Helm chart, one-click Railway/Render | Partly: Dockerfile, compose, Railway, Vercel exist. Workers, Helm and git sync to build. |
| **TraceBi Cloud** | Teams without ops capacity | Managed server and workers. Customer connects the warehouse (read-only credentials) and the GitHub repo. Data stays in the warehouse. Only results and receipts are stored. | To build, after self-hosted is proven |
| **Customer VPC** | Regulated buyers | Cloud's control plane with workers inside the customer's network | Later, when a buyer requires it |

Rule: **anything in Cloud must also run self-hosted.** Cloud sells
operations, identity and retention, not features held back from the
library.

## 6. Distribution

**Open core.** The library, CLI, gateway and self-hosted server are MIT.
Paid features: Cloud, SSO/SCIM, row-level security at scale, audit
retention, and support.

Channels, in order of leverage:

1. **Where agents already are.** Publish the MCP server to the MCP registries
   and the Claude/Cursor/VS Code catalogs. Ship `skills/tracebi-analyst` and an
   "author a report" skill as installable packs. The pitch to a developer: *add
   one MCP server, and your agent can build governed reports.*
2. **PyPI and GitHub.** `pip install tracebi`, tagged releases, a Docker
   image on GHCR, a template repo ("Use this template" → working project).
3. **Report template gallery.** Ready-made report packs by domain (SaaS
   metrics, finance close, fund/LP reporting, sales pipeline, marketing
   funnel), each a model plus reports an agent adapts to the customer's
   tables. Templates are the growth loop: each one is a landing page and a
   starting point.
4. **The dbt community.** "Point TraceBi at your dbt marts" is the shortest
   path to a team that already has clean data and no BI they like.
5. **Design partners.** Five teams migrating their recurring BI reports.
   Measure the reports moved, and the hours per month no longer spent
   maintaining them.

**Pricing hypothesis (Cloud):** per *active scheduled report*, not per seat.
Readers are free. That makes BI seat costs the thing TraceBi removes, and
aligns price with repeatable value.

## 7. Stages

Each stage ends with a demo that works end to end. Build in order.

**Stage 1: Repeatable (runs itself)**
- Report runner: `schedule` block → refresh → build → check → record the
  run → deliver (email, Slack) with retries. **Shipped:** the block,
  `tracebi schedule list | run | serve`, email, and the run log. **Next:**
  refresh before the build, and retries.
- Parameters and per-recipient delivery.
- Report run history and failure alerts in the app.
- PyPI 0.6.0 release. Docker image with workers.
- *Done when:* a report scheduled in `report.json` arrives in an inbox every
  Monday without anyone touching it, and a failure alerts the owner.

**Stage 2: On your warehouse**
- Query compiler with push-down for Snowflake, BigQuery and Postgres, plus a
  per-run result cache.
- Model points at existing tables. dbt marts import. Model scaffold from
  warehouse metadata (agent drafts it, a person approves).
- Add Databricks and Redshift connectors.
- *Done when:* a 1-billion-row fact table in Snowflake backs a scheduled
  report that builds in under a minute, with no transform written.

**Stage 3: Agent-run team workflow**
- Request inbox → agent task → PR through the GitHub App → preview in the
  app → approve → publish on merge.
- Monitor loop: a failed or drifted run becomes an agent fix PR.
- Template gallery (five domains). MCP registry listings.
- *Done when:* a business user types a request, and a reviewed, scheduled
  report reaches them. The builder never opens an editor.

**Stage 4: Replace the BI tool**
- SSO/OIDC, row-level security from identity, per-report sharing, a
  catalog with owners and usage.
- Embedding (signed-URL iframe), Microsoft Teams delivery, PDF export.
- Migration assistant: the agent reads an exported Tableau/Power BI/Looker
  definition and drafts the model and report.
- TraceBi Cloud general availability.
- *Done when:* a design partner switches off BI seats for its recurring
  reporting.

## 8. What we won't build

- A drag-and-drop chart editor. Agents author, people approve.
- A second query path in the browser or the server. The engine is the only
  calculator.
- Writes to the customer's warehouse from agents or from Cloud.
- Features that exist only in Cloud.

## 9. Metrics

| Metric | Why |
| --- | --- |
| Scheduled reports active | The unit of value, and of pricing |
| Scheduled runs delivered on time | Proof of repeatability |
| Request → published report (median hours) | Proof that agents author |
| Share of report changes authored by agents | The thesis |
| BI seats switched off at design partners | Proof of replacement |
