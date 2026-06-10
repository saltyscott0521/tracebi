"""
Shared DataModel for the demo app.

Imported by reports, dashboard, and registry. Never import from registry.py
back into this file — that would create a circular dependency.
"""

import pandas as pd

from tracebi import DataModel, MemoryConnector

orders_df = pd.DataFrame({
    "order_id":    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "customer_id": [1, 2, 3, 4, 1, 3, 2, 4, 1, 3],
    "region":   ["North East", "South East", "Midwest", "West",
                 "North East", "Midwest", "South East", "West",
                 "North East", "Midwest"],
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

trend_df = pd.DataFrame({
    "month":   ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
    "revenue": [28000, 31500, 29800, 34200, 38100, 39145],
    "orders":  [95, 108, 101, 119, 131, 138],
    "cost":    [19600, 22050, 20860, 23940, 26670, 27400],
})

customers_df = pd.DataFrame({
    "customer_id": [1, 2, 3, 4, 5],
    "name":        ["Acme Corp", "Globex", "Initech", "Umbrella", "Vandelay"],
    "region":      ["North East", "South East", "Midwest", "West", "North East"],
    "tier":        ["enterprise", "smb", "smb", "enterprise", "mid-market"],
})

connector = MemoryConnector("demo", tables={
    "orders":    orders_df,
    "trend":     trend_df,
    "customers": customers_df,
})

model = DataModel("SalesModel")
model.add_connector(connector)
model.add_table("orders",    connector="demo", source="orders")
model.add_table("trend",     connector="demo", source="trend")
model.add_table("customers", connector="demo", source="customers")
model.add_relationship(
    "orders_to_customers",
    left_table="orders",
    right_table="customers",
    left_key="customer_id",
)

# Star-schema tags — power the Explore query builder in the web UI.
model.add_dimension(
    "dim_customer",
    table_name="customers",
    key_col="customer_id",
    attributes=["name", "region", "tier"],
)
model.add_fact(
    "fact_orders",
    table_name="orders",
    measures=["revenue", "qty", "cost"],
    foreign_keys={"dim_customer": "customer_id"},
)

model.connect()
