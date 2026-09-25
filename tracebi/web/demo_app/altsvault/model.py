"""The star-schema contract over the AltsVault warehouse the transform sinks.

Two modeling decisions worth reading before the measures:

1. **Mark is a ratio of totals, never a mean of rates.** The source ships a
   per-fund ``weighted_mark_cost``, but averaging per-row rates overweights
   small positions. ``mark`` divides summed fair value by summed cost, so it
   composes correctly at every grain a report groups by.

2. **``period_end`` is descriptive, not a time axis.** Each fund has one row,
   but funds report as of different dates: a snapshot, not a panel. The
   declared quarter grain shows how stale the universe is, never a trend.

Construction is declarative and lazy; importing this does not touch the
warehouse, which may not exist until the pipeline's first run.
"""

from __future__ import annotations

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector

from tracebi.web.demo_app.altsvault import WAREHOUSE

connector = DuckDBConnector("warehouse", database=WAREHOUSE)

model = (
    DataModel("altsvault_credit_marks")
    .add_connector(connector)
    # ── tables ← the exact names phase ① sank ────────────────────────────────
    .add_table("fact_position_marks", connector="warehouse", source="fact_position_marks")
    .add_table("fact_fund_marks", connector="warehouse", source="fact_fund_marks")
    .add_table("dim_fund", connector="warehouse", source="dim_fund")
    .add_table("dim_issuer", connector="warehouse", source="dim_issuer")
    .add_table("dim_period", connector="warehouse", source="dim_period")
    .add_table("dim_mark_band", connector="warehouse", source="dim_mark_band")
    .add_table("dim_seniority", connector="warehouse", source="dim_seniority")
    .add_table("dim_position_class", connector="warehouse", source="dim_position_class")
    # ── dimensions ───────────────────────────────────────────────────────────
    .add_dimension("dim_fund", table_name="dim_fund", key_col="slug",
                   attributes=["fund_name", "structure", "asset_class",
                               "recon_status", "crowding_band", "months_stale"])
    .add_dimension("dim_issuer", table_name="dim_issuer", key_col="issuer_key",
                   attributes=["display_name", "industry", "holder_band"])
    .add_dimension("dim_period", table_name="dim_period", key_col="period_end",
                   attributes=["quarter", "year"])
    .add_dimension("dim_mark_band", table_name="dim_mark_band", key_col="mark_band",
                   attributes=["band_order", "band_note"])
    .add_dimension("dim_seniority", table_name="dim_seniority", key_col="seniority",
                   attributes=["seniority_order", "is_secured"])
    .add_dimension("dim_position_class", table_name="dim_position_class",
                   key_col="position_class", attributes=["class_note"])
    # a declared quarter rollup over the as-of date — used to show how stale
    # the universe is, NOT as a trend axis (see the module docstring)
    .add_time_grain("dim_period", "as_of_quarter", source="period_end", grain="quarter")
    # ── facts ────────────────────────────────────────────────────────────────
    .add_fact("fact_position_marks", table_name="fact_position_marks",
              measures=["fair_value", "cost", "mark_cost", "principal", "position_one"],
              foreign_keys={"dim_fund": "slug", "dim_period": "period_end",
                            "dim_issuer": "issuer_key", "dim_mark_band": "mark_band",
                            "dim_seniority": "seniority",
                            "dim_position_class": "position_class"})
    .add_fact("fact_fund_marks", table_name="fact_fund_marks",
              measures=["book_fv", "marked_fv", "positions_counted",
                        "positions_excluded", "fv_below_watch", "fv_below_stress",
                        "fv_below_deep", "positions_total"],
              foreign_keys={"dim_fund": "slug", "dim_period": "period_end"})
    # ── measures — position grain ────────────────────────────────────────────
    .add_measure("fair_value", column="fair_value", agg="sum",
                 description="Fair value carried, summed across positions",
                 format="currency0")
    .add_measure("cost_basis", column="cost", agg="sum",
                 description="Original cost basis of those positions",
                 format="currency0")
    .add_measure("positions", column="position_one", agg="sum",
                 description="Number of positions")
    .add_measure("issuers", column="issuer_key", agg="nunique",
                 description="Distinct issuers held")
    .add_measure("funds_holding", column="slug", agg="nunique",
                 description="Distinct funds holding")
    .add_measure("mark", ratio=("fair_value", "cost_basis"),
                 description="Fair value as a share of cost — a ratio of totals, "
                             "not a mean of per-position rates",
                 format="percent")
    .add_measure("median_mark", column="mark_cost", agg="median",
                 description="Median position mark — the typical position, "
                             "unmoved by the tail", format="percent")
    .add_measure("mark_dispersion", column="mark_cost", agg="stddev",
                 description="Standard deviation of position marks — how widely "
                             "marks spread within the group")
    # concentration, governed: share → rank → running(share) is the whole
    # Pareto table without a line of report.py
    .add_measure("fv_share", share="fair_value",
                 description="This row's share of total fair value",
                 format="percent")
    .add_measure("fv_rank", rank="fair_value",
                 description="Position by fair value, 1 = largest")
    .add_measure("fv_cumshare", running="fv_share",
                 description="Cumulative share of fair value, largest first",
                 format="percent")
    # ── measures — fund grain ────────────────────────────────────────────────
    .add_measure("book_fv", column="book_fv", agg="sum",
                 description="Total book fair value across funds",
                 format="currency0")
    .add_measure("marked_fv", column="marked_fv", agg="sum",
                 description="Fair value with a computable mark", format="currency0")
    .add_measure("funds", column="slug", agg="nunique", description="Fund count")
    .add_measure("fv_below_stress", column="fv_below_stress", agg="sum",
                 description="Fair value carried below 80% of cost",
                 format="currency0")
    .add_measure("fv_below_deep", column="fv_below_deep", agg="sum",
                 description="Fair value carried below 70% of cost",
                 format="currency0")
    .add_measure("stress_share", ratio=("fv_below_stress", "book_fv"),
                 description="Share of book value carried below the stress band",
                 format="percent")
    .add_measure("marked_coverage", ratio=("marked_fv", "book_fv"),
                 description="Share of book value that has a computable mark",
                 format="percent")
    .add_measure("median_months_stale", column="months_stale", agg="median",
                 description="Median months since the fund's reporting date")
)
