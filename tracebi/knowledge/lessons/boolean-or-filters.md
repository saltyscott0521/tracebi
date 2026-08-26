---
slug: boolean-or-filters
title: OR across different columns is a filter group, not two queries
when: filtering rows on an OR condition — this OR that, across different columns or operators
---
**The pitfall.** `filters` AND-s its entries, so `{"sector": "Tech", "rating":
"AAA"}` means Tech *and* AAA. When you actually want Tech *or* AAA, the AND
grammar can't say it — so the work spills into two separate queries stitched
together in `report.py` (ungoverned, `verifiable: false`), or a wrong number
ships because the AND quietly returned far fewer rows than intended.

`in` only covers OR over **one** column's values (`{"rating": ["AAA", "AA"]}`).
OR across **different** columns or operators needs a boolean group.

**The correct pattern in TraceBi.** The reserved keys `or` and `and` take a
list of condition groups (each itself a filter dict):

```python
model.query(fact="holdings", measures=["fair_value"],
            filters={"or": [{"dim_issuer.sector": "Tech"},
                            {"dim_issuer.rating": "AAA"}]})   # Tech OR AAA
```

Every other key in the same dict **AND-s** with the group, and groups nest, so
you can build any boolean expression:

```python
filters={"status": "active",
         "or": [{"dim_region.region": "West"},
                {"revenue": {"gte": 1000}}]}
# status = active AND (region = West OR revenue >= 1000)
```

It stays one governed query with a receipt — the boolean structure is recorded
in the stamped spec, and the result is reproducible.

**The tell.** Running two queries and unioning them in `report.py`, or reaching
for an AND filter and getting suspiciously few rows because you meant OR? Use an
`or` group. (For OR over a single column's values, `in` is simpler — reach for
`or` when the branches differ in column or operator.)
