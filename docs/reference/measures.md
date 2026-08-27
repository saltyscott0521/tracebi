# Measures

**Named, declarative calculations on a [[model]]. Ten kinds, a closed set of
aggregations, and guardrails that refuse the arithmetic that is quietly wrong.**

A report asks for a measure **by name**. That is what makes a figure
re-runnable, and therefore [[receipts|receiptable]].

---

## Declaring one

```python
model.add_measure(
    name, *,
    column=None, expr=None, ratio=None, share=None, rank=None, running=None,
    period_end=None, offset=None, growth=None, to_date=None,   # exactly ONE
    partition_by=None,      # rank / running only
    agg=None,               # required for column= / expr=; rejected by the rest
    description="", format=None,
    allow_rate_agg=False, allow_additive=False,
)
```

Exactly one kind argument. `format` takes a name from [[number-formats]].
Chainable — it returns the model.

---

## The ten kinds

### `simple` — one column, one aggregation

```python
model.add_measure("revenue", column="revenue", agg="sum", format="currency0")
model.add_measure("orders",  column="order_id", agg="nunique")
```

### `expression` — row arithmetic, then aggregate

```python
model.add_measure("gross_margin", expr="revenue - cost", agg="sum")
```

**Arithmetic over column names only** — no function calls, no quotes, no SQL
fragments. A spec that cannot be validated before execution is not a spec.

### `ratio` — divide aggregated totals

```python
model.add_measure("margin_pct", ratio=("gross_margin", "revenue"), format="percent")
```

**Divides totals, not per-row values** — `sum(a) / sum(b)`, never the mean of
per-row ratios. This is the fix the rate guard points you at, and it is also how
you express a **weighted average**: a ratio whose numerator carries the weight
(sum it, then divide).

Null-safe: a zero denominator yields null, not an infinity.

### `share` — percent of total

```python
model.add_measure("revenue_share", share="revenue", format="percent")
```

Each row's value over the total **across the whole result, before `having` and
before `limit`** — so a top-10 table shows each row's share of the whole
population, not of the ten rows displayed.

### `rank` — 1..N position

```python
model.add_measure("rev_rank",       rank="revenue")
model.add_measure("rank_in_region", rank="revenue", partition_by="dim_customer.region")
```

Ordered by the named measure descending (rank 1 = largest), with a total
tie-break so it reproduces.

`partition_by` restarts the rank per group. Paired with `having`, it expresses
**top-N-per-group** — which a global `order_by` + `limit` cannot:

```python
model.query(
    fact="fact_orders",
    measures=["revenue", "rank_in_region"],
    dimensions=["dim_customer.region", "dim_customer.segment"],
    having={"rank_in_region": {"lte": 3}},        # top 3 per region
    order_by=["dim_customer.region", "-revenue"],
)
```

Every `partition_by` column must be in the query's `dimensions`.

### `running` — cumulative, largest first

```python
model.add_measure("cum_share", running="revenue_share", format="percent")
```

The Pareto/concentration direction. `running` of a share is the cumulative
percent of total, so `rank` + `share` + `running(share)` is the whole
concentration table — governed, with its receipt intact.

### `period_end` — semi-additive balances

```python
model.add_measure("aum", period_end=("balance", "dim_date.as_of_date"),
                  format="currency0")
```

For **stocks**, not flows: AUM, NAV, headcount, inventory. Summed across
non-time dimensions, but taken at the **latest snapshot** over time — never
summed across snapshots, because January AUM + February AUM is not AUM.

Group by a time grain to get the period-end series.

### `offset` — the prior period's value

```python
model.add_measure("rev_ly", offset=("revenue", "year", 1), format="currency0")
```

A `(base, unit, n)` triple; unit is `day`/`week`/`month`/`quarter`/`year`.

### `growth` — period-over-period change

```python
model.add_measure("rev_yoy", growth=("revenue", "year", 1), format="percent")
```

`(current − prior) / prior`. YoY with `('revenue','year',1)`; QoQ and MoM by
unit.

> **Both compare against periods *present in the result*.** Don't filter out the
> comparison period — a `WHERE` removes the prior period the measure needs.
> Restrict the display with `order_by` + `limit`, which run *after* the shift.

```python
model.query(
    fact="fact_orders",
    measures=["revenue", "rev_ly", "rev_yoy"],
    dimensions=["dim_date.order_month"],
    order_by=["-dim_date.order_month"], limit=12,     # not a filter
)
```

### `to_date` — YTD / QTD / MTD

```python
model.add_measure("rev_ytd", to_date=("revenue", "year"), format="currency0")
```

A running total from the start of the reset period. Reset periods are
`week`/`month`/`quarter`/`year` — **`day` is not one**.

The query's time grain must be **finer** than the reset period: YTD over
monthly works; YTD over yearly does not.

> **`running` vs `to_date`:** `running` is a cumulative ordered by the *base
> measure* (largest first, Pareto). `to_date` is a cumulative ordered by *time*
> within a reset partition. Different orderings, different questions.

Both `offset`/`growth`/`to_date` require exactly **one** declared time grain
among the query's dimensions.

---

## Aggregations

```
avg  count  max  mean  median  min  nunique  stddev  sum  p<N>
```

- `count` counts non-null rows; `nunique` counts distinct values.
- `median` and `stddev` summarize a distribution's **shape** — a mean hides skew
  and tails, so reach for them on returns, P&L, sizes and spreads.
- `p<N>` is any percentile from `p0` to `p100`. `p50` is the median; `p90`/`p95`/
  `p99` are the tail a mean and even a median hide.

```python
model.add_measure("p95_order", column="revenue", agg="p95", format="currency")
```

---

## Derived dimension attributes

Two governed ways to group by something the warehouse doesn't store as a column.
Both are declared on a dimension and referenced as `dim.name` like any attribute.

### `add_time_grain` — group by month/quarter/…

```python
model.add_time_grain("dim_date", "order_month", source="order_date", grain="month")

model.query(fact="fact_orders", measures=["revenue"],
            dimensions=["dim_date.order_month"])
```

A governed `date_trunc`. Grains: `day`, `week`, `month`, `quarter`, `year`.
This is "group by month" without dropping to `report.py` or pre-baking the
bucket in the [[transform]].

### `add_value_bins` — group by a numeric band

```python
model.add_value_bins("dim_customer", "score_band",
                     source="credit_score", edges=[600, 700, 800])
# 3 edges → 4 bands: "< 600", "600–700", "700–800", "≥ 800"
```

A governed `CASE` over ranges — credit score, age, vintage. Custom `labels` take
one per band (`len(edges) + 1`).

Three things to know:
- A **null** source groups as null, not as the top band.
- Bands sort **lexicographically by label**, so choose labels that sort if
  magnitude order matters (`"1 subprime"`, `"2 near-prime"`, …).
- Bands are **groupable, not filterable** — filter on the source column.

---

## The guardrails

Five refusals. Each exists because the alternative is a confident wrong number.

### Callables are rejected

A `column`, `expr` or `agg` that is a function is refused outright, with no
override. A function cannot be serialized, diffed, or validated before
execution — so it cannot be part of a declarative contract.

### Non-unique dimension keys → `allow_fanout=True`

Joining a dimension whose key repeats fans out the fact table and **inflates
every additive measure**. The refusal names the duplicate values and the exact
row multiplication.

The override is a *query* argument, and taking it records a `warning` lineage
node — so the opt-in leaves its own receipt.

### Rate aggregation, by name → `allow_rate_agg=True`

Aggregating a rate-named measure (`*_pct`, `*_bps`, `*_yield`, `*_rate`, or
anything described as "weighted") with `sum`/`mean`/`avg` is refused.

You do not additively combine per-row rates: summing is meaningless, and
averaging overweights small rows. `min`/`max` stay fine.

**The fix is a `ratio` measure** — the blended rate is
`sum(numerator) / sum(denominator)`.

### Rate aggregation, by value → `allow_rate_agg=True`

The name guard is blind to a per-row ratio whose name matches nothing —
`mark_cost = fair_value / cost`, sitting near 1.0. So the same guard fires again
at **query** time on the values: a floating column centred near 1.0, over at
least 20 rows, refuses `sum`/`mean`.

Override on the measure or on the query.

### Summing a stock → `allow_additive=True`

`agg="sum"` on a measure named `aum`, `nav`, `balance`, `headcount`,
`inventory` or `outstanding` is refused — a point-in-time balance
double-counts when summed across snapshots.

**The fix is a `period_end` measure.** Override only for a genuine *flow* (a
delta, not a level). This one is declare-time only; there is no query-level
escape.

---

## Related

- [[queries]] — asking for these measures
- [[model]] — where they are declared
- [[number-formats]] — the `format` argument
- Lessons: `tracebi knowledge ratio-of-totals`, `semi-additive`,
  `period-over-period`, `year-to-date`, `group-by-band`
