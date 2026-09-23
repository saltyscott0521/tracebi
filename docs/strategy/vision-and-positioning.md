# Vision and positioning

**Ask anything, keep what matters. Agents write the reports, people approve
them, and the ones worth keeping run themselves.**

---

## Vision

In five years, people won't build reports by dragging fields onto a canvas,
whether it's a one-off question or the weekly pack. They'll ask in plain
words, and an agent will answer from the company's approved definitions.
Answers worth keeping become reports that a person reviews once and that then
refresh and deliver themselves. TraceBi is the framework that makes both safe
and routine: the definitions, the report format, the review step and the
runner.

## The shift we're betting on

BI tools were built on two assumptions that are breaking:

| Old assumption | What it produced | Why it's breaking |
| --- | --- | --- |
| **Authoring is expensive**, because only a trained person can build a report | Drag-and-drop editors, per-author seats, a backlog of report requests, and simple questions waiting days for an analyst | An agent can answer a question in seconds, or write a report in minutes, from a sentence |
| **Logic lives in the tool**, because that's where the author works | Metric definitions hidden in workbooks, copied between dashboards, drifting apart | Agents need definitions they can read and reuse. Reviewers need a diff they can read. |

When authoring is cheap, the bottleneck moves to three things:

1. **Consistency.** Revenue means the same thing in a quick answer as in the
   board pack. In TraceBi a measure is declared once in the model and
   referenced by name everywhere.
2. **Approval.** A person signed off on the definitions, and on every report
   that gets published. The agent can't write to the warehouse.
3. **Repeatability.** A good answer doesn't have to be rebuilt next month. In
   TraceBi any report can declare its own schedule and recipients.

TraceBi is built around those three. BI tools are built around the editor.

## Two modes, one set of definitions

| | **Ask** (ad hoc) | **Publish** (recurring) |
| --- | --- | --- |
| Starts with | A question: "What was fair value in Software last quarter?" | A need: "Send the sales leads this every Monday." |
| The agent | Queries the model and answers in seconds, or builds a one-off report in minutes | Builds the report as code on a branch |
| Review | None needed per question. It only uses definitions a person already approved in the model. | A person approves the pull request once |
| Result | An answer with the query and a fingerprint behind every number; a one-off report file to share | A report that refreshes, checks itself and arrives on schedule |
| Today | Ask on a report, the MCP gateway (`query_model`), `tracebi new-report` + `tracebi dev` | `schedule` block, `tracebi schedule` |

**The bridge is the point.** A one-off answer that turns out to matter becomes
a recurring report with one approval, with no rebuild in another tool.
Because both modes use the same definitions, the quick answer and the
scheduled pack never disagree.

**Review is proportional to risk.** The model (what "revenue" means) is
reviewed carefully, because everything depends on it. A question answered from
it needs no review of its own. A report that goes out to people on a schedule
is reviewed once.

## Positioning

**For** teams that need more reports and answers than their data people can
produce,
**TraceBi is** a report-as-code framework that agents author and people
approve,
**that** turns a plain-language question into a trustworthy answer in
seconds, and turns the answers worth keeping into reports that refresh and
deliver themselves.
**Unlike** BI tools, where logic lives in a GUI and every report is built by
hand,
**TraceBi** keeps definitions, reports and schedules as code in your
repository, so any agent can build on them and any change can be reviewed.

### One-liners, by audience

| Audience | Line |
| --- | --- |
| Buyer (head of data, CFO, COO) | "Ask for any report in plain words. Agents build it from your definitions, and the ones you keep arrive on schedule." |
| Business user | "Ask a question, get a number you can trust, and keep it as a weekly report if it's useful." |
| Data / analytics engineer | "A semantic model and report format your agents can write, with PR review and a scheduler built in." |
| Agent developer | "Add one MCP server and your agent can answer questions and build governed reports." |
| Skeptic | "Every number comes from a declared definition, every published report is reviewed, and every number can be re-run to prove it." |

## What TraceBi replaces, and what it doesn't

| Replaces | Doesn't replace (yet, or ever) |
| --- | --- |
| "Can you pull me the numbers on X?" requests to the data team | Hand-built drag-and-drop exploration (TraceBi's answer is Ask, not a chart editor) |
| Weekly, monthly and quarterly KPI packs | Real-time operational monitoring (seconds-fresh dashboards) |
| Investor, board and client reports | Spreadsheet modelling and planning |
| "Can you rebuild this for region X?" requests | The data warehouse, ETL or dbt. TraceBi sits on top of them. |
| Dashboards that are really scheduled reports | Data science notebooks |
| Metric definitions scattered across workbooks | |

## Principles

These decide trade-offs when the documents don't.

1. **Agents author, people approve.** Every feature has two users: the agent
   doing the work and the person accountable for it. A feature that works
   for only one of them isn't done.
2. **Review in proportion to risk.** Definitions and published reports are
   reviewed. A question answered from approved definitions is not held up
   waiting for one.
3. **Everything kept is code in the customer's repo.** Definitions, published
   reports, schedules and recipients live in files, get reviewed in pull
   requests, and are versioned by git. The server never edits them in place.
4. **One definition, one calculator.** A measure is declared once, and the
   engine is the only thing that computes it, for a quick answer and a
   published report alike. No second query path in the browser or the server.
5. **Read-only on customer data.** TraceBi and its agents read the warehouse.
   They never write to it.
6. **Open by default.** Everything that produces a report is MIT and
   self-hostable. Paid features make it easier to run at scale. They are
   never the only way to get a correct report.
7. **Honest about limits.** A receipt proves a number reproduces, not that
   it's right. We say so, in the product and in sales.

## Where receipts fit

Receipts (per-figure fingerprints, `tracebi verify`, the tamper check) stay in
the product. They let a quick answer be re-checked later, and let a recurring
report prove it ran the same way twice. But they are a **supporting feature,
not the headline**. The headline is agent-built reporting, ad hoc and
recurring, from definitions people approved. Receipts are why a finance or
compliance buyer can trust it.
