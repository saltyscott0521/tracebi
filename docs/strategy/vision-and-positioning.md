# Vision and positioning

**Ask it, build it, schedule it. Analysts and agents write every kind of
report from one set of approved definitions, and the ones worth repeating
run themselves.**

---

## Vision

In five years, nobody will build reports by dragging fields onto a canvas,
whether it's a quick question, a one-off analysis or the weekly pack.
Business users will ask in plain words and get answers from the company's
approved definitions. Analysts, working with agents, will build the deep
dives, memos and client deliverables as code, in hours instead of days. And
anything worth repeating will be approved once and then refresh and deliver
itself. TraceBi is the framework that makes all three safe and routine: the
definitions, the report format, the review step and the runner.

## The shift we're betting on

BI tools were built on two assumptions that are breaking:

| Old assumption | What it produced | Why it's breaking |
| --- | --- | --- |
| **Authoring is expensive**, because only a trained person can build a report | Drag-and-drop editors, per-author seats, a backlog of report requests, and simple questions waiting days for an analyst | An agent can answer a question in seconds, and an analyst working with one can build a full analysis in hours |
| **Logic lives in the tool**, because that's where the author works | Metric definitions hidden in workbooks, copied between dashboards, drifting apart | Agents need definitions they can read and reuse. Reviewers need a diff they can read. |

When authoring is cheap, the bottleneck moves to three things:

1. **Consistency.** Revenue means the same thing in a quick answer as in the
   board pack. In TraceBi a measure is declared once in the model and
   referenced by name everywhere.
2. **Approval.** A person signed off on the definitions, and on every report
   that runs on a schedule. The agent can't write to the warehouse.
3. **Repeatability.** A good answer doesn't have to be rebuilt next month. In
   TraceBi any report can declare its own schedule and recipients.

TraceBi is built around those three. BI tools are built around the editor.

## Three ways to use it, one set of definitions

| | **Ask** | **Build** | **Schedule** |
| --- | --- | --- | --- |
| Who | Anyone: a sales lead, a CFO | An analyst, usually working with an agent; or an agent on a request | Whoever owns a report that should repeat |
| Starts with | A question: "What was fair value in Software last quarter?" | A piece of work: a deep dive, a board memo, a client deliverable, a one-off investigation | "Send the sales leads this every Monday." |
| What happens | An agent queries the model and answers in seconds | The analyst explores live (`tracebi dev`), shapes the story, lays out the page their way, and builds one self-contained file | The report gets a `schedule` block and runs on its own: refresh, build, check, deliver |
| Review | None per question: it only uses definitions already approved | The analyst's call. Peer review for anything that leaves the team, as with any analysis. | Approved once, before it is published |
| Result | An answer with the query and a fingerprint behind every number | A one-off artifact: charts, tables and prose, every number traceable, shareable as one file | A report that arrives on time, every time |
| Today | Ask on a report; any MCP agent (`query_model`) | ✅ `tracebi new-report`, `tracebi dev` with the workbench, `report build`, custom styling and assets | ✅ `schedule` block, `tracebi schedule` |

**They connect.** A question can grow into a one-off analysis, and a one-off
analysis can become a scheduled report, with no rebuild in another tool.
Because all three use the same definitions, the quick answer, the deep dive
and the board pack never disagree.

**Not everything should repeat.** Most analysis is a one-off: it answers a
question once, well, and is done. TraceBi treats that as a first-class
artifact, not as a report that hasn't been scheduled yet.

**Review is proportional to risk.** The model (what "revenue" means) is
reviewed carefully, because everything depends on it. A question answered from
it needs no review of its own. A one-off analysis is reviewed the way the team
already reviews analysis. A report that goes out on a schedule is approved
once.

## Positioning

**For** teams that need more answers, analyses and reports than their data
people can produce,
**TraceBi is** a report-as-code framework that analysts and agents author
from approved definitions,
**that** answers questions in seconds, lets an analyst build a polished,
checkable analysis in hours, and turns the pieces worth repeating into
reports that refresh and deliver themselves.
**Unlike** BI tools, where logic lives in a GUI and every report is built by
hand,
**TraceBi** keeps definitions, reports and schedules as code in your
repository, so any agent can build on them and any change can be reviewed.

### One-liners, by audience

| Audience | Line |
| --- | --- |
| Buyer (head of data, CFO, COO) | "Every report your team needs, from one set of definitions: ask it, build it, or schedule it." |
| Business user | "Ask a question, get a number you can trust, and keep it as a weekly report if it's useful." |
| Analyst | "Build the analysis your way, with an agent doing the heavy lifting, and every number in it checkable." |
| Data / analytics engineer | "A semantic model and report format your analysts and agents can write, with review before publishing and a scheduler built in." |
| Agent developer | "Add one MCP server and your agent can answer questions and build governed reports." |
| Skeptic | "Every number comes from a declared definition, every scheduled report is reviewed, and every number can be re-run to prove it." |

## What TraceBi replaces, and what it doesn't

| Replaces | Doesn't replace (yet, or ever) |
| --- | --- |
| "Can you pull me the numbers on X?" requests to the data team | Hand-built drag-and-drop exploration (TraceBi's answer is Ask, not a chart editor) |
| One-off analyses assembled from exports, spreadsheets and slides | |
| Weekly, monthly and quarterly KPI packs | Real-time operational monitoring (seconds-fresh dashboards) |
| Investor, board and client reports | Spreadsheet modelling and planning |
| "Can you rebuild this for region X?" requests | The data warehouse, ETL or dbt. TraceBi sits on top of them. |
| Dashboards that are really scheduled reports | Data science notebooks |
| Metric definitions scattered across workbooks | |

## Principles

These decide trade-offs when the documents don't.

1. **Analysts and agents author; people approve what ships.** Every
   authoring feature has two users: the person and the agent working with
   them. A feature that works for only one of them isn't done.
2. **Review in proportion to risk.** Definitions and scheduled reports are
   reviewed. A question answered from approved definitions is not held up
   waiting for one, and a one-off analysis follows the team's own review
   habits.
3. **Everything kept is files the customer owns.** Definitions, analyses,
   scheduled reports and recipients live in files, in folders or in source
   control (never required, and git on any host when used). A published file
   changes only through an approved publish, and every version is kept.
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
not the headline**. The headline is reporting of every kind (questions, one-off
analyses, recurring reports) built by analysts and agents from definitions
people approved. Receipts are why a finance or
compliance buyer can trust it.
