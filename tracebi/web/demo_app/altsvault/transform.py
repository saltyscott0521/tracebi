"""Step 2 — TRANSFORM: AltsVault BDC credit marks.

Ordinary pandas over the pulled exports. It does the cleaning the data
actually needs and SINKS a star schema for credit marks into the warehouse,
then declares the sink contract.

**The grain finding that shapes everything.** The API serves each fund's
history: one ``fund_marks`` row per fund per reporting period. This report is
about where marks sit *now*, so it keeps each fund's **latest** reported
period. Funds report as of *different* latest dates, so the result is a
snapshot, not a panel: ``period_end`` is a descriptive attribute of the fund
and never a time axis. (Summing a fund's book value across its periods would
count the same book several times; the sink contract refuses that.)

**Cleaning actually required:**

* ``cost`` and ``mark_cost`` arrive as strings ("27500000.000000000000").
* ``seniority`` is often null → ``UNSTATED``; ``mark_band`` sometimes → ``UNCOMPUTABLE``.
* ``issuer_key`` is null on a small share → kept as ``(unresolved)`` rather
  than dropped, so positions still reconcile to the fund book exactly.

**Rates are never pre-aggregated here.** The model declares mark as a ratio of
totals (fair value / cost), so it composes correctly at every grain.

Because the data is pulled live, the contract checks what this pull must
satisfy (one fact row per fund pulled, positions reconciling to each fund's
book), not the counts of any one past snapshot.
"""

from __future__ import annotations

import os

import pandas as pd

from tracebi.web.demo_app.altsvault import RAW_DIR, WAREHOUSE


def _raw(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(RAW_DIR, f"{name}.csv"), low_memory=False)


def run() -> tuple[int, int]:
    """Clean, sink and check. Returns ``(raw position rows, sunk position rows)``."""
    pm = _raw("position_marks")
    fm = _raw("fund_marks")
    completeness = _raw("quality_fund_completeness")
    crowding = _raw("fund_crowding")
    exposure = _raw("issuer_fund_exposure")

    # ── Each fund's latest reported period ───────────────────────────────────
    n_fund_periods_all = len(fm)
    latest = fm.loc[fm.groupby("slug")["period_end"].transform("max") == fm["period_end"],
                    ["slug", "period_end"]].drop_duplicates()
    fm = fm.merge(latest, on=["slug", "period_end"])
    pm = pm.merge(latest, on=["slug", "period_end"])
    # Holder counts mean "funds holding it now", so the exposure census is cut
    # to the same latest periods (a fund that exited years ago isn't a holder).
    exposure = exposure.merge(latest, on=["slug", "period_end"])
    n_positions_raw, n_funds_raw = len(pm), len(fm)

    # ── The position grain: strings to numbers, nulls to closed sets ──────────
    pm["period_end"] = pd.to_datetime(pm["period_end"], utc=True).dt.date
    for col in ("cost", "mark_cost", "fair_value"):
        pm[col] = pd.to_numeric(pm[col], errors="coerce")
    n_unkeyed = int(pm["issuer_key"].isna().sum())
    n_unstated = int(pm["seniority"].isna().sum())
    n_uncomputable = int(pm["mark_band"].isna().sum())
    pm["issuer_key"] = pm["issuer_key"].fillna("(unresolved)")
    pm["seniority"] = pm["seniority"].fillna("UNSTATED")
    pm["mark_band"] = pm["mark_band"].fillna("UNCOMPUTABLE")
    debt = pm["is_debt_proxy"].astype(str).str.lower().map({"true": True, "false": False})
    pm["position_class"] = debt.map({True: "DEBT_PROXY", False: "EQUITY_OTHER"})
    pm["position_one"] = 1            # the countable unit, for the reconcile check

    fm["period_end"] = pd.to_datetime(fm["period_end"], utc=True).dt.date

    # ── Dimensions: closed sets, declared so the contract can check them ──────
    dim_mark_band = pd.DataFrame([
        ("UNSTRESSED",   1, 0.90, "at or above the watch band (≥90% of cost)"),
        ("WATCH",        2, 0.80, "below 90% of cost"),
        ("STRESS",       3, 0.70, "below 80% of cost"),
        ("DEEP_STRESS",  4, 0.00, "below 70% of cost"),
        ("UNCOMPUTABLE", 5, None, "no usable cost basis — mark cannot be computed"),
    ], columns=["mark_band", "band_order", "band_floor", "band_note"])
    dim_seniority = pd.DataFrame([
        ("FIRST_LIEN",      1, True),
        ("SECOND_LIEN",     2, True),
        ("OTHER_DEBT",      3, True),
        ("EQUITY_WARRANTS", 4, False),
        ("UNSTATED",        5, False),
    ], columns=["seniority", "seniority_order", "is_secured"])
    dim_position_class = pd.DataFrame([
        ("DEBT_PROXY",   "carried as a debt instrument"),
        ("EQUITY_OTHER", "equity, warrants, or other non-debt"),
    ], columns=["position_class", "class_note"])

    struct = (completeness[["slug", "structure", "asset_class", "months_stale"]]
              .drop_duplicates(subset="slug"))
    crowd = (crowding[["slug", "crowded_share", "unique_share", "total_issuers"]]
             .drop_duplicates(subset="slug"))
    dim_fund = (fm[["slug", "fund_name", "period_end", "recon_status", "is_partial"]]
                .drop_duplicates(subset="slug")
                .merge(struct, on="slug", how="left")
                .merge(crowd, on="slug", how="left"))
    dim_fund["structure"] = dim_fund["structure"].fillna("UNSTATED")
    dim_fund["asset_class"] = dim_fund["asset_class"].fillna("UNSTATED")
    dim_fund["crowding_band"] = pd.cut(
        dim_fund["crowded_share"], bins=[-0.001, 0.25, 0.50, 0.75, 1.001],
        labels=["Low (<25%)", "Moderate (25–50%)", "High (50–75%)", "Very high (>75%)"],
    ).astype("object").fillna("Unknown")

    iss = (exposure.groupby("issuer_key")
           .agg(display_name=("display_name", "first"),
                industry=("industry", "first"),
                holder_count=("slug", "nunique"))
           .reset_index())
    dim_issuer = pd.concat([iss, pd.DataFrame([{
        "issuer_key": "(unresolved)", "display_name": "(unresolved issuer)",
        "industry": None, "holder_count": 0,
    }])], ignore_index=True)
    dim_issuer["industry"] = dim_issuer["industry"].fillna("Unstated")
    dim_issuer["holder_band"] = pd.cut(
        dim_issuer["holder_count"], bins=[-1, 0, 1, 3, 7, 15, 10**6],
        labels=["Census unknown", "1 (sole holder)", "2–3", "4–7", "8–15", "16+"],
    ).astype("object")
    # Positions can name issuers the exposure census doesn't know yet; add them
    # as "census unknown" rather than dropping the positions.
    missing = sorted(set(pm["issuer_key"]) - set(dim_issuer["issuer_key"]))
    if missing:
        dim_issuer = pd.concat([dim_issuer, pd.DataFrame({
            "issuer_key": missing, "display_name": missing, "industry": "Unstated",
            "holder_count": 0, "holder_band": "Census unknown"})], ignore_index=True)
    dim_issuer = dim_issuer[dim_issuer["issuer_key"].isin(pm["issuer_key"].unique())].reset_index(drop=True)

    dim_period = (pd.DataFrame({"period_end": sorted(fm["period_end"].unique())})
                  .assign(quarter=lambda d: pd.PeriodIndex(pd.to_datetime(d["period_end"]), freq="Q").astype(str),
                          year=lambda d: pd.to_datetime(d["period_end"]).dt.year))

    # ── Facts ─────────────────────────────────────────────────────────────────
    fact_position_marks = pm[[
        "slug", "period_end", "position_seq", "issuer_key", "mark_band",
        "seniority", "position_class", "fair_value", "cost", "mark_cost",
        "principal", "recon_status", "position_one",
    ]].reset_index(drop=True)
    pos_rollup = (fact_position_marks.groupby(["slug", "period_end"])
                  .agg(positions_total=("position_one", "sum")).reset_index())
    fact_fund_marks = (
        fm[["slug", "period_end", "book_fv", "marked_fv", "positions_counted",
            "positions_excluded", "fv_below_watch", "fv_below_stress",
            "fv_below_deep", "recon_status"]]
        .merge(pos_rollup, on=["slug", "period_end"], how="left")
        .reset_index(drop=True))

    # ── SINK: these named tables are the contract the model reads ────────────
    from tracebi.connectors.duckdb_connector import DuckDBConnector

    os.makedirs(os.path.dirname(WAREHOUSE), exist_ok=True)
    wh = DuckDBConnector("warehouse", database=WAREHOUSE)
    for name, frame in [
        ("dim_fund", dim_fund), ("dim_issuer", dim_issuer), ("dim_period", dim_period),
        ("dim_mark_band", dim_mark_band), ("dim_seniority", dim_seniority),
        ("dim_position_class", dim_position_class),
        ("fact_fund_marks", fact_fund_marks), ("fact_position_marks", fact_position_marks),
    ]:
        wh.write(frame, name)

    # ── The sink CONTRACT: read-only SQL over what just landed ───────────────
    from tracebi.contracts import contract

    n_periods = int(fm["period_end"].nunique())
    with contract(
        "altsvault_credit_marks", warehouse=WAREHOUSE,
        note=(f"BDC credit marks pulled live from the AltsVault API, which served "
              f"{n_fund_periods_all:,} fund reporting periods. Each of the "
              f"{n_funds_raw} funds is taken as of its latest period; those fall on "
              f"{n_periods} different dates, so this is a snapshot, not a panel, and "
              "period_end is a descriptive attribute, never a time axis. "
              f"{n_unkeyed:,} positions with no "
              "resolvable issuer were kept as '(unresolved)' rather than dropped, so "
              f"positions still reconcile to the fund book exactly. {n_unstated:,} "
              f"null seniorities became UNSTATED and {n_uncomputable:,} null mark "
              "bands UNCOMPUTABLE. cost and mark_cost arrived as strings and were "
              "coerced."),
    ) as c:
        c.rows("fact_fund_marks", exactly=n_funds_raw, note="one row per fund: its latest period")
        c.unique("fact_fund_marks", ["slug"])
        c.rows("fact_position_marks", exactly=n_positions_raw,
               note="every pulled position lands; none are dropped in cleaning")
        c.rows("fact_fund_marks", at_least=1)
        c.rows("dim_position_class", exactly=2)
        for table, key in [("dim_fund", ["slug"]), ("dim_issuer", ["issuer_key"]),
                           ("dim_period", ["period_end"]), ("dim_mark_band", ["mark_band"]),
                           ("dim_seniority", ["seniority"]),
                           ("dim_position_class", ["position_class"]),
                           ("fact_fund_marks", ["slug", "period_end"]),
                           ("fact_position_marks", ["slug", "period_end", "position_seq"])]:
            c.unique(table, key)
        c.not_null("fact_fund_marks", ["slug", "period_end", "book_fv"])
        c.not_null("fact_position_marks",
                   ["slug", "period_end", "position_seq", "fair_value",
                    "mark_band", "seniority", "position_class", "issuer_key"])
        c.not_null("dim_fund", ["slug", "fund_name", "structure", "recon_status"])
        c.foreign_key("fact_fund_marks", "slug", refers_to=("dim_fund", "slug"))
        c.foreign_key("fact_fund_marks", "period_end", refers_to=("dim_period", "period_end"))
        c.foreign_key("fact_position_marks", "slug", refers_to=("dim_fund", "slug"))
        c.foreign_key("fact_position_marks", "period_end", refers_to=("dim_period", "period_end"))
        c.foreign_key("fact_position_marks", "issuer_key", refers_to=("dim_issuer", "issuer_key"))
        c.foreign_key("fact_position_marks", "mark_band", refers_to=("dim_mark_band", "mark_band"))
        c.foreign_key("fact_position_marks", "seniority", refers_to=("dim_seniority", "seniority"))
        c.foreign_key("fact_position_marks", "position_class",
                      refers_to=("dim_position_class", "position_class"))
        c.values("fact_position_marks", "mark_band",
                 within=["UNSTRESSED", "WATCH", "STRESS", "DEEP_STRESS", "UNCOMPUTABLE"])
        c.values("fact_position_marks", "seniority",
                 within=["FIRST_LIEN", "SECOND_LIEN", "OTHER_DEBT", "EQUITY_WARRANTS", "UNSTATED"])
        c.values("fact_position_marks", "position_class", within=["DEBT_PROXY", "EQUITY_OTHER"])
        c.values("dim_fund", "recon_status", within=["RECONCILED", "UNRECONCILED"])
        c.reconcile("fact_position_marks", "fair_value",
                    against=("fact_fund_marks", "book_fv"), by="slug", tolerance=0.0,
                    note="every position's fair value sums to the fund's book value exactly")
        c.reconcile("fact_position_marks", "position_one",
                    against=("fact_fund_marks", "positions_total"), by="slug", tolerance=0.0)

    return n_positions_raw, len(fact_position_marks)
