# TraceBi

A **code-first, traceable BI and analytics framework** for Python.

Define your data model, transformations, and reports entirely in code.
Every report is traceable back to the exact query, connector, and transform steps that produced it.

---

## Why TraceBi?

| Feature | Dash / Streamlit | dbt | Qlik / Tableau | **TraceBi** |
|---|---|---|---|---|
| Code-defined reports | ✓ | ✗ | ✗ | ✓ |
| Relational data model | ✗ | ✓ | ✓ | ✓ |
| Full data lineage per report | ✗ | partial | ✗ | ✓ |
| PDF / Excel output | ✗ | ✗ | ✓ | ✓ |
| Scheduled pipelines | ✗ | ✓ | ✓ | ✓ (Phase 4) |
| Web dashboard | ✓ | ✗ | ✓ | ✓ (Phase 3) |

---

## Roadmap

- [x] **Phase 1** — Connectors (CSV, SQL, BigQuery, Snowflake), DataModel, DataSet with lineage
- [x] **Phase 2** — Report Engine (Excel, HTML, PDF renderers + manifest)
- [ ] **Phase 3** — Dashboard server (Dash-based, driven by the same DataModel)
- [ ] **Phase 4** — Pipelines and scheduling (APScheduler, on-demand and cron)

---

## Installation

```bash
# Core (CSV + SQLite support)
pip install pandas openpyxl sqlalchemy matplotlib

# PostgreSQL
pip install psycopg2-binary

# BigQuery
pip install google-cloud-bigquery db-dtypes

# Snowflake
pip install snowflake-connector-python

# PDF rendering
pip install weasyprint
```

---

## Quick Start

### 1. Define a DataModel

```python
from tracebi import DataModel, CSVConnector, SQLConnector

db  = SQLConnector("sales_db", url="postgresql://user:pass@host/db")
csv = CSVConnector("lookups", directory="data/")

model = DataModel("SalesModel")
model.add_connector(db)
model.add_connector(csv)

model.add_table("orders",    connector="sales_db", source="orders")
model.add_table("customers", connector="sales_db", source="customers")
model.add_table("regions",   connector="lookups",  source="regions.csv")

model.add_relationship(
    name="orders_customers",
    left_table="orders",
    right_table="customers",
    left_key="customer_id",
    how="left",
)
model.add_relationship(
    name="customers_regions",
    left_table="customers",
    right_table="regions",
    left_key="region_code",
    how="left",
)
```

### 2. Load and transform data

```python
model.connect()

orders = model.load("orders")

active = (
    orders
    .filter("status != 'cancelled'", description="Exclude cancelled orders")
    .transform(
        lambda df: df.assign(revenue=df["qty"] * df["unit_price"]),
        description="revenue = qty × unit_price",
    )
    .sort("revenue", ascending=False)
)

# Full join chain: orders → customers → regions
full_view = model.resolve_chain(["orders_customers", "customers_regions"])
```

### 3. Inspect lineage at any point

```python
active.print_lineage()
# ============================================================
#   Lineage for DataSet: 'orders'
#   Shape: 243 rows × 8 cols
# ============================================================
#   Step 1: [LOAD]  Loaded 'orders' from connector 'sales_db'
#     Connector : sales_db (SQLConnector)
#     Source    : orders
#   Step 2: [FILTER]  Exclude cancelled orders
#     rows_before : 250
#     rows_after  : 243
#   Step 3: [TRANSFORM]  revenue = qty × unit_price
#   Step 4: [SORT]  Sorted by revenue (desc)
# ============================================================
```

### 4. Build and render a report

```python
from tracebi.reports import Report, TextSection, TableSection, ChartSection
from tracebi.reports import ExcelRenderer, HTMLRenderer

report = (
    Report("Monthly Sales Report")
    .author("Data Team")
    .parameter("month", "2024-06")
    .add(TextSection(
        title="Executive Summary",
        content="Revenue up 12% vs prior month.",
        style="heading1",
    ))
    .add(TableSection(
        title="Top Orders",
        dataset=active,
        columns=["order_id", "customer_id", "revenue"],
        totals=["revenue"],
        number_formats={"revenue": "{:,.2f}"},
    ))
    .add(ChartSection(
        title="Revenue by Region",
        dataset=full_view,
        chart_type="bar",
        x="region_name",
        y="revenue",
    ))
)

# Renders the report AND saves a .manifest.json with full lineage
ExcelRenderer().render(report, "output/monthly_sales.xlsx")
HTMLRenderer().render(report, "output/monthly_sales.html")
```

Every render automatically produces a manifest file:
```json
{
  "report_name": "Monthly Sales Report",
  "rendered_at": "2024-06-01T09:00:00Z",
  "rendered_by": "Data Team",
  "format": "excel",
  "parameters": { "month": "2024-06" },
  "sections": [
    {
      "section_type": "table",
      "dataset_name": "orders",
      "dataset_fingerprint": "a3f9...",
      "dataset_lineage": [
        { "operation": "load",      "source": "orders", "connector": "sales_db" },
        { "operation": "filter",    "description": "Exclude cancelled orders" },
        { "operation": "transform", "description": "revenue = qty × unit_price" },
        { "operation": "sort",      "description": "Sorted by revenue (desc)" }
      ]
    }
  ]
}
```

---

## Project Structure

```
tracebi/
├── tracebi/
│   ├── connectors/
│   │   ├── base.py              # Abstract connector
│   │   ├── csv_connector.py     # CSV / Excel files
│   │   ├── sql_connector.py     # SQLAlchemy (SQLite, Postgres, MySQL…)
│   │   ├── bigquery_connector.py
│   │   └── snowflake_connector.py
│   ├── model/
│   │   ├── data_model.py        # Relational graph, Qlik-style associations
│   │   └── dataset.py           # DataSet + LineageNode chain
│   ├── reports/
│   │   ├── report.py            # Report, Section types, ReportManifest
│   │   ├── base_renderer.py     # Abstract renderer
│   │   ├── excel_renderer.py    # .xlsx output
│   │   └── html_renderer.py     # .html output (+ PDF via WeasyPrint)
│   ├── dashboard/               # Phase 3 — coming soon
│   └── pipeline/                # Phase 4 — coming soon
├── examples/
│   ├── phase1_example.py
│   └── phase2_example.py
├── tests/
│   ├── test_phase1.py
│   └── test_phase2.py
└── pyproject.toml
```

---

## Running the examples

```bash
python examples/phase1_example.py
python examples/phase2_example.py
```

## Running tests

```bash
pytest tests/
```

---

## License

MIT
