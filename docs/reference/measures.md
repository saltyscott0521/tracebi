# Measures

A measure is a named calculation on a [[model]]. A report asks for it by
name, which is what lets every figure be re-run.

```python
model.add_measure("revenue", column="revenue", agg="sum", format="currency0")
model.add_measure("margin_pct", ratio=("gross_margin", "revenue"), format="percent")
```

In a YAML model the same keywords go in a `measures:` entry
([[model-json]]).

## Signature

```python
model.add_measure(
    name, *,
    column=None, expr=None, ratio=None, share=None, rank=None, running=None,
    period_end=None, offset=None, growth=None, to_date=None,   # exactly one
    partition_by=None,      # rank and running only
    agg=None,               # required for column= and expr=; refused by the rest
    label=None, description="", format=None,
    allow_rate_agg=False, allow_additive=False,
    synonyms=None,
)
```

| Argument | Meaning |
|---|---|
| One kind argument | Exactly one of the ten kinds below. |
| `format` | A name from [[number-formats]]. |
| `label` | The name people read in the app ("Share of fair value" for `fv_share`). Changes no number; queries still use `name`. Without it the app makes one from the name. |
| `description` | The shared meaning, shown in tooltips, the trace and the model's Semantic layer page. |
| `synonyms` | Other words people use for it (`[market value, FV]`). Ask matches them, and an agent receives them in its context, so it can map a person's word to this measure. Words only: a query still uses `name`. |

It returns the model, so calls chain.

## The ten kinds

| Kind | Example | What it computes |
|---|---|---|
| `column` (simple) | `add_measure("revenue", column="revenue", agg="sum")` | One column, one aggregation. |
| `expr` (expression) | `add_measure("gross_margin", expr="revenue - cost", agg="sum")` | Row arithmetic, then the aggregation. Column names, numbers and `+ - * / ( )` only: no function calls, quotes or SQL. |
| `ratio` | `add_measure("margin_pct", ratio=("gross_margin", "revenue"), format="percent")` | `sum(a) / sum(b)`: totals divided, never a mean of row ratios. A zero denominator gives null. Also the way to write a weighted average. |
| `share` | `add_measure("revenue_share", share="revenue", format="percent")` | Each row's value over the total of the whole result, before `having` and `limit`. A top-10 table shows each row's share of everything. |
| `rank` | `add_measure("rev_rank", rank="revenue")` | Position 1..N by the measure, largest first, with a full tie-break. `partition_by="dim_customer.region"` restarts it per group. |
| `running` | `add_measure("cum_share", running="revenue_share", format="percent")` | A cumulative total ordered by the measure, largest first (Pareto). |
| `period_end` | `add_measure("aum", period_end=("balance", "dim_date.as_of_date"), format="currency0")` | For balances (AUM, NAV, headcount, inventory): summed across other dimensions, taken at the latest snapshot over time. |
| `offset` | `add_measure("rev_ly", offset=("revenue", "year", 1), format="currency0")` | The prior period's value. `(base, unit, n)`; unit is `day`, `week`, `month`, `quarter` or `year`. |
| `growth` | `add_measure("rev_yoy", growth=("revenue", "year", 1), format="percent")` | `(current − prior) / prior`. QoQ and MoM by unit. |
| `to_date` | `add_measure("rev_ytd", to_date=("revenue", "year"), format="currency0")` | A running total from the start of the period: `week`, `month`, `quarter` or `year` (not `day`). |

### Notes by kind

- **`rank` with `partition_by` and `having`** gives the top N per group, which
  a global `order_by` and `limit` cannot. Every `partition_by` column must be
  in the query's `dimensions`:

  ```python
  model.query(
      fact="fact_orders",
      measures=["revenue", "rank_in_region"],
      dimensions=["dim_customer.region", "dim_customer.segment"],
      having={"rank_in_region": {"lte": 3}},        # top 3 per region
      order_by=["dim_customer.region", "-revenue"],
  )
  ```

- **`rank`, `share` and `running(share)` together** make a concentration
  table.
- **`period_end`**: group by a time grain to get the period-end series.
  January AUM plus February AUM is not AUM.
- **`offset` and `growth` compare against periods present in the result.**
  Don't filter out the comparison period. Limit what is shown with `order_by`
  and `limit`, which run after the shift:

  ```python
  model.query(
      fact="fact_orders",
      measures=["revenue", "rev_ly", "rev_yoy"],
      dimensions=["dim_date.order_month"],
      order_by=["-dim_date.order_month"], limit=12,     # not a filter
  )
  ```

- **`to_date`** needs a time grain finer than its period: YTD by month works,
  YTD by year does not.
- **`running` and `to_date` differ.** `running` orders by the measure, largest
  first. `to_date` orders by time within each period.
- `offset`, `growth` and `to_date` need exactly one declared time grain among
  the query's dimensions.

## Aggregations

```
avg  count  max  mean  median  min  nunique  stddev  sum  p<N>
```

| Aggregation | Meaning |
|---|---|
| `count` | Non-null rows |
| `nunique` | Distinct values |
| `median`, `stddev` | The shape of a distribution, which a mean hides: use them on returns, P&L, sizes and spreads. |
| `p<N>` | Any percentile from `p0` to `p100`. `p50` is the median; `p90`, `p95` and `p99` show the tail. |

```python
model.add_measure("p95_order", column="revenue", agg="p95", format="currency")
```

## Derived attributes

Two ways to group by something the warehouse doesn't store as a column. Both
are declared on a dimension and used as `dim.name`.

### `add_time_grain`

```python
model.add_time_grain("dim_date", "order_month", source="order_date", grain="month")

model.query(fact="fact_orders", measures=["revenue"],
            dimensions=["dim_date.order_month"])
```

Grains: `day`, `week`, `month`, `quarter`, `year`. Each period is a label:
`2026-03-14`, `2026-W11` (ISO week), `2026-03`, `2026-Q1`, `2026`. A built
page's filters and recomputed figures use the same labels.

### `add_value_bins`

```python
model.add_value_bins("dim_customer", "score_band",
                     source="credit_score", edges=[600, 700, 800])
# 3 edges → 4 bands: "< 600", "600–700", "700–800", "≥ 800"
```

- `labels` takes one per band (`len(edges) + 1`).
- A null source groups as null, not as the top band.
- Bands sort by label as text, so pick labels that sort (`"1 subprime"`,
  `"2 near-prime"`).
- You can group by a band but not filter on it; filter on the source column.

## Refusals

Each refusal stops a confident wrong number.

| Refusal | When | Override |
|---|---|---|
| Callable | A `column`, `expr` or `agg` that is a function. A function cannot be serialized, diffed or checked before running. | None |
| Fan-out | A dimension's key repeats, which multiplies fact rows and inflates every sum. The error names the duplicate values and the multiplication. | `allow_fanout=True` on the query; it adds a `warning` lineage node. |
| Rate by name | `sum`, `mean` or `avg` of a measure named `*_pct`, `*_bps`, `*_yield`, `*_rate`, or described as "weighted". `min` and `max` are fine. Fix: a `ratio` measure. | `allow_rate_agg=True` on the measure or the query |
| Rate by value | At query time, `sum` or `mean` of a float column centred near 1.0 over at least 20 rows (such as `fair_value / cost`). | `allow_rate_agg=True` on the measure or the query |
| Summing a stock | `agg="sum"` on a measure named `aum`, `nav`, `balance`, `headcount`, `inventory` or `outstanding`. Fix: a `period_end` measure. | `allow_additive=True` on the measure only, for a real flow |

## Lessons

`tracebi knowledge ratio-of-totals`, `semi-additive`, `period-over-period`,
`year-to-date` and `group-by-band` explain these in full.
