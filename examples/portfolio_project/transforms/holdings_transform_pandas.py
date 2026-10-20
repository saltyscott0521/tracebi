"""
Phase ① — TRANSFORM, the escape hatch: the same work in pandas.

The reference project's transform is holdings_transform.sql (with its sink
contract beside it in holdings_transform.contract.yaml); that is what the
pipeline runs. This file is the escape-hatch example: when the cleaning needs
more than SQL says comfortably, write ordinary pandas (or polars), end by
writing the frames, and the trace line is still drawn at the sink. Both forms
sink IDENTICAL tables, fingerprint for fingerprint
(tests/e2e/test_reference_project.py proves it), so either can feed the model.

Read the messy Schedule-of-Investments export, do the work a fund-ops analyst
(or their agent) actually does — parse prose instrument blobs into issuers,
strip trailing position counters, normalise sectors spelled six ways, coerce
money stored as strings, dedupe — and SINK the clean, star-shaped result into
the warehouse. The contract is not *how* you clean, it is *what lands* — the
named tables at the bottom of this file. Phase ② (models/) reads those tables
and never sees this code.

Reads the CRM's issuer ratings the way the SQL form's `-- source:` line
does, through the declared connection (connections/crm.yaml) with
tracebi.transforms.load_source, which falls back to the committed snapshot
inputs/issuer_ratings.csv when TRACEBI_CRM_URL is unset and records which one
fed it; the record goes into the certificate's `sources`.

Reads a raw pull from inputs/ and sinks to the project's warehouse: the
DuckDB file data/warehouse.duckdb unless tracebi.yaml's warehouse block puts
it on object storage (Parquet per table) or a remote engine.

    tracebi run-transform holdings_transform_pandas

Idempotent: rerun any time; it replaces the warehouse tables.
"""

from __future__ import annotations

import os
import re

import pandas as pd

from tracebi.connectors.duckdb_connector import DuckDBConnector
from tracebi.contracts import contract
from tracebi.project_config import sink_target
from tracebi.transforms import load_source

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "inputs", "holdings.csv")
# Where tracebi.yaml says the warehouse is, on whichever tier.
WAREHOUSE = sink_target(ROOT)


# ── cleaning helpers ─────────────────────────────────────────────────────────

_MONEY_RE = re.compile(r"[^\d.\-]")          # strip $, commas, spaces, footnotes
_COUNTER_RE = re.compile(r"\s*\(\d+\)\s*$")  # trailing "(2)" position counter
_FOOTNOTE_RE = re.compile(r"\s*\([a-z]\)\s*$")


def parse_money(series: pd.Series) -> pd.Series:
    """'$ 8,135,782.69 (a)' → 8135782.69. Unparseable → NaN (loud, not silent)."""
    cleaned = (
        series.astype(str)
        .str.replace(_FOOTNOTE_RE, "", regex=True)
        .str.replace(_MONEY_RE, "", regex=True)
        .str.strip()
    )
    return pd.to_numeric(cleaned, errors="coerce")


def parse_issuer(position: pd.Series) -> pd.Series:
    """
    'Acme Industrial Holdings, LLC — Senior Secured … (2)' → 'Acme Industrial
    Holdings, LLC'. Name is the text before the em dash; the trailing position
    counter is stripped first so it never rides along.
    """
    before_dash = position.astype(str).str.split(" — ", n=1).str[0]
    return before_dash.str.replace(_COUNTER_RE, "", regex=True).str.strip()


def parse_instrument(position: pd.Series) -> pd.Series:
    """The text after the em dash, counter stripped — the instrument type."""
    after = position.astype(str).str.split(" — ", n=1).str[-1]
    # rows with no em dash split to the whole blob; blank those out
    after = after.where(position.astype(str).str.contains(" — "), other="")
    return after.str.replace(_COUNTER_RE, "", regex=True).str.strip()


# canonical sector ← the six spellings each administrator uses
_SECTOR_MAP = {
    "industrials": "Industrials", "industrial": "Industrials",
    "software": "Software", "tech - software": "Software",
    "technology/software": "Software",
    "healthcare": "Healthcare", "health care": "Healthcare",
    "health-care": "Healthcare",
    "consumer": "Consumer", "consumer discretionary": "Consumer", "cons.": "Consumer",
    "energy": "Energy", "oil & gas": "Energy",
    "financials": "Financials", "financial services": "Financials", "fin.": "Financials",
}


def normalise_sector(industry: pd.Series) -> pd.Series:
    key = industry.astype(str).str.strip().str.lower()
    return key.map(_SECTOR_MAP).fillna("Other")


def parse_spread_bps(rate: pd.Series) -> pd.Series:
    """
    'SOFR + 597' → 597; 'L+7.44%' → 744; 'SOFR + 4.84%' → 484.
    Everything ends up in basis points, whichever convention the row used.
    """
    txt = rate.astype(str).str.replace(" ", "")
    # split off the base ('SOFR', 'L', 'TermSOFR'); keep the spread token
    spread_txt = txt.str.replace(r"^[A-Za-z]+\+?", "", regex=True)
    has_pct = spread_txt.str.contains("%")
    num = pd.to_numeric(spread_txt.str.replace("%", "", regex=False), errors="coerce")
    # a percent spread ('7.44%') is points → ×100 bps; a bare integer is already bps
    return num.where(~has_pct, num * 100).round().astype("Int64")


def run() -> dict:
    """Do the manipulation and sink the star-schema tables. Returns a summary."""
    raw = pd.read_csv(RAW)
    n_raw = len(raw)

    df = raw.copy()
    # a blank cell reads back as NaN; coerce first so it never becomes "nan"
    df["position"] = df["position"].fillna("").astype(str)
    df["issuer"] = parse_issuer(df["position"])
    df["instrument_type"] = parse_instrument(df["position"])
    df["sector"] = normalise_sector(df["industry"])
    df["par"] = parse_money(df["par"])
    df["cost"] = parse_money(df["cost"])
    df["fair_value"] = parse_money(df["fair_value"])
    df["spread_bps"] = parse_spread_bps(df["rate"])
    df["maturity"] = pd.to_datetime(df["maturity"], format="mixed", errors="coerce").dt.date

    # drop rows we could not key to a real issuer — loud, counted, not silent.
    # "real" means at least one letter: this rejects an em-dash-only blob and a
    # blanked cell alike, where a bare length check would let "—" through.
    has_issuer = df["issuer"].str.contains(r"[A-Za-z]", regex=True, na=False)
    keyed = df[has_issuer].copy()
    n_unkeyed = n_raw - len(keyed)

    # collapse exact double-booked positions
    keyed = keyed.drop_duplicates(
        subset=["fund", "issuer", "instrument_type", "par", "fair_value"]
    ).reset_index(drop=True)
    n_deduped = len(df[df["issuer"].str.len() > 0]) - len(keyed)

    # ── build the dimension tables ────────────────────────────────────────────
    dim_fund = (
        pd.DataFrame({"fund": sorted(keyed["fund"].unique())})
        .reset_index(names="fund_id")
    )
    dim_fund["fund_id"] += 1

    dim_issuer = (
        keyed[["issuer", "sector"]].drop_duplicates()
        .sort_values("issuer").reset_index(drop=True)
        .reset_index(names="issuer_id")
    )
    dim_issuer["issuer_id"] += 1

    # Each held issuer's CRM rating, and whether the credit team has it on
    # watch. An issuer the CRM does not cover is Unrated, its watch unknown:
    # a row with no rating is a fact about the CRM, so it stays in the book.
    ratings, crm = load_source("crm.issuer_ratings", ROOT,
                               fallback="inputs/issuer_ratings.csv")
    issuer_rating = pd.DataFrame({"issuer": keyed["issuer"].unique()}).merge(
        ratings[["issuer", "rating", "watch"]], on="issuer", how="left")
    issuer_rating["watch"] = issuer_rating["watch"].map(
        {True: "yes", False: "no"}).fillna("unknown")
    issuer_rating["rating"] = issuer_rating["rating"].fillna("Unrated")
    dim_rating = (
        issuer_rating[["rating", "watch"]].drop_duplicates()
        .sort_values(["rating", "watch"]).reset_index(drop=True)
        .reset_index(names="rating_id")
    )
    dim_rating["rating_id"] += 1

    # ── build the fact table, keyed to the dimensions ─────────────────────────
    fact = keyed.merge(dim_fund, on="fund").merge(
        dim_issuer[["issuer_id", "issuer"]], on="issuer"
    ).merge(issuer_rating, on="issuer", how="left").merge(
        dim_rating, on=["rating", "watch"], how="left")
    fact = fact[[
        "fund_id", "issuer_id", "rating_id", "instrument_type",
        "par", "cost", "fair_value", "spread_bps", "maturity",
    ]].reset_index(names="holding_id")
    fact["holding_id"] += 1

    # ── a second fact: the book's cash flows ──────────────────────────────────
    # Derived from the holdings themselves (no second raw pull), so the demo
    # stays one input file: a quarterly coupon on alternate quarters (par ×
    # (spread + a 4.3% base rate) / 4), a drawdown on every fourth position
    # and a partial repayment on every fifth, all in 2025. Signed from the
    # fund's side: money lent out is negative, money received positive. It
    # shares dim_fund and dim_issuer with the holdings and adds two
    # dimensions only it reaches (the flow's date and its type), which is
    # what a page needs to show a filter that reaches one fact and not the
    # other.
    flow_types = ["Drawdown", "Interest", "Repayment"]
    dim_flow_type = pd.DataFrame({"flow_type_id": [1, 2, 3], "flow_type": flow_types})
    flows = []
    for h in fact.dropna(subset=["par", "spread_bps"]).itertuples():
        coupon = round(h.par * (h.spread_bps / 10_000 + 0.043) / 4, 2)
        for q in range(4):
            if (h.holding_id + q) % 2 == 0:
                flows.append((h.fund_id, h.issuer_id,
                              pd.Timestamp(2025, 3 * q + 3, 1) + pd.offsets.MonthEnd(0),
                              2, coupon))
        month = h.holding_id % 12 + 1
        if h.holding_id % 4 == 1:
            flows.append((h.fund_id, h.issuer_id, pd.Timestamp(2025, month, 1), 1,
                          -round(h.par * 0.10, 2)))
        if h.holding_id % 5 == 0:
            flows.append((h.fund_id, h.issuer_id, pd.Timestamp(2025, month, 15), 3,
                          round(h.par * 0.05, 2)))
    fact_cashflows = pd.DataFrame(
        flows, columns=["fund_id", "issuer_id", "flow_date", "flow_type_id", "amount"],
    ).sort_values(["flow_date", "fund_id", "issuer_id"]).reset_index(drop=True)
    fact_cashflows["flow_date"] = fact_cashflows["flow_date"].dt.date
    fact_cashflows = fact_cashflows.reset_index(names="cashflow_id")
    fact_cashflows["cashflow_id"] += 1
    dim_date = pd.DataFrame({"flow_date": sorted(fact_cashflows["flow_date"].unique())})

    # ── SINK to the warehouse ─────────────────────────────────────────────────
    # No connect() here: write() manages its own short-lived read-write
    # connection, and a read-only connect would fail on a fresh clone whose
    # warehouse file does not exist yet (first-run bug caught by the
    # showcase rot-proof test).
    wh = DuckDBConnector("warehouse", database=WAREHOUSE)
    wh.write(dim_fund, "dim_fund")
    wh.write(dim_issuer, "dim_issuer")
    wh.write(dim_rating, "dim_rating")
    wh.write(fact, "fact_holdings")
    wh.write(dim_date, "dim_date")
    wh.write(dim_flow_type, "dim_flow_type")
    wh.write(fact_cashflows, "fact_cashflows")

    # ── the sink CONTRACT ─────────────────────────────────────────────────────
    # Declare what must be true of the tables that just landed — checked as
    # read-only SQL against the warehouse, recorded beside it. A failed check
    # raises here, so a broken sink never freezes quietly. This says "the sink
    # satisfied its contract" — it does NOT verify the pandas above. The
    # note= is the STATED methodology: prose about what the cleaning did,
    # recorded verbatim and carried into report traces, never verified.
    with contract(
        "holdings", warehouse=WAREHOUSE, sources={"crm.issuer_ratings": crm},
        note="issuer and instrument type parsed from the prose position "
             "blob; sectors normalised from each administrator's spelling; "
             "money coerced from strings; exact double-booked positions "
             "deduped; rows with no keyable issuer dropped and counted",
    ) as c:
        c.rows("fact_holdings", at_least=10,
               note="a Schedule of Investments under 10 positions means the "
                    "raw pull is truncated, not that the book shrank")
        c.unique("dim_issuer", ["issuer_id"])
        c.not_null("fact_holdings", ["fund_id", "issuer_id", "rating_id", "fair_value"])
        c.foreign_key("fact_holdings", "issuer_id",
                      refers_to=("dim_issuer", "issuer_id"))
        c.foreign_key("fact_holdings", "fund_id",
                      refers_to=("dim_fund", "fund_id"))
        c.foreign_key("fact_holdings", "rating_id",
                      refers_to=("dim_rating", "rating_id"))
        c.unique("dim_rating", ["rating", "watch"])
        c.values("dim_rating", "rating", within=[
            "AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-",
            "BB+", "BB", "BB-", "B+", "B", "B-", "CCC+", "CCC", "CCC-", "CC",
            "C", "D", "Unrated"],
            note="the CRM's ratings on the agency scale; an issuer it does "
                 "not cover is Unrated, never dropped")
        c.values("dim_rating", "watch", within=["yes", "no", "unknown"])
        c.rows("fact_cashflows", at_least=10)
        c.not_null("fact_cashflows",
                   ["fund_id", "issuer_id", "flow_date", "flow_type_id", "amount"])
        c.unique("dim_date", ["flow_date"])
        c.values("dim_flow_type", "flow_type", within=flow_types)
        for column, dim in (("fund_id", "dim_fund"), ("issuer_id", "dim_issuer"),
                            ("flow_date", "dim_date"), ("flow_type_id", "dim_flow_type")):
            c.foreign_key("fact_cashflows", column, refers_to=(dim, column))

    return {
        "rows_in": n_raw,
        "unkeyed_dropped": int(n_unkeyed),
        "duplicates_dropped": int(n_deduped),
        "funds": len(dim_fund),
        "issuers": len(dim_issuer),
        "ratings_from": "inputs/issuer_ratings.csv (TRACEBI_CRM_URL unset)"
                        if crm.get("source_fallback") else "crm (Postgres)",
        "holdings": len(fact),
        "cash_flows": len(fact_cashflows),
        "total_fair_value": float(fact["fair_value"].sum()),
        "warehouse": WAREHOUSE,
    }


if __name__ == "__main__":
    summary = run()
    print("Phase ① — transform → sink")
    for k, v in summary.items():
        print(f"  {k:22} {v}")
