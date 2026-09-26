# Where `housing_history.csv` comes from

One row per year, 1979 through the latest complete year, in current (not
inflation-adjusted) dollars. `python inputs/fetch_housing.py` rebuilds it from
the publishers; nothing is typed in by hand.

| Column | Series | Publisher |
| --- | --- | --- |
| `mortgage_rate` | 30-year fixed-rate average, annual mean of the weekly survey, percent | Freddie Mac PMMS (FRED `MORTGAGE30US`) |
| `existing_price` | Existing-home price level: the FHFA all-transactions repeat-sales index scaled to NAR's median existing-home price over its latest year or so | FHFA (FRED `USSTHPI`) + NAR (FRED `HOSMEDUSM052N`) |
| `new_home_price` | Median sales price of houses sold — mostly new construction | Census/HUD (FRED `MSPUS`) |
| `median_income` | Median household income, current dollars | Census CPS ASEC table H-5 (all races) |
| `earner_income` | Median usual weekly earnings of full-time wage and salary workers × 52 | BLS (FRED `LEU0252881500A`) |

`housing_anchor.txt` records the scale that turned the index into dollars on
the last refresh.

## Why these series

- **Existing homes, not `MSPUS`.** `MSPUS` is mostly new houses, which are
  bigger and pricier than the stock most people buy, and the mix has shifted.
  FRED carries NAR's existing-home median for the latest thirteen months only,
  so the price level comes from a repeat-sales index (the same homes over
  time) anchored to NAR. It is an estimate: close to NAR's published annual
  medians in some years, several percent off in others. That uncertainty is
  bigger than the gap between the eighties peak and today on the ten-year
  share, and the report says so.
- **One earner as well as the household.** Far more households have two
  earners than in the early eighties, so the household median flatters the
  present. The per-earner share shows the other side.
- **Starts in 1979** because the per-earner series does; that still includes
  the 1981 rate peak.

## What the transform assumes

20% down (so no mortgage insurance), closing costs 3% of price, a 30-year
fixed loan at the year's average rate, property tax 1.1% and insurance 0.35%
of the home's value a year — the same in every year. Each year's buyer is
followed for up to ten years, refinancing the remaining balance when a later
year's average rate is a full point lower; refinancing costs are left out.
The figures are national medians and hide metro differences.
