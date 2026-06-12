# TraceBi in Notebooks

How to use TraceBi from Jupyter — rich previews while you explore, and
notebooks that double as production request scripts when you're done.

Companion to the [Analyst Guide](analyst-guide.md), which covers the full
development flow; this guide covers what's different in a notebook.

---

## Setup

```bash
pip install "tracebi[analyst]"   # includes IPython/Jupyter integration deps
```

```bash
tracebi list-models              # see what shared models are available
tracebi new-model "Sales Model"  # scaffold models/sales_model.py if none exists yet
tracebi new-request "Weekly Sales" --notebook
# → requests/weekly_sales.ipynb, pre-structured: params → model → datasets → report
```

Or start from a blank notebook — nothing about TraceBi requires the scaffold.

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

## Notebooks as request scripts

A `.ipynb` file in `requests/` is a first-class request script:

- `tracebi run weekly_sales` executes it (tries `.py`, then `.ipynb`)
- `tracebi list-requests` shows it
- The web UI's **Requests** page lists it with a run button, parameter
  form, and lineage graphs — exactly like a `.py` script

**How execution works:** the code cells are concatenated top-to-bottom into
one script and executed. Markdown cells are ignored. Line magics
(`%matplotlib inline`) and shell escapes (`!pip install ...`) are silently
dropped — they only mean something inside a Jupyter kernel.

Practical implications:

- **Cell order matters.** The notebook must run clean top-to-bottom
  (`Kernel → Restart & Run All` is the honesty test). Hidden state from
  out-of-order execution won't exist when the runner executes it.
- **Don't rely on magics for logic.** Anything load-bearing belongs in
  plain Python.
- **Side effects run on import-style execution.** Keep heavyweight work
  behind the same structure the `.py` template uses if you need control.

## Parameters in notebooks

`request_params` works identically:

```python
from tracebi import request_params
params = request_params(period="Q2 2024", min_revenue=0)
```

In the kernel you get the defaults; under `tracebi run --param` or the web
UI's form, overrides are injected and coerced to the defaults' types.

## Publishing from a notebook

The same registration decorator works in a notebook cell:

```python
from tracebi.web import register

@register.report("weekly_sales", description="Weekly sales summary")
def _factory():
    return report
```

When the web server discovers the notebook in `requests/`, that cell runs
and the report appears in the UI. In an interactive kernel the decorator
is harmless if the web extras aren't installed — it raises a clear
`ImportError` telling you to `pip install "tracebi[web]"`.

## From notebook to script

When a notebook matures into something scheduled or reviewed, convert it:
copy the code cells into a file based on `requests/_template.py`. The
template's numbered sections map one-to-one to the scaffolded notebook's
cells, so this is usually a paste-and-tidy job, not a rewrite.
