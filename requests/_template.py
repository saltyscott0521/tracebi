"""
TraceBi Request Template
========================
Copy this file into requests/ and rename it (e.g. weekly_sales.py).
Fill in each section below.

Run with:
    python requests/weekly_sales.py

Or scaffold a brand-new request with:
    tracebi new-request "Weekly Sales"
"""

import os
import pandas as pd
from tracebi import (
    DataModel, MemoryConnector, CSVConnector, DuckDBConnector,
    DataSet, LineageNode,
)
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer
# from tracebi import LandingLayer, ManipulationLayer, FinalLayer
# from tracebi.lineage.diagram import LineageDiagram


# ── 1. Connect ────────────────────────────────────────────────────────────────
# Register connectors and build a DataModel.
#
# Connectors all share the same load(source, filter=None, columns=None)
# contract — pass filter/columns to push predicates down to the source
# when possible (SQL WHERE, DuckDB, BigQuery).

model = DataModel("MyModel")

# Example: in-memory connector for quick demos
# connector = MemoryConnector("mem", tables={"orders": orders_df})
# model.add_connector(connector)
# model.add_table("orders", connector="mem", source="orders")

# Example: CSV files
# model.add_connector(CSVConnector("files", directory="data/"))
# model.add_table("orders", connector="files", source="orders.csv")

# Example: DuckDB over a Parquet file
# model.add_connector(DuckDBConnector("warehouse", directory="data/"))
# model.add_table("orders", connector="warehouse", source="orders.parquet")

# Example: SQL database
# from tracebi import SQLConnector
# model.add_connector(SQLConnector("db", url="sqlite:///sales.db"))
# model.add_table("orders", connector="db", source="orders")


# ── 2. Build DataSets ─────────────────────────────────────────────────────────
# Load and transform data using the fluent DataSet API.
# Each operation appends a LineageNode — no data is mutated in place.

# orders_ds = (
#     model.load("orders", filter={"status": "shipped"})  # pushed down to source
#     .transform(
#         lambda df: df.assign(margin=df["revenue"] - df["cost"]),
#         description="Calculated margin",
#     )
#     .sort("margin", ascending=False)
# )


# ── 3. Build Report ───────────────────────────────────────────────────────────

report = (
    Report("My Report Title")
    .author("Your Name")
    .description("Short description of this report.")
    .parameter("period", "Q2 2024")

    .add(TextSection(title="Executive Summary", content="Executive Summary", style="heading1"))
    .add(TextSection(content="Write your narrative here.", style="normal"))
    .spacer()

    # .add(ChartSection(
    #     title="Revenue Trend",
    #     dataset=trend_ds,
    #     chart_type="line",
    #     x="month",
    #     y="revenue",
    #     ylabel="Revenue (USD)",
    # ))

    # .add(TableSection(
    #     title="Order Detail",
    #     dataset=orders_ds,
    #     columns=["region", "product", "revenue"],
    #     totals=["revenue"],
    # ))
)

report.describe()


# ── 4. Render ─────────────────────────────────────────────────────────────────

def run():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)

    xlsx_path = os.path.join(output_dir, "my_report.xlsx")
    html_path = os.path.join(output_dir, "my_report.html")

    ExcelRenderer().render(report, xlsx_path)
    print(f"Excel saved: {xlsx_path}")

    HTMLRenderer().render(report, html_path)
    print(f"HTML saved:  {html_path}")


def serve(port: int = 8080):
    """Render and open the report in a local browser."""
    HTMLRenderer().serve(report, port=port)


# ── 5. Optional: register with the web UI ─────────────────────────────────────
# If this file is auto-discovered by the web server, expose it as a report.

try:
    from tracebi.web import register

    @register.report("my_report", description="Short description of this report.")
    def _factory():
        return report
except ImportError:
    pass


if __name__ == "__main__":
    run()
