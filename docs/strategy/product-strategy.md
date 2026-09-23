# Product strategy

**Own three paths that share one set of definitions: Ask, which answers a
question in seconds; Build, where an analyst (with an agent) makes a one-off
analysis; and Schedule, which turns the pieces worth repeating into reports
that run themselves. Match BI tools on what those need. Deliberately
skip what they need only for drag-and-drop exploration.**

---

## Three paths, one set of definitions

```
ASK ────── question → answer in seconds ──────────────┐
                                                      │ grows into
BUILD ──── explore → shape → lay out → build one file ┤
                                                      │ worth repeating
SCHEDULE ─ review → publish → run → deliver → monitor ┘
```

### Ask: the ad hoc path

| Step | What happens | Today | Target | Quarter |
| --- | --- | --- | --- | --- |
| **Question** | A person asks in plain words, in the app, Slack or their agent tool | Ask on an open report; any MCP agent via `query_model` | Ask anywhere in the app, not only on a report; Slack | Q2–Q3 |
| **Answer** | The agent queries the model; every number carries its query and fingerprint | ✅ `query_model`, selections on the model | Answers with a small chart or table, and the definition used, in plain words | Q2 |
| **One-off report** | For a bigger question, the agent builds a report file to share | ✅ `tracebi new-report`, `tracebi dev`, `build_report` | One click from an answer to a shareable report | Q3 |
| **Keep it** | A useful answer becomes a published report | Manual: add a package and a `schedule` block | "Keep this" opens the pull request for review | Q3 |

No review per question: an answer uses only definitions a person already
approved in the model. If the question needs a definition that doesn't exist,
the agent says so and proposes one, and that proposal is reviewed like any
model change.

### Build: the analyst's one-off path

A deep dive, a board memo, a client deliverable, an investigation. Most
analysis is done once, and that's fine: TraceBi treats a one-off artifact as
first-class, not as a report waiting for a schedule.

| Step | What happens | Today | Target | Quarter |
| --- | --- | --- | --- | --- |
| **Explore** | The analyst (or their agent) queries the model and tries ideas; scratch work stays out of the final file | ✅ `tracebi dev`, the workbench, exploration blocks, `tracebi.workbench.show()`, `tracebi session export` | Share a live exploration link with a colleague | Q2 |
| **Shape** | Pick what the story needs: figures, prose, tables | ✅ Package grammar, `{{ figure() }}`, `report.py` for the analysis the model can't express | Templates for common analyses (variance, cohort, concentration) | Q2 |
| **Lay out** | The page looks the way the analyst wants | ✅ `style.css`, `assets/` fonts and images, `configureChart` | A small gallery of layouts to start from | Q2 |
| **Build and share** | One self-contained file, every number traceable | ✅ `tracebi report build`, `tracebi report send`, `verify --file` | Download as PDF; a shareable link from the app | Q2–Q3 |
| **Review** | Peer review, the way the team already reviews analysis | Git pull request, pins in the workbench | Review in the app for people who don't use git | Q3 |

The analyst stays in charge: plain files, their own layout and prose, and an
agent that does the querying, charting and first draft when asked.

### Schedule: the recurring path

| Step | What happens | Today | Target | Quarter |
| --- | --- | --- | --- | --- |
| **Request** | A person asks for a recurring report, or keeps an answer or analysis | Ask on one report | Request inbox. Each request becomes an agent task tied to a branch. | Q3 |
| **Author** | An agent writes the model and report | MCP gateway, package grammar, validation, `tracebi dev` | Templates, model scaffold from warehouse metadata | Q1–Q2 |
| **Review** | A person approves | Git pull request, Desk pins | Plain-language review in the app: rendered preview, what changed, which definitions it uses | Q3 |
| **Publish** | Merge makes it live | Server discovers at startup | Publish on merge, no restart | Q3 |
| **Run** | It refreshes and builds on schedule | ✅ `schedule` block, `tracebi schedule run / serve`, refresh before build | Retries, run history in the app | Q1 |
| **Deliver** | It reaches readers | ✅ Email with the report attached | Slack/Teams, links, in-body summary, per-recipient versions | Q1–Q2 |
| **Monitor** | Failures and surprises get handled | Run log, `tracebi verify` | Alerts on failure, empty data and thresholds. Agent opens a fix PR. | Q3 |

**Rule:** a quarter's work finishes a step end to end before starting the
next one. A half-built path is worth less than a narrow, complete one.

## BI parity map

What a team expects from a BI tool, and our answer.

| Capability | Needed? | TraceBi answer | Status |
| --- | --- | --- | --- |
| Dashboards and reports | Yes | Report packages (HTML), specs | ✅ |
| Charts, tables, KPIs | Yes | ECharts figures, tables, value cards | ✅ |
| Filters and drill-down | Yes | Controls; selection that recomputes through the model | ✅ partial |
| Semantic layer and metrics | Yes | `DataModel`: facts, dimensions, measures (ratios, windows, time intelligence) | ✅ |
| Scheduled delivery | Yes | `tracebi schedule`, email | ✅ v1 |
| Per-recipient versions (bursting) | Yes | Parameters in the filter grammar | ❌ Q2 |
| Connectors | Yes | CSV, SQL/Postgres, Snowflake, BigQuery, DuckDB | ✅ partial. Queries not yet pushed down (Q2). |
| Performance at warehouse scale | Yes | Query compiler + per-run cache | ❌ Q2 |
| Exports | Yes | HTML, Excel. PDF untested. | ✅ partial |
| Access control | Yes | Roles (viewer, analyst, admin) | ✅ partial. SSO, row-level security Q4. |
| Alerts | Yes | Thresholds and failures | ❌ Q3 |
| Catalog and search | Yes | Reports list | ✅ basic. Owners and usage Q4. |
| Version history | Yes | Git | ✅ (better than BI) |
| Embedding | Sometimes | Signed-URL embed | ❌ Q4 |
| Natural-language questions | Yes: the ad hoc path | Ask, through the agent, from the approved definitions | ✅ partial (on a report and via MCP) |
| Drag-and-drop authoring | No | Agents author | Won't build |
| Pixel-perfect paginated layout | Rarely | HTML + CSS; PDF later | Later |
| Real-time streaming dashboards | No | Out of scope | Won't build |

## Where to be better, not just equal

1. **Fast answers without going around the definitions.** Today a quick
   question goes to a spreadsheet export or a one-off query, and gets a number
   that disagrees with the board pack. Ask answers in seconds from the same
   model the published reports use.
2. **Authoring by analysts and agents together.** The analyst keeps full
   control of the story and the page; the agent works in a closed, validated
   vocabulary so its drafts are right the first time. Measure it: first-build
   success rate.
3. **Consistency.** One definition used everywhere, with a linter that
   refuses silently wrong aggregations (already shipped: rate and stock
   guards).
4. **Review.** A plain-language diff of what a report change does, so an
   approver who doesn't code can approve it.
5. **Repeatability and proof.** Schedules in the repo, run history, and
   receipts that re-run.
6. **Ownership.** Plain files in the customer's git. Leaving TraceBi means
   keeping everything.

## The template gallery

Templates are the product's front door for a horizontal market. Each one
is a model plus two or three reports, which an agent adapts to the customer's
tables.

| Order | Template | Why this one |
| --- | --- | --- |
| 1 | **SaaS metrics** (MRR, churn, cohorts) | Huge, horizontal, well-known definitions |
| 2 | **Sales pipeline** (by stage, rep, region) | Every company has one; perfect bursting demo |
| 3 | **Finance close pack** (P&L, budget vs actual) | Recurring, high-stakes, loved by approvers |
| 4 | **Marketing funnel** | Horizontal, frequent requests |
| 5 | **Fund / portfolio reporting** | The existing reference demo; regulated segment |
| 6 | **Support operations** (SLA, backlog) | Common, easy data |

Each template ships with sample data, a `tracebi init --template <name>`
path, and a landing page.

## What we won't build

| Won't build | Because |
| --- | --- |
| A drag-and-drop chart editor | Agents author. A GUI editor puts logic back into the tool. |
| A second calculator (browser SQL, server-side re-aggregation) | One definition, one calculator |
| Warehouse writes by agents or Cloud | Read-only on customer data |
| Our own ETL platform | Sits on dbt and the warehouse. `transforms/` stays for teams without one. |
| Cloud-only features that change what a report can compute | Open by default |
| Real-time streaming dashboards | Not the reporting job, ad hoc or recurring |

## Product quality bars

| Bar | Target |
| --- | --- |
| Question to answer (Ask), on a model that exists | < 10 seconds |
| Install to first scheduled report, on your own data | < 30 minutes |
| Agent first-build success (report builds and validates on the first try) | > 80% on template-based requests |
| Scheduled runs delivered on time | > 99% |
| Report build time on a warehouse (compiled queries) | < 60 s for a typical pack |
| Approver can review without reading code | Every report change |
