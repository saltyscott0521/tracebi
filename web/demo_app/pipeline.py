"""
Medallion pipeline for the demo app.

Runs Landing → Manipulation → Final at module import time so the Pipelines
page in the UI has live run history immediately. Exports `runner` and
`pipeline_model` for use by the medallion_revenue report.
"""

import os
import tempfile

from sqlalchemy import create_engine

from tracebi import (
    DataModel, SQLConnector,
    LandingLayer, ManipulationLayer, FinalLayer,
    PipelineRunner,
)
from tracebi.model_registry import get_model

# Seed the pipeline from the shared SalesModel's source tables.
_sales = get_model("sales_model")
orders_df = _sales.load("orders").to_pandas()
customers_df = _sales.load("customers").to_pandas()

# Source data — orders with customer_id FK, customers with segment rename
_orders_raw = orders_df.assign(
    customer_id=[1, 2, 3, 4, 1, 3, 2, 4, 1, 3]
)[["order_id", "customer_id", "product", "qty", "revenue", "cost", "status"]]

_customers_raw = customers_df.rename(columns={"tier": "segment"})

# SQLite DB for pipeline persistence.
#
# This used to be hardcoded to the repo's data/ directory, which is why the
# Vercel entry point had to skip this whole app module: a serverless
# deployment mounts its own code read-only, so the makedirs/to_sql below
# raised at import and took the demo reports and connectors down with it.
# Hence a production site with an empty Reports, Connectors and Pipelines
# page. Set TRACEBI_DEMO_DB_DIR to place it explicitly; otherwise fall back
# to the system temp dir when the checkout is not writable, so the demo
# comes up anywhere without needing configuration.
#
# On serverless, temp is per-invocation, so run history does not survive
# between requests — the pipeline is still runnable and inspectable, which
# is what the demo needs.
_DB_DIR = os.environ.get("TRACEBI_DEMO_DB_DIR") or os.path.join(
    os.path.dirname(__file__), "..", "..", "data"
)
try:
    os.makedirs(_DB_DIR, exist_ok=True)
    _probe = os.path.join(_DB_DIR, ".write-probe")
    with open(_probe, "w") as fh:
        fh.write("")
    os.remove(_probe)
except OSError:
    _DB_DIR = tempfile.gettempdir()

_DB_URL = f"sqlite:///{os.path.join(_DB_DIR, 'demo.db')}"

_orders_raw.to_sql("orders_raw",     con=create_engine(_DB_URL), if_exists="replace", index=False)
_customers_raw.to_sql("customers_raw", con=create_engine(_DB_URL), if_exists="replace", index=False)

db = SQLConnector("demo_db", url=_DB_URL)

# Landing — raw ingest
_orders_landing = LandingLayer(
    connector=db, source="orders_raw", description="Raw orders",
    sink=db, sink_table="orders_bronze",
)
_customers_landing = LandingLayer(
    connector=db, source="customers_raw", description="Raw customers",
    sink=db, sink_table="customers_bronze",
)

# Manipulation — light cleaning
_orders_manip = (
    ManipulationLayer(source=db, source_table="orders_bronze", sink=db, sink_table="orders_silver")
    .drop_nulls(subset=["order_id", "customer_id"])
    .deduplicate(subset=["order_id"])
)
_customers_manip = (
    ManipulationLayer(source=db, source_table="customers_bronze", sink=db, sink_table="customers_silver")
    .drop_nulls()
    .deduplicate(subset=["customer_id"])
)

# DataModel reading from silver tables — star-schema query surface
pipeline_model = DataModel("SalesPipelineModel")
pipeline_model.add_connector(db)
pipeline_model.add_table("orders_silver",    connector="demo_db", source="orders_silver")
pipeline_model.add_table("customers_silver", connector="demo_db", source="customers_silver")
pipeline_model.add_dimension(
    name="dim_customer",
    table_name="customers_silver",
    key_col="customer_id",
    attributes=["region", "segment"],
)
pipeline_model.add_fact(
    name="fact_orders",
    table_name="orders_silver",
    measures=["revenue", "qty", "cost"],
    foreign_keys={"dim_customer": "customer_id"},
)

# Final / serving layers
_final_by_region = FinalLayer(
    model=pipeline_model, fact="fact_orders",
    measures={"revenue": "sum", "qty": "sum", "cost": "sum"},
    dimensions=["dim_customer.region"],
    sink=db, sink_table="gold_revenue_by_region",
)
_final_by_segment = FinalLayer(
    model=pipeline_model, fact="fact_orders",
    measures={"revenue": "sum", "order_id": "count"},
    dimensions=["dim_customer.segment"],
    filters={"status": "shipped"},
    sink=db, sink_table="gold_revenue_by_segment",
)

# PipelineRunner
runner = PipelineRunner(db_url=_DB_URL)
runner.register(_orders_landing,    name="orders_bronze",     schedule="0 * * * *")
runner.register(_customers_landing, name="customers_bronze",  schedule="0 * * * *")
runner.register(_orders_manip,      name="orders_silver",     schedule="15 * * * *",
                depends_on="orders_bronze")
runner.register(_customers_manip,   name="customers_silver",  schedule="15 * * * *",
                depends_on="customers_bronze")
runner.register(_final_by_region,   name="revenue_by_region", schedule="30 6 * * *",
                depends_on="orders_silver")
runner.register(_final_by_segment,  name="revenue_by_segment", schedule="30 6 * * *",
                depends_on="orders_silver")

# Run full pipeline once at startup so the UI has live data immediately
runner.run("orders_bronze")
runner.run("customers_bronze")
runner.run("orders_silver")
runner.run("customers_silver")
runner.run("revenue_by_region")
runner.run("revenue_by_segment")
