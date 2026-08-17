"""
Orders Clean
============

Phase ① — TRANSFORM. Scaffolded by ``tracebi new-transform`` on 2026-08-17.

Ordinary, unconstrained pandas: read the raw pull, do whatever the data
needs — window functions, prose parsing, cleaning, dedupe — then SINK the
clean, star-shaped result into the warehouse. The framework does not
constrain this phase; the contract is not *how* you clean, it is *what
lands* — the named tables at the bottom of this file. Phase ② (models/)
reads those tables and never sees this code.

    python transforms/orders_clean.py

Keep it idempotent: a rerun replaces the warehouse tables.
"""

from __future__ import annotations

import os

import pandas as pd

from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAREHOUSE = os.path.join(ROOT, "data", "warehouse.duckdb")


# This file is notebook-shaped: the `# %%` markers below are cell
# boundaries, and `# %% [markdown]` cells are prose. VS Code, Cursor,
# PyCharm, and Jupyter (via jupytext) open it AS a notebook — collapse
# cells, run cell-by-cell, write markdown beside code — while the file
# stays plain, reviewable Python that runs top-to-bottom with
# `python transforms/orders_clean.py`. While `tracebi dev` serves, any cell can
# `tracebi.workbench.show(df, note=...)` to put its output in the portal.

# %% [markdown]
# ## Methodology
#
# Narrate the cleaning here — what gets dropped and why, how keys are
# chosen. Distill the load-bearing claims into the sink contract's
# `note=` at the bottom; they travel with the certificate.

# %%  Read the raw input (inputs/, an API pull, a SQL export…)
# df = pd.read_csv(os.path.join(ROOT, "inputs", "orders.csv"))  # ← your raw pull

# %%  Clean — any pandas you like; none of this is traced, by design
# df = df.dropna(subset=["id"]).drop_duplicates(subset=["id"])

# %%  Shape into star-schema tables (facts keyed to dimensions)
# dim_x = df[["x"]].drop_duplicates().rename_axis("x_id").reset_index()
# fact = df.merge(dim_x, on="x")[["id", "x_id", "value"]]

# %%  Sink — the contract: these named tables are what phase ② models
os.makedirs(os.path.dirname(WAREHOUSE), exist_ok=True)
wh = DuckDBConnector("warehouse", database=WAREHOUSE)
# wh.write(dim_x, "dim_x")
# wh.write(fact, "fact_orders_clean")

# %%  Declare the sink CONTRACT (optional, recommended)
# Read-only SQL checks on what just landed, recorded beside the warehouse.
# A failed check raises; note= carries your stated methodology into the
# certificate. This certifies the SINK, never the pandas above.
# from tracebi.contracts import contract
# with contract("orders_clean", warehouse=WAREHOUSE,
#               note="stated methodology: what was dropped, and why") as c:
#     c.rows("fact_orders_clean", at_least=1)
#     c.unique("dim_x", ["x_id"])
#     c.not_null("fact_orders_clean", ["id", "value"])
#     c.foreign_key("fact_orders_clean", "x_id", refers_to=("dim_x", "x_id"))

# %%
print(f"sunk → {WAREHOUSE}")
