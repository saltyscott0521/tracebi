"""The demo's raw data: what its pipelines write into the demo database.

Orders and customers as an export would hand them over. The sales pipeline
writes them to ``orders_raw`` / ``customers_raw``, cleans them, and
``sales_model`` (see ``pipeline.py``) reads the cleaned tables.

Below them, the bank behind ``wealth_model``: branches, clients, products,
accounts, holdings and activities, generated from a fixed seed. The wealth
pipeline's seed step (``wealth_pipeline.py``) writes the six tables into the
demo database (``data/demo.db``, or ``TRACEBI_DEMO_DB_URL``), where the model
reads them through the ``demo_db`` connector.
"""

import datetime as _dt

import numpy as np
import pandas as pd

orders_df = pd.DataFrame({
    "order_id":    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "customer_id": [1, 2, 3, 4, 1, 3, 2, 4, 1, 3],
    "product":  ["Widget A", "Widget B", "Gadget X", "Widget A",
                 "Gadget X", "Widget B", "Widget A", "Gadget X",
                 "Widget B", "Widget A"],
    "qty":      [120, 85, 200, 60, 95, 150, 40, 110, 75, 180],
    "revenue":  [3598.80, 4249.15, 19998.00, 1799.40, 9499.05,
                 14998.50, 1199.60, 10998.90, 3748.25, 17997.00],
    "cost":     [2100.00, 2800.00, 14000.00, 1050.00, 6600.00,
                 10500.00, 700.00, 7700.00, 2200.00, 12600.00],
    "status":   ["shipped", "shipped", "open", "shipped", "open",
                 "shipped", "shipped", "open", "shipped", "open"],
})

customers_df = pd.DataFrame({
    "customer_id": [1, 2, 3, 4, 5],
    "name":        ["Acme Corp", "Globex", "Initech", "Umbrella", "Vandelay"],
    "region":      ["North East", "South East", "Midwest", "West", "North East"],
    "segment":     ["enterprise", "smb", "smb", "enterprise", "mid-market"],
})

# ── The bank behind wealth_model ──────────────────────────────────────────────

rng = np.random.default_rng(42)

# ── Dimension: branches (~6 rows) ─────────────────────────────────────────────

branches_df = pd.DataFrame({
    "branch_id": [1, 2, 3, 4, 5, 6],
    "branch":    ["Manhattan", "Boston", "Chicago", "San Francisco", "Miami", "Dallas"],
    "region":    ["Northeast", "Northeast", "Midwest", "West", "South", "South"],
    "manager":   ["Alice Huang", "Bob Reeves", "Carol Kim", "Dan Osei", "Elena Ruiz", "Frank Patel"],
})

# ── Dimension: clients (~30 rows) ─────────────────────────────────────────────

_segments   = ["retail", "affluent", "private"]
_seg_weights = [0.5, 0.35, 0.15]
_profiles   = ["conservative", "balanced", "aggressive"]

_first = ["James", "Mary", "John", "Patricia", "Robert", "Linda", "Michael",
          "Barbara", "William", "Elizabeth", "David", "Jennifer", "Richard",
          "Maria", "Joseph", "Susan", "Thomas", "Margaret", "Charles", "Dorothy"]
_last  = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
          "Davis", "Wilson", "Taylor", "Anderson", "Thomas", "Jackson", "White",
          "Harris", "Martin", "Thompson", "Young", "Lewis", "Walker"]

_advisors = ["Sara Green", "Tom Hall", "Lisa Chen", "Mike Torres", "Anna Park"]

_seg_idx   = rng.choice(len(_segments), size=30, p=_seg_weights)
_prof_idx  = rng.integers(0, len(_profiles), size=30)
_adv_idx   = rng.integers(0, len(_advisors), size=30)
_br_idx    = rng.integers(0, len(branches_df), size=30)
_name_idx  = rng.choice(len(_first) * len(_last), size=30, replace=False)

clients_df = pd.DataFrame({
    "client_id":    list(range(1, 31)),
    "name":         [f"{_first[i % len(_first)]} {_last[i // len(_first)]}"
                     for i in _name_idx],
    "segment":      [_segments[i] for i in _seg_idx],
    "risk_profile": [_profiles[i] for i in _prof_idx],
    "advisor":      [_advisors[i] for i in _adv_idx],
    "branch_id":    [int(branches_df["branch_id"].iloc[i]) for i in _br_idx],
})

# ── Dimension: products (~10 rows) ────────────────────────────────────────────

products_df = pd.DataFrame({
    "product_id":   list(range(1, 11)),
    "ticker":       ["SPY", "AGG", "QQQ", "BND", "GLD", "VXUS", "SHY", "VNQ", "HYG", "CASH"],
    "product_name": ["S&P 500 ETF", "US Agg Bond ETF", "Nasdaq 100 ETF",
                     "Total Bond ETF", "Gold ETF", "Intl Equity ETF",
                     "Short Treasury ETF", "REIT ETF", "High Yield ETF", "Cash/MMF"],
    "asset_class":  ["equity", "fixed income", "equity", "fixed income", "alternatives",
                     "equity", "money market", "alternatives", "fixed income", "money market"],
    "risk_rating":  [3, 2, 4, 1, 3, 3, 1, 3, 3, 1],
    # Basis points, not a fraction: SPY charges 9.45 bp, i.e. 0.0945%. Stored
    # as `expense_ratio` these read as fractions to any percent-formatting
    # default, and 0.0945 rendered as "9.4%" — a hundredfold overstatement of
    # a fund fee. The unit is in the name so no consumer has to guess it.
    "expense_ratio_bps": [9.45, 3.0, 20.0, 3.0, 40.0, 7.0, 15.0, 12.0, 48.0, 0.0],
})

# ── Dimension: accounts (~40 rows) ────────────────────────────────────────────

_acct_types   = ["brokerage", "IRA", "trust", "checking"]
_acct_weights = [0.4, 0.35, 0.15, 0.10]
_client_ids = rng.choice(range(1, 31), size=40, replace=True)
_acct_type_idx = rng.choice(len(_acct_types), size=40, p=_acct_weights)
_opened_years  = rng.integers(2010, 2024, size=40)

accounts_df = pd.DataFrame({
    "account_id":   list(range(1, 41)),
    "client_id":    [int(c) for c in _client_ids],
    "account_type": [_acct_types[i] for i in _acct_type_idx],
    "opened":       [int(y) for y in _opened_years],
})

# Facts carry denormalized client_id / branch_id so the star-schema query
# engine (direct fact→dimension joins only) can slice by client and branch.
_acct_to_client = dict(zip(accounts_df["account_id"], accounts_df["client_id"]))
_client_to_branch = dict(zip(clients_df["client_id"], clients_df["branch_id"]))

# ── Fact: holdings (~120 rows) — current snapshot ────────────────────────────

_h_account_ids = rng.choice(range(1, 41), size=120, replace=True)
_h_product_ids = rng.choice(range(1, 11), size=120, replace=True)
_h_units       = rng.uniform(10, 500, size=120).round(2)
# cost_basis per unit: $50–$400; market_value slightly above cost on average
_h_cost_per    = rng.uniform(50, 400, size=120).round(2)
_h_return_pct  = rng.normal(0.08, 0.12, size=120)   # 8% avg return, some negative
_h_market_per  = (_h_cost_per * (1 + _h_return_pct)).round(2)

holdings_df = pd.DataFrame({
    "holding_id":   list(range(1, 121)),
    "account_id":   [int(a) for a in _h_account_ids],
    "client_id":    [_acct_to_client[int(a)] for a in _h_account_ids],
    "branch_id":    [_client_to_branch[_acct_to_client[int(a)]] for a in _h_account_ids],
    "product_id":   [int(p) for p in _h_product_ids],
    "units":        _h_units.tolist(),
    "market_value": (_h_units * _h_market_per).round(2).tolist(),
    "cost_basis":   (_h_units * _h_cost_per).round(2).tolist(),
})

# ── Fact: activities (~150 rows) — last 12 months ────────────────────────────

_today = _dt.date(2026, 6, 11)
_months = [
    (_today.replace(day=1) - _dt.timedelta(days=30 * i)).strftime("%Y-%m")
    for i in range(12)
][::-1]   # oldest first

_a_activity_types = ["purchase", "sale", "fee"]
_a_type_weights   = [0.55, 0.30, 0.15]
_a_account_ids = rng.choice(range(1, 41), size=150, replace=True)
_a_product_ids = rng.choice(range(1, 11), size=150, replace=True)
_a_month_idx   = rng.integers(0, len(_months), size=150)
_a_type_idx    = rng.choice(len(_a_activity_types), size=150, p=_a_type_weights)
_a_units       = rng.uniform(1, 100, size=150).round(2)
_a_price       = rng.uniform(50, 400, size=150).round(2)
_a_amounts_raw = (_a_units * _a_price).round(2)
# fees are small flat amounts
_a_amounts = [
    round(float(amt) if t != 2 else float(rng.uniform(5, 50)), 2)
    for amt, t in zip(_a_amounts_raw, _a_type_idx)
]

activities_df = pd.DataFrame({
    "activity_id":   list(range(1, 151)),
    "account_id":    [int(a) for a in _a_account_ids],
    "client_id":     [_acct_to_client[int(a)] for a in _a_account_ids],
    "branch_id":     [_client_to_branch[_acct_to_client[int(a)]] for a in _a_account_ids],
    "product_id":    [int(p) for p in _a_product_ids],
    "trade_date":    [_months[i] for i in _a_month_idx],
    "activity_type": [_a_activity_types[i] for i in _a_type_idx],
    "units":         _a_units.tolist(),
    "amount":        _a_amounts,
})
