# Queries

A query is what a report asks a [[model]]: measures, dimensions, filters,
`having`, ordering and a limit, written as data rather than SQL.

```json
{
  "fact": "fact_orders",
  "measures": ["revenue", "margin_pct"],
  "dimensions": ["dim_customer.region"],
  "filters": {"status": "shipped"},
  "having": {"revenue": {"gte": 250}},
  "order_by": [{"column": "revenue", "desc": true}],
  "limit": 10
}
```

This is what a [[report-json]] binding holds. Because a query is data (a
`QuerySpec`), it can be checked before it runs, reviewed in a pull request,
and re-run later by `tracebi verify`. Unknown fields are refused by name.

## In Python

```python
model.query(
    fact,                 # required: a registered fact
    measures,             # required: declared names, or {out_col: spec}
    dimensions=None,      # ["dim_name.attribute", ...]; None for totals only
    filters=None,         # WHERE: before aggregation
    having=None,          # HAVING: after aggregation
    aggregate=True,
    allow_fanout=False,
    allow_rate_agg=False,
    order_by=None,
    limit=None,
)
```

It returns a `DataSet` with full [[lineage]]:

```python
top_segments = model.query(
    fact="fact_orders",
    measures=["revenue", "gross_margin", "margin_pct",
              "rev_rank", "revenue_share", "cum_share"],
    dimensions=["dim_customer.region", "dim_customer.segment"],
    filters={
        "status": "shipped",
        "or": [{"dim_customer.region": ["NE", "SE"]},
               {"revenue": {"gte": 10_000}}],
    },
    having={"revenue": {"gte": 250}},
    order_by=["-revenue"],
    limit=10,
)
top_segments.print_lineage()   # load → join → filter → aggregate → assign → filter → sort
top_segments.fingerprint()     # a content hash that reproduces
```

## `measures`

| Form | Example |
|---|---|
| Declared names | `["revenue", "gross_margin", "margin_pct"]` |
| Ad hoc: aggregate a column | `{"revenue": "sum"}` |
| Ad hoc: aggregate a renamed column | `{"units": ("qty", "sum")}` |
| Ad hoc: row expression | `{"margin": {"expr": "revenue - cost", "agg": "sum"}}` |
| Ad hoc: ratio after aggregation | `{"margin_pct": {"ratio": ["margin", "revenue"]}}` |

An undeclared name in the list form is refused with both fixes: declare it
with `add_measure()`, or use the ad-hoc form.

## `dimensions`

Dotted references, `"dim_name.attribute"`. Attributes include declared ones,
time grains and value bins ([[measures]]). Leave them out for totals only.

## `filters`

Filters apply before aggregation (`WHERE`). Every operator is parameterised,
and the set is closed:

```
eq  ne  in  not_in  gt  gte  lt  lte  between  is_null  not_null  contains
```

| Operator | Value |
|---|---|
| `between` | `[low, high]` |
| `in` / `not_in` | A list. An empty list matches nothing / everything. |
| `contains` | A substring |
| `is_null` / `not_null` | Ignored |

```python
filters={"status": "shipped"}                    # equality
filters={"region": ["NE", "SE"]}                 # a list means in
filters={"revenue": {"gte": 1000}}               # an operator
filters={"dim_customer.region": "West"}          # a dimension attribute
filters={"or": [{"sector": "Tech"},              # a boolean group
                {"rating": "AAA"}]}
```

A dimension used only in a filter is still joined.

**Boolean groups.** `or` and `and` take a list of condition groups. Every
other key in the same dict is ANDed with the group, and groups nest:

```python
filters={
    "status": "shipped",                      # ANDed with the group below
    "or": [
        {"dim_customer.segment": "Enterprise"},
        {"revenue": {"gte": 10_000}},
        {"and": [
            {"dim_customer.region": ["NE", "SE"]},
            {"qty": {"gt": 100}},
        ]},
    ],
}
# WHERE status = 'shipped'
#   AND (segment = 'Enterprise' OR revenue >= 10000
#        OR (region IN ('NE','SE') AND qty > 100))
```

Use `in` for several values of one column; use `or` across columns or
operators.

## `having`

`having` applies after aggregation, to result columns: measures, ratios,
shares, ranks, running totals, growth. It uses the same operators as filters.

```python
having={"revenue": {"gte": 250}}    # keeps groups whose total revenue is ≥ 250; totals unchanged
filters={"revenue": {"gte": 250}}   # drops rows under 250 before summing; every total changes
```

- `having` is a flat dict; every entry is ANDed. Only `filters` takes `or` and
  `and`.
- It is refused with `aggregate=False`.

## `order_by`

```python
order_by=["-revenue"]                            # '-col' descending, 'col' ascending
order_by=[{"column": "revenue", "desc": True}]   # the canonical form
order_by=["dim_customer.region", "-revenue"]     # earlier keys sort first
```

- Keys may be any result column, measures included.
- A lone key (`"-revenue"`, or one dict) is wrapped in a list.
- After your keys, every remaining column is added as an ascending
  tie-break, dimensions first, then measures. Without it, a top 10 with ties
  at the boundary could return a different set each run and move the
  fingerprint.
- The resolved ordering is stamped into the recorded query. A non-aggregate
  query with no `order_by` gets a full ordering for the same reason.

## `limit`

`limit` requires `order_by`. Without a stated order, "first N rows" would pass
for "top N".

```python
order_by=["-revenue"], limit=10    # correct
limit=10                           # refused
```

## Order of operations

```
aggregation → ratios → shares → windows (rank, running)
  → period-over-period → to-date → having → order_by → limit
```

This is why `having` can filter a rank, and why a share is computed over the
whole result.
