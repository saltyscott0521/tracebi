# Vision and positioning

**Agents write the BI. People approve it. It runs itself.**

---

## Vision

In five years, most of a company's recurring reports won't be built by people
dragging fields onto a canvas. An agent will write them, and a person will
review them the way engineers review code. Once approved, they will refresh
and deliver themselves. TraceBi is the framework that makes that safe and
routine: the definitions, the report format, the review step and the runner.

## The shift we're betting on

BI tools were built on two assumptions that are breaking:

| Old assumption | What it produced | Why it's breaking |
| --- | --- | --- |
| **Authoring is expensive**, because only a trained person can build a report | Drag-and-drop editors, per-author seats, a backlog of report requests | An agent can write a report in minutes, as code, from a sentence |
| **Logic lives in the tool**, because that's where the author works | Metric definitions hidden in workbooks, copied between dashboards, drifting apart | Agents need definitions they can read and reuse. Reviewers need a diff they can read. |

When authoring is cheap, the bottleneck moves to three things:

1. **Consistency.** Revenue means the same thing in every report. In TraceBi
   a measure is declared once in the model and referenced by name everywhere.
2. **Approval.** A person signed off on what ships. In TraceBi every change is
   a pull request, and the agent can't write to the warehouse.
3. **Repeatability.** It runs next month without anyone rebuilding it. In
   TraceBi a report declares its own schedule and recipients.

TraceBi is built around those three. BI tools are built around the editor.

## Positioning

**For** teams whose recurring reports take more people to build and maintain
than they have,
**TraceBi is** a report-as-code framework that agents author and people
approve,
**that** turns a plain-language request into a reviewed report that refreshes
and delivers itself.
**Unlike** BI tools, where logic lives in a GUI and every report is rebuilt by
hand,
**TraceBi** keeps definitions, reports and schedules as code in your
repository, so any agent can build on them and any change can be reviewed.

### One-liners, by audience

| Audience | Line |
| --- | --- |
| Buyer (head of data, CFO, COO) | "Your recurring reports, built by agents, approved by your team, delivered on schedule." |
| Data / analytics engineer | "A semantic model and report format your agents can write, with PR review and a scheduler built in." |
| Agent developer | "Add one MCP server and your agent can build governed, repeatable reports." |
| Skeptic | "Every number comes from a declared definition, every change is reviewed, and every report can be re-run to prove it." |

## What TraceBi replaces, and what it doesn't

| Replaces | Doesn't replace (yet, or ever) |
| --- | --- |
| Weekly, monthly and quarterly KPI packs | Free-form visual exploration by humans (drag and drop) |
| Investor, board and client reports | Real-time operational monitoring (seconds-fresh dashboards) |
| "Can you rebuild this for region X?" requests | Spreadsheet modelling and planning |
| Dashboards that are really scheduled reports | The data warehouse, ETL or dbt. TraceBi sits on top of them. |
| Metric definitions scattered across workbooks | Data science notebooks |

Ad hoc questions still matter. TraceBi answers them through **Ask**, an agent
that queries the same definitions. It doesn't answer them through a chart
editor.

## Principles

These decide trade-offs when the documents don't.

1. **Agents author, people approve.** Every feature has two users: the agent
   doing the work and the person accountable for it. A feature that works
   for only one of them isn't done.
2. **Everything is code in the customer's repo.** Definitions, reports,
   schedules and recipients live in files, get reviewed in pull requests, and
   are versioned by git. The server never edits them in place.
3. **One definition, one calculator.** A measure is declared once, and the
   engine is the only thing that computes it. No second query path in the
   browser or the server.
4. **Read-only on customer data.** TraceBi and its agents read the warehouse.
   They never write to it.
5. **Open by default.** Everything that produces a report is MIT and
   self-hostable. Paid features make it easier to run at scale. They are
   never the only way to get a correct report.
6. **Honest about limits.** A receipt proves a number reproduces, not that
   it's right. We say so, in the product and in sales.

## Where receipts fit

Receipts (per-figure fingerprints, `tracebi verify`, the tamper check) stay in
the product. They are how a repeatable report proves it ran the same way twice.
But they are a **supporting feature, not the headline**. The headline is
agent-built, reviewed, repeatable reporting. Receipts are why a finance or
compliance buyer can trust it.
