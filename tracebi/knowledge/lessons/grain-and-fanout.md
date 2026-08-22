---
slug: grain-and-fanout
title: Pick the grain first; a join that fans out inflates every sum
when: joining a fact to a dimension that is one-to-many, or any sum that looks too big
---
**The pitfall.** You join orders to a dimension where each order matches several
rows (a bridge table, a multi-value attribute, a coarser calendar). The join
duplicates every fact row, and now `sum(revenue)` counts each order two, three,
five times. The total is confidently, invisibly too large.

**What TraceBi does for you.** The engine has a **fanout guard**: a query whose
join multiplies fact rows *raises* rather than returning an inflated total. This
is the single most valuable guardrail in the framework — it refuses the wrong
number at the moment you'd make it, for any agent, unskippably. If you hit it,
the fix is not to work around it; it's that your grain is wrong.

**The correct pattern.** Decide the **grain** — the one row-level your fact
lives at — before you model anything, and keep measures additive at that grain.
When you need a coarser rollup (revenue by month, by region), that's a
`GROUP BY` over the grain, which is exactly what a model query does:

```python
model.query(fact="orders", measures=["revenue"], dimensions=["dim_date.month"])
```

not a join that stretches one order across many rows.

**The tell.** A total that jumped when you added a dimension, or the fanout guard
firing, both mean the same thing: the query is counting fact rows more than once.
Fix the grain, don't silence the guard.
