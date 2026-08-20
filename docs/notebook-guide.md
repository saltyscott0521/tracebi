# TraceBi in Notebooks

How to use TraceBi from Jupyter — rich previews while you explore, and how a
notebook becomes a phase-① transform once the analysis settles.

Companion to the [Analyst Guide](analyst-guide.md), which covers the full
development flow; this guide covers what's different in a notebook.

---

## Where the notebook fits the workflow

TraceBi's spine is the three-phase workflow in [WORKFLOW.md](../WORKFLOW.md):
phase ① `transforms/` writes clean star-schema tables into a DuckDB warehouse,
phase ② `models/` declares a thin `DataModel` over it, and phase ③ `reports/`
is an artifact package (or a JSON `ReportSpec`) served on the Reports page.

A notebook is the natural home for **phase ①** — the slow, unconstrained pandas
analysis — because the rich previews below let you *see* the data as you clean
it, before you commit anything. When the analysis settles, sink the named
tables:

```python
from tracebi.connectors import DuckDBConnector

wh = DuckDBConnector("warehouse", database="data/warehouse.duckdb")
wh.write(fact_holdings_df, "fact_holdings")   # freeze: the sink is now the contract
```

From there the model (②) and report (③) are small, reviewable artifacts that
never re-run the notebook. The trust machinery (`tracebi verify`, stamped
queries) applies from the model boundary onward — it does not read the pandas in
your notebook, by design.

So a notebook has two surviving roles: the **discovery workbench feed** while
you explore, and — once the cleaning settles — a **notebook-shaped transform**
you run with `tracebi run-transform`. Both are covered below.

---

## Setup

```bash
pip install "tracebi[analyst]"   # the data deps: DuckDB, the pandas stack, dotenv
pip install ipython              # rich HTML previews (or run inside an existing Jupyter env)
```

`tracebi[analyst]` gives you the data dependencies; the rich `_repr_html_`
previews below additionally need IPython, which the `analyst` extra does not
pull in.

Scaffold a notebook-shaped transform, or start from a blank notebook — nothing
about TraceBi requires the scaffold:

```bash
tracebi list-models                      # see what shared models are available
tracebi new-transform "Holdings clean"   # → transforms/holdings_clean.py (# %% cells)
```

`tracebi new-transform` writes a **notebook-shaped `.py`**: the `# %%` markers
are cell boundaries and `# %% [markdown]` cells are prose, so VS Code, Cursor,
PyCharm, and Jupyter (via jupytext) open it *as* a notebook — run it
cell-by-cell — while it stays plain, reviewable Python that runs top-to-bottom.
Models stay `.py` (`tracebi new-model`); reports scaffold with
`tracebi new-report`.

## Rich object previews

`DataSet` and `DataModel` render as rich HTML in notebooks. Putting one at
the end of a cell shows shape, columns, dtypes, sample rows, and the lineage
chain — no `print` calls needed:

```python
from tracebi.model_registry import get_model, list_models

print(list_models())             # see what's in models/
model = get_model("sales_model") # loads models/sales_model.py — no web server needed
model                            # tables, relationships, facts/dimensions, as HTML

orders = model.load("orders")
orders                           # shape, dtypes, sample rows, operation chain

orders.help()          # plain-text cheat sheet of every verb
model.describe()       # plain-text model summary
```

This makes notebooks the best place to *discover* data before committing
transforms to a script.

## The discovery workbench

While you explore, push what you find into a live, shared surface. Run the
workbench in **discovery mode** in a terminal:

```bash
tracebi dev            # no report named → the project-level workbench at /__workbench
```

Then, from any notebook cell, `show()` frames, charts, and notes into its feed:

```python
import tracebi.workbench as workbench

workbench.show(fact_holdings_df, note="after dedupe — 3 rows dropped")
workbench.show(by_sector_df, chart="bar", x="sector", y="market_value")
```

`show()` is zero-config and a no-op when nothing is listening (no fresh
heartbeat), so the same cell is harmless outside a `tracebi dev` session. It is
where phases ① and ② become visible before any report package exists.

## Inline report preview

Render a report directly into the notebook output — no server, no files left
behind:

```python
from tracebi.reports.html_renderer import HTMLRenderer

HTMLRenderer().preview(report)                  # embedded iframe, 800px tall
HTMLRenderer().preview(report, height=1200)     # taller
```

This is the notebook equivalent of `tracebi dev`'s live preview loop:
re-run the cell after each change.

## From notebook to transform

The notebook-shaped `.py` **is** the production artifact — there is no separate
conversion step. End it by sinking your clean star-schema tables and, optionally,
declaring a **sink contract**:

```python
# %%  Sink — the contract is the named tables, not how you produced them
from tracebi.connectors import DuckDBConnector
from tracebi.contracts import contract

WAREHOUSE = "data/warehouse.duckdb"
DuckDBConnector("warehouse", database=WAREHOUSE).write(fact_holdings_df, "fact_holdings")

# %%  Declare the sink CONTRACT (optional, recommended)
with contract("holdings", warehouse=WAREHOUSE) as c:
    c.rows("fact_holdings", min=1)
    c.not_null("fact_holdings", ["holding_id", "market_value"])
    c.foreign_key("fact_holdings", "sector_key", "dim_sector", "sector_key")
```

Run it top-to-bottom in a fresh namespace:

```bash
tracebi run-transform holdings_clean   # executes transforms/holdings_clean.py or .ipynb
```

**How `tracebi run-transform` executes a file:** the code cells are
concatenated top-to-bottom into one script and executed in a fresh namespace,
so the sink never comes from out-of-order kernel state. Line magics
(`%matplotlib inline`) and shell escapes (`!pip install ...`) are silently
dropped — they only mean something inside a Jupyter kernel. In a notebook-shaped
`.py`, `# %% [markdown]` cells stay as reviewable prose comments; only a literal
`.ipynb`'s markdown cells are dropped at run time.

Practical implications:

- **Cell order matters.** The file must run clean top-to-bottom
  (`Kernel → Restart & Run All` is the honesty test). Hidden state from
  out-of-order execution won't exist when the runner executes it.
- **Don't rely on magics for logic.** Anything load-bearing belongs in
  plain Python.
- **Keep the sink idempotent.** A rerun replaces the warehouse tables.

## Exporting the exploration record

A discovery session is a lab notebook, not a report. Capture it verbatim:

```bash
tracebi session export             # → explorations/<name>.html
tracebi session export --format md # → explorations/<name>.md (the markdown twin)
```

This writes the committed record of what you looked at — frames, charts, and
notes from the workbench feed. It carries **no manifest**, because nothing in it
is a verified figure; `tracebi verify` refuses the file by name rather than
letting a lab notebook read as a receipt. It is the honest home for the
narrative that a governed report deliberately does not carry.

## Publishing a report from a notebook

The same registration decorator works in a notebook cell:

```python
from tracebi import register

@register.report("weekly_sales", description="Weekly sales summary")
def _factory():
    return report
```

Place the notebook (with its `@register.report` cell) in **`reports/`** — the
server auto-discovers `*.py` and `*.ipynb` there, and the report appears on the
Reports page. In an interactive kernel the decorator is harmless if the web
extras aren't installed — it raises a clear `ImportError` telling you to
`pip install "tracebi[web]"`.

For a governed, receipt-bearing report, prefer the artifact package
(`tracebi new-report` → `tracebi dev` → `tracebi report build`), covered in the
[Analyst Guide](analyst-guide.md).

Reference files: `examples/portfolio_project/transforms/holdings_transform.py`,
`examples/portfolio_project/models/portfolio_model.py`, and
`examples/portfolio_project/reports/portfolio_dashboard.json`.
