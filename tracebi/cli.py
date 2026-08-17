"""
TraceBi CLI.

Usage:
    tracebi init my_project                      # scaffold a new project
    tracebi new-request "Open orders by region"  # scaffolds requests/<slug>.py
    tracebi list-requests                        # show all request scripts
    tracebi run <name>                           # run a request and render outputs
    tracebi dev <name>                           # live preview: re-run + reload on save
    tracebi validate                             # sanity-check the current project
    tracebi --version

The CLI is intentionally small — its job is to scaffold and run files
in ``requests/``. Everything else lives in the library.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import runpy
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from tracebi._version import get_version as _tracebi_version


# Resolve the project folders relative to the user's current working
# directory by default, honouring the same TRACEBI_*_DIR env vars the server
# and gateway read (so the CLI and the server agree on where a project
# lives). Override per-invocation with the --*-dir flags.
def _default_requests_dir() -> Path:
    return Path(os.environ.get("TRACEBI_REQUESTS_DIR", "requests"))


def _default_models_dir() -> Path:
    return Path(os.environ.get("TRACEBI_MODELS_DIR", "models"))


def _default_pipelines_dir() -> Path:
    return Path(os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines"))


def _default_reports_dir() -> Path:
    return Path(os.environ.get("TRACEBI_REPORTS_DIR", "reports"))


def _default_transforms_dir() -> Path:
    return Path(os.environ.get("TRACEBI_TRANSFORMS_DIR", "transforms"))


def _slugify(title: str) -> str:
    """Convert "Open orders by region" → "open_orders_by_region"."""
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "request"


def _template_text(title: str) -> str:
    today = date.today().isoformat()
    slug = _slugify(title)
    return f'''"""
{title}
{'=' * len(title)}

Scaffolded by ``tracebi new-request`` on {today}.
Fill in the four sections below, then run with:

    python requests/{slug}.py
"""

import os
from tracebi import request_params
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer

# ── 0. Parameters ───────────────────────────────────────────────────────────
# Override at run time:  tracebi run {slug} --param period="Q3 2024"
# The web UI's Requests page renders a form from these defaults.
params = request_params(period="Q2 2024")

# Use a model from models/ if one is defined, or build your own below.
# List available models: tracebi list-models
# Create a new model:    tracebi new-model "My Model"
try:
    from tracebi.model_registry import get_default_model
    model = get_default_model()
except KeyError:
    model = None

if model is None:
    from tracebi import DataModel  # noqa: F401
    # model = DataModel("MyModel")
    # model.add_connector(...)
    # model.add_table("orders", connector="...", source="...")
    pass


# ── 1. Build DataSets ───────────────────────────────────────────────────────
# Every verb returns a new DataSet and records a lineage step. Run
# ds.help() for the full cheat sheet, or see docs/analyst-guide.md.
#
# orders = (
#     model.load("orders", filter={{"status": "shipped"}})
#     .deduplicate(subset="order_id")
#     .dropna(subset="region")
#     .assign(margin=lambda df: df.revenue - df.cost)
#     .sort("margin", ascending=False)
# )


# ── 2. Build Report ─────────────────────────────────────────────────────────
report = (
    Report("{title}")
    .author("Your Name")
    .description("Short description of this report.")
    .add(TextSection(title="Summary", style="heading1"))
    .add(TextSection(content="Write your narrative here."))
)


# ── 3. Render ───────────────────────────────────────────────────────────────

def run():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, "{slug}")
    ExcelRenderer().render(report, base + ".xlsx")
    HTMLRenderer.for_project().render(report, base + ".html")
    print(f"Saved: {{base}}.xlsx / .html")


# ── 4. Publish to the project registry ─────────────────────────────────────
# Makes this report available to `tracebi run`, the web UI, and any other
# consumer. Harmless when nothing is listening.
from tracebi import register


@register.report("{slug}", description="Short description of this report.")
def _factory():
    return report


if __name__ == "__main__":
    run()
'''


def _notebook_text(title: str) -> str:
    slug = _slugify(title)
    today = date.today().isoformat()
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language":     "python",
                "name":         "python3",
            },
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata":  {},
                "source": [
                    f"# {title}\n",
                    f"\n",
                    f"_Scaffolded by `tracebi new-request --notebook` on {today}._\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata":  {},
                "execution_count": None,
                "outputs":   [],
                "source": [
                    "from tracebi import request_params\n",
                    "from tracebi.reports.report import Report, TextSection, TableSection, ChartSection\n",
                    "from tracebi.reports.html_renderer import HTMLRenderer\n",
                    "\n",
                    "# Declare defaults; override via tracebi run --param or the web UI form\n",
                    "params = request_params(period=\"Q2 2024\")\n",
                    "\n",
                    "# Pull the shared project model (registry, then models/ on disk)\n",
                    "from tracebi import register\n",
                    "\n",
                    "model = register.get_default_model()\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata":  {},
                "execution_count": None,
                "outputs":   [],
                "source": [
                    "# Build DataSets with model.load(...) — every step adds a lineage node.\n",
                    "# Run ds.help() for the full verb cheat sheet.\n",
                    "# orders = (\n",
                    "#     model.load(\"orders\", filter={\"status\": \"shipped\"})\n",
                    "#     .deduplicate(subset=\"order_id\")\n",
                    "#     .assign(margin=lambda df: df.revenue - df.cost)\n",
                    "# )\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata":  {},
                "execution_count": None,
                "outputs":   [],
                "source": [
                    f'report = (\n',
                    f'    Report("{title}")\n',
                    '    .author("Your Name")\n',
                    '    .add(TextSection(title="Summary", style="heading1"))\n',
                    '    .add(TextSection(content="Write your narrative here."))\n',
                    ')\n',
                    'HTMLRenderer().preview(report)\n',
                ],
            },
            {
                "cell_type": "markdown",
                "metadata":  {},
                "source": [
                    "## Expose to the web UI\n",
                    "\n",
                    "Uncomment to register this report so the running server picks it up via `tracebi.web.register`.\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata":  {},
                "execution_count": None,
                "outputs":   [],
                "source": [
                    "# from tracebi import register\n",
                    f"# @register.report(\"{slug}\", description=\"...\")\n",
                    "# def _factory():\n",
                    "#     return report\n",
                ],
            },
        ],
    }
    return json.dumps(nb, indent=1) + "\n"


def _model_template_text(title: str) -> str:
    today = date.today().isoformat()
    slug = _slugify(title)
    model_name = title.strip().replace(" ", "")
    return f'''\
"""
{title}
{'=' * len(title)}

DataModel definition. Scaffolded by ``tracebi new-model`` on {today}.

Use in any notebook or script:

    from tracebi.model_registry import get_model
    model = get_model("{slug}")
    ds = model.load("my_table")

Or set as default so notebooks that call get_default_model() pick it up:

    from tracebi.model_registry import get_model, set_default
    set_default("{slug}")
"""

import os

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector
# from tracebi import CSVConnector, SQLConnector, MemoryConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Connectors ───────────────────────────────────────────────────────────────
# Default: the warehouse your phase-① transforms sink into. Swap for
# SQLConnector("{slug}_db", url=os.environ["{slug}_DB_URL".upper()]) etc. to
# model a database directly.
connector = DuckDBConnector("warehouse",
                            database=os.path.join(ROOT, "data", "warehouse.duckdb"))

# ── Model ─────────────────────────────────────────────────────────────────────
# The variable MUST be named `model` — the registry looks for it at load time.
model = DataModel("{model_name}")
model.add_connector(connector)
model.add_table("my_table", connector="warehouse", source="my_table")
# model.add_relationship(
#     name="orders_customers",
#     left_table="orders", right_table="customers", left_key="customer_id",
# )
# model.add_dimension("dim_customer", table_name="customers", key_col="customer_id",
#                     attributes=["region", "segment"])
# model.add_fact("fact_orders", table_name="orders", measures=["revenue", "qty"],
#                foreign_keys={{"dim_customer": "customer_id"}})

# Construction is declarative and lazy: importing this file must not touch
# the database (discovery imports every model file, and a connect here would
# open a connection — or fail outright — on every scan). A query is what
# connects. Do not call model.connect() at import time.

# Files in models/ are auto-discovered — by the web server, and by
# `get_model("{slug}")` from notebooks and scripts. An explicit
# `register.model(model)` is only needed for files living OUTSIDE models/.
'''


def _pipeline_template_text(title: str) -> str:
    today = date.today().isoformat()
    slug = _slugify(title)
    return f'''\
"""
{title}
{'=' * len(title)}

PipelineRunner definition. Scaffolded by ``tracebi new-pipeline`` on {today}.

Use in any script or notebook:

    from tracebi.pipeline_registry import get_runner
    runner = get_runner("{slug}")
    runner.run("layer_name")
    runner.status()
"""

from tracebi import PipelineRunner
# from tracebi import LandingLayer, ManipulationLayer, FinalLayer, SQLConnector
# from tracebi.model_registry import get_model

_DB_URL = "sqlite:///data/{slug}.db"

# ── Layers ────────────────────────────────────────────────────────────────────
# Uncomment and adapt to wire your medallion layers.
#
# from tracebi import LandingLayer, ManipulationLayer, SQLConnector
# _db = SQLConnector("{slug}_db", url=_DB_URL)
#
# _bronze = LandingLayer(
#     connector=_db, source="orders_raw",
#     sink=_db, sink_table="orders_bronze",
# )
# _silver = (
#     ManipulationLayer(source=_db, source_table="orders_bronze",
#                       sink=_db, sink_table="orders_silver")
#     .drop_nulls(subset=["order_id"])
#     .deduplicate(subset=["order_id"])
# )

# ── Runner ─────────────────────────────────────────────────────────────────────
# The variable MUST be named `runner` — the registry looks for it at load time.
runner = PipelineRunner(db_url=_DB_URL)
# runner.register(_bronze, name="orders_bronze", schedule="0 * * * *")
# runner.register(_silver, name="orders_silver", schedule="15 * * * *",
#                 depends_on="orders_bronze")

# ── Publish to the project registry ──────────────────────────────────────────
# Also discoverable without this line via `get_runner("{slug}")`, since files
# in pipelines/ are auto-loaded. Registering makes it visible to the web UI too.
from tracebi import register

register.pipeline("{slug}", runner)
'''


def _transform_template_text(title: str) -> str:
    today = date.today().isoformat()
    slug = _slugify(title)
    return f'''\
"""
{title}
{'=' * len(title)}

Phase ① — TRANSFORM. Scaffolded by ``tracebi new-transform`` on {today}.

Ordinary, unconstrained pandas: read the raw pull, do whatever the data
needs — window functions, prose parsing, cleaning, dedupe — then SINK the
clean, star-shaped result into the warehouse. The framework does not
constrain this phase; the contract is not *how* you clean, it is *what
lands* — the named tables at the bottom of this file. Phase ② (models/)
reads those tables and never sees this code.

    python transforms/{slug}.py

Keep it idempotent: a rerun replaces the warehouse tables.
"""

from __future__ import annotations

import os

import pandas as pd

from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAREHOUSE = os.path.join(ROOT, "data", "warehouse.duckdb")


def run() -> dict:
    # ── 1. Read the raw input (inputs/, an API pull, a SQL export…) ─────────
    # df = pd.read_csv(os.path.join(ROOT, "inputs", "orders.csv"))  # ← your raw pull

    # ── 2. Clean — any pandas you like; none of this is traced, by design ───
    # df = df.dropna(subset=["id"]).drop_duplicates(subset=["id"])

    # ── 3. Shape into star-schema tables (facts keyed to dimensions) ────────
    # dim_x = df[["x"]].drop_duplicates().rename_axis("x_id").reset_index()
    # fact = df.merge(dim_x, on="x")[["id", "x_id", "value"]]

    # ── 4. Sink — the contract: these named tables are what phase ② models ──
    os.makedirs(os.path.dirname(WAREHOUSE), exist_ok=True)
    wh = DuckDBConnector("warehouse", database=WAREHOUSE)
    # wh.write(dim_x, "dim_x")
    # wh.write(fact, "fact_{slug}")

    # ── 5. Declare the sink CONTRACT (optional, recommended) ────────────────
    # What must be true of the tables that just landed — read-only SQL checks
    # recorded beside the warehouse. A failed check raises, so a broken sink
    # never freezes quietly. This certifies the SINK, never the pandas above.
    # from tracebi.contracts import contract
    # with contract("{slug}", warehouse=WAREHOUSE) as c:
    #     c.rows("fact_{slug}", at_least=1)
    #     c.unique("dim_x", ["x_id"])
    #     c.not_null("fact_{slug}", ["id", "value"])
    #     c.foreign_key("fact_{slug}", "x_id", refers_to=("dim_x", "x_id"))

    return {{"warehouse": WAREHOUSE}}


if __name__ == "__main__":
    for k, v in run().items():
        print(f"  {{k:12}} {{v}}")
'''


# ── init project scaffolding ────────────────────────────────────────────────

_INIT_GITIGNORE = """\
__pycache__/
*.py[cod]
.venv/
venv/
.env
# Rendered outputs are disposable, but the *.manifest.json files inside are
# receipts — the audit trail. `<dir>/*` with a negation (git cannot re-include
# under an excluded directory) keeps outputs ignored while the manifests you
# need to stand behind a report stay retained. data/ holds the warehouse and
# `tracebi report build` renders; output/ holds ad-hoc renders.
data/*
!data/*.manifest.json
output/*
!output/*.manifest.json
!output/.gitkeep
*.db
.ipynb_checkpoints/
# Workbench dev-state (exhibit feed, pins) — session scratch, never receipts.
.tracebi/
"""

_INIT_ENV_EXAMPLE = """\
# Copy to .env and fill in. The .env file is gitignored.
#
# The framework does not auto-load this file: call
# `from dotenv import load_dotenv; load_dotenv()` at the top of your scripts
# (python-dotenv ships with the analyst/all extras).

# ── Connectors ──────────────────────────────────────────────────────────────
# Construct connectors in your own code and pass credential-bearing URLs
# explicitly via os.environ[...] — the framework never reads these implicitly.
# TRACEBI_SALES_DB_URL=postgresql+psycopg://user:password@host:5432/sales
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# ── Web UI auth ─────────────────────────────────────────────────────────────
# HTTP Basic (single shared credential — development / small teams):
# TRACEBI_AUTH_USER=admin
# TRACEBI_AUTH_PASS=changeme
# Reverse-proxy header trust (SSO in front — the header names the principal):
# TRACEBI_AUTH_PROXY_HEADER=X-Forwarded-User
# TRACEBI_AUTH_PROXY_TRUSTED_IPS=10.0.0.1

# ── Authorization (roles) ───────────────────────────────────────────────────
# Without a usable role source every authenticated caller is admin
# (documented, deliberate). The role sources are TRACEBI_AUTH_ROLE_MAP
# (user:role pairs) and, under proxy auth, TRACEBI_AUTH_ROLE_HEADER (a header
# the proxy sets). TRACEBI_AUTH_DEFAULT_ROLE is only the fallback for
# principals a source does not name — set by itself it enforces nothing.
# TRACEBI_AUTH_ROLE_MAP=alice:admin,bob:analyst
# TRACEBI_AUTH_DEFAULT_ROLE=viewer

# ── Agent gateway (MCP over HTTP) ───────────────────────────────────────────
# TRACEBI_MCP_TOKEN=a-long-random-string
# TRACEBI_MCP_ACTOR=agent
"""

_INIT_SAMPLE_CSV = """\
order_id,order_date,region,product,qty,revenue
1001,2025-01-15,north east,Widget,12,"$1,198.80"
1002,2025-01-20,Northeast,Gadget,8,"$1,599.20"
1003,2025-02-03,midwest,Widget,20,"$1,998.00"
1004,2025-02-11,MIDWEST,Sprocket,5,"$749.50"
1005,2025-03-02,south east,Gadget,15,"$2,998.50"
1006,2025-03-18,Southeast,Widget,9,"$899.10"
1007,2025-04-05,west,Sprocket,11,"$1,649.45"
1008,2025-04-22,West,Widget,25,"$2,497.50"
1009,2025-05-09,north east,Gadget,6,"$1,199.40"
1009,2025-05-09,north east,Gadget,6,"$1,199.40"
1010,2025-05-30,midwest,Sprocket,14,"$2,098.60"
,2025-06-01,west,Widget,3,"$299.70"
"""

_INIT_SAMPLE_TRANSFORM = '''\
"""
Phase ① — TRANSFORM.

Ordinary pandas. Read the raw pull from inputs/, do whatever the data needs —
here: drop the row with no key, dedupe, normalise regions spelled four ways,
parse money stored as strings — and SINK the clean, star-shaped result into
the warehouse.

This is the phase the framework does NOT constrain: write as much pandas as
the data needs. The contract is not *how* you clean, it is *what lands* — the
named tables at the bottom of this file. Phase ② (models/) reads those tables
and never sees this code.

    python transforms/sample_transform.py

Idempotent: rerun any time; it replaces the warehouse tables.
"""

from __future__ import annotations

import os

import pandas as pd

from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "inputs", "orders.csv")
WAREHOUSE = os.path.join(ROOT, "data", "warehouse.duckdb")

_REGIONS = {
    "north east": "Northeast", "northeast": "Northeast",
    "south east": "Southeast", "southeast": "Southeast",
    "midwest": "Midwest", "west": "West",
}


def run() -> dict:
    df = pd.read_csv(RAW)

    # Clean — any pandas you like; none of this is traced, by design.
    df = df.dropna(subset=["order_id"]).drop_duplicates(subset=["order_id"])
    df["order_id"] = df["order_id"].astype(int)
    df["region"] = df["region"].str.strip().str.lower().map(_REGIONS)
    df["revenue"] = (
        df["revenue"].str.replace(r"[$,]", "", regex=True).astype(float)
    )
    df["qty"] = df["qty"].astype(int)

    # Shape — one dimension, one fact, keyed.
    dim_region = (
        df[["region"]].drop_duplicates().reset_index(drop=True)
        .rename_axis("region_id").reset_index()
    )
    fact = df.merge(dim_region, on="region")[
        ["order_id", "order_date", "region_id", "product", "qty", "revenue"]
    ]

    # Sink — the contract. These named tables are what phase ② models.
    os.makedirs(os.path.dirname(WAREHOUSE), exist_ok=True)
    wh = DuckDBConnector("warehouse", database=WAREHOUSE)
    wh.write(dim_region, "dim_region")
    wh.write(fact, "fact_orders")

    # Declare the sink CONTRACT: what must be true of the tables that just
    # landed, checked as read-only SQL and recorded beside the warehouse.
    # A failed check raises — a broken sink never freezes quietly. This
    # certifies the SINK; it never verifies the pandas above. The note= is
    # the STATED methodology — prose about what the cleaning did, recorded
    # verbatim and carried into report receipts, never a verified claim.
    from tracebi.contracts import contract
    with contract("sample_transform", warehouse=WAREHOUSE,
                  note="dropped rows without an order_id; regions "
                       "normalized from four spellings") as c:
        c.rows("fact_orders", at_least=1)
        c.unique("fact_orders", ["order_id"])
        c.not_null("fact_orders", ["order_id", "region_id", "revenue"])
        c.foreign_key("fact_orders", "region_id",
                      refers_to=("dim_region", "region_id"))

    return {"orders": len(fact), "regions": len(dim_region),
            "revenue": round(fact["revenue"].sum(), 2), "warehouse": WAREHOUSE}


if __name__ == "__main__":
    for k, v in run().items():
        print(f"  {k:12} {v}")
'''

_INIT_SAMPLE_MODEL = '''\
"""
Phase ② — MODEL.

A star schema over the warehouse phase ① sank into. This file is the
*contract*: grain, keys, and measures in a few declarative lines a reviewer
reads without ever opening the pandas that produced the tables.

    from tracebi.model_registry import get_model
    model = get_model("sample_model")

Construction is declarative and lazy — importing this file does not touch the
warehouse, so it loads fine before phase ① has ever run; a query is what
reads the file. Keep it that way: never call model.connect() at import time.
"""

from __future__ import annotations

import os

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAREHOUSE = os.path.join(ROOT, "data", "warehouse.duckdb")

connector = DuckDBConnector("warehouse", database=WAREHOUSE)

model = (
    DataModel("sample_model")
    .add_connector(connector)
    # tables ← the exact names phase ① sank
    .add_table("fact_orders", connector="warehouse", source="fact_orders")
    .add_table("dim_region", connector="warehouse", source="dim_region")
    # dimensions
    .add_dimension("dim_region", table_name="dim_region", key_col="region_id",
                   attributes=["region"])
    # fact
    .add_fact("fact_orders", table_name="fact_orders",
              measures=["revenue", "qty"],
              foreign_keys={"dim_region": "region_id"})
    # measures ← the vocabulary a report queries by name
    .add_measure("revenue", column="revenue", agg="sum",
                 description="Total revenue", format="currency0")
    .add_measure("units", column="qty", agg="sum", description="Units sold")
    .add_measure("orders", column="order_id", agg="count",
                 description="Order count")
)
'''

# The sample report is an ARTIFACT PACKAGE — the one report lane — so the
# first page a new project renders demonstrates the real product: figure
# claims, the presentation stack, provenance badges, and a receipt that
# joins the sink contract. (A JSON spec still renders and `tracebi migrate
# spec` compiles one, but the scaffold must not teach the legacy form.)
_INIT_SAMPLE_REPORT_JSON = """\
{
  "name": "Sample Dashboard",
  "author": "tracebi init",
  "description": "Every figure claims a stamped binding. Edit template.html to reshape the page; nothing re-runs the pandas.",
  "libs": ["echarts"],
  "data": {
    "kpis": {
      "model": "sample_model",
      "query": { "fact": "fact_orders", "measures": ["revenue", "orders", "units"] }
    },
    "by_region": {
      "model": "sample_model",
      "query": {
        "fact": "fact_orders",
        "measures": ["revenue"],
        "dimensions": ["dim_region.region"],
        "order_by": ["-revenue"]
      }
    },
    "region_detail": {
      "model": "sample_model",
      "query": {
        "fact": "fact_orders",
        "measures": ["revenue", "orders", "units"],
        "dimensions": ["dim_region.region"],
        "order_by": ["-revenue"]
      }
    }
  }
}
"""

_INIT_SAMPLE_TEMPLATE_HTML = """\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Sample Dashboard</title></head>
<body>
<main class="tb-page">
  <h1>Orders — Sample Dashboard</h1>
  <p class="tb-note">Cleaned from <code>inputs/orders.csv</code> by the
    phase-① transform. Every number on this page is a live, fingerprinted
    query — including the one in this sentence: total revenue across all
    regions is
    <span data-tb-figure="value" data-tb-binding="kpis" data-tb-cell="revenue"
          data-tb-format="currency0" id="val-revenue-inline">—</span>.
    Prose numbers can be bound too; never type one in.</p>

  <div class="tb-grid">
    <div class="tb-kpi" data-tb-figure="value" data-tb-binding="kpis"
         data-tb-cell="revenue" data-tb-format="currency0" id="kpi-revenue">
      <span class="tb-kpi-label">Revenue</span>
      <span class="tb-kpi-value"></span>
    </div>
    <div class="tb-kpi" data-tb-figure="value" data-tb-binding="kpis"
         data-tb-cell="orders" data-tb-format="comma" id="kpi-orders">
      <span class="tb-kpi-label">Orders</span>
      <span class="tb-kpi-value"></span>
    </div>
    <div class="tb-kpi" data-tb-figure="value" data-tb-binding="kpis"
         data-tb-cell="units" data-tb-format="comma" id="kpi-units">
      <span class="tb-kpi-label">Units</span>
      <span class="tb-kpi-value"></span>
    </div>
  </div>

  <div class="tb-card">
    <h2>Revenue by region</h2>
    <div data-tb-figure="chart" data-tb-binding="by_region" data-tb-type="bar"
         data-tb-x="dim_region.region" data-tb-y="revenue"
         data-tb-value-format="compact" id="chart-by-region"></div>
  </div>

  <div class="tb-card">
    <h2>Region detail</h2>
    <table data-tb-figure="table" data-tb-binding="region_detail"
           class="tb-table--striped" id="tbl-regions"></table>
  </div>

  <section data-tb-stage="exploration">
    <h3>Working notes</h3>
    <p>Scratch space: this block renders under <code>tracebi dev</code> and is
       DELETED at the final build. Explore here; promote what matters into a
       figure above.</p>
  </section>
</main>
</body></html>
"""

def _init_project_readme(project: str) -> str:
    return f"""\
# {project}

A TraceBi project. Scaffolded by `tracebi init`.

TraceBi is the trust layer for AI-generated analytics: work moves through
three phases, and from the model boundary onward every number carries a
receipt you can re-check.

```
⓪  INPUT       inputs/       raw pulls land here (API export · CSV · SQL dump)
①  TRANSFORM   transforms/   unconstrained pandas → SINK star tables
                                      ── freeze: data/warehouse.duckdb ──
②  MODEL       models/       a declarative star schema over the sink
                                      ── freeze: the model (the contract) ──
③  REPORT      reports/      artifact packages whose every figure claims a binding
```

## Install

TraceBi is not on PyPI — install it from GitHub:

```bash
pip install "tracebi[analyst] @ git+https://github.com/saltyscott0521/tracebi"
```

For the web UI and REST API as well (in addition to the analyst extras):

```bash
pip install "tracebi[analyst,web] @ git+https://github.com/saltyscott0521/tracebi"
```

(That install carries the API; the built React bundle is not in the repo the
installer builds from, so `/` explains how to build it. Every `/api/...`
route works either way.)

## Run the whole loop now

The scaffold is a complete working example — messy input included:

```bash
python transforms/sample_transform.py       # ① clean + sink → data/warehouse.duckdb
tracebi report build sample_dashboard       # ③ render → output/sample_dashboard.html + receipt
tracebi verify output/sample_dashboard.html.manifest.json   # every checked section: REPRODUCES
tracebi serve                               # browse it at http://127.0.0.1:8000
```

That last `verify` is the point: it re-runs the recorded queries against the
model and confirms the rendered numbers still reproduce. Every number drawn
through the model has a receipt; anything else must be marked as not having
one.

## Layout

```
{project}/
├── inputs/           Phase ⓪ — raw pulls (orders.csv is the sample)
├── transforms/       Phase ① — pandas that reads inputs/, sinks star tables
├── models/           Phase ② — each .py exposes `model` (a DataModel)
├── reports/          Phase ③ — ReportSpec .json, packages, and factories
├── pipelines/        PipelineRunner definitions — each .py exposes `runner`
├── scheduled/        Reports on a cron schedule
├── data/             The warehouse (gitignored)
├── output/           Rendered reports; *.manifest.json receipts stay tracked
└── .env.example      Copy to `.env` and fill in credentials
```

Everything in the artifact directories is discovered automatically — by
`tracebi serve`, and by notebooks via `get_model()` / `get_runner()`. There
is no registration file to edit.

Run `git init && git add . && git commit -m init` — manifests stamp the
commit (`git_sha`), which
is half the audit story.

## Wire your own data

1. Copy `.env.example` to `.env` and add your database URL.
2. Drop a raw pull in `inputs/` (or query it in your transform directly).
3. `tracebi new-transform "Orders Clean"` — write the pandas; end by sinking
   named tables to the warehouse. The framework does not constrain this
   phase; the contract is what lands.
4. `tracebi new-model "Sales"` — declare the star schema over those tables.
   `tracebi validate` confirms it loads and its dimension keys are unique.
5. Copy `reports/sample_dashboard/` (or `tracebi new-report "My Report"`),
   point its `report.json` bindings at your model, and put figures in the
   template: `data-tb-figure` + `data-tb-binding` on any element — spans in
   prose included. `tracebi dev my_report` opens the live loop (edit, watch,
   pin). Exploration happens *inside* the artifact — blocks marked
   `data-tb-stage="exploration"` die at the final build.

## Agents

The same contracts drive the agent surface: `tracebi context` emits the
vocabulary as JSON, `tracebi mcp` opens the gateway (validate a spec, query
a model, render, verify — read-and-compute only). An agent and an analyst
author against the same model and produce the same receipts. **`AGENTS.md`
in this project orients an AI agent working here** — point a fresh session at
it (most coding agents read it automatically).
"""


_INIT_AGENTS_MD = '''\
# Working in this TraceBi project

You are an agent working in a **TraceBi** project. TraceBi is the trust layer
for AI-generated analytics: every number you put in front of a person should
carry a receipt. Read this before you touch anything.

## The one rule

**Every figure in a report names a stamped data binding — never a hard-coded
number.** A number you typed in has no receipt and cannot be verified. If a
figure genuinely cannot come from a query, mark the element
`data-tb-unverified` (with a `data-tb-note` saying why); do not fake it.
There is no third state.

This includes prose. A sentence's numbers can be live: any element — a
`<span>` mid-sentence included — can carry
`data-tb-figure="value" data-tb-binding="..." data-tb-cell="..."` and the
runtime fills it from the fingerprinted bytes. When you are asked to
"explain the results", bind the numbers in your sentences instead of typing
them; narrative prose is where unverified numbers usually hide, and here the
honest path costs one attribute.

## The workflow — three phases, three folders

```
⓪  inputs/       raw data lands here (a CSV, an API export, a SQL dump)
①  transforms/   ordinary pandas: clean it, then SINK clean star-schema
                 tables into the warehouse (data/warehouse.duckdb) and
                 declare a SINK CONTRACT on what landed
                        ── freeze: the warehouse + its contract ──
②  models/       a declarative DataModel over the sink: grain, keys, measures.
                 It reads the warehouse; it never sees the transform.
                        ── freeze: the model (the contract) ──
③  reports/      an ARTIFACT PACKAGE — reports/<name>/ holding report.json
                 (named query bindings) + template.html (your page, where
                 every figure claims a binding). Builds to one self-contained
                 HTML + a manifest (the receipt).
```

The phases are decoupled: editing a report never re-runs the pandas. Phase ①
is unconstrained — write whatever pandas the data needs; the contract is the
named tables you sink, not how you cleaned them. End the transform with a
`with contract(...)` block (see `transforms/sample_transform.py`): declared
checks — `rows`, `unique`, `not_null`, `foreign_key`, `values`, `reconcile` —
run as read-only SQL at sink time, raise on failure, and record a certificate
(`data/warehouse.contracts.json`) that report manifests join against. The
exact claim is "the sink satisfied its contract" — never "the transform was
verified"; nothing machine-checks the pandas above the sink.

## Authoring a report (the artifact package)

`reports/sample_dashboard/` is the working example — a page of ordinary HTML
whose figures each name a binding from `report.json`:

- `data-tb-figure="value|chart|table|custom"` + `data-tb-binding="<name>"` —
  the claim. Values add `data-tb-cell="<column>"` and optionally
  `data-tb-format` (`compact`, `currency`, `comma`, `percent`, …). Charts add
  `data-tb-type` (`bar`, `barh`, `line`, `area`, `pie`, `scatter`),
  `data-tb-x`, `data-tb-y` (comma-list for multi-series), optional
  `data-tb-color` and `data-tb-value-format`. Tables optionally add
  `data-tb-columns` and the `tb-table--striped` / `tb-table--compact` classes.
- **Give every figure an `id`** — ids are how humans redirect you
  ("fix `tbl-seniority`").
- "Top N" is declarative: put `order_by` + `limit` in the binding's query.
  Never sort or slice in `script.js` — that moves ordering out of the receipt.
- Blocks marked `data-tb-stage="exploration"` are working scratch: they render
  in dev and are DELETED at the final build.
- Styling: the shipped defaults render well with zero CSS. To restyle, set
  tokens in `reports/_theme.css` (project-wide) or the package's `style.css`
  (per report); later wins. `script.js` may restyle charts via
  `tracebi.configureChart` — config can restyle, never re-source: series data
  always comes from the stamped bytes. Provenance badges pick their state
  from the manifest; a stylesheet can restyle a badge, never re-color honesty.
- Methodology travels the pipeline: `contract(..., note=...)` (and per-check
  `note=`) records the transform's STATED methodology in the certificate;
  measure `description=` carries modeling intent. Add ONE
  `<section data-tb-methodology></section>` to the template and the build
  appends them after your own prose — an appendix of what the pipeline
  states about itself, clearly not a verified claim, never badged.

## The loop you run

```bash
python transforms/<name>.py                 # ① clean + sink + contract
tracebi new-model "<Name>"                  # ② scaffold a model; edit it
tracebi new-report "<Name>"                 # ③ scaffold reports/<name>/
tracebi dev <name>                          # the live loop (see below)
tracebi report status <name>                # earned state in the terminal (📌 pins)
tracebi report build <name>                 # render → output/<name>.html + manifest
tracebi verify output/<name>.html.manifest.json --contracts
tracebi serve                               # browse at http://127.0.0.1:8000
```

### The dev iteration, step by step

0. **Discovery comes first — and it has a live surface.** Before any report
   exists, run `tracebi dev` with **no name** (backgrounded — it blocks):
   the discovery workbench. While it serves, ANY script you run can call
   `tracebi.workbench.show(...)` — no env var needed — and the portal
   updates live. **Work like a notebook**: `show("## Approach\\n...")`
   renders as a markdown cell (narrate the methodology as you go — the
   human can flip the feed to read top-down as a document);
   `show(df, note=...)` posts a frame excerpt with column profiles;
   `show(df, chart="bar", x=..., y=...)` sketches a real chart (bar,
   barh, line, area, pie, scatter) — iterate by re-showing, and when the
   human pins one for the report, re-express it as a model-query binding
   + figure: the sketch is exploration, the figure is the claim. The
   Warehouse panel lists tables, row counts, column profiles, and
   sink-contract status as transforms land; the Models panel shows the
   star schema taking shape as you edit `models/`. Pins read via the MCP
   `workbench_state` tool called with no `report`. All dev-state; no
   receipts exist before the model boundary, and `show()` is a no-op the
   moment the server is down. When a session shaped the pipeline, save it:
   `tracebi session export` (add `--format md` for the git-review twin)
   writes the full feed to `explorations/` as a committed lab-notebook
   record — exploration-stamped, no receipts, `verify` refuses it by name.
1. **Start the dev server — it blocks.** Run `tracebi dev <name>` in a
   background shell (or ask the human to run it and keep the tab open; the
   page is their view, not yours). It serves the report at the root and the
   workbench at `/__workbench`, and reloads on every save to the package,
   `models/`, `transforms/`, or `reports/_theme.css`.
2. **Edit; the portal follows.** Work in `template.html` / `report.json` /
   `style.css` / `script.js`. Explore inside `data-tb-stage="exploration"`
   blocks — they render in dev and die at build. From `report.py`,
   `tracebi.workbench.show(title, df_or_fig, note=...)` posts exhibits to
   the workbench feed during dev and is a no-op everywhere else, so probe
   code needs no cleanup and no promotion step.
3. **Read the pins before every pass.** The human steers by PINNING figures
   in the workbench with a note ("make this top 8 sectors only"). Read them
   with `tracebi report status <name>` (pins print with 📌) or the MCP
   `workbench_state` tool. Address pins first; they are the human pointing.
4. **Share a draft with `tracebi report snapshot <name>`.** One HTML with
   the exploration blocks KEPT and a review banner; it carries no manifest
   and `verify` refuses it by name — a draft can never impersonate a
   final. Use it when the human wants to look without a dev server.
5. **Publish with `tracebi report build <name>`**, then
   `tracebi verify output/<name>.html.manifest.json --strict --contracts`.
   The build strips exploration, validates every figure claim against the
   embedded bindings, and writes the receipt. `output/<name>.html` (+ its
   `.manifest.json`) is the deliverable to hand over or commit — and the
   package is already served live on the Reports page of `tracebi serve`;
   there is no separate publish step.

`tracebi verify` is the point: it re-runs the recorded queries and confirms
every figure still reproduces. Only `REPRODUCES` means a number was re-run
and matched. `--contracts` also re-runs the sink contracts. Run it before
you tell a human a report is done.

## First moves

1. Run `tracebi context --brief` — the token-lean vocabulary tier (~2.3k
   tokens): the semantic model, the figure grammar, contracts, and
   conventions — everything this loop needs; it names what it omitted.
   Nothing outside the vocabulary validates. Add `--model <name>` for one
   model's schema; drop `--brief` only when writing Python against the
   library directly.
2. Read the sample files: `transforms/sample_transform.py`,
   `models/sample_model.py`, `reports/sample_dashboard/`. They are a complete
   working example of the loop, receipt included.
3. Read `README.md` for the run commands.

## The honest boundary — do not overclaim

The trust machinery covers the model boundary onward (the query and the
report), **not** the phase-① pandas that built the warehouse. `verify` checks
that a number still reproduces from its recorded query; it does not assert the
number is *correct*, and it never reads the transform. The sink contract
certifies what landed, not how. Say so honestly. An "unverifiable" that says
so beats a green badge on unchecked work.

## Legacy forms

A JSON `ReportSpec` under `reports/` still renders (it is a serialization,
not a lane) and `tracebi migrate spec reports/<name>.json` compiles one into
an artifact package that shadows it. The `requests/` script lane is
deprecated and removed in 0.8 — do not create it.

## Scaffolding commands

`tracebi new-transform "<Name>"` · `tracebi new-model "<Name>"` ·
`tracebi new-report "<Name>"` · `tracebi spec schema` (the ReportSpec JSON
Schema). Discover more with `tracebi --help`.
'''


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.project).resolve()
    if target.exists() and any(target.iterdir()):
        if not args.force:
            print(
                f"refusing to init into non-empty {target}; pass --force to override",
                file=sys.stderr,
            )
            return 1

    # The full three-phase layout: the workflow folders (inputs/, transforms/)
    # plus every directory the server auto-discovers at startup. The scaffold
    # is a complete working example — the first thing a new user runs ends
    # with `tracebi verify` reading REPRODUCES.
    # No requests/ — the scratchpad lane is deprecated (removed in 0.8); the
    # exploration story is the artifact's own: `tracebi dev` + exploration
    # blocks that die at build (architecture v2 §7).
    for d in ("inputs", "transforms", "models", "pipelines", "reports",
              "scheduled", "data", "output"):
        (target / d).mkdir(parents=True, exist_ok=True)

    files = {
        target / ".gitignore":              _INIT_GITIGNORE,
        target / ".env.example":            _INIT_ENV_EXAMPLE,
        target / "README.md":               _init_project_readme(target.name),
        target / "AGENTS.md":               _INIT_AGENTS_MD,
        target / "inputs" / "orders.csv":   _INIT_SAMPLE_CSV,
        target / "transforms" / "sample_transform.py": _INIT_SAMPLE_TRANSFORM,
        target / "models" / "sample_model.py": _INIT_SAMPLE_MODEL,
        target / "reports" / "sample_dashboard" / "report.json":
            _INIT_SAMPLE_REPORT_JSON,
        target / "reports" / "sample_dashboard" / "template.html":
            _INIT_SAMPLE_TEMPLATE_HTML,
    }
    # Keep the still-empty discovery directories in git so the layout
    # survives a clone.
    for d in ("pipelines", "scheduled"):
        files[target / d / ".gitkeep"] = ""

    for path, content in files.items():
        if path.exists() and not args.force:
            print(f"skipping existing {path}", file=sys.stderr)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(f"Initialised TraceBi project at {target}")
    print(f"  cd {target.name}")
    print(f"  git init && git add . && git commit -m init   # manifests stamp the commit (git_sha)")
    print(f"  python transforms/sample_transform.py  # ① clean + sink the sample input")
    print(f"  tracebi report build sample_dashboard  # ③ render + receipt")
    print(f"  tracebi verify output/sample_dashboard.html.manifest.json")
    print(f"  tracebi serve                          # browse at http://127.0.0.1:8000")
    print(f"AGENTS.md orients an AI agent working in this project.")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    """
    Print TraceBi's vocabulary as JSON — every section and panel type with
    its fields and allowed values, the DataSet verbs, measure kinds, filter
    operators, and the discovery conventions.

    Generated from the code, so it cannot drift. Intended as context for a
    tool or agent authoring a project; add --model to include a specific
    model's tables, dimensions and declared measures.
    """
    from tracebi.capabilities import describe

    payload = describe(brief=getattr(args, "brief", False))
    if args.model:
        from tracebi.model_registry import get_model
        try:
            payload["model"] = get_model(args.model).info()
        except (KeyError, AttributeError) as exc:
            print(f"Could not describe model '{args.model}': {exc}", file=sys.stderr)
            return 1

    print(json.dumps(payload, indent=None if args.compact else 2, default=str))
    return 0


def _load_project_models() -> dict:
    """Every model in models/, keyed by the name the spec would reference."""
    from tracebi import model_registry

    models: dict = {}
    d = _default_models_dir()
    if not d.is_dir():
        return models
    for stem in model_registry.auto_discover(str(d)):
        try:
            m = model_registry.get_model(stem)
        except Exception:  # noqa: BLE001 — validate reports load failures itself
            continue
        models[m.name] = m
        models.setdefault(stem, m)
    return models


def cmd_spec(args: argparse.Namespace) -> int:
    """
    Work with report specs — a report as JSON rather than Python.

        tracebi spec schema                 # the JSON Schema
        tracebi spec validate report.json   # check it without running it
        tracebi spec render report.json     # build and render it
    """
    from tracebi.spec import ReportSpec, json_schema

    if args.action == "schema":
        print(json.dumps(json_schema(), indent=2))
        return 0

    if not args.file:
        print(f"`tracebi spec {args.action}` needs a spec file.", file=sys.stderr)
        return 1
    path = Path(args.file)
    if not path.is_file():
        print(f"No such file: {path}", file=sys.stderr)
        return 1

    try:
        spec = ReportSpec.from_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a bad file is a user error
        print(f"{path}: could not read spec — {exc}", file=sys.stderr)
        return 1

    models = _load_project_models()
    result = spec.validate(models)

    for warn in result["warnings"]:
        print(f"· {warn}")
    for err in result["errors"]:
        print(f"✗ {err}", file=sys.stderr)
    if not result["ok"]:
        print(f"\n{len(result['errors'])} problem(s) in {path}.", file=sys.stderr)
        return 1

    if args.action == "validate":
        coverage = spec.data_coverage()
        print(f"✓ {path} is valid — {len(spec.sections)} section(s), "
              f"{coverage['with_data_ref']}/{coverage['total']} data-bearing "
              f"section(s) have a reference")
        return 0

    # render
    from tracebi.reports.html_renderer import HTMLRenderer

    report = spec.build(models)
    out = Path(args.output or f"{_slugify(spec.name)}.html")
    HTMLRenderer.for_project(
        report_css=_report_theme_css(spec, extra_theme=getattr(args, "theme", None)),
        report_js=_report_script_js(spec),
    ).render(report, str(out))
    print(f"Rendered {spec.name} → {out}")
    return 0


def _web_app_importable() -> bool:
    """True when the FastAPI app package can be imported.

    ``tracebi serve`` boots ``tracebi.web.api.main:app``. The wheel ships that
    package, but an install predating the move out of the top-level ``web``
    package does not — checked up front so the failure is an actionable
    message instead of uvicorn's ModuleNotFoundError mid-boot. (The web app is
    not the same thing as the built UI: a wheel can ship the app with no
    bundle, which boots and explains itself at ``/``.)
    """
    import importlib.util

    try:
        return importlib.util.find_spec("tracebi.web.api.main") is not None
    except ImportError:
        return False


def cmd_serve(args: argparse.Namespace) -> int:
    """
    Serve the current project's web UI.

    The one CLI step between an installed package and a running app.
    Artifacts are discovered from the working directory, so this is run
    from a project root — the layout ``tracebi init`` creates.
    """
    cwd = Path.cwd()
    discovered = {
        d: len([p for p in (cwd / d).glob("*.py") if not p.name.startswith("_")])
        for d in ("models", "pipelines", "reports", "requests")
        if (cwd / d).is_dir()
    }
    if not discovered:
        print(
            f"No TraceBi project found in {cwd}.\n"
            f"Expected at least one of: models/ pipelines/ reports/ requests/\n"
            f"Run `tracebi init .` to scaffold one, or cd to a project root.",
            file=sys.stderr,
        )
        return 1

    # The app reads artifact directories relative to the working directory,
    # so it must stay on sys.path for the discovery imports to resolve.
    # Inserted before the checks below so a checkout in cwd counts as one.
    sys.path.insert(0, str(cwd))

    if not _web_app_importable():
        print(
            "tracebi serve: the web app (tracebi.web.api) is not importable.\n"
            "Current wheels ship it inside the `tracebi` package; an install\n"
            "predating the move shipped it as a top-level `web` package.\n"
            "Upgrade, or run `tracebi serve` from a clone of the repo:\n"
            "    git clone https://github.com/saltyscott0521/tracebi\n"
            "or point PYTHONPATH at an existing checkout:\n"
            "    PYTHONPATH=/path/to/tracebi-checkout tracebi serve\n"
            "(TraceBi is not on PyPI; the library installs with:\n"
            '    pip install "tracebi[web] @ git+https://github.com/saltyscott0521/tracebi")',
            file=sys.stderr,
        )
        return 1

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "The web UI needs the web extras. TraceBi is not on PyPI —\n"
            "install from the repo:\n"
            '    pip install "tracebi[web] @ git+https://github.com/saltyscott0521/tracebi"',
            file=sys.stderr,
        )
        return 1

    # Don't drag the bundled demo app into someone else's project — it
    # references demo data they do not have. An app module is only needed
    # for connectors; opt in by setting TRACEBI_APP.
    os.environ.setdefault("TRACEBI_APP", "")

    summary = ", ".join(f"{n} {d}" for d, n in discovered.items() if n) or "no artifacts yet"
    print(f"TraceBi — serving {cwd.name} ({summary})")
    print(f"  http://{args.host}:{args.port}")

    import uvicorn
    uvicorn.run(
        "tracebi.web.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def cmd_new_request(args: argparse.Namespace) -> int:
    print(_REQUESTS_DEPRECATION, file=sys.stderr)
    requests_dir: Path = args.requests_dir
    requests_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    suffix = ".ipynb" if args.notebook else ".py"
    out_path = requests_dir / f"{slug}{suffix}"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    if args.notebook:
        out_path.write_text(_notebook_text(args.title), encoding="utf-8")
    else:
        out_path.write_text(_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    return 0


def cmd_list_requests(args: argparse.Namespace) -> int:
    requests_dir: Path = args.requests_dir
    if not requests_dir.is_dir():
        print(f"No requests directory at {requests_dir}")
        return 0
    files = sorted(
        p for p in list(requests_dir.glob("*.py")) + list(requests_dir.glob("*.ipynb"))
        if not p.name.startswith("_")
    )
    if not files:
        print(f"No request scripts found in {requests_dir}")
        return 0
    for p in files:
        print(p.relative_to(requests_dir.parent))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    requests_dir: Path = args.requests_dir
    name = args.name
    path = _resolve_request_path(requests_dir, name)
    if path is None:
        print(f"Request not found in {requests_dir}: {name}", file=sys.stderr)
        return 1
    print(_REQUESTS_DEPRECATION, file=sys.stderr)

    overrides: dict = {}
    for item in args.param or []:
        if "=" not in item:
            print(f"--param expects key=value, got: {item}", file=sys.stderr)
            return 1
        key, _, value = item.partition("=")
        overrides[key.strip()] = value

    from tracebi._params import reset_param_overrides, set_param_overrides

    print(f"Running {path}…")
    token = set_param_overrides(overrides or None)
    try:
        if path.suffix == ".ipynb":
            from tracebi._notebook import notebook_to_source
            source = notebook_to_source(path)
            ns: dict = {"__name__": "__main__", "__file__": str(path)}
            exec(compile(source, str(path), "exec"), ns)
            if callable(ns.get("run")):
                ns["run"]()
        else:
            runpy.run_path(str(path), run_name="__main__")
    finally:
        reset_param_overrides(token)
    return 0


def cmd_dev(args: argparse.Namespace) -> int:
    # Form-aware (v2 §2.5): an artifact package under reports/ gets the
    # artifact-native loop with the workbench; a request script keeps the
    # legacy single-file loop (deprecated, removed in 0.8). No name at all
    # is DISCOVERY MODE — no report anchored, the project-level workbench
    # (warehouse, models, packages, exhibit feed) for phases ① and ②.
    if args.name is None:
        from tracebi._dev_server import serve_dev
        return serve_dev(None, port=args.port,
                         open_browser=not args.no_browser)
    pkg_dir = _default_reports_dir() / args.name
    if (pkg_dir / "report.json").is_file() and \
            (pkg_dir / "template.html").is_file():
        from tracebi._dev_server import serve_dev
        return serve_dev(pkg_dir, port=args.port,
                         open_browser=not args.no_browser)
    path = _resolve_request_path(args.requests_dir, args.name)
    if path is None:
        print(f"Report not found: {args.name}. Looked for a package at "
              f"{pkg_dir} and a request script in {args.requests_dir}.",
              file=sys.stderr)
        return 1
    print(_REQUESTS_DEPRECATION, file=sys.stderr)
    from tracebi._dev_server import serve_dev
    return serve_dev(path, port=args.port, open_browser=not args.no_browser)


#: One sentence, everywhere the deprecated lane is touched — the CLI runner,
#: the dev server's script branch, and the requests router say the same thing.
_REQUESTS_DEPRECATION = (
    "[tracebi] requests/ is deprecated and will be removed in 0.8. The one "
    "report lane is the artifact package: `tracebi new-report`, then "
    "`tracebi dev <name>` for the live loop — exploration blocks die at "
    "build, and every figure earns its receipt."
)


def _resolve_request_path(requests_dir: Path, name: str) -> Optional[Path]:
    """Find a request file by name, trying .py then .ipynb if no suffix given."""
    candidate = requests_dir / name
    if candidate.is_file():
        return candidate
    for suffix in (".py", ".ipynb"):
        cand = requests_dir / f"{name}{suffix}"
        if cand.is_file():
            return cand
    return None


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Sanity-check the project: layout, then the models themselves.

    Layout checks are cheap file stats. The substantive part is loading each
    model in models/ and running ``DataModel.validate()``, which catches the
    failures that would otherwise surface as wrong numbers — chiefly a
    non-unique dimension key silently inflating every additive measure.
    """
    cwd = Path.cwd()
    problems: list[str] = []
    warnings: list[str] = []
    ok: list[str] = []

    requests_dir = args.requests_dir
    # requests/ is the deprecated lane (removed in 0.8): its ABSENCE is the
    # expected state and says nothing. Only report it when it still exists.
    if requests_dir.is_dir():
        scripts = [p for p in requests_dir.glob("*.py") if not p.name.startswith("_")]
        nbs = list(requests_dir.glob("*.ipynb"))
        warnings.append(
            f"· requests/ contains {len(scripts) + len(nbs)} script(s) — "
            f"the lane is deprecated (removed in 0.8); migrate to artifact "
            f"packages under reports/"
        )

    # ── Import every discoverable artifact and report what failed ────────
    # A file that raises on import is skipped at startup with only a
    # warning, so this is where it becomes visible.
    from tracebi.web.discovery import auto_discover, discovery_report

    for label in ("reports", "requests", "scheduled"):
        d = cwd / label
        if d.is_dir():
            auto_discover(str(d))
    for entry in discovery_report():
        if entry["status"] == "failed":
            problems.append(
                f"✗ {entry['directory']}/{entry['file']}: {entry['reason']}"
            )
    n_registered = sum(1 for e in discovery_report() if e["status"] == "registered")
    if n_registered:
        ok.append(f"✓ {n_registered} artifact module(s) imported cleanly")

    env_path = cwd / ".env"
    if env_path.is_file():
        ok.append("✓ .env file found")
    else:
        ok.append("· .env not present (only needed if you load it yourself)")

    # ── Models: load each one and check its declared structure ──────────
    models_dir = args.models_dir
    if not models_dir.is_dir():
        warnings.append(f"· models/ not present at {models_dir}")
    else:
        from tracebi import model_registry

        names = model_registry.auto_discover(str(models_dir))
        if not names:
            warnings.append("· models/ contains no model files")
        for name in names:
            try:
                model = model_registry.get_model(name)
            except Exception as exc:  # noqa: BLE001 — reported, not raised
                problems.append(f"✗ models/{name}.py failed to load: {exc}")
                continue

            result = model.validate()
            if result["ok"]:
                ndims = len(result["dimensions"])
                ok.append(f"✓ {name}: {model.name} loaded, {ndims} dimension(s) key-unique")
            else:
                for err in result["errors"]:
                    problems.append(f"✗ {name}: {err}")
            for warn in result["warnings"]:
                warnings.append(f"· {name}: {warn}")

    for line in ok:
        print(line)
    for line in warnings:
        print(line)
    for line in problems:
        print(line, file=sys.stderr)

    if problems:
        print(f"\n{len(problems)} problem(s) found.", file=sys.stderr)
        return 1
    print("\nProject looks good.")
    return 0


def cmd_new_model(args: argparse.Namespace) -> int:
    models_dir: Path = args.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    out_path = models_dir / f"{slug}.py"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    out_path.write_text(_model_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    print(f"  Edit the file, then use it with:")
    print(f"    from tracebi.model_registry import get_model")
    print(f'    model = get_model("{slug}")')
    return 0


def cmd_new_transform(args: argparse.Namespace) -> int:
    transforms_dir: Path = args.transforms_dir
    transforms_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    out_path = transforms_dir / f"{slug}.py"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    out_path.write_text(_transform_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    print(f"  Write the pandas, end by sinking named tables, then run it:")
    print(f"    python {out_path}")
    return 0


def cmd_list_models(args: argparse.Namespace) -> int:
    models_dir: Path = args.models_dir
    if not models_dir.is_dir():
        print(f"No models directory at {models_dir}")
        return 0
    files = sorted(p for p in models_dir.glob("*.py") if not p.name.startswith("_"))
    if not files:
        print(f"No model files found in {models_dir}")
        return 0
    for p in files:
        print(p.relative_to(models_dir.parent))
    return 0


def cmd_new_pipeline(args: argparse.Namespace) -> int:
    pipelines_dir: Path = args.pipelines_dir
    pipelines_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    out_path = pipelines_dir / f"{slug}.py"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    out_path.write_text(_pipeline_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    print(f"  Edit the file, then use it with:")
    print(f"    from tracebi.pipeline_registry import get_runner")
    print(f'    runner = get_runner("{slug}")')
    return 0


def _pipeline_plan(runner) -> list[str]:
    """
    Every registered layer, upstream-first, each appearing once.

    ``execution_order`` resolves the chain for a single layer. Concatenating
    each layer's chain and keeping the first occurrence gives a valid order
    for the whole pipeline: within any chain a layer's upstreams precede it,
    and deduplicating on first sight can only move a layer earlier.
    """
    plan: list[str] = []
    for layer in runner.layers():
        for step in runner.execution_order(layer["name"]):
            if step not in plan:
                plan.append(step)
    return plan


def cmd_run_pipeline(args: argparse.Namespace) -> int:
    """
    Run a pipeline from the command line.

    This is the execution plane's entry point. Until it existed the only way
    to execute a layer was ``POST /api/pipelines/{name}/layers/{layer}/run``,
    which meant the web server had to be running — and had to be the thing
    doing the work — for any data to be produced. That is what tied batch
    execution to the serving process and made deployments where the two are
    separate (a scheduled job writing to Postgres, a stateless API reading
    from it) impossible to express. See NOTES.md, "Deployment planes".

    Any external scheduler can now drive this: cron, a Kubernetes CronJob,
    Airflow, a CI job. TraceBi does not need to own the schedule.
    """
    import getpass

    from tracebi.audit import set_actor
    from tracebi.pipeline_registry import get_runner, list_pipelines

    # Attribute CLI-driven runs too. A cron job or CI step runs as some
    # account, and "who ran this" should answer that rather than shrug at
    # everything the web UI did not trigger.
    try:
        set_actor(getpass.getuser(), role="cli")
    except Exception:  # noqa: BLE001 — no controlling user (some containers)
        set_actor(None, role="cli")

    try:
        runner = get_runner(args.name)
    except KeyError as exc:
        print(str(exc).strip("\"'"), file=sys.stderr)
        known = list_pipelines()
        if not known:
            print(f"No pipelines found in {args.pipelines_dir}. "
                  'Scaffold one with: tracebi new-pipeline "My ETL"', file=sys.stderr)
        return 1

    if args.status:
        rows = runner.layers()
        if not rows:
            print(f"Pipeline '{args.name}' has no registered layers.")
            return 0
        width = max(len(r["name"]) for r in rows)
        for r in rows:
            # layers() returns registration data only — name, type, schedule,
            # depends_on. Run status is a separate DB read per layer, which is
            # what the web router does too.
            try:
                last = runner.last_run(r["name"])
            except Exception as exc:  # noqa: BLE001
                status, when = f"error: {type(exc).__name__}", ""
            else:
                status = (last or {}).get("status") or "never run"
                when = (last or {}).get("completed_at") or (last or {}).get("started_at") or ""
            print(f"  {r['name']:<{width}}  {r['type']:<12} {status:<10} {when}")
        return 0

    if args.layer:
        if not runner.has_layer(args.layer):
            print(f"Layer '{args.layer}' is not registered in pipeline '{args.name}'. "
                  f"Available: {[r['name'] for r in runner.layers()]}", file=sys.stderr)
            return 1
        chain = runner.execution_order(args.layer) if args.refresh else [args.layer]
    else:
        chain = _pipeline_plan(runner)

    if not chain:
        print(f"Pipeline '{args.name}' has no registered layers.")
        return 0

    print(f"[tracebi] {args.name}: {' → '.join(chain)}")
    failed: list[str] = []
    for step in chain:
        try:
            runner.execute_layer(step)
        except Exception as exc:  # noqa: BLE001 — report and keep going
            # Downstream layers read what upstream wrote, so a failure part
            # way through leaves the rest resting on stale data. Report every
            # failure rather than stopping at the first, and exit non-zero so
            # whatever scheduler invoked this can act on it.
            failed.append(step)
            print(f"[tracebi] {step} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)

    if failed:
        print(f"[tracebi] {len(failed)} of {len(chain)} layer(s) failed: "
              f"{', '.join(failed)}", file=sys.stderr)
        return 1

    print(f"[tracebi] {len(chain)} layer(s) completed.")
    return 0


def cmd_list_pipelines(args: argparse.Namespace) -> int:
    pipelines_dir: Path = args.pipelines_dir
    if not pipelines_dir.is_dir():
        print(f"No pipelines directory at {pipelines_dir}")
        return 0
    files = sorted(p for p in pipelines_dir.glob("*.py") if not p.name.startswith("_"))
    if not files:
        print(f"No pipeline files found in {pipelines_dir}")
        return 0
    for p in files:
        print(p.relative_to(pipelines_dir.parent))
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """
    Serve the agent gateway over the Model Context Protocol.

    stdio by default, which is what a locally-configured agent speaks;
    --transport http for a remote one. Models come from the same project
    conventions as every other command (./models, or TRACEBI_MODELS_DIR).

    The http transport refuses to start until an auth decision is made:
    set TRACEBI_MCP_TOKEN (bearer auth) or pass --insecure explicitly.
    """
    from tracebi.mcp_server import GatewayAuthError, serve

    try:
        serve(transport=args.transport, port=args.port,
              insecure=args.insecure)
    except (ImportError, GatewayAuthError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


def cmd_verify_file(args: argparse.Namespace) -> int:
    """
    Offline check of a self-contained report ``.html`` (architecture §3.2).

    Recovers the exact fingerprinted bytes from every embedded data block and
    rehashes them — no model, no DataFrame rebuild — against a sibling
    ``<file>.manifest.json``. Catches a number edited in the shipped file, which
    ``verify <manifest>`` (query → model) cannot see. Exit 0 only when every
    embedded block matches the manifest.
    """
    from tracebi.verify import (
        FIGURE_MATCHES, FIGURE_UNVERIFIED_MARK, FILE_FIGURE_LABELS,
        FILE_MATCHES, FILE_STATUS_LABELS, REFUSED_SNAPSHOT, verify_file,
    )

    html_path = Path(args.verify_file)
    if not html_path.is_file():
        print(f"report file not found: {html_path}", file=sys.stderr)
        return 1

    manifest_path = (
        Path(args.file_manifest) if getattr(args, "file_manifest", None)
        else html_path.with_name(html_path.name + ".manifest.json")
    )
    if not manifest_path.is_file():
        print(f"no manifest found next to the report: expected {manifest_path}\n"
              "(pass --manifest <path> to point at it explicitly)",
              file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"manifest is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(manifest, dict):
        print(f"manifest must be a JSON object, got {type(manifest).__name__}",
              file=sys.stderr)
        return 1

    html = html_path.read_text(encoding="utf-8")
    result = verify_file(html, manifest)

    # A refused snapshot prints only the refusal — a header and "0 bindings
    # checked" would read like a check that ran and found little, and this
    # one deliberately did not run at all.
    if result["verdict"] == REFUSED_SNAPSHOT:
        print(result["verdict_detail"], file=sys.stderr)
        return result["exit_code"]

    name = result["report_name"] or html_path.name
    print(f"Verifying embedded data in '{name}' ({html_path})")
    print(f"  against manifest {manifest_path}")
    width = max(len(v) for v in FILE_STATUS_LABELS.values())
    for b in result["bindings"]:
        status = b["status"]
        mark = "✓" if status == FILE_MATCHES else "✗"
        line = f"{mark} {FILE_STATUS_LABELS[status]:<{width}}  {b['binding']}"
        if status != FILE_MATCHES:
            line += f" — {b['detail']}"
        print(line, file=sys.stdout if mark != "✗" else sys.stderr)

    # Figure cross-check rows (manifest schema 2) — the claims layer, so a
    # failure names the figure, not just the verdict.
    if result.get("figures"):
        fwidth = max(len(v) for v in FILE_FIGURE_LABELS.values())
        print()
        for f in result["figures"]:
            status = f["status"]
            ok = status in (FIGURE_MATCHES, FIGURE_UNVERIFIED_MARK)
            mark = "✓" if status == FIGURE_MATCHES else "·" if ok else "✗"
            line = (f"{mark} {FILE_FIGURE_LABELS[status]:<{fwidth}}  "
                    f"{f.get('figure')}")
            if not ok:
                line += f" — {f['detail']}"
            print(line, file=sys.stdout if mark != "✗" else sys.stderr)

    counts = ", ".join(
        f"{n} {FILE_STATUS_LABELS[status].lower()}"
        for status, n in result["summary"].items() if n
    ) or "no embedded data blocks"
    print(f"\n{len(result['bindings'])} binding(s) checked: {counts}")
    print(result["verdict_detail"],
          file=sys.stdout if result["exit_code"] == 0 else sys.stderr)
    return result["exit_code"]


def cmd_verify(args: argparse.Namespace) -> int:
    """
    Re-verify a rendered manifest: the other half of the stamp.

    Every recorded query in the manifest is re-run against the project's
    models and classified — REPRODUCES, SOURCE DRIFT (result differs and
    an input fingerprint moved), MODEL CHANGED (a table now loads from a
    different source/connector — a governance event), UNEXPLAINED (result
    differs but the inputs did not — the alarming case), or UNVERIFIABLE
    (no recorded query to re-run). One line per section, then a summary
    and the receipt-level verdict.

    Exit codes: 0 all reproduce/unverifiable · 2 diagnosed drift only ·
    1 anything unexplained, of unknown cause, errored, or a manifest with
    no data-bearing section at all (nothing was verified, so nothing passed).
    """
    from tracebi.verify import (
        FIGURE_STATUS_LABELS, REPRODUCES, STATUS_LABELS, UNVERIFIABLE,
        UNVERIFIED, load_models, verify_manifest,
    )

    # Two distinct checks under one verb (architecture §4). `--file` opens the
    # shipped .html and rehashes its embedded bytes against a sibling manifest
    # (embedded bytes → manifest); it never touches a model. The positional
    # `manifest` re-runs recorded queries (query → model). Neither implies the
    # other, so they are kept apart rather than merged.
    if getattr(args, "verify_file", None) is not None:
        return cmd_verify_file(args)
    if not args.manifest:
        print("verify: provide a manifest path, or --file <report.html>",
              file=sys.stderr)
        return 1

    path = Path(args.manifest)
    if not path.is_file():
        print(f"manifest not found: {path}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"manifest is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(manifest, dict):
        print(f"manifest must be a JSON object, got {type(manifest).__name__}",
              file=sys.stderr)
        return 1

    models = load_models(args.verify_models_dir or args.models_dir)
    try:
        result = verify_manifest(manifest, models,
                                 strict=getattr(args, "strict", False))
    except Exception as exc:  # noqa: BLE001 — a corrupt receipt is a user error
        print(f"manifest could not be verified: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return result["exit_code"]

    name = result["report_name"] or path.name
    print(f"Verifying '{name}' ({path})")
    width = max(len(v) for v in STATUS_LABELS.values())
    for s in result["sections"]:
        status = s["status"]
        mark = ("✓" if status == REPRODUCES
                else "·" if status == UNVERIFIABLE
                else "✗")
        line = f"{mark} {STATUS_LABELS[status]:<{width}}  {s['section']}"
        if status != REPRODUCES:
            line += f" — {s['detail']}"
        print(line, file=sys.stdout if mark != "✗" else sys.stderr)

    counts = ", ".join(
        f"{n} {STATUS_LABELS[status].lower()}"
        for status, n in result["summary"].items() if n
    ) or "no data-bearing sections"
    print(f"\n{len(result['sections'])} section(s) checked: {counts}")

    # Figure rollup (manifest schema 2): the claims layer, figures first.
    if result.get("figures"):
        fwidth = max(len(v) for v in FIGURE_STATUS_LABELS.values())
        print()
        for f in result["figures"]:
            status = f["status"]
            mark = ("✓" if status == REPRODUCES
                    else "·" if status in (UNVERIFIABLE, UNVERIFIED)
                    else "✗")
            line = (f"{mark} {FIGURE_STATUS_LABELS[status]:<{fwidth}}  "
                    f"{f['figure']}")
            if status != REPRODUCES:
                line += f" — {f['detail']}"
            print(line, file=sys.stdout if mark != "✗" else sys.stderr)

    exit_code = result["exit_code"]

    # The phase-① claim, reported beside the figure claims — never blended
    # (v2 §2.6). The recorded block says what the warehouse certified about
    # itself at BUILD time; it is informational here and moves no exit code.
    recorded_contracts = manifest.get("transform_contracts")
    if recorded_contracts:
        print("\nsink contracts (recorded at build):")
        for table, rec in sorted(recorded_contracts.items()):
            status = rec.get("status", "?")
            mark = "✓" if status == "satisfied" else "·"
            line = f"{mark} {status:<12} {table}"
            if status == "satisfied":
                line += f" — {rec.get('checks', 0)} check(s), transform '{rec.get('transform')}'"
            elif status == "stale":
                line += (f" — re-sunk after transform '{rec.get('transform')}' "
                         f"checked it; the certificate no longer describes "
                         f"this data")
            print(line)

    # --contracts: re-run the recorded checks against the CURRENT warehouse.
    # This is its own claim with its own exit: a check failing NOW means the
    # sink no longer satisfies its declared contract. It never says the
    # transform was verified, and it never colors a figure status.
    if getattr(args, "contracts", False):
        from tracebi.contracts import rerun_checks
        warehouses = sorted({
            c.database for m in models.values() for c in m.connectors()
            if isinstance(getattr(c, "database", None), str)
            and c.database != ":memory:"
            and type(c).__name__ == "DuckDBConnector"
        })
        rows = [r for wh in warehouses for r in rerun_checks(wh)]
        print("\nsink contracts (re-run now):")
        if not rows:
            print("· no contract record found beside the warehouse")
        failed_now = 0
        for r in rows:
            ok = r.get("passed_now")
            mark = "✓" if ok else "✗"
            desc = f"{r['check']}({r['table']}, {r.get('params')})"
            line = f"{mark} {'satisfied' if ok else 'VIOLATED':<12} {r['transform']}: {desc}"
            if not ok:
                line += f" — observed {r.get('observed_now', r.get('note'))}"
                failed_now += 1
            print(line, file=sys.stdout if ok else sys.stderr)
        if failed_now:
            print(f"{failed_now} check(s) the sink no longer satisfies.",
                  file=sys.stderr)
            exit_code = 1

    # Routed by exit code, not by verdict: a run that exits 0 must write
    # nothing to stderr, or CI wrappers that treat stderr as failure will
    # fail a receipt this command just called fine.
    print(result["verdict_detail"],
          file=sys.stdout if exit_code == 0 else sys.stderr)
    return exit_code


def cmd_migrate(args: argparse.Namespace) -> int:
    """
    ``tracebi migrate spec <file.json>`` — compile a JSON spec into an
    artifact package directory beside it.

    Emits alongside, never replaces: ``reports/sales.json`` compiles to
    ``reports/sales/``, sharing the stem — and at discovery the artifact
    directory *shadows* the same-named spec (with a warning naming both),
    so the migration is a cutover the moment the directory exists, and a
    rollback is deleting it. The spec's ``theme``/``script`` files compile
    into the package's ``style.css``/``script.js``.
    """
    from tracebi.reports.compile_spec import compile_spec
    from tracebi.spec import ReportSpec

    src = Path(args.path)
    if not src.is_file():
        print(f"spec not found: {src}", file=sys.stderr)
        return 1
    try:
        spec = ReportSpec.from_json(src.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a bad spec is a user error
        print(f"cannot read spec: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # theme/script are filenames resolved against the reports directory —
    # the directory the spec itself lives in.
    theme_css, script_js = "", ""
    for field_name, value in (("theme", spec.theme), ("script", spec.script)):
        if not value:
            continue
        ref = src.parent / value
        if ref.is_file():
            content = ref.read_text(encoding="utf-8")
            if field_name == "theme":
                theme_css = content
            else:
                script_js = content
        else:
            print(f"warning: {field_name} file '{value}' not found beside the "
                  f"spec — not compiled in", file=sys.stderr)

    compiled = compile_spec(spec, theme_css=theme_css, script_js=script_js)

    target = src.parent / src.stem
    if target.exists() and not args.force:
        print(f"target already exists: {target}\n"
              f"Pass --force to overwrite it.", file=sys.stderr)
        return 1
    target.mkdir(parents=True, exist_ok=True)
    for fname, content in compiled.files.items():
        (target / fname).write_text(content, encoding="utf-8")

    print(f"Compiled {src.name} → {target}/")
    for fname in compiled.files:
        print(f"  {fname}")
    for w in compiled.warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"\nThe artifact now shadows the spec at discovery (delete the "
          f"directory to roll back). Next:\n"
          f"  tracebi report build {src.stem}\n"
          f"  tracebi dev {src.stem}")
    return 0


# ── Report generator: new-report / report build|preview ────────────────────

def _scaffold_binding() -> tuple[str, dict, str]:
    """A concrete ``(model_name, query_dict, note)`` for a starter package.

    So ``tracebi new-report`` renders out of the box, the query is derived from
    the first model in ``models/``: its first fact, first measure, and — when
    the model has one — a dimension attribute to slice by. With no model yet,
    a placeholder is emitted and the note tells the author to point it at one.
    """
    models = _load_project_models()
    for name, model in sorted(models.items()):
        try:
            info = model.info()
        except Exception:  # noqa: BLE001 — an unloadable model is not a scaffold source
            continue
        facts = info.get("facts") or []
        measures = info.get("measures") or []
        if not facts or not measures:
            continue
        query: dict = {"fact": facts[0]["name"],
                       "measures": [measures[0]["name"]]}
        dims = info.get("dimensions") or []
        for d in dims:
            if d.get("attributes"):
                query["dimensions"] = [f"{d['name']}.{d['attributes'][0]}"]
                break
        return info.get("name", name), query, ""
    return (
        "your_model",
        {"fact": "your_fact", "measures": ["your_measure"],
         "dimensions": ["your_dimension.attribute"]},
        "No model found in models/ — edit report.json's 'data' block to name a "
        "real model and query before running `tracebi report build`.",
    )


def _report_json_text(title: str, model: str, query: dict) -> str:
    declaration = {
        "name": title,
        "author": "",
        "description": "Freeform report package scaffolded by tracebi new-report.",
        "libs": ["echarts"],
        "data": {"rows": {"model": model, "query": query}},
    }
    return json.dumps(declaration, indent=2) + "\n"


_REPORT_TEMPLATE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
</head>
<body>
  <main class="report">
    <h1>{{ title }}</h1>
    <p class="note">Every number below is embedded, fingerprinted, and recorded.
      Check it offline with <code>tracebi verify --file</code>.</p>
    <div id="chart" class="chart"></div>
    <table id="rows"><thead></thead><tbody></tbody></table>
  </main>
</body>
</html>
"""

_REPORT_STYLE_CSS = """:root { color-scheme: light; }
/* A report is a document: commit to a light ground so it reads the same in any
   browser mode (a file that only set text colour goes dark-on-dark in dark mode). */
body { font: 15px/1.5 system-ui, sans-serif; background: #fff; color: #1a1a1a;
       margin: 2rem auto; max-width: 60rem; }
h1 { margin-bottom: .25rem; }
.note { color: #666; margin-top: 0; }
.chart { width: 100%; height: 340px; margin-top: 1.5rem; }
table { border-collapse: collapse; width: 100%; margin-top: 1.5rem; }
th, td { padding: .5rem .75rem; border-bottom: 1px solid #ddd; text-align: left; }
th { border-bottom: 2px solid #999; }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
"""

# Reads the embedded data and draws the table with DOM APIs only — the data
# never reaches innerHTML, so a hostile cell value cannot execute (architecture
# §5). The block is <script type="application/json">, parsed with JSON.parse.
_REPORT_SCRIPT_JS = """(function () {
  // Minimal RFC-4180 CSV parser — handles quoted fields and commas inside them.
  function parseCsv(text) {
    var rows = [], row = [], field = "", inQ = false, i = 0, c;
    while (i < text.length) {
      c = text[i];
      if (inQ) {
        if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else { inQ = false; } }
        else { field += c; }
      } else if (c === '"') { inQ = true; }
      else if (c === ',') { row.push(field); field = ""; }
      else if (c === '\\n') { row.push(field); rows.push(row); row = []; field = ""; }
      else if (c !== '\\r') { field += c; }
      i++;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    var head = rows.shift() || [];
    return rows.filter(function (r) { return r.length === head.length; })
      .map(function (r) { var o = {}; head.forEach(function (h, j) { o[h] = r[j]; }); return o; });
  }

  var el = document.getElementById("tracebi-data-rows");
  if (!el) return;
  // Draw from the fingerprinted `csv` — the exact bytes the receipt covers — so
  // a displayed number cannot diverge from a verified one.
  var rows = parseCsv(JSON.parse(el.textContent).csv || "");
  var table = document.getElementById("rows");
  if (!rows.length || !table) return;
  var cols = Object.keys(rows[0]);

  // A starter bar chart: first column as category, first numeric column as
  // value. ECharts is the inlined global (report.json "libs": ["echarts"]).
  (function () {
    var host = document.getElementById("chart");
    var val = null;
    for (var k = 1; k < cols.length; k++) {
      if (rows[0][cols[k]] !== "" && !isNaN(Number(rows[0][cols[k]]))) { val = cols[k]; break; }
    }
    if (!host || !window.echarts || !val) { if (host) host.style.display = "none"; return; }
    var cat = cols[0];
    function draw() {
      // A report is a static document — render immediately, don't animate (and
      // the tree-shaken bundle's grow-animation does not complete).
      var chart = echarts.init(host);
      window.addEventListener("resize", function () { chart.resize(); });
      chart.setOption({
        animation: false,
        tooltip: { trigger: "axis" },
        grid: { left: 64, right: 24, top: 16, bottom: 72 },
        xAxis: { type: "category", axisLabel: { rotate: 30 },
                 data: rows.map(function (r) { return r[cat]; }) },
        yAxis: { type: "value" },
        series: [{ type: "bar", name: val, itemStyle: { color: "#1f4e79" },
                   data: rows.map(function (r) { return Number(r[val]); }) }],
      });
    }
    // Draw after layout so ECharts reads the container's real size.
    if (document.readyState === "complete") requestAnimationFrame(draw);
    else window.addEventListener("load", function () { requestAnimationFrame(draw); });
  })();

  var thead = table.querySelector("thead");
  var htr = document.createElement("tr");
  cols.forEach(function (c) {
    var th = document.createElement("th");
    th.textContent = c;
    htr.appendChild(th);
  });
  thead.appendChild(htr);
  var tbody = table.querySelector("tbody");
  rows.forEach(function (row) {
    var tr = document.createElement("tr");
    cols.forEach(function (c) {
      var td = document.createElement("td");
      var v = row[c];
      if (v !== "" && v != null && !isNaN(Number(v))) {
        td.className = "num";
        td.textContent = Number(v).toLocaleString();
      } else {
        td.textContent = v == null ? "" : String(v);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
})();
"""


def cmd_new_report(args: argparse.Namespace) -> int:
    """
    Scaffold a freeform report package under ``reports/<name>/``.

    Four starter files — ``report.json`` (a data binding), ``template.html``,
    ``style.css``, ``script.js`` — that render a titled page with a table out of
    the box against the first model in ``models/``. A directory holding
    ``report.json`` + ``template.html`` is discovered as a report (architecture
    §7) and built with ``tracebi report build <name>``.
    """
    reports_dir: Path = args.reports_dir
    slug = _slugify(args.title)
    pkg_dir = reports_dir / slug
    if pkg_dir.exists() and not args.force:
        print(f"refusing to overwrite existing {pkg_dir}; pass --force to replace",
              file=sys.stderr)
        return 1
    pkg_dir.mkdir(parents=True, exist_ok=True)

    model, query, note = _scaffold_binding()
    (pkg_dir / "report.json").write_text(
        _report_json_text(args.title, model, query), encoding="utf-8")
    (pkg_dir / "template.html").write_text(
        _REPORT_TEMPLATE_HTML.replace("{{ title }}", args.title), encoding="utf-8")
    (pkg_dir / "style.css").write_text(_REPORT_STYLE_CSS, encoding="utf-8")
    (pkg_dir / "script.js").write_text(_REPORT_SCRIPT_JS, encoding="utf-8")

    print(f"Created {pkg_dir}/ (report.json, template.html, style.css, script.js)")
    if note:
        print(f"  {note}")
    else:
        print(f"  Bound to model '{model}'. Build it with:")
        print(f"    tracebi report build {slug}")
    return 0


def _resolve_report_target(name: str, reports_dir: Path) -> tuple[str, Path]:
    """Resolve *name* to a package directory or a spec file under ``reports/``.

    Looks for a ``reports/<name>/`` package first, then a ``reports/<name>.json``
    spec. Returns ``("package"|"spec", path)`` or raises ``FileNotFoundError``
    listing where it looked. All report forms live in one ``reports/`` folder.
    """
    pkg_dir = reports_dir / name
    if (pkg_dir / "report.json").is_file() and (pkg_dir / "template.html").is_file():
        return "package", pkg_dir
    spec_path = reports_dir / f"{name}.json"
    if spec_path.is_file():
        return "spec", spec_path
    raise FileNotFoundError(
        f"No report '{name}' found. Looked for a package or spec at:\n  "
        + "\n  ".join([str(pkg_dir), str(spec_path)])
    )


def _report_status(kind: str, path: Path, as_json: bool = False) -> int:
    """The earned state of an artifact, from the one workbench state builder.

    What a driving agent and CI call between edits: figures by provenance,
    coverage, unused bindings, pins — printed compact, or as the full state
    JSON with --json.
    """
    if kind != "package":
        print("status applies to artifact packages (reports/<name>/); "
              "verify a spec's receipt with `tracebi verify` instead.",
              file=sys.stderr)
        return 1
    from tracebi.workbench import collect_state

    state = collect_state(str(path), _load_project_models())
    if as_json:
        print(json.dumps(state, indent=2, default=str))
        return 0
    cov = state.get("coverage", {})
    parts = [f"{cov.get('verified', 0)} query-backed",
             f"{cov.get('derived', 0)} python-derived",
             f"{cov.get('unverified', 0)} unverified"]
    if cov.get("unbound_errors"):
        parts.append(f"{cov['unbound_errors']} unbound-ERROR")
    print(f"{state.get('name', path.name)}: {cov.get('total', 0)} figure(s) — "
          + ", ".join(parts))
    for f in state.get("figures", []):
        mark = {"verified": "✓", "derived": "·", "unverified": "·"}.get(
            f.get("provenance"), "✗")
        pin = " 📌" if f.get("pinned") else ""
        print(f"  {mark} {f.get('id')}  [{f.get('provenance')}]"
              f"{'  ← ' + f['binding'] if f.get('binding') else ''}{pin}")
    unused = state.get("unused_bindings") or []
    if unused:
        print(f"  ! unused binding(s): {', '.join(unused)}")
    errs = [b for b in state.get("bindings", []) if b.get("error")]
    for b in errs:
        print(f"  ✗ binding '{b['name']}' failed: {b['error']}", file=sys.stderr)
    return 1 if (cov.get("unbound_errors") or errs) else 0


def _snapshot_report_target(kind: str, path: Path, output: Path) -> int:
    """Write a review snapshot — the sendable working state (v2 §2.5).

    Packages only: a spec has no exploration blocks or code to review.
    The snapshot carries NO manifest, on purpose — a weaker-looking receipt
    is worse than none — and ``verify`` refuses the file by name.
    """
    if kind != "package":
        print("snapshot applies to artifact packages (reports/<name>/); "
              "a spec has no exploration state to snapshot — use build.",
              file=sys.stderr)
        return 1
    from tracebi.reports.template_package import TemplatePackage

    models = _load_project_models()
    TemplatePackage(str(path)).snapshot(models, str(output))
    print(f"Snapshot → {output}")
    print("  review copy: exploration blocks kept, code appendix attached, "
          "NO manifest — `tracebi verify` will refuse it by name.")
    return 0


def _build_report_target(kind: str, path: Path, output: Path,
                         theme: Optional[str] = None,
                         badges: bool = True) -> Path:
    """Render one report target to *output* (+ a sibling manifest). Returns output."""
    output.parent.mkdir(parents=True, exist_ok=True)
    models = _load_project_models()
    if kind == "package":
        from tracebi.reports.template_package import TemplatePackage
        TemplatePackage(str(path)).render(models, str(output), badges=badges)
    else:
        from tracebi.reports.html_renderer import HTMLRenderer
        from tracebi.spec import ReportSpec
        spec = ReportSpec.from_json(path.read_text(encoding="utf-8"))
        report = spec.build(models)
        HTMLRenderer.for_project(
            report_css=_report_theme_css(spec, extra_theme=theme),
            report_js=_report_script_js(spec),
        ).render(report, str(output), save_manifest=True)
    return output


def _report_theme_css(spec, extra_theme: Optional[str] = None) -> str:
    """The spec's theme CSS (plus a --theme override file), resolved against
    the reports directory. Later layers win, so the flag stacks last."""
    parts = []
    for name in (getattr(spec, "theme", ""), extra_theme or ""):
        if not name:
            continue
        p = Path(name)
        if not p.is_file():
            p = _default_reports_dir() / name
        if not p.is_file():
            raise FileNotFoundError(
                f"theme file not found: {name} (looked in cwd and "
                f"{_default_reports_dir()})"
            )
        parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _report_script_js(spec) -> str:
    """The spec's script file, resolved against the reports directory."""
    name = getattr(spec, "script", "")
    if not name:
        return ""
    p = Path(name)
    if not p.is_file():
        p = _default_reports_dir() / name
    if not p.is_file():
        raise FileNotFoundError(
            f"script file not found: {name} (looked in cwd and "
            f"{_default_reports_dir()})"
        )
    return p.read_text(encoding="utf-8")


def _serve_file(html_path: Path, name: str, port: int, open_browser: bool) -> None:
    """Serve *html_path*'s directory over HTTP, as ``HTMLRenderer.serve`` does.

    The freeform ``.html`` is already built and self-contained, so preview
    serves that artifact statically rather than re-rendering it — the built-in
    renderers never touch the analyst's ``template.html``.
    """
    import http.server
    import threading
    import webbrowser

    directory = str(html_path.parent.resolve())
    url = f"http://localhost:{port}/{html_path.name}"

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)

        def log_message(self, fmt, *a):  # silence request logs
            pass

    server = http.server.HTTPServer(("", port), _Handler)
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    print(f"\n  TraceBi Report — '{name}'")
    print(f"  Serving at {url}")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
    finally:
        server.server_close()


def cmd_report(args: argparse.Namespace) -> int:
    """
    Build, preview, or snapshot a report — the build step (architecture §2).

        tracebi report build <name>      # → output/<name>.html + manifest
        tracebi report preview <name>    # build, then serve it locally
        tracebi report snapshot <name>   # review snapshot — NO manifest

    A report is a package (``reports/<name>/``) or a spec
    (``reports/<name>.json``). Output defaults to ``output/<name>.html`` —
    self-contained, offline, and checkable with ``tracebi verify --file``.
    A snapshot keeps the exploration blocks, banners itself, appends a
    read-only code appendix, and writes NO manifest: it is the sendable
    working state, and ``verify`` refuses it by name.
    """
    reports_dir: Path = args.reports_dir
    try:
        kind, path = _resolve_report_target(args.name, reports_dir)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.action == "status":
        return _report_status(kind, path, as_json=getattr(args, "json", False))
    if args.action == "snapshot":
        output = (Path(args.output) if args.output
                  else Path.cwd() / "output" / f"{args.name}.snapshot.html")
        return _snapshot_report_target(kind, path, output)
    output = Path(args.output) if args.output else Path.cwd() / "output" / f"{args.name}.html"
    try:
        _build_report_target(kind, path, output,
                             theme=getattr(args, 'theme', None),
                             badges=not getattr(args, 'no_badges', False))
    except Exception as exc:  # noqa: BLE001 — a build failure is the user's to fix
        print(f"failed to build report '{args.name}': "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    manifest = output.with_name(output.name + ".manifest.json")
    print(f"Rendered {args.name} ({kind}) → {output}")
    print(f"  manifest → {manifest}")

    if args.action == "preview":
        _serve_file(output, args.name, args.port, not args.no_browser)
    return 0


# ── Workbench sessions: export / clear ──────────────────────────────────────

def cmd_session(args: argparse.Namespace) -> int:
    """
    Save or reset a workbench session feed.

        tracebi session export [name]    # → explorations/<date>-<name>.html
        tracebi session clear [name]     # remove the feed and pins

    *name* defaults to the discovery session (``_discovery``); a package
    name addresses that package's session. The export is an exploration
    RECORD — the full feed, uncapped, as one self-contained lab-notebook
    HTML with NO manifest; ``tracebi verify`` refuses it by name. ``clear``
    is prompt-free, but refuses while a dev server's heartbeat for the
    session is fresh — the live watcher would keep posting over the reset.
    """
    import time

    from tracebi.workbench import (
        ACTIVE_FILE, DISCOVERY_NAME, EXHIBITS_FILE, HEARTBEAT_WINDOW,
        PINS_FILE,
    )

    name = args.name or DISCOVERY_NAME
    wb = os.path.join(os.getcwd(), ".tracebi", "workbench", name)

    if args.action == "export":
        from datetime import datetime

        from tracebi._session_export import export_session

        ext = "md" if getattr(args, "format", "html") == "md" else "html"
        out = Path(args.output) if args.output else (
            Path("explorations") / f"{datetime.now():%Y-%m-%d}-{name}.{ext}")
        try:
            export_session(wb, str(out), title=args.title)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"Exported session '{name}' → {out}")
        print("  An exploration record — commit it; verify refuses it "
              "by name.")
        return 0

    # clear
    try:
        age = time.time() - os.path.getmtime(os.path.join(wb, ACTIVE_FILE))
    except OSError:
        age = None
    if age is not None and age <= HEARTBEAT_WINDOW:
        print(f"session '{name}' has a live dev server (fresh heartbeat) — "
              f"stop the server first, then clear.", file=sys.stderr)
        return 1
    removed = [fname for fname in (EXHIBITS_FILE, PINS_FILE)
               if os.path.isfile(os.path.join(wb, fname))]
    for fname in removed:
        os.remove(os.path.join(wb, fname))
    if removed:
        print(f"Cleared session '{name}' ({', '.join(removed)}).")
    else:
        print(f"Session '{name}' has no feed or pins to clear.")
    return 0


# ── Argparse wiring ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracebi",
        description=("TraceBi — the trust layer for AI-generated analytics: "
                     "a code-first BI framework where every number has a receipt."),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tracebi {_tracebi_version()}",
    )
    parser.add_argument(
        "--requests-dir",
        type=Path,
        default=_default_requests_dir(),
        help="Directory holding request scripts (default: ./requests).",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=_default_models_dir(),
        help="Directory holding model definitions (default: ./models).",
    )
    parser.add_argument(
        "--pipelines-dir",
        type=Path,
        default=_default_pipelines_dir(),
        help="Directory holding pipeline definitions (default: ./pipelines).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser(
        "init",
        help="Scaffold a complete three-phase project (inputs/, transforms/, "
             "models/, reports/, …) whose sample loop ends in "
             "`tracebi verify` reading REPRODUCES.",
    )
    p_init.add_argument("project", help="Target directory name.")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing files.")
    p_init.set_defaults(func=cmd_init)

    p_new = sub.add_parser(
        "new-request",
        help="Scaffold a new request script. DEPRECATED (removed in 0.8): "
             "use `tracebi new-report` — the artifact package is the one "
             "report lane.",
    )
    p_new.add_argument("title", help='Free-form title, e.g. "Open orders by region".')
    p_new.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new.add_argument(
        "--notebook", action="store_true",
        help="Scaffold a Jupyter notebook (.ipynb) instead of a .py script.",
    )
    p_new.set_defaults(func=cmd_new_request)

    p_list = sub.add_parser("list-requests", help="List request scripts.")
    p_list.set_defaults(func=cmd_list_requests)

    p_run = sub.add_parser(
        "run",
        help="Run a request script (.py or .ipynb). DEPRECATED (removed in "
             "0.8) with the requests/ lane it runs.",
    )
    p_run.add_argument("name", help="Request file name (suffix optional; tries .py then .ipynb).")
    p_run.add_argument(
        "--param", action="append", metavar="KEY=VALUE",
        help="Override a request_params() default (repeatable), "
             "e.g. --param period=2026-Q1",
    )
    p_run.set_defaults(func=cmd_run)

    p_spec = sub.add_parser(
        "spec",
        help="Work with report specs (a report as JSON): print the schema, "
             "validate a spec without running it, or render one.",
    )
    p_spec.add_argument("action", choices=["schema", "validate", "render"])
    p_spec.add_argument(
        "--theme",
        help="Extra CSS file stacked over the spec's own theme (later wins).",
    )
    p_spec.add_argument("file", nargs="?", help="Path to a spec .json file.")
    p_spec.add_argument("--output", help="Output path for `render`.")
    p_spec.set_defaults(func=cmd_spec)

    p_context = sub.add_parser(
        "context",
        help="Print the framework's vocabulary as JSON (section and panel "
             "types, DataSet verbs, measures, operators, conventions).",
    )
    p_context.add_argument("--model", help="Also include this model's schema.")
    p_context.add_argument(
        "--brief", action="store_true",
        help="The token-lean tier (~40%% of the payload): semantic model, "
             "figure grammar, contracts, conventions — everything the "
             "package-first loop needs. Omits the legacy section classes, "
             "DataSet verbs, and Python cheat sheets.",
    )
    p_context.add_argument("--compact", action="store_true",
                           help="Single-line JSON.")
    p_context.set_defaults(func=cmd_context)

    p_serve = sub.add_parser(
        "serve",
        help="Serve this project's web UI (models, reports, pipelines, "
             "requests) at http://127.0.0.1:8000.",
    )
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true",
                         help="Restart on file changes (development).")
    p_serve.set_defaults(func=cmd_serve)

    p_dev = sub.add_parser(
        "dev",
        help="Live-preview a report while you edit it. An artifact package "
             "(reports/<name>/) gets the in-memory exploration render plus "
             "the workbench at /__workbench; with no name, DISCOVERY MODE "
             "serves the project-level workbench (warehouse tables, sink "
             "contracts, models, packages, exhibit feed) — the live surface "
             "before any report exists; a request script keeps the legacy "
             "single-file loop (deprecated; removed in 0.8).",
    )
    p_dev.add_argument("name", nargs="?",
                       help="Package name under reports/, or a request file "
                            "name (suffix optional). Omit for discovery "
                            "mode: the project-level workbench.")
    p_dev.add_argument("--port", type=int, default=8001,
                       help="Port for the preview server (default 8001).")
    p_dev.add_argument("--no-browser", action="store_true",
                       help="Do not open the browser automatically.")
    p_dev.set_defaults(func=cmd_dev)

    p_validate = sub.add_parser(
        "validate",
        help="Sanity-check the project: layout, plus load every model in "
             "models/ and verify its dimension keys are unique.",
    )
    p_validate.set_defaults(func=cmd_validate)

    p_new_model = sub.add_parser("new-model", help="Scaffold a new model definition.")
    p_new_model.add_argument("title", help='Free-form title, e.g. "Sales Model".')
    p_new_model.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new_model.set_defaults(func=cmd_new_model)

    p_list_models = sub.add_parser("list-models", help="List model definition files.")
    p_list_models.set_defaults(func=cmd_list_models)

    p_new_pipeline = sub.add_parser("new-pipeline", help="Scaffold a new pipeline definition.")
    p_new_pipeline.add_argument("title", help='Free-form title, e.g. "Sales Pipeline".')
    p_new_pipeline.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new_pipeline.set_defaults(func=cmd_new_pipeline)

    p_new_transform = sub.add_parser(
        "new-transform",
        help="Scaffold a phase-① transform (transforms/<name>.py): pandas "
             "that reads a raw input and sinks star tables to the warehouse.",
    )
    p_new_transform.add_argument("title", help='Free-form title, e.g. "Orders Clean".')
    p_new_transform.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new_transform.add_argument(
        "--transforms-dir", type=Path, default=_default_transforms_dir(),
        help="Directory holding transforms (default: ./transforms).",
    )
    p_new_transform.set_defaults(func=cmd_new_transform)

    p_list_pipelines = sub.add_parser("list-pipelines", help="List pipeline definition files.")
    p_list_pipelines.set_defaults(func=cmd_list_pipelines)

    p_new_report = sub.add_parser(
        "new-report",
        help="Scaffold a freeform report package (reports/<name>/): report.json "
             "+ template.html + style.css + script.js.",
    )
    p_new_report.add_argument("title", help='Free-form title, e.g. "Portfolio Book".')
    p_new_report.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new_report.add_argument("--reports-dir", type=Path, default=_default_reports_dir(),
                              help="Directory holding report packages (default: ./reports).")
    p_new_report.set_defaults(func=cmd_new_report)

    p_report = sub.add_parser(
        "report",
        help="Build a report package or spec to one self-contained .html + "
             "manifest, or preview it locally.",
    )
    p_report.add_argument("action", choices=["build", "preview", "snapshot", "status"])
    p_report.add_argument("name", help="Report name (package dir or spec stem).")
    p_report.add_argument("--output", help="Output .html path (default: output/<name>.html).")
    p_report.add_argument(
        "--json", action="store_true",
        help="With `status`: print the full workbench state as JSON (what "
             "the workbench page and the MCP workbench_state tool consume).",
    )
    p_report.add_argument(
        "--no-badges", action="store_true",
        help="Omit the provenance badges from the rendered page (client "
             "deliverables). The manifest is unaffected.",
    )
    p_report.add_argument(
        "--theme",
        help="Extra CSS file stacked over the spec's own theme (later wins). "
             "Spec targets only; packages carry their own style.css.",
    )
    p_report.add_argument("--reports-dir", type=Path, default=_default_reports_dir(),
                          help="Directory holding report packages (default: ./reports).")
    p_report.add_argument("--port", type=int, default=8080,
                          help="Port for `preview` (default 8080).")
    p_report.add_argument("--no-browser", action="store_true",
                          help="With `preview`, do not open the browser.")
    p_report.set_defaults(func=cmd_report)

    p_session = sub.add_parser(
        "session",
        help="Save or reset a workbench session feed. `session export "
             "[name]` renders the FULL feed (uncapped) to one exploration-"
             "record HTML — a lab notebook, not a report: no manifest, and "
             "`tracebi verify` refuses it by name. `session clear [name]` "
             "removes the feed and pins (refused while a dev server's "
             "heartbeat is fresh). Name defaults to the discovery session.",
    )
    p_session.add_argument("action", choices=["export", "clear"])
    p_session.add_argument(
        "name", nargs="?", default=None,
        help="Session name: a package name, or omit for the discovery "
             "session (_discovery).",
    )
    p_session.add_argument(
        "-o", "--output",
        help="Output .html path for `export` "
             "(default: explorations/<YYYY-MM-DD>-<name>.html).",
    )
    p_session.add_argument(
        "--title",
        help="Page title (default: '<session> — exploration record').",
    )
    p_session.add_argument(
        "--format", choices=["html", "md"], default="html",
        help="Export format: self-contained HTML (default; charts render, "
             "verify refuses it by name) or the Markdown twin — the "
             "git-review format: raw markdown notes verbatim, tables for "
             "frames and sketches, made for reading in a pull request. An "
             "explicit -o extension (.md/.html) also selects the format.",
    )
    p_session.set_defaults(func=cmd_session)

    p_migrate = sub.add_parser(
        "migrate",
        help="Migrate legacy report forms to the artifact package. "
             "`migrate spec <file.json>` compiles a JSON spec into "
             "reports/<stem>/ (report.json bindings + template.html of "
             "default-component figures) alongside the original.",
    )
    p_migrate.add_argument("what", choices=["spec"])
    p_migrate.add_argument("path", help="Path to a reports/<name>.json spec.")
    p_migrate.add_argument("--force", action="store_true",
                           help="Overwrite an existing target directory.")
    p_migrate.set_defaults(func=cmd_migrate)

    p_run_pipeline = sub.add_parser(
        "run-pipeline",
        help="Run a pipeline's layers (the execution plane — no web server needed).",
    )
    p_run_pipeline.add_argument("name", help="Pipeline name, as listed by list-pipelines.")
    p_run_pipeline.add_argument(
        "--layer",
        help="Run only this layer instead of the whole pipeline.",
    )
    p_run_pipeline.add_argument(
        "--refresh", action="store_true",
        help="With --layer, run its upstream chain first.",
    )
    p_run_pipeline.add_argument(
        "--status", action="store_true",
        help="Show each layer and its last run without executing anything.",
    )
    p_run_pipeline.set_defaults(func=cmd_run_pipeline)

    p_mcp = sub.add_parser(
        "mcp",
        help="Serve the agent gateway over the Model Context Protocol.",
    )
    p_mcp.add_argument(
        "--transport", choices=("stdio", "http"), default="stdio",
        help="stdio for a local agent (default); http for a remote one.",
    )
    p_mcp.add_argument(
        "--port", type=int, default=8765,
        help="Port for --transport http (default 8765).",
    )
    p_mcp.add_argument(
        "--insecure", action="store_true",
        help="Serve --transport http without authentication. Deliberate "
             "opt-out: without it, http requires TRACEBI_MCP_TOKEN.",
    )
    p_mcp.set_defaults(func=cmd_mcp)

    p_verify = sub.add_parser(
        "verify",
        help="Re-run every recorded query in a rendered manifest and "
             "classify each section: reproduces, source drift, model changed, "
             "unexplained, or unverifiable. Exits 0 only when something was actually "
             "checked and nothing failed.",
    )
    p_verify.add_argument(
        "manifest", nargs="?", default=None,
        help="Path to a *.manifest.json file (query → model check). "
             "Omit when using --file.",
    )
    # A wholly separate offline check: the shipped .html's embedded bytes vs
    # the manifest (architecture §3.2). Kept apart from the positional so
    # neither can be mistaken for the other.
    p_verify.add_argument(
        "--strict", action="store_true",
        help="Fail unless every FIGURE in a schema-2 manifest reproduces — "
             "the CI gate for a finalized report.",
    )
    p_verify.add_argument(
        "--file", dest="verify_file", default=None,
        help="Path to a self-contained report *.html*; rehash its embedded "
             "data against a sibling <file>.manifest.json (no model needed).",
    )
    p_verify.add_argument(
        "--contracts", action="store_true",
        help="Also re-run the warehouse's recorded sink contracts against "
             "the current warehouse. A separate claim, reported separately: "
             "it says whether today's sink still satisfies its declared "
             "contract — never that the transform was verified.",
    )
    p_verify.add_argument(
        "--manifest", dest="file_manifest", default=None,
        help="With --file: the manifest to check against, if it is not the "
             "sibling <file>.manifest.json.",
    )
    # Distinct dest: a subparser option sharing dest with a main-parser
    # option would clobber an already-parsed `tracebi --models-dir X verify`.
    p_verify.add_argument(
        "--models-dir", type=Path, default=None, dest="verify_models_dir",
        help="Directory holding model definitions (default: ./models).",
    )
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
