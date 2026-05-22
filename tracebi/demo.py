"""
Built-in demo data for TraceBi.

Provides a ready-to-use DataModel backed by in-memory sample data so you can
follow the walkthrough immediately after ``pip install tracebi`` — no files,
no database, no configuration required.

Usage:
    from tracebi.demo import load_demo_model

    model = load_demo_model()
    orders = model.load("orders")
    orders.print_lineage()
"""

from __future__ import annotations

import pandas as pd

from tracebi.connectors.memory_connector import MemoryConnector
from tracebi.model.data_model import DataModel


def load_demo_model() -> DataModel:
    """Return a connected DataModel loaded with sample sales data.

    Tables available:
        - ``orders``    — 10 sales orders with region, product, qty, revenue, cost, status
        - ``customers`` — 5 customers with region and segment
        - ``trend``     — 6-month revenue and cost trend
    """
    orders = pd.DataFrame({
        "order_id":    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "customer_id": [1, 2, 3, 4, 1, 3, 2, 4, 1, 3],
        "region":      ["North East", "South East", "Midwest", "West",
                        "North East", "Midwest", "South East", "West",
                        "North East", "Midwest"],
        "product":     ["Widget A", "Widget B", "Gadget X", "Widget A",
                        "Gadget X", "Widget B", "Widget A", "Gadget X",
                        "Widget B", "Widget A"],
        "qty":         [120, 85, 200, 60, 95, 150, 40, 110, 75, 180],
        "revenue":     [3598.80, 4249.15, 19998.00, 1799.40, 9499.05,
                        14998.50, 1199.60, 10998.90, 3748.25, 17997.00],
        "cost":        [2100.00, 2800.00, 14000.00, 1050.00, 6600.00,
                        10500.00, 700.00, 7700.00, 2200.00, 12600.00],
        "status":      ["shipped", "shipped", "open", "shipped", "open",
                        "shipped", "shipped", "open", "shipped", "open"],
    })

    customers = pd.DataFrame({
        "customer_id": [1, 2, 3, 4, 5],
        "name":        ["Acme Corp", "Globex", "Initech", "Umbrella", "Vandelay"],
        "region":      ["North East", "South East", "Midwest", "West", "North East"],
        "segment":     ["enterprise", "smb", "smb", "enterprise", "mid-market"],
    })

    trend = pd.DataFrame({
        "month":   ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        "revenue": [28000, 31500, 29800, 34200, 38100, 39145],
        "orders":  [95, 108, 101, 119, 131, 138],
        "cost":    [19600, 22050, 20860, 23940, 26670, 27400],
    })

    connector = MemoryConnector("demo", tables={
        "orders":    orders,
        "customers": customers,
        "trend":     trend,
    })

    model = DataModel("SalesModel")
    model.add_connector(connector)
    model.add_table("orders",    connector="demo", source="orders")
    model.add_table("customers", connector="demo", source="customers")
    model.add_table("trend",     connector="demo", source="trend")
    model.connect()

    return model
