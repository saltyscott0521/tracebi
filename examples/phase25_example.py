"""
TraceBi — Phase 2.5 Example
============================
Demonstrates:
  - Medallion architecture  (BronzeLayer → SilverLayer → GoldLayer)
  - Star schema queries      (StarSchema with dot-notation dimensions)
  - Lineage diagrams         (LineageDiagram → show / to_html / to_mermaid)

No external files or databases needed — uses MemoryConnector.

Run with:
    python examples/phase25_example.py

Or in Jupyter:
    from examples.phase25_example import run
    run()
"""

import os
import pandas as pd

from tracebi import DataModel, MemoryConnector
from tracebi import BronzeLayer, SilverLayer, GoldLayer
from tracebi.model.star_schema import StarSchema
from tracebi.lineage.diagram import LineageDiagram


# ── Sample source data ────────────────────────────────────────────────────────

orders_raw = pd.DataFrame({
    "order_id":    [1, 2, 3, 4, 5, 6, 5],          # row 6 is a duplicate
    "customer_id": [101, 102, 101, 103, 102, 104, 102],
    "product":     ["Widget A", "Widget B", "Gadget X", "Widget A",
                    "Gadget X", "Widget B", "Gadget X"],
    "qty":         ["120", "85", "200", "60", "95", "150", "95"],  # strings
    "revenue":     [3598.80, 4249.15, 19998.00, 1799.40, 9499.05, 14998.50, 9499.05],
    "status":      ["shipped", "shipped", "open", "shipped", "open", "shipped", "open"],
    "order_date":  ["2024-01-15", "2024-02-20", "2024-03-05", "2024-04-10",
                    "2024-05-01", "2024-06-12", "2024-05-01"],
})

customers_raw = pd.DataFrame({
    "customer_id": [101, 102, 103, 104],
    "name":        ["Alice", "Bob", "Carol", "Dave"],
    "region":      ["North East", "Midwest", "South East", "West"],
    "segment":     ["Enterprise", "SMB", "SMB", "Enterprise"],
})


# ── DataModel ─────────────────────────────────────────────────────────────────

connector = MemoryConnector("mem", tables={
    "orders_raw":    orders_raw,
    "customers_raw": customers_raw,
})

model = DataModel("SalesModel")
model.add_connector(connector)
model.add_table("orders_raw",    connector="mem", source="orders_raw")
model.add_table("customers_raw", connector="mem", source="customers_raw")


def run():
    print("\n" + "=" * 60)
    print("  Phase 2.5 — Medallion Architecture + Star Schema")
    print("=" * 60)

    # ── Bronze ───────────────────────────────────────────────────
    print("\n[1] Bronze — raw ingest")

    orders_bronze = BronzeLayer(
        connector=connector,
        source="orders_raw",
        description="Raw orders from source system",
    ).load(name="orders_bronze")

    customers_bronze = BronzeLayer(
        connector=connector,
        source="customers_raw",
        description="Raw customer records",
    ).load(name="customers_bronze")

    print(f"  orders_bronze:    {orders_bronze.shape}")
    print(f"  customers_bronze: {customers_bronze.shape}")

    # ── Silver ───────────────────────────────────────────────────
    print("\n[2] Silver — clean")

    orders_silver = (
        SilverLayer()
        .cast({"qty": "int64", "order_date": "datetime64[ns]"})
        .drop_nulls(subset=["order_id", "customer_id"])
        .deduplicate(subset=["order_id"])
    ).apply(orders_bronze, name="orders_silver")

    customers_silver = (
        SilverLayer()
        .drop_nulls()
        .deduplicate(subset=["customer_id"])
    ).apply(customers_bronze, name="customers_silver")

    print(f"  orders_silver:    {orders_silver.shape}  "
          f"(was {orders_bronze.shape[0]} rows before dedup)")
    print(f"  customers_silver: {customers_silver.shape}")

    orders_silver.print_lineage()

    # ── Star Schema ──────────────────────────────────────────────
    print("\n[3] Star Schema setup")

    # Re-register clean tables so StarSchema can load them via DataModel
    connector.add_table("orders_silver",    orders_silver.to_pandas())
    connector.add_table("customers_silver", customers_silver.to_pandas())
    model.add_table("orders_silver",    connector="mem", source="orders_silver")
    model.add_table("customers_silver", connector="mem", source="customers_silver")

    schema = StarSchema("Sales", model=model)
    schema.add_dimension(
        name="dim_customer",
        table_name="customers_silver",
        key_col="customer_id",
        attributes=["region", "segment"],
    )
    schema.add_fact(
        name="fact_orders",
        table_name="orders_silver",
        measures=["revenue", "qty"],
        foreign_keys={"dim_customer": "customer_id"},
    )
    schema.describe()

    # ── Gold ─────────────────────────────────────────────────────
    print("\n[4] Gold — aggregated results")

    gold = GoldLayer(schema=schema)

    revenue_by_region = gold.query(
        fact="fact_orders",
        measures={"revenue": "sum", "qty": "sum"},
        dimensions=["dim_customer.region"],
        name="revenue_by_region",
    )
    print("\n  Revenue by region:")
    print(revenue_by_region.to_pandas().to_string(index=False))

    revenue_by_segment = gold.query(
        fact="fact_orders",
        measures={"revenue": "sum", "order_id": "count"},
        dimensions=["dim_customer.segment"],
        filters={"status": "shipped"},
        name="revenue_by_segment_shipped",
    )
    print("\n  Revenue by segment (shipped only):")
    print(revenue_by_segment.to_pandas().to_string(index=False))

    total = gold.query(
        fact="fact_orders",
        measures={"revenue": "sum", "qty": "sum"},
        name="grand_total",
    )
    print("\n  Grand totals:")
    print(total.to_pandas().to_string(index=False))

    revenue_by_region.print_lineage()

    # ── Lineage Diagram ──────────────────────────────────────────
    print("\n[5] Lineage Diagram")

    diag = LineageDiagram(revenue_by_region)
    print(f"  {diag}")

    print("\n  Mermaid:\n")
    print(diag.to_mermaid())

    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    html_path = os.path.join(output_dir, "lineage_revenue_by_region.html")
    diag.to_html(html_path)
    print(f"  Lineage HTML saved: {html_path}")

    print("\nAll Phase 2.5 steps complete ✓")
    return revenue_by_region


if __name__ == "__main__":
    run()
