# Then vs Now: financing the median home

A complete TraceBi project on public data: what the median US home cost to
finance every year since 1971, and how much of the median household's
income the payment took. The report compares any two eras, and lets the
reader try their own numbers.

```bash
cd examples/mortgage_project
python run_workflow.py            # transform → model → report
open output/affordability.html    # or: tracebi serve
```

## What is on the page

- **Receipted figures.** The headline, the four cards and the four line
  charts (rate; price and income; monthly payment; payment as a share of
  income) are live queries against `housing_model`, fingerprinted in the
  manifest. `tracebi verify output/affordability.html.manifest.json
  --strict --contracts` re-runs every one.
- **A scenario.** "Compare any two years" is a `data-tb-scenario` block.
  Picking a year fills the inputs from that year's stamped row. The reader
  can then change the rate, price, income, down payment or term. The
  payment, share of income and total interest are computed in the browser
  from those inputs. The block is labeled as a scenario, is never a figure,
  and is recorded in the manifest as a declaration with `verifiable: false`.

## The three phases

| Phase | File | What it does |
| --- | --- | --- |
| ⓪ input | `inputs/housing_history.csv` | One row per year: rate, median price, median income. See `inputs/SOURCES.md`. |
| ① transform | `transforms/affordability_transform.py` | Works out each year's payment (20% down, 30 years, principal and interest) and sinks `fact_housing` + `dim_year`, with a sink contract. |
| ② model | `models/housing_model.py` | The measures: rate, price, income, payment, `payment_share` and `price_to_income` as ratios of totals. |
| ③ report | `reports/affordability/` | `report.json` bindings, `template.html` with the charts and the scenario. |

## Refresh the data first

The committed CSV is a snapshot typed in without network access; it is
close, not exact. On a machine that can reach FRED:

```bash
python inputs/fetch_data.py && python run_workflow.py
```
