"""
Seed the reference project's billing database: the ``subscriptions`` and
``plans`` tables the ``billing`` connection names (connections/billing.yaml).
With TRACEBI_BILLING_URL unset that is the SQLite file that ships,
inputs/billing.sqlite; set it to put the same tables in any database.

    python inputs/seed_billing.py

``subscriptions`` is inputs/subscriptions.csv as the billing system holds it,
mess and all: every value text as exported (plans and statuses spelled
several ways, money as "$149" or "49.00", a duplicated account-month, a row
with no account id), numbered by ``subscription_id`` in export order.
``plans`` is the price list: each plan's code, its name and its list MRR.
transforms/saas_transform.sql reads both.

Idempotent: it replaces the two tables. A SQLite file is rewritten from
empty, so a rerun produces the same file.
"""

from __future__ import annotations

import os

import pandas as pd

from tracebi.connections import connection_file, load_connection

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def frames() -> dict[str, pd.DataFrame]:
    """The two tables, by name."""
    # Text, as exported; an empty cell is NULL (the row with no account id).
    subscriptions = pd.read_csv(os.path.join(HERE, "subscriptions.csv"), dtype=str,
                                keep_default_na=False, na_values=[""])
    subscriptions.insert(0, "subscription_id", range(1, len(subscriptions) + 1))
    plans = pd.DataFrame({
        "plan_code": ["starter", "growth", "scale"],
        "plan":      ["Starter", "Growth", "Scale"],
        "list_mrr":  [49.0, 149.0, 499.0],
    })
    return {"subscriptions": subscriptions, "plans": plans}


def seed() -> dict[str, int]:
    """Write the tables through the connection; returns rows per table."""
    connector = load_connection(connection_file("billing", ROOT), root=ROOT)
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
        print(f"billing: {table}, {rows} rows")
