# Where `housing_history.csv` comes from

One row per year, 1979 through the latest complete year, in current (not
inflation-adjusted) dollars. `python inputs/fetch_housing.py` rebuilds it from
the publishers; nothing is typed in by hand.

| Column | Series | Publisher |
| --- | --- | --- |
| `mortgage_rate` | 30-year fixed-rate average, annual mean of the weekly survey, percent | Freddie Mac PMMS (FRED `MORTGAGE30US`) |
| `existing_price` | NAR's median existing-home price: NAR's own annual figures through 2012 (`nar_existing_median_1968_2012.csv`, as reprinted by HUD); after that the FHFA repeat-sales index, pinned to NAR at both ends (2012, and NAR's latest months) | NAR via HUD *U.S. Housing Market Conditions*; FHFA (FRED `USSTHPI`); NAR (FRED `HOSMEDUSM052N`) |
| `new_home_price` | Median sales price of houses sold — mostly new construction | Census/HUD (FRED `MSPUS`) |
| `median_income` | Median household income, current dollars | Census CPS ASEC table H-5 (all races) |
| `earner_income` | Median usual weekly earnings of full-time wage and salary workers × 52 | BLS (FRED `LEU0252881500A`) |

`housing_anchor.txt` records the scale that turned the index into dollars on
the last refresh.

## Why these series

- **Existing homes, not `MSPUS`.** `MSPUS` is mostly new houses, which are
  bigger and pricier than the stock most people buy, and the mix has shifted.
  Through 2012 the price is NAR's own annual median, as HUD reprinted it in
  *U.S. Housing Market Conditions* (3Q2006 Table 9 and 4Q2012 Exhibit 9 — the
  two editions agree on every shared year). NAR does not publish its annual
  history freely after that, and FRED carries only its latest thirteen months,
  so 2013 on is an estimate: the FHFA repeat-sales index, pinned to NAR at
  both ends. An earlier version scaled the index to NAR's latest months only;
  checked against NAR's published figures it ran 6% low in 1981 and 9% high
  in 2010, which is why the published history now leads.
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
