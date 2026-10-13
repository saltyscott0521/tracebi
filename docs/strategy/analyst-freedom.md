# Analyst freedom

**An analyst can calculate almost anything, in their own workspace, without
changing the shared model first. Every number says honestly how it was made.
The model keeps the definitions that must mean one thing; everything else
happens around it, and what proves itself is promoted into it.**

Status: decided 2026-10-13. Builds on [[report-library]] (folders, publishing)
and [[remote-authoring]] (drafts, what may come in which way). Prompted by the
field test `docs/agents/field-test-2026-10-12-mcp-user.md`.

---

## The problem

Today a calculation can only be a model measure, and a measure can only say
"add up X, grouped by Y". The field test could not report *net new assets*
(purchases minus sales) without changing the shared `wealth_model`. A
realistic follow-up, *cost basis per account over time* (start from positions,
roll forward the activities that change cost basis), needs ordered, stateful
logic: sign each activity by type, order by date, restart per account, carry a
running balance from an opening position. No measure kind expresses that, and
adding kinds one at a time would never keep up.

Meanwhile, if many analysts edit the shared model to answer their own
questions, it drifts and nobody can say which number is official.

## The principle

Freedom, labelled. The receipt does not stop anyone; it says how each number
was made. Restriction lives in **folders** (what may be published where), not
in what an analyst may calculate.

## Three layers of calculation

| Layer | Where it is defined | Who adds it | Label on the page and in the receipt |
|---|---|---|---|
| **Model measures** | the model file | publish through review (below) | the shared definition |
| **Report and personal calculations** | the report's `report.json`, or the analyst's workspace | anyone who can edit that report / the owner | "calculated in this report" / "personal" |
| **SQL calculations** | the report or the analyst's workspace | the same | "calculated in this report (SQL)" |

Plus, beyond SQL: **code** (Python, run in a sandbox), labelled "computed by
custom code", never re-checkable, as `report.py` is today.

### Report and personal calculations

The model's own declarative vocabulary, declared outside the model: a measure
built from the model's columns and measures, defined for one report or kept in
the analyst's workspace for reuse. One new building block is needed everywhere,
the model included: **a measure with its own filter** (sum `amount` where
`activity_type = 'purchase'`). Net new assets is then a report measure.

### SQL calculations

An analyst (or their agent) defines a named calculation as a SQL query over
the warehouse tables. It runs **read-only** in DuckDB and its result is
something a report binds to, like a model query.

```sql
-- calc: cost_basis_by_account (one row per account per month)
WITH moves AS (
  SELECT account_id, trade_date,
         CASE activity_type WHEN 'purchase' THEN amount
                            WHEN 'sale'     THEN -cost_relieved
                            ELSE 0 END AS basis_change
  FROM fact_activities
)
SELECT account_id, trade_date,
       opening.cost_basis
       + SUM(basis_change) OVER (PARTITION BY account_id ORDER BY trade_date) AS cost_basis
FROM moves JOIN opening_positions AS opening USING (account_id)
```

Why SQL is the escape hatch:

- Analysts and agents already know it; it covers rollforwards, conditional
  sums, as-of joins and window functions in one language.
- It stays checkable: SQL on a fixed warehouse is deterministic, so the receipt
  records the query and the result's fingerprint and `verify` re-runs it.
- It is safe over the connector: read-only DuckDB reaches no secrets and
  writes nothing, unlike Python.
- **It may reference model measures by name** (for example
  `{{ measure('fair_value') }}`), so full freedom still reuses the governed
  definitions where consistency matters.

The data still has to hold the answer: a cost-basis rollforward needs the cost
relieved on a sale, which the demo's `fact_activities` does not carry yet.

## Why not make everything SQL (considered, rejected)

The case for it is real: one language with no ceiling, what agents write best,
receipts still work, less to build, dbt shows teams cope. It was rejected
because:

1. **One number, many definitions.** Ten analysts write "revenue" ten ways;
   each has a valid receipt. A receipt proves where a number came from, not
   what it means. A named measure is what makes "revenue" mean one thing.
2. **Joins are where numbers go wrong.** The model knows grain and keys and
   refuses a fan-out; free SQL multiplies rows silently.
3. **Measures recompose; queries do not.** A measure stays correct sliced by
   any dimension, filtered, compared with last period. A query answers one
   question.
4. **Ratios and balances are traps.** A ratio of totals, a month-end balance:
   the model encodes them once; in SQL every author must know them every time.
5. **Review and "official".** A reviewer can read a model; nobody reviews 300
   report queries.
6. **Agents need constraints most.** An agent composing at volume writes
   plausible, subtly wrong SQL with nobody reading it.

So: the model is the foundation, SQL is the escape hatch, each labelled.

## Keeping the model correct with many editors

- **Every model change is a draft, then published.** Nobody edits the live
  model ([[remote-authoring]] step 1, already built).
- **Impact check before publishing.** Re-run every published report that
  reads the model against the changed model and show which numbers move (the
  re-run and compare `tracebi verify` already does). A change that moves
  numbers is accepted on purpose by someone with Publish on the model.
- **Owners.** Each model has owners; only they or admins publish it. Analysts
  are never blocked: they calculate in their report or workspace and propose.
- **Promotion.** A report, personal or SQL calculation that keeps being reused
  is proposed into the model (or into the transform, as a table) and goes
  through that review.

## Workspaces (from [[report-library]], one addition)

- Personal drafts (`drafts/<owner>/`, "My work") and publishing as TraceBi's
  own step, with history kept beside each report, are decided; drafts are built.
- Folders with View / Build / Publish / Manage per sign-in group, and
  publish-with-approval, are decided, not built.
- **Addition:** a personal folder a person can **publish into** ("My
  published"), for something shareable and scheduled without the public folder.
- A folder decides what it accepts: anything honestly labelled, or only
  re-checkable numbers.

## Not changing

The three phases, the receipts, the closed vocabulary over the connector for
anything executable (Python still comes through a laptop and review, or the
sandbox), and the roles (viewer, analyst, admin) as folder defaults.

## Order of work

1. The filtered measure, and report-level calculations (unblocks the field
   test's question).
2. SQL calculations: read-only, stamped, re-checked by `verify`, able to
   reference model measures.
3. The impact check on model publishing, and model owners.
4. Folders, permissions, publishing into folders, "My published".
5. Personal calculations and promotion.
6. The Python sandbox.
