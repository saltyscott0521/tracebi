# Users and their jobs

**Six user types. Agents author. Builders own the data. Approvers sign off.
Requesters ask. Readers read. Admins run it. Only builders need to write
code.**

---

## The six user types

| User | Who they are | Job to be done | Main surface | Technical? |
| --- | --- | --- | --- | --- |
| **Requester** | Sales lead, finance manager, ops manager | "Get me a weekly view of X without waiting a month." | Web app: Ask, request form. Email and Slack for results | No |
| **Reader** | Exec, board member, client, investor | "Show me the numbers I need, where I already look." | Delivered report (email, Slack, link), mobile | No |
| **Approver** | Data owner, finance controller, team lead | "Make sure what goes out is right and uses our definitions." | Review in the app, or the pull request | Some |
| **Builder** | Analytics engineer, data engineer, technical analyst | "Connect the data once, define it once, let agents do the rest." | Repo, CLI, `tracebi dev`, models | Yes |
| **Agent** | Claude, Cursor, Codex, or a custom agent | "Turn a request into a correct report the reviewer approves first time." | MCP gateway, `tracebi context`, `AGENTS.md`, skills | Is software |
| **Admin** | Platform engineer, IT, the builder at small companies | "Run it securely, connect sources, control who sees what." | Config, CLI, admin settings | Yes |

At a 30-person company, one person may be builder, approver and admin. At a
1,000-person company, these are different teams. Both must work.

## The agent is a user

Designing for the agent is a first-class product job, not an integration.
What an agent needs from TraceBi:

| Need | How TraceBi serves it | Status |
| --- | --- | --- |
| Know what exists | `tracebi context`, `describe_model`, schema resources | ✅ |
| Write in a closed, checkable format | Package grammar (`report.json` + `data-tb-*`), validation before execution | ✅ |
| Get told exactly what's wrong | Errors with a repair path (`sections[0].data.query.fact`) | ✅ |
| Check its own work | `build_report`, `verify_manifest`, `workbench_state` | ✅ |
| Take a request and open a PR | Request inbox + GitHub App | ❌ Q3 |
| Fix a report that broke overnight | Run failure → agent task with the error and the last good run | ❌ Q3 |
| Start from a known-good pattern | Template gallery | ❌ Q1 |

## Key journeys

### 1. First report (builder, day one)

`pip install tracebi` → `tracebi init` → connect a database → the agent drafts
the model from the table metadata → the builder approves it → the agent builds
the first report from a template → it's scheduled for Monday.

**Target:** under 30 minutes from install to a scheduled report on the
builder's own data. **Today:** only possible on the sample data. Needs
templates, connection setup and a model scaffold (Q1–Q2).

### 2. A new request (requester → agent → approver)

The requester types "weekly pipeline by region, to the sales leads" → an agent
task starts → the agent builds the report on a branch and opens a PR with a
rendered preview → the approver reviews it in the app, asks for a change or
approves → merge publishes it → it arrives Monday.

**Target:** request to published in under a day, with the builder not
involved. **Today:** the agent loop works from an IDE. The inbox, the PR app
and in-app review are Q3.

### 3. Monday morning (reader)

The report arrives by email or Slack. It opens on a phone. The numbers match
last week's definitions. A "Ask about this report" link answers follow-up
questions without a new request.

**Today:** scheduled email with the HTML attached works (`tracebi schedule`).
Slack file delivery, in-body summaries and links are Q1–Q2.

### 4. Something broke (admin → agent → approver)

A source column was renamed. The Monday run fails and is recorded, and the
owner is alerted. An agent reads the failure, proposes a fix PR, and the
approver merges it. The run is retried.

**Today:** failures are recorded in `schedule_runs.jsonl`. Alerts and the
agent fix loop are Q3.

### 5. Proving a number (approver or auditor)

"Where did this number in March's board pack come from?" The receipt names
the definition, the query and the fingerprint. `tracebi verify` re-runs it.

**Today:** works (receipts, `verify`, `verify --file`).

## What each user must never have to do

| User | Never |
| --- | --- |
| Requester | Learn a tool, file a ticket with a template, or wait for a sprint |
| Reader | Log in to see a report that was sent to them, or install anything |
| Approver | Read Python to approve a report. Plain-language review is the goal. |
| Builder | Rebuild the same report for a new region or month by hand |
| Agent | Guess a column name or a measure definition |
| Admin | Grant anyone, human or agent, write access to the warehouse |
