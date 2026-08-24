---
slug: rank-and-cumulative
title: Rank and running totals are governed measures, not report.py
when: ranking rows, or building a concentration / Pareto / cumulative view (top-N with cumulative %)
---
**The pitfall.** A concentration table — rank each position, its % of the book,
and the *cumulative* % as you go down — is the classic thing that used to force
`report.py`: it's a window over the ordered result, which the query surface
couldn't express, so the numbers came back `verifiable: false`, out of the
governed lane.

**The correct pattern in TraceBi.** Three governed measures give the whole table:

```python
model.add_measure("revenue", column="revenue", agg="sum")
model.add_measure("rev_rank",      rank="revenue")                       # 1..N, largest first
model.add_measure("revenue_share", share="revenue", format="percent")    # % of total
model.add_measure("cum_share",     running="revenue_share", format="percent")  # cumulative %

model.query(fact="holdings",
            measures=["revenue", "rev_rank", "revenue_share", "cum_share"],
            dimensions=["dim_issuer.issuer"],
            order_by=[{"column": "rev_rank", "desc": False}])
```

| issuer | revenue | rev_rank | revenue_share | cum_share |
|--------|--------:|---------:|--------------:|----------:|
| West   |   500   |    1     |     50%       |    50%    |
| East   |   300   |    2     |     30%       |    80%    |
| …      |    …    |    …     |      …        |     …     |

`rank` orders by its base measure descending (rank 1 = largest); `running` is the
cumulative sum in that same largest-first order — a `running` of a *share* is the
cumulative % of total. Every one carries a receipt, and a total tie-break makes
them reproducible (see [[share-of-total]]).

**The tell.** Reaching for `report.py` to compute a rank, a running total, or a
concentration curve? You don't need it — those are `rank` and `running`
measures. Save `report.py` for the genuinely bespoke; a concentration table is
not bespoke.
