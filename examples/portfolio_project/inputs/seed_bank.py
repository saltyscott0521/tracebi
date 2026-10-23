"""
Seed the reference project's core-banking database: the six raw tables
the ``bank`` connection names (connections/bank.yaml). With
TRACEBI_BANK_URL unset that is the SQLite file that ships,
inputs/bank.sqlite; set it to put the same tables in any database.

    python inputs/seed_bank.py

The tables are what a core-banking system would export: branches, clients,
products, accounts, position holdings and a year of account activity. They
keep a little mess for transforms/wealth_transform.sql to clean, as a real
export would: the ``affluent`` segment is spelled three ways, market values
are text with thousands separators, and one activity appears twice.

Deterministic (a fixed seed), and idempotent: it replaces the six tables. A
SQLite file is rewritten from empty, so a rerun produces the same file.
"""

from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd

from tracebi.connections import connection_file, load_connection

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def frames() -> dict[str, pd.DataFrame]:
    """The six raw tables, by name. The same bank the demo app generates
    (tracebi/web/demo_app/sample_data.py, same seed, same draws), as the
    source system holds it: holdings and activities carry the account only,
    not the client or branch it belongs to."""
    rng = np.random.default_rng(42)

    branches = pd.DataFrame({
        "branch_id": [1, 2, 3, 4, 5, 6],
        "branch":    ["Manhattan", "Boston", "Chicago", "San Francisco", "Miami", "Dallas"],
        "region":    ["Northeast", "Northeast", "Midwest", "West", "South", "South"],
        "manager":   ["Alice Huang", "Bob Reeves", "Carol Kim", "Dan Osei", "Elena Ruiz",
                      "Frank Patel"],
    })

    segments, seg_weights = ["retail", "affluent", "private"], [0.5, 0.35, 0.15]
    profiles = ["conservative", "balanced", "aggressive"]
    first = ["James", "Mary", "John", "Patricia", "Robert", "Linda", "Michael",
             "Barbara", "William", "Elizabeth", "David", "Jennifer", "Richard",
             "Maria", "Joseph", "Susan", "Thomas", "Margaret", "Charles", "Dorothy"]
    last = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
            "Davis", "Wilson", "Taylor", "Anderson", "Thomas", "Jackson", "White",
            "Harris", "Martin", "Thompson", "Young", "Lewis", "Walker"]
    advisors = ["Sara Green", "Tom Hall", "Lisa Chen", "Mike Torres", "Anna Park"]

    seg_idx = rng.choice(len(segments), size=30, p=seg_weights)
    prof_idx = rng.integers(0, len(profiles), size=30)
    adv_idx = rng.integers(0, len(advisors), size=30)
    br_idx = rng.integers(0, len(branches), size=30)
    name_idx = rng.choice(len(first) * len(last), size=30, replace=False)

    clients = pd.DataFrame({
        "client_id":    list(range(1, 31)),
        "name":         [f"{first[i % len(first)]} {last[i // len(first)]}" for i in name_idx],
        "segment":      [segments[i] for i in seg_idx],
        "risk_profile": [profiles[i] for i in prof_idx],
        "advisor":      [advisors[i] for i in adv_idx],
        "branch_id":    [int(branches["branch_id"].iloc[i]) for i in br_idx],
    })

    products = pd.DataFrame({
        "product_id":   list(range(1, 11)),
        "ticker":       ["SPY", "AGG", "QQQ", "BND", "GLD", "VXUS", "SHY", "VNQ", "HYG", "CASH"],
        "product_name": ["S&P 500 ETF", "US Agg Bond ETF", "Nasdaq 100 ETF",
                         "Total Bond ETF", "Gold ETF", "Intl Equity ETF",
                         "Short Treasury ETF", "REIT ETF", "High Yield ETF", "Cash/MMF"],
        "asset_class":  ["equity", "fixed income", "equity", "fixed income", "alternatives",
                         "equity", "money market", "alternatives", "fixed income",
                         "money market"],
        "risk_rating":  [3, 2, 4, 1, 3, 3, 1, 3, 3, 1],
        # Basis points, the unit in the name: 9.45 means 0.0945%.
        "expense_ratio_bps": [9.45, 3.0, 20.0, 3.0, 40.0, 7.0, 15.0, 12.0, 48.0, 0.0],
    })

    acct_types, acct_weights = ["brokerage", "IRA", "trust", "checking"], [0.4, 0.35, 0.15, 0.10]
    client_ids = rng.choice(range(1, 31), size=40, replace=True)
    acct_type_idx = rng.choice(len(acct_types), size=40, p=acct_weights)
    opened_years = rng.integers(2010, 2024, size=40)
    accounts = pd.DataFrame({
        "account_id":   list(range(1, 41)),
        "client_id":    [int(c) for c in client_ids],
        "account_type": [acct_types[i] for i in acct_type_idx],
        "opened":       [int(y) for y in opened_years],
    })

    # Holdings: a current snapshot, ~120 positions.
    h_account_ids = rng.choice(range(1, 41), size=120, replace=True)
    h_product_ids = rng.choice(range(1, 11), size=120, replace=True)
    h_units = rng.uniform(10, 500, size=120).round(2)
    h_cost_per = rng.uniform(50, 400, size=120).round(2)
    h_return_pct = rng.normal(0.08, 0.12, size=120)
    h_market_per = (h_cost_per * (1 + h_return_pct)).round(2)
    holdings = pd.DataFrame({
        "holding_id":   list(range(1, 121)),
        "account_id":   [int(a) for a in h_account_ids],
        "product_id":   [int(p) for p in h_product_ids],
        "units":        h_units.tolist(),
        "market_value": (h_units * h_market_per).round(2).tolist(),
        "cost_basis":   (h_units * h_cost_per).round(2).tolist(),
    })

    # Activities: the last twelve months, ~150 purchases, sales and fees.
    today = dt.date(2026, 6, 11)
    months = [(today.replace(day=1) - dt.timedelta(days=30 * i)).strftime("%Y-%m")
              for i in range(12)][::-1]
    a_types, a_weights = ["purchase", "sale", "fee"], [0.55, 0.30, 0.15]
    a_account_ids = rng.choice(range(1, 41), size=150, replace=True)
    a_product_ids = rng.choice(range(1, 11), size=150, replace=True)
    a_month_idx = rng.integers(0, len(months), size=150)
    a_type_idx = rng.choice(len(a_types), size=150, p=a_weights)
    a_units = rng.uniform(1, 100, size=150).round(2)
    a_price = rng.uniform(50, 400, size=150).round(2)
    a_amounts_raw = (a_units * a_price).round(2)
    a_amounts = [round(float(amt) if t != 2 else float(rng.uniform(5, 50)), 2)
                 for amt, t in zip(a_amounts_raw, a_type_idx)]
    activities = pd.DataFrame({
        "activity_id":   list(range(1, 151)),
        "account_id":    [int(a) for a in a_account_ids],
        "product_id":    [int(p) for p in a_product_ids],
        "trade_date":    [months[i] for i in a_month_idx],
        "activity_type": [a_types[i] for i in a_type_idx],
        "units":         a_units.tolist(),
        "amount":        a_amounts,
    })

    # The mess. The affluent segment as three desks typed it; market values
    # exported as text ("12,345.67"); and activity 42 posted twice.
    spellings = ["affluent", "Affluent", " AFFLUENT"]
    clients["segment"] = [spellings[cid % 3] if seg == "affluent" else seg
                          for cid, seg in zip(clients["client_id"], clients["segment"])]
    holdings["market_value"] = [f"{v:,.2f}" for v in holdings["market_value"]]
    activities = pd.concat([activities, activities[activities["activity_id"] == 42]],
                           ignore_index=True)

    return {"branches": branches, "clients": clients, "products": products,
            "accounts": accounts, "holdings": holdings, "activities": activities}


def seed() -> dict[str, int]:
    """Write the six tables through the connection; returns rows per table."""
    connector = load_connection(connection_file("bank", ROOT), root=ROOT)
    url = connector.url
    if url.startswith("sqlite"):
        from sqlalchemy.engine import make_url
        database = make_url(url).database
        if database and os.path.exists(database):
            os.remove(database)     # from empty, so a rerun writes the same file
    tables = frames()
    try:
        for name, frame in tables.items():
            connector.write(frame, name)
    finally:
        connector.disconnect()
    return {name: len(frame) for name, frame in tables.items()}


if __name__ == "__main__":
    for table, rows in seed().items():
        print(f"bank: {table}, {rows} rows")
