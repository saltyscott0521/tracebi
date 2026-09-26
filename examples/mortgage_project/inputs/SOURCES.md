# Where `housing_history.csv` comes from

One row per year, 1971 through 2023, in current (not inflation-adjusted)
dollars.

| Column | Series | Publisher |
| --- | --- | --- |
| `mortgage_rate` | 30-year fixed-rate mortgage average, annual mean of the weekly survey, in percent | Freddie Mac Primary Mortgage Market Survey (FRED `MORTGAGE30US`) |
| `median_price` | Median sales price of houses sold, annual mean of the quarterly series | U.S. Census Bureau and HUD (FRED `MSPUS`) |
| `median_income` | Median household income, current dollars | U.S. Census Bureau, CPS ASEC table H-8 (FRED `MEHOINUSA646N` from 1984) |

## The committed file is a snapshot. Refresh it before you cite it

The committed CSV was typed in from the published annual tables while the
build machine had no network access. Treat it as close, not exact. On a
machine that can reach FRED, run:

```bash
python inputs/fetch_data.py
```

That rewrites `housing_history.csv` from the official series (rate, price,
and income from 1984 on). Then rerun the transform. The FRED income series
starts in 1984, so the script keeps the snapshot's earlier income years and
says so as it runs.

Two things to know when comparing eras:

- **Annual averages differ from the numbers people remember.** Rates peaked
  well above the 1985 annual average, and in 2023 they peaked in October,
  above that year's average. The report plots the averages. The scenario
  lets you type in any rate you remember.
- **`median_price` is for new and existing houses sold as tracked by
  Census/HUD (`MSPUS`), which runs higher than existing-home medians from
  the National Association of Realtors.** Pick one series and keep it. The
  comparison is only fair within a series.
