# Use TraceBi in a notebook

Explore data in Jupyter with rich previews, then turn the notebook into a
transform that writes the warehouse.

## Before you begin

- A TraceBi workspace (`tracebi init`)
- The data dependencies and IPython for previews:

  ```bash
  pip install "tracebi[analyst]"   # DuckDB, the pandas stack, dotenv
  pip install ipython              # rich HTML previews, unless you already run Jupyter
  ```

## 1. Create a notebook-shaped transform

```bash
tracebi new-transform "Holdings clean" --python   # transforms/holdings_clean.py
```

The file uses `# %%` cell markers and `# %% [markdown]` prose cells. VS Code,
Cursor, PyCharm and Jupyter (with jupytext) open it as a notebook, and it
stays plain Python that runs top to bottom. A blank `.ipynb` works too.
Without `--python`, `tracebi new-transform` writes a SQL transform.

## 2. Look at the data

`DataSet` and `DataModel` render as HTML at the end of a cell:

```python
from tracebi.model_registry import get_model, list_models

print(list_models())             # what's in models/
model = get_model("sales_model") # no web server needed
model                            # tables, relationships, facts and dimensions

orders = model.load("orders")
orders                           # shape, dtypes, sample rows, lineage
orders.help()                    # every DataSet method
model.describe()                 # the model as text
```

## 3. Show your work in the app (optional)

In a terminal:

```bash
tracebi dev            # the app's Data page, with the workspace feed
```

Then, from any cell:

```python
import tracebi.workbench as workbench

workbench.show(fact_holdings_df, note="after dedupe: 3 rows dropped")
workbench.show(by_sector_df, chart="bar", x="sector", y="market_value")
```

Each call appears on the Data page under *From your agent*. `show()` needs no
setup and does nothing when `tracebi dev` is not running, so the cell is safe
to leave in.

## 4. Preview a report in the notebook (optional)

```python
from tracebi.reports.html_renderer import HTMLRenderer

HTMLRenderer().preview(report)                  # an embedded frame, 800px tall
HTMLRenderer().preview(report, height=1200)
```

Re-run the cell after each change.

## 5. Write the warehouse tables

End the file by writing clean star-schema tables, and declare a sink contract:

```python
# %%  Sink: the named tables are what the model reads
from tracebi.connectors import DuckDBConnector
from tracebi.contracts import contract
from tracebi.project_config import sink_target

WAREHOUSE = sink_target(ROOT)
DuckDBConnector("warehouse", database=WAREHOUSE).write(fact_holdings_df, "fact_holdings")

# %%  The sink contract (optional, recommended)
with contract("holdings", warehouse=WAREHOUSE) as c:
    c.rows("fact_holdings", at_least=1)
    c.not_null("fact_holdings", ["holding_id", "market_value"])
    c.foreign_key("fact_holdings", "sector_key", refers_to=("dim_sector", "sector_key"))
```

## 6. Run it top to bottom

```bash
tracebi run-transform holdings_clean   # runs transforms/holdings_clean.py or .ipynb
```

The runner joins the code cells into one script and runs it in a fresh
namespace. Line magics (`%matplotlib inline`) and shell escapes
(`!pip install ...`) are dropped, because they only work inside a Jupyter
kernel. Markdown cells in a `.py` stay as comments; a `.ipynb`'s markdown
cells are dropped.

## What happened

- The notebook file is the production transform. There is no conversion step.
- A fresh run means hidden state from cells run out of order cannot reach the
  warehouse. Test with **Kernel → Restart & Run All** before you commit.
- A rerun replaces the warehouse tables.
- The model and reports read only the tables. They never re-run the notebook.
  `tracebi verify` does not read the notebook's pandas: lineage is traced from
  the sink, not through the transform.

## Save the exploration

```bash
tracebi session export             # explorations/<name>.html
tracebi session export --format md # explorations/<name>.md
```

This saves the tables, charts and notes you posted with `show()`. It carries
no manifest, and `tracebi verify` refuses it.

## Next

- Build a report on the tables you wrote: `tracebi new-dashboard` or
  `tracebi new-report`, then `tracebi dev` and `tracebi report build`
  ([[analyst-guide]])
- A notebook in `reports/` that registers a factory with
  `@register.report(...)` is still imported, but a report with no package is
  refused (HTTP 422) and `tracebi validate` flags it. Pandas a model cannot
  express goes in a package's `report.py`.
- Reference files: `examples/portfolio_project/transforms/holdings_transform_pandas.py`,
  `examples/portfolio_project/models/portfolio_model.yaml` and
  `examples/portfolio_project/reports/portfolio_model/portfolio_dashboard/`.
