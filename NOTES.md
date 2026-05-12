# TraceBi — Design Notes

Code-first, traceable BI and analytics framework for Python.
Every data operation is tracked with a full, immutable lineage chain.

---

## Architecture Overview

```
tracebi/
  connectors/     Source adapters (CSV, SQL, BigQuery, Snowflake, Memory)
  model/          Core data abstractions (DataSet, DataModel, StarSchema)
  etl/            Medallion layers (Bronze → Silver → Gold)
  reports/        Report engine + renderers (Excel, HTML)
  dashboard/      Dash-based live dashboard server
  lineage/        Lineage visualisation (LineageDiagram)
examples/         Runnable demos for each phase
tests/            Pytest suite (one file per phase)
requests/         Project-specific report scripts (copy _template.py)
output/           Generated files — gitignored
```

---

## Core Abstractions

### LineageNode
A single, immutable record of one operation in a DataSet's history.

```python
@dataclass
class LineageNode:
    operation: str       # 'load', 'filter', 'transform', 'join', 'bronze', 'silver', 'gold', …
    description: str
    connector: dict      # connector metadata (for load/bronze steps)
    source: str          # table name, file path, SQL query
    timestamp: str       # UTC ISO-8601, auto-set
    metadata: dict       # arbitrary key/value (rows_before/after, agg spec, …)
```

### DataSet
Immutable pandas DataFrame wrapper. Every fluent method returns a **new** DataSet.

```python
ds = (
    model.load("orders")
    .filter("status == 'shipped'")
    .transform(lambda df: df.assign(margin=df.revenue - df.cost))
    .sort("margin", ascending=False)
    .select(["region", "product", "margin"])
)
ds.print_lineage()
```

### DataModel
Qlik-style relational graph. Register connectors + tables, declare joins.

```python
model = DataModel("SalesModel")
model.add_connector(CSVConnector("files", directory="data/"))
model.add_table("orders",    connector="files", source="orders.csv")
model.add_table("customers", connector="files", source="customers.csv")
model.add_relationship("orders_customers", "orders", "customers", "customer_id")
orders_ds = model.resolve("orders_customers")
```

---

## Medallion Architecture

### Bronze (raw ingest)
- Load data from any connector with zero transforms.
- Lineage stamped with `operation="bronze"` + ingestion timestamp.

```python
bronze = BronzeLayer(connector=csv_connector, source="orders.csv")
raw_ds = bronze.load(name="orders_raw")
```

### Silver (clean)
- Declarative pipeline: cast, drop_nulls, deduplicate, rename, transform.
- Each step appends a `operation="silver"` lineage node.

```python
silver = (
    SilverLayer()
    .cast({"order_date": "datetime64[ns]", "qty": "int64"})
    .drop_nulls(subset=["order_id"])
    .deduplicate(subset=["order_id"])
)
clean_ds = silver.apply(raw_ds, name="orders_silver")
```

### Gold (aggregated)
- Delegates to `StarSchema.query()`.
- Appends a `operation="gold"` lineage node with query parameters.

```python
gold = GoldLayer(schema=schema)
revenue_by_region = gold.query(
    fact="fact_orders",
    measures={"revenue": "sum", "order_id": "count"},
    dimensions=["dim_customer.region"],
    filters={"status": "shipped"},
)
```

---

## Star Schema

```python
schema = StarSchema("Sales", model=model)

schema.add_dimension("dim_customer", table_name="customers",
                     key_col="customer_id", attributes=["region", "segment"])
schema.add_fact("fact_orders", table_name="orders",
                measures=["revenue", "qty"],
                foreign_keys={"dim_customer": "customer_id"})

ds = schema.query(
    fact="fact_orders",
    measures={"revenue": "sum", "order_id": "count"},
    dimensions=["dim_customer.region"],
    filters={"status": "shipped"},
    aggregate=True,
)
```

**Dimension references** use dot notation: `"dim_name.attribute"`.  
**Measures** are a dict: `{"column": "agg_func"}`.  
Supported agg funcs: `sum`, `count`, `mean`, `min`, `max`, `nunique`.

---

## Report Engine (Phase 2)

```python
report = (
    Report("Q2 Sales")
    .author("Data Team")
    .add(TextSection(title="Summary", content="...", style="heading1"))
    .add(ChartSection(dataset=trend_ds, chart_type="line", x="month", y="revenue"))
    .add(TableSection(dataset=region_ds, columns=["region", "revenue"], totals=["revenue"]))
)

ExcelRenderer().render(report, "output/report.xlsx")
HTMLRenderer().render(report, "output/report.html")
HTMLRenderer().serve(report, port=8080)   # open in browser
HTMLRenderer().preview(report)            # inline in Jupyter
```

Every render saves a `.manifest.json` with report metadata + full lineage.

---

## Dashboard (Phase 3)

```python
dashboard = (
    Dashboard("Sales Dashboard")
    .columns(2)
    .add_filter(FilterPanel("region-filter", label="Region", column="region", table_name="orders"))
    .add_panel(MetricPanel("total-revenue", title="Revenue", table_name="orders",
                           column="revenue", aggregation="sum", prefix="$"))
    .add_panel(ChartPanel("by-region", title="By Region", table_name="orders",
                          chart_type="bar", x="region", y="revenue"))
    .add_panel(TablePanel("orders-table", title="Orders", table_name="orders",
                          columns=["order_id", "region", "revenue"]))
)

DashboardServer(dashboard, model=model).run(port=8050)
```

Filters are **associative**: selecting a value in any FilterPanel automatically
filters every panel whose dataset contains that column.

---

## Lineage Diagram (Phase 2.5)

```python
from tracebi.lineage.diagram import LineageDiagram

diag = LineageDiagram(ds)
diag.show()                  # matplotlib / Jupyter inline
diag.to_html("lineage.html") # standalone HTML with embedded SVG
print(diag.to_mermaid())     # Mermaid markdown string

# Works on Reports too
diag = LineageDiagram(report)
```

Node colors by operation type:

| operation  | color   |
|-----------|---------|
| load      | navy    |
| bronze    | bronze  |
| silver    | silver  |
| gold      | gold    |
| filter    | green   |
| transform | amber   |
| join      | orange  |
| sort      | purple  |
| select    | steel   |
| rename    | teal    |

---

## Connectors

| Class              | Extra dep                          | Notes                          |
|--------------------|------------------------------------|--------------------------------|
| CSVConnector       | openpyxl (optional for xlsx)       | `directory=` + filename source |
| SQLConnector       | sqlalchemy                         | Any SQLAlchemy URL             |
| BigQueryConnector  | google-cloud-bigquery, db-dtypes   | Uses ADC by default            |
| SnowflakeConnector | snowflake-connector-python         | Keyword auth supported         |
| MemoryConnector    | (none)                             | In-process dict of DataFrames  |

---

## Install

```bash
pip install -e ".[reports,dashboard]"      # reports + Dash
pip install -e ".[reports,dashboard,sql]"  # + SQLAlchemy
pip install networkx matplotlib            # for LineageDiagram
```

---

## Running Examples

```bash
python examples/phase1_example.py    # connectors + DataModel
python examples/phase2_example.py    # reports (opens browser)
python examples/phase3_example.py    # live Dash dashboard
python examples/phase25_example.py   # medallion + star schema + lineage diagram
```

In Jupyter:
```python
from examples.phase25_example import run
run()
```

---

## Design Decisions

**Why immutable DataSet?**  
Lineage is append-only. You can always reconstruct exactly which operations
produced a result. No in-place mutation means no hidden state bugs.

**Why DataModel instead of just pandas merge?**  
Named relationships let you declare the schema once and reuse it everywhere.
The model is the single source of truth for joins — reports, dashboards, and
pipelines all read from the same definitions.

**Why MemoryConnector?**  
Tests and demos should not require external files or databases. MemoryConnector
provides a drop-in connector backed by a Python dict, so tests run in pure
memory with full lineage.

**Why dot notation for star schema dimensions?**  
`"dim_customer.region"` is self-documenting and prevents column name
collisions when multiple dimensions are joined. It's also easy to parse
and display in lineage nodes.

**Why medallion layers as separate classes?**  
Bronze/Silver/Gold are distinct _contracts_, not just naming conventions.
BronzeLayer enforces "no transforms". SilverLayer enforces "declarative pipeline".
GoldLayer enforces "aggregated via StarSchema". The type boundary makes it
impossible to accidentally skip a layer.
