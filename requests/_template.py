"""
TraceBi Request Template
========================
Copy this file into requests/ and rename it (e.g. weekly_sales.py).
Fill in each section below.

Run with:
    python requests/weekly_sales.py
    # or, if the web server has registered a shared DataModel:
    tracebi run weekly_sales

Or scaffold a brand-new request with:
    tracebi new-request "Weekly Sales"            # .py
    tracebi new-request "Weekly Sales" --notebook # .ipynb
"""

import os
from tracebi import request_params
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer


# ── 0. Parameters ─────────────────────────────────────────────────────────────
# Declare defaults here; override at run time with
#   tracebi run my_report --param period="Q3 2024"
# or from the parameter form on the web UI's Requests page.

params = request_params(period="Q2 2024")


# ── 1. Get the project DataModel ─────────────────────────────────────────────
# Prefer the shared model registered by the web app (via
# ``registry.add_model(model, default=True)``). Fall back to building a
# local one when running the script standalone outside the web server.

try:
    from tracebi.web import register
    model = register.get_default_model()
except ImportError:
    model = None

if model is None:
    from tracebi import DataModel, MemoryConnector  # noqa: F401
    # Example local model — uncomment and adapt:
    # model = DataModel("MyModel")
    # model.add_connector(MemoryConnector("mem", tables={"orders": orders_df}))
    # model.add_table("orders", connector="mem", source="orders")
    pass


# ── 2. Build DataSets ─────────────────────────────────────────────────────────
# Load and transform via the model — every step appends a LineageNode.
#
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
    .parameter("period", params["period"])

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
