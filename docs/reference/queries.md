# Queries

**What a report may ask a [[model]]: measures, dimensions, filters, `having`,
ordering, limits — as data, not SQL.**

A query is a `QuerySpec`: validatable, serializable, diffable in a pull request,
and replayable. That is what lets [[receipts|`tracebi verify`]] re-run it later.

---

## The shape

```python
model.query(
    fact,                 # required — a registered fact
    measures,             # required — declared names, or {out_col: spec}
    dimensions=None,      # ["dim_name.attribute", ...]; None = totals only
    filters=None,         # WHERE  — before aggregation
    having=None,          # HAVING — after aggregation
    aggregate=True,
    allow_fanout=False,
    allow_rate_agg=False,
    order_by=None,
    limit=None,
)
```

The same thing as JSON, which is what a [[report-json]] binding holds:

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

Unknown fields are rejected by name.

## Measures

**By declared name** — the governed form:

```python
measures=["revenue", "gross_margin", "margin_pct"]
```

**Ad hoc**, when the model hasn't declared it yet — the same three kinds:

```python
measures={
    "revenue":    "sum",                                    # aggregate a column
    "units":      ("qty", "sum"),                           # aggregate a renamed column
    "margin":     {"expr": "revenue - cost", "agg": "sum"}, # a row expression
    "margin_pct": {"ratio": ["margin", "revenue"]},         # divided AFTER aggregation
}
```

An undeclared name in the list form is refused, and tells you both fixes:
declare it with `add_measure()`, or pass the ad-hoc form.

## Dimensions

Dotted references — `"dim_name.attribute"`. Attributes include declared ones
plus derived [[measures#`add_time_grain` — group by month/quarter/…|time grains]]
and [[measures#`add_value_bins` — group by a numeric band|value bins]].

Omit them for totals only.

---

## Filters — `WHERE`, before aggregation

### Operators

```
eq  ne  in  not_in  gt  gte  lt  lte  between  is_null  not_null  contains
```

A **closed set**, deliberately: free SQL cannot be validated and is an injection
surface. Every operator is parameterised.

- `between` takes `[low, high]`
- `in` / `not_in` take a list — an empty list matches nothing / everything,
  explicitly
- `contains` is a substring match
- `is_null` / `not_null` ignore the value

### The five forms

```python
filters={"status": "shipped"}                    # 1. equality
filters={"region": ["NE", "SE"]}                 # 2. list → in
filters={"revenue": {"gte": 1000}}               # 3. explicit operator
filters={"dim_customer.region": "West"}          # 4. dimension attribute
filters={"or": [{"sector": "Tech"},              # 5. boolean group
                {"rating": "AAA"}]}
```

A dimension referenced only by a filter is still joined.

### Boolean groups

`or` and `and` are reserved keys taking a list of condition groups. **Every
other key in the same dict ANDs with the group**, and groups nest:

```python
filters={
    "status": "shipped",                      # AND-ed with the group below
    "or": [
        {"dim_customer.segment": "Enterprise"},
        {"revenue": {"gte": 10_000}},
        {"and": [                             # groups nest
            {"dim_customer.region": ["NE", "SE"]},
            {"qty": {"gt": 100}},
        ]},
    ],
}
# WHERE status = 'shipped'
#   AND (segment = 'Enterprise' OR revenue >= 10000
#        OR (region IN ('NE','SE') AND qty > 100))
```

Use `in` for OR over **one column's values**; use `or` for OR across
**different columns or operators**.

---

## `having` — after aggregation

**This is the distinction that quietly ruins totals if you get it backwards:**

```python
having={"revenue": {"gte": 250}}    # keeps GROUPS whose summed revenue ≥ 250 — totals intact
filters={"revenue": {"gte": 250}}   # drops raw ROWS below 250 BEFORE summing — every total changes
```

Same operators and value spellings as filters, on **result** columns — measure
names, ratios, shares, ranks, running totals, growth. It runs after every
post-aggregation measure is computed, which is exactly why it can filter them.

Two limits worth knowing:

- **No boolean grouping.** `having` is a flat dict; every entry ANDs. Only
  `filters` supports `or`/`and`.
- Refused with `aggregate=False` — there are no group totals to filter.

---

## Ordering and limit

```python
order_by=["-revenue"]                            # '-col' desc, 'col' asc
order_by=[{"column": "revenue", "desc": True}]   # canonical form
order_by=["dim_customer.region", "-revenue"]     # earlier keys sort first
```

A lone key (`"-revenue"`, or a single dict) is accepted and wrapped — otherwise
a bare string would iterate as characters and fail at a character. The canonical
form is a list.

Keys may be any **result** column, measures included.

### `limit` requires `order_by`

```python
limit=10                       # REFUSED on its own
order_by=["-revenue"], limit=10  # correct
```

> *"without a stated ordering, 'first N rows' silently masquerades as 'top N'."*

### Ties break deterministically

After your stated keys, **every remaining column** is appended as an ascending
tie-break — the dimension columns first, then the measures — so the sort key
uniquely orders every row.

Without this, a "top 10" whose values tie at the boundary returns a different
set across identical runs, and the fingerprint moves for no reason.

The fully resolved ordering is stamped into the recorded query, so a replay
compares like with like. A non-aggregate query with no `order_by` gets a
canonical total order imposed for the same reason.

---

## A complete query

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
top_segments.fingerprint()     # reproducible content hash
```

Returns a `DataSet` with full [[lineage]] — hand it to a report section and the
lineage travels into the manifest.

## Order of operations

Worth knowing, because it explains what `having` can filter and what `share`
and `running` are computed over:

```
engine aggregation → ratios → shares → windows (rank/running)
  → period-over-period → to-date → having → order_by → limit
```

## Related

- [[measures]] — what you can ask for
- [[report-json]] — where a query lives in a report
- [[model]] — what answers it
