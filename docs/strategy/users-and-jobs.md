# Users and their jobs

**Seven user types. Requesters ask. Analysts build. Agents help both.
Builders own the data. Approvers sign off. Readers read. Admins run it.
Only analysts and builders need to touch code, and an agent can do most of
that for them.**

---

## The seven user types

| User | Who they are | Job to be done | Main surface | Technical? |
| --- | --- | --- | --- | --- |
| **Requester** | Sales lead, finance manager, ops manager | "Answer this question now, and get me a weekly view of X without waiting a month." | Web app: Ask, request form. Slack for questions; email and Slack for results | No |
| **Reader** | Exec, board member, client, investor | "Show me the numbers I need, where I already look." | Delivered report (email, Slack, link), mobile | No |
| **Analyst** | Financial analyst, data analyst, consultant | "Build the analysis I need to make the case, the way I want it to look, and fast." | `tracebi dev` and the workbench, their agent (Claude, Cursor), the package files | Some: an agent handles the code they don't want to write |
| **Approver** | Data owner, finance controller, team lead | "Make sure what goes out is right and uses our definitions." | Review in the app, or the pull request | Some |
| **Builder** | Analytics engineer, data engineer, technical analyst | "Connect the data once, define it once, let agents do the rest." | Repo, CLI, `tracebi dev`, models | Yes |
| **Agent** | Claude, Cursor, Codex, or a custom agent | "Answer the question, draft the analysis with the analyst, and build reports that are right the first time." | MCP gateway, `tracebi context`, `AGENTS.md`, skills | Is software |
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
| Take a request and propose a report | Request inbox + publish requests (a pull request where the team uses git) | ❌ Q3 |
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

### 2. A quick question (requester → agent)

The requester asks "What was fair value in Software last quarter, by fund?"
→ the agent answers from the model in seconds, with a small table, the
definition it used, and a fingerprint behind each number → a follow-up ("and
the quarter before?") refines it → if it's useful, "Keep this" turns it into
a request (journey 4), or into an analysis (journey 3).

**Target:** answer in under 10 seconds, no data person involved, and the
number matches the board pack because it uses the same definition.
**Today:** works through any MCP agent (`query_model`) and through Ask on an
open report. Ask anywhere in the app, Slack, and "Keep this" are Q2–Q3.

### 3. A one-off analysis (analyst + agent)

The CFO asks why margin fell in the West. The analyst opens `tracebi dev`,
asks their agent to pull margin by region and product, and explores in
scratch blocks that never reach the final file. They keep three charts and a
table, write the explanation in their own words, and lay the page out with
the team's style. `tracebi report build` produces one file with every number
traceable; a colleague reviews it, and it goes to the CFO. Nobody schedules
it. It answered the question.

**Target:** from question to a polished, shareable analysis in an afternoon.
**Today:** works end to end (`tracebi new-report`, `dev`, the workbench,
`report build`, `report send`). Templates for common analyses and sharing a
live exploration link are Q2.

### 4. A new recurring report (requester → agent → approver)

The requester types "weekly pipeline by region, to the sales leads" → an agent
task starts → the agent builds the report as a draft and asks to publish it,
with a rendered preview → the approver reviews it in the app, asks for a change
or approves → approval publishes it → it arrives Monday.

**Target:** request to published in under a day, with the builder not
involved. **Today:** the agent loop works from an IDE. The inbox, publish
requests and in-app review are Q3 (see [[report-library]]).

### 5. Monday morning (reader)

The report arrives by email or Slack. It opens on a phone. The numbers match
last week's definitions. A "Ask about this report" link answers follow-up
questions without a new request.

**Today:** scheduled email with the HTML attached works (`tracebi schedule`).
Slack file delivery, in-body summaries and links are Q1–Q2.

### 6. Something broke (admin → agent → approver)

A source column was renamed. The Monday run fails and is recorded, and the
owner is alerted. An agent reads the failure, proposes a fix as a draft, and
the approver publishes it. The run is retried.

**Today:** failures are recorded in `schedule_runs.jsonl`. Alerts and the
agent fix loop are Q3.

### 7. Proving a number (approver or auditor)

"Where did this number in March's board pack come from?" The receipt names
the definition, the query and the fingerprint. `tracebi verify` re-runs it.

**Today:** works (receipts, `verify`, `verify --file`).

## What each user must never have to do

| User | Never |
| --- | --- |
| Requester | Learn a tool, file a ticket, or wait for a sprint to get a simple answer |
| Analyst | Rebuild numbers by hand in a spreadsheet, or give up control of the story to a tool |
| Reader | Log in to see a report that was sent to them, or install anything |
| Approver | Read Python to approve a report. Plain-language review is the goal. |
| Builder | Rebuild the same report for a new region or month by hand |
| Agent | Guess a column name or a measure definition |
| Admin | Grant anyone, human or agent, write access to the warehouse |
