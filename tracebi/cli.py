"""
TraceBi CLI.

Usage:
    tracebi init my_project                      # scaffold a new project
    tracebi new-request "Open orders by region"  # scaffolds requests/<slug>.py
    tracebi list-requests                        # show all request scripts
    tracebi run <name>                           # run a request and render outputs
    tracebi dev <name>                           # live preview: re-run + reload on save
    tracebi validate                             # sanity-check the current project
    tracebi --version

The CLI is intentionally small — its job is to scaffold and run files
in ``requests/``. Everything else lives in the library.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import runpy
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from tracebi._version import get_version as _tracebi_version


# Resolve the requests/ folder relative to the user's current working
# directory by default. Override with --requests-dir.
def _default_requests_dir() -> Path:
    return Path.cwd() / "requests"


def _default_models_dir() -> Path:
    return Path.cwd() / "models"


def _default_pipelines_dir() -> Path:
    return Path.cwd() / "pipelines"


def _slugify(title: str) -> str:
    """Convert "Open orders by region" → "open_orders_by_region"."""
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "request"


def _template_text(title: str) -> str:
    today = date.today().isoformat()
    slug = _slugify(title)
    return f'''"""
{title}
{'=' * len(title)}

Scaffolded by ``tracebi new-request`` on {today}.
Fill in the four sections below, then run with:

    python requests/{slug}.py
"""

import os
from tracebi import request_params
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer

# ── 0. Parameters ───────────────────────────────────────────────────────────
# Override at run time:  tracebi run {slug} --param period="Q3 2024"
# The web UI's Requests page renders a form from these defaults.
params = request_params(period="Q2 2024")

# Use a model from models/ if one is defined, or build your own below.
# List available models: tracebi list-models
# Create a new model:    tracebi new-model "My Model"
try:
    from tracebi.model_registry import get_default_model
    model = get_default_model()
except KeyError:
    model = None

if model is None:
    from tracebi import DataModel  # noqa: F401
    # model = DataModel("MyModel")
    # model.add_connector(...)
    # model.add_table("orders", connector="...", source="...")
    pass


# ── 1. Build DataSets ───────────────────────────────────────────────────────
# Every verb returns a new DataSet and records a lineage step. Run
# ds.help() for the full cheat sheet, or see docs/analyst-guide.md.
#
# orders = (
#     model.load("orders", filter={{"status": "shipped"}})
#     .deduplicate(subset="order_id")
#     .dropna(subset="region")
#     .assign(margin=lambda df: df.revenue - df.cost)
#     .sort("margin", ascending=False)
# )


# ── 2. Build Report ─────────────────────────────────────────────────────────
report = (
    Report("{title}")
    .author("Your Name")
    .description("Short description of this report.")
    .add(TextSection(title="Summary", style="heading1"))
    .add(TextSection(content="Write your narrative here."))
)


# ── 3. Render ───────────────────────────────────────────────────────────────

def run():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, "{slug}")
    ExcelRenderer().render(report, base + ".xlsx")
    HTMLRenderer().render(report, base + ".html")
    print(f"Saved: {{base}}.xlsx / .html")


# ── 4. Publish to the project registry ─────────────────────────────────────
# Makes this report available to `tracebi run`, the web UI, and any other
# consumer. Harmless when nothing is listening.
from tracebi import register


@register.report("{slug}", description="Short description of this report.")
def _factory():
    return report


if __name__ == "__main__":
    run()
'''


def _notebook_text(title: str) -> str:
    slug = _slugify(title)
    today = date.today().isoformat()
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language":     "python",
                "name":         "python3",
            },
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata":  {},
                "source": [
                    f"# {title}\n",
                    f"\n",
                    f"_Scaffolded by `tracebi new-request --notebook` on {today}._\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata":  {},
                "execution_count": None,
                "outputs":   [],
                "source": [
                    "from tracebi import request_params\n",
                    "from tracebi.reports.report import Report, TextSection, TableSection, ChartSection\n",
                    "from tracebi.reports.html_renderer import HTMLRenderer\n",
                    "\n",
                    "# Declare defaults; override via tracebi run --param or the web UI form\n",
                    "params = request_params(period=\"Q2 2024\")\n",
                    "\n",
                    "# Pull the shared project model (registry, then models/ on disk)\n",
                    "from tracebi import register\n",
                    "\n",
                    "model = register.get_default_model()\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata":  {},
                "execution_count": None,
                "outputs":   [],
                "source": [
                    "# Build DataSets with model.load(...) — every step adds a lineage node.\n",
                    "# Run ds.help() for the full verb cheat sheet.\n",
                    "# orders = (\n",
                    "#     model.load(\"orders\", filter={\"status\": \"shipped\"})\n",
                    "#     .deduplicate(subset=\"order_id\")\n",
                    "#     .assign(margin=lambda df: df.revenue - df.cost)\n",
                    "# )\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata":  {},
                "execution_count": None,
                "outputs":   [],
                "source": [
                    f'report = (\n',
                    f'    Report("{title}")\n',
                    '    .author("Your Name")\n',
                    '    .add(TextSection(title="Summary", style="heading1"))\n',
                    '    .add(TextSection(content="Write your narrative here."))\n',
                    ')\n',
                    'HTMLRenderer().preview(report)\n',
                ],
            },
            {
                "cell_type": "markdown",
                "metadata":  {},
                "source": [
                    "## Expose to the web UI\n",
                    "\n",
                    "Uncomment to register this report so the running server picks it up via `tracebi.web.register`.\n",
                ],
            },
            {
                "cell_type": "code",
                "metadata":  {},
                "execution_count": None,
                "outputs":   [],
                "source": [
                    "# from tracebi import register\n",
                    f"# @register.report(\"{slug}\", description=\"...\")\n",
                    "# def _factory():\n",
                    "#     return report\n",
                ],
            },
        ],
    }
    return json.dumps(nb, indent=1) + "\n"


def _model_template_text(title: str) -> str:
    today = date.today().isoformat()
    slug = _slugify(title)
    model_name = title.strip().replace(" ", "")
    return f'''\
"""
{title}
{'=' * len(title)}

DataModel definition. Scaffolded by ``tracebi new-model`` on {today}.

Use in any notebook or script:

    from tracebi.model_registry import get_model
    model = get_model("{slug}")
    ds = model.load("my_table")

Or set as default so notebooks that call get_default_model() pick it up:

    from tracebi.model_registry import get_model, set_default
    set_default("{slug}")
"""

from tracebi import DataModel, SQLConnector
# from tracebi import CSVConnector, DuckDBConnector, MemoryConnector

# ── Connectors ───────────────────────────────────────────────────────────────
connector = SQLConnector("{slug}_db", url="sqlite:///data/{slug}.db")

# ── Model ─────────────────────────────────────────────────────────────────────
# The variable MUST be named `model` — the registry looks for it at load time.
model = DataModel("{model_name}")
model.add_connector(connector)
model.add_table("my_table", connector="{slug}_db", source="my_table")
# model.add_relationship(
#     name="orders_customers",
#     left_table="orders", right_table="customers", left_key="customer_id",
# )
# model.add_dimension("dim_customer", table_name="customers", key_col="customer_id",
#                     attributes=["region", "segment"])
# model.add_fact("fact_orders", table_name="orders", measures=["revenue", "qty"],
#                foreign_keys={{"dim_customer": "customer_id"}})
model.connect()

# ── Publish to the project registry ──────────────────────────────────────────
# Also discoverable without this line via `get_model("{slug}")`, since files
# in models/ are auto-loaded. Registering makes it visible to the web UI too.
from tracebi import register

register.model(model)
'''


def _pipeline_template_text(title: str) -> str:
    today = date.today().isoformat()
    slug = _slugify(title)
    return f'''\
"""
{title}
{'=' * len(title)}

PipelineRunner definition. Scaffolded by ``tracebi new-pipeline`` on {today}.

Use in any script or notebook:

    from tracebi.pipeline_registry import get_runner
    runner = get_runner("{slug}")
    runner.run("layer_name")
    runner.status()
"""

from tracebi import PipelineRunner
# from tracebi import LandingLayer, ManipulationLayer, FinalLayer, SQLConnector
# from tracebi.model_registry import get_model

_DB_URL = "sqlite:///data/{slug}.db"

# ── Layers ────────────────────────────────────────────────────────────────────
# Uncomment and adapt to wire your medallion layers.
#
# from tracebi import LandingLayer, ManipulationLayer, SQLConnector
# _db = SQLConnector("{slug}_db", url=_DB_URL)
#
# _bronze = LandingLayer(
#     connector=_db, source="orders_raw",
#     sink=_db, sink_table="orders_bronze",
# )
# _silver = (
#     ManipulationLayer(source=_db, source_table="orders_bronze",
#                       sink=_db, sink_table="orders_silver")
#     .drop_nulls(subset=["order_id"])
#     .deduplicate(subset=["order_id"])
# )

# ── Runner ─────────────────────────────────────────────────────────────────────
# The variable MUST be named `runner` — the registry looks for it at load time.
runner = PipelineRunner(db_url=_DB_URL)
# runner.register(_bronze, name="orders_bronze", schedule="0 * * * *")
# runner.register(_silver, name="orders_silver", schedule="15 * * * *",
#                 depends_on="orders_bronze")

# ── Publish to the project registry ──────────────────────────────────────────
# Also discoverable without this line via `get_runner("{slug}")`, since files
# in pipelines/ are auto-loaded. Registering makes it visible to the web UI too.
from tracebi import register

register.pipeline("{slug}", runner)
'''


# ── init project scaffolding ────────────────────────────────────────────────

_INIT_GITIGNORE = """\
__pycache__/
*.py[cod]
.venv/
venv/
.env
data/
output/
*.db
.ipynb_checkpoints/
"""

_INIT_ENV_EXAMPLE = """\
# Copy to .env and fill in. The .env file is gitignored.
#
# python-dotenv will load these into os.environ when your scripts run if you
# call `from dotenv import load_dotenv; load_dotenv()` at the top of your app.

# Example: Postgres warehouse for SQLConnector
# TRACEBI_SALES_DB_URL=postgresql+psycopg://user:password@host:5432/sales

# Example: BigQuery
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# Optional auth for the web UI (basic auth)
# TRACEBI_AUTH_USER=admin
# TRACEBI_AUTH_PASS=changeme
"""

_INIT_SAMPLE_REQUEST = '''"""
Sample report — runs against an in-memory DataFrame so you can see TraceBi
working immediately. Replace MemoryConnector with SQLConnector / CSVConnector
once you wire your real data source (see models/ and `tracebi new-model`).

Run:
    python requests/sample_report.py
"""

import os
import pandas as pd

from tracebi import DataModel, MemoryConnector
from tracebi.reports.report import Report, TextSection, TableSection
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer


# ── 1. Connect ──────────────────────────────────────────────────────────────
orders = pd.DataFrame({
    "order_id": [1, 2, 3, 4, 5],
    "region":   ["NE", "SE", "NE", "MW", "SE"],
    "product":  ["Widget", "Gadget", "Widget", "Widget", "Gadget"],
    "revenue":  [100.0, 200.0, 150.0, 300.0, 250.0],
})

model = DataModel("Sample").add_connector(MemoryConnector("mem", {"orders": orders}))
model.add_table("orders", connector="mem", source="orders")


# ── 2. Build report ─────────────────────────────────────────────────────────
ds = model.load("orders")

report = (
    Report("Sample Report")
    .author("Your Name")
    .description("Replace this with your own data — see models/.")
    .add(TextSection(title="Summary", content="Five orders across three regions.",
                     style="heading1"))
    .add(TableSection(title="Orders", dataset=ds,
                      columns=["order_id", "region", "product", "revenue"],
                      totals=["revenue"]))
)


# ── 3. Render ───────────────────────────────────────────────────────────────

def run():
    out_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(out_dir, exist_ok=True)
    ExcelRenderer().render(report, os.path.join(out_dir, "sample_report.xlsx"))
    HTMLRenderer().render(report, os.path.join(out_dir, "sample_report.html"))
    print(f"Saved: {out_dir}/sample_report.{{xlsx,html}}")


if __name__ == "__main__":
    run()
'''


def _init_project_readme(project: str) -> str:
    return f"""\
# {project}

A TraceBi project. Scaffolded by `tracebi init`.

## Layout

```
{project}/
├── .env.example      Copy to `.env` and fill in credentials
├── models/           DataModel definitions — each .py exposes `model`
├── pipelines/        PipelineRunner definitions — each .py exposes `runner`
├── reports/          Named reports — each .py uses @register.report()
├── requests/         Ad-hoc report scripts — copy sample_report.py
├── scheduled/        Reports on a cron schedule
├── data/             Local databases / cached files (gitignored)
└── output/           Rendered reports (gitignored)
```

Everything in those four artifact directories is picked up automatically —
by `tracebi serve`, and by notebooks via `get_model()` / `get_runner()`.
There is no registration file to edit.

## Run the sample report

```bash
pip install "tracebi[analyst]"
tracebi run sample_report
open output/sample_report.html
```

## Browse in the web UI

```bash
pip install "tracebi[web]"
tracebi serve                 # http://127.0.0.1:8000
```

## Wire your own data

1. Copy `.env.example` to `.env` and add your database URL.
2. `tracebi new-model "Sales"` — edit `models/sales.py` to point at your
   connector and declare tables, dimensions, facts, and measures.
3. `tracebi validate` — confirms the model loads and its dimension keys
   are unique (a duplicate key silently inflates every total).
4. Copy `requests/sample_report.py` to `requests/my_report.py` and adapt.
5. `tracebi run my_report`.
"""


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.project).resolve()
    if target.exists() and any(target.iterdir()):
        if not args.force:
            print(
                f"refusing to init into non-empty {target}; pass --force to override",
                file=sys.stderr,
            )
            return 1

    # The four artifact directories the server auto-discovers at startup,
    # plus scheduled/. init used to create only requests/, so an init'd
    # project was structurally incompatible with `tracebi serve`.
    for d in ("models", "pipelines", "reports", "requests", "scheduled",
              "data", "output"):
        (target / d).mkdir(parents=True, exist_ok=True)

    files = {
        target / ".gitignore":              _INIT_GITIGNORE,
        target / ".env.example":            _INIT_ENV_EXAMPLE,
        target / "README.md":               _init_project_readme(target.name),
        target / "requests" / "sample_report.py": _INIT_SAMPLE_REQUEST,
    }
    # Keep the discovery directories in git even while empty, so the layout
    # survives a clone.
    for d in ("models", "pipelines", "reports", "scheduled"):
        files[target / d / ".gitkeep"] = ""

    for path, content in files.items():
        if path.exists() and not args.force:
            print(f"skipping existing {path}", file=sys.stderr)
            continue
        path.write_text(content, encoding="utf-8")

    print(f"Initialised TraceBi project at {target}")
    print(f"  cd {target.name}")
    print(f"  tracebi run sample_report     # render to output/")
    print(f"  tracebi serve                 # browse at http://127.0.0.1:8000")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    """
    Print TraceBi's vocabulary as JSON — every section and panel type with
    its fields and allowed values, the DataSet verbs, measure kinds, filter
    operators, and the discovery conventions.

    Generated from the code, so it cannot drift. Intended as context for a
    tool or agent authoring a project; add --model to include a specific
    model's tables, dimensions and declared measures.
    """
    from tracebi.capabilities import describe

    payload = describe()
    if args.model:
        from tracebi.model_registry import get_model
        try:
            payload["model"] = get_model(args.model).info()
        except (KeyError, AttributeError) as exc:
            print(f"Could not describe model '{args.model}': {exc}", file=sys.stderr)
            return 1

    print(json.dumps(payload, indent=None if args.compact else 2, default=str))
    return 0


def _load_project_models() -> dict:
    """Every model in models/, keyed by the name the spec would reference."""
    from tracebi import model_registry

    models: dict = {}
    d = _default_models_dir()
    if not d.is_dir():
        return models
    for stem in model_registry.auto_discover(str(d)):
        try:
            m = model_registry.get_model(stem)
        except Exception:  # noqa: BLE001 — validate reports load failures itself
            continue
        models[m.name] = m
        models.setdefault(stem, m)
    return models


def cmd_spec(args: argparse.Namespace) -> int:
    """
    Work with report specs — a report as JSON rather than Python.

        tracebi spec schema                 # the JSON Schema
        tracebi spec validate report.json   # check it without running it
        tracebi spec render report.json     # build and render it
    """
    from tracebi.spec import ReportSpec, json_schema

    if args.action == "schema":
        print(json.dumps(json_schema(), indent=2))
        return 0

    if not args.file:
        print(f"`tracebi spec {args.action}` needs a spec file.", file=sys.stderr)
        return 1
    path = Path(args.file)
    if not path.is_file():
        print(f"No such file: {path}", file=sys.stderr)
        return 1

    try:
        spec = ReportSpec.from_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a bad file is a user error
        print(f"{path}: could not read spec — {exc}", file=sys.stderr)
        return 1

    models = _load_project_models()
    result = spec.validate(models)

    for warn in result["warnings"]:
        print(f"· {warn}")
    for err in result["errors"]:
        print(f"✗ {err}", file=sys.stderr)
    if not result["ok"]:
        print(f"\n{len(result['errors'])} problem(s) in {path}.", file=sys.stderr)
        return 1

    if args.action == "validate":
        coverage = spec.data_coverage()
        print(f"✓ {path} is valid — {len(spec.sections)} section(s), "
              f"{coverage['with_data_ref']}/{coverage['total']} data-bearing "
              f"section(s) have a reference")
        return 0

    # render
    from tracebi.reports.html_renderer import HTMLRenderer

    report = spec.build(models)
    out = Path(args.output or f"{_slugify(spec.name)}.html")
    HTMLRenderer().render(report, str(out))
    print(f"Rendered {spec.name} → {out}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """
    Serve the current project's web UI.

    The one CLI step between an installed package and a running app.
    Artifacts are discovered from the working directory, so this is run
    from a project root — the layout ``tracebi init`` creates.
    """
    cwd = Path.cwd()
    discovered = {
        d: len([p for p in (cwd / d).glob("*.py") if not p.name.startswith("_")])
        for d in ("models", "pipelines", "reports", "requests")
        if (cwd / d).is_dir()
    }
    if not discovered:
        print(
            f"No TraceBi project found in {cwd}.\n"
            f"Expected at least one of: models/ pipelines/ reports/ requests/\n"
            f"Run `tracebi init .` to scaffold one, or cd to a project root.",
            file=sys.stderr,
        )
        return 1

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "The web UI needs the web extras. Install with:\n"
            "    pip install 'tracebi[web]'",
            file=sys.stderr,
        )
        return 1

    # The app reads artifact directories relative to the working directory,
    # so it must stay on sys.path for the discovery imports to resolve.
    sys.path.insert(0, str(cwd))

    # Don't drag the bundled demo app into someone else's project — it
    # references demo data they do not have. An app module is only needed
    # for connectors and dashboards; opt in by setting TRACEBI_APP.
    os.environ.setdefault("TRACEBI_APP", "")

    summary = ", ".join(f"{n} {d}" for d, n in discovered.items() if n) or "no artifacts yet"
    print(f"TraceBi — serving {cwd.name} ({summary})")
    print(f"  http://{args.host}:{args.port}")

    import uvicorn
    uvicorn.run(
        "web.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def cmd_new_request(args: argparse.Namespace) -> int:
    requests_dir: Path = args.requests_dir
    requests_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    suffix = ".ipynb" if args.notebook else ".py"
    out_path = requests_dir / f"{slug}{suffix}"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    if args.notebook:
        out_path.write_text(_notebook_text(args.title), encoding="utf-8")
    else:
        out_path.write_text(_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    return 0


def cmd_list_requests(args: argparse.Namespace) -> int:
    requests_dir: Path = args.requests_dir
    if not requests_dir.is_dir():
        print(f"No requests directory at {requests_dir}")
        return 0
    files = sorted(
        p for p in list(requests_dir.glob("*.py")) + list(requests_dir.glob("*.ipynb"))
        if not p.name.startswith("_")
    )
    if not files:
        print(f"No request scripts found in {requests_dir}")
        return 0
    for p in files:
        print(p.relative_to(requests_dir.parent))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    requests_dir: Path = args.requests_dir
    name = args.name
    path = _resolve_request_path(requests_dir, name)
    if path is None:
        print(f"Request not found in {requests_dir}: {name}", file=sys.stderr)
        return 1

    overrides: dict = {}
    for item in args.param or []:
        if "=" not in item:
            print(f"--param expects key=value, got: {item}", file=sys.stderr)
            return 1
        key, _, value = item.partition("=")
        overrides[key.strip()] = value

    from tracebi._params import reset_param_overrides, set_param_overrides

    print(f"Running {path}…")
    token = set_param_overrides(overrides or None)
    try:
        if path.suffix == ".ipynb":
            from tracebi._notebook import notebook_to_source
            source = notebook_to_source(path)
            ns: dict = {"__name__": "__main__", "__file__": str(path)}
            exec(compile(source, str(path), "exec"), ns)
            if callable(ns.get("run")):
                ns["run"]()
        else:
            runpy.run_path(str(path), run_name="__main__")
    finally:
        reset_param_overrides(token)
    return 0


def cmd_dev(args: argparse.Namespace) -> int:
    path = _resolve_request_path(args.requests_dir, args.name)
    if path is None:
        print(f"Request not found in {args.requests_dir}: {args.name}",
              file=sys.stderr)
        return 1
    from tracebi._dev_server import serve_dev
    return serve_dev(path, port=args.port, open_browser=not args.no_browser)


def _resolve_request_path(requests_dir: Path, name: str) -> Optional[Path]:
    """Find a request file by name, trying .py then .ipynb if no suffix given."""
    candidate = requests_dir / name
    if candidate.is_file():
        return candidate
    for suffix in (".py", ".ipynb"):
        cand = requests_dir / f"{name}{suffix}"
        if cand.is_file():
            return cand
    return None


def cmd_validate(args: argparse.Namespace) -> int:
    """
    Sanity-check the project: layout, then the models themselves.

    Layout checks are cheap file stats. The substantive part is loading each
    model in models/ and running ``DataModel.validate()``, which catches the
    failures that would otherwise surface as wrong numbers — chiefly a
    non-unique dimension key silently inflating every additive measure.
    """
    cwd = Path.cwd()
    problems: list[str] = []
    warnings: list[str] = []
    ok: list[str] = []

    requests_dir = args.requests_dir
    if requests_dir.is_dir():
        scripts = [p for p in requests_dir.glob("*.py") if not p.name.startswith("_")]
        nbs = list(requests_dir.glob("*.ipynb"))
        ok.append(f"✓ requests/ contains {len(scripts) + len(nbs)} script(s)")
    else:
        warnings.append(f"· requests/ not present at {requests_dir}")

    # ── Import every discoverable artifact and report what failed ────────
    # A file that raises on import is skipped at startup with only a
    # warning, so this is where it becomes visible.
    from tracebi.web.discovery import auto_discover, discovery_report

    for label in ("reports", "requests", "scheduled"):
        d = cwd / label
        if d.is_dir():
            auto_discover(str(d))
    for entry in discovery_report():
        if entry["status"] == "failed":
            problems.append(
                f"✗ {entry['directory']}/{entry['file']}: {entry['reason']}"
            )
    n_registered = sum(1 for e in discovery_report() if e["status"] == "registered")
    if n_registered:
        ok.append(f"✓ {n_registered} artifact module(s) imported cleanly")

    env_path = cwd / ".env"
    if env_path.is_file():
        ok.append("✓ .env file found")
    else:
        ok.append("· .env not present (only needed if you load it yourself)")

    # ── Models: load each one and check its declared structure ──────────
    models_dir = args.models_dir
    if not models_dir.is_dir():
        warnings.append(f"· models/ not present at {models_dir}")
    else:
        from tracebi import model_registry

        names = model_registry.auto_discover(str(models_dir))
        if not names:
            warnings.append("· models/ contains no model files")
        for name in names:
            try:
                model = model_registry.get_model(name)
            except Exception as exc:  # noqa: BLE001 — reported, not raised
                problems.append(f"✗ models/{name}.py failed to load: {exc}")
                continue

            result = model.validate()
            if result["ok"]:
                ndims = len(result["dimensions"])
                ok.append(f"✓ {name}: {model.name} loaded, {ndims} dimension(s) key-unique")
            else:
                for err in result["errors"]:
                    problems.append(f"✗ {name}: {err}")
            for warn in result["warnings"]:
                warnings.append(f"· {name}: {warn}")

    for line in ok:
        print(line)
    for line in warnings:
        print(line)
    for line in problems:
        print(line, file=sys.stderr)

    if problems:
        print(f"\n{len(problems)} problem(s) found.", file=sys.stderr)
        return 1
    print("\nProject looks good.")
    return 0


def cmd_new_model(args: argparse.Namespace) -> int:
    models_dir: Path = args.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    out_path = models_dir / f"{slug}.py"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    out_path.write_text(_model_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    print(f"  Edit the file, then use it with:")
    print(f"    from tracebi.model_registry import get_model")
    print(f'    model = get_model("{slug}")')
    return 0


def cmd_list_models(args: argparse.Namespace) -> int:
    models_dir: Path = args.models_dir
    if not models_dir.is_dir():
        print(f"No models directory at {models_dir}")
        return 0
    files = sorted(p for p in models_dir.glob("*.py") if not p.name.startswith("_"))
    if not files:
        print(f"No model files found in {models_dir}")
        return 0
    for p in files:
        print(p.relative_to(models_dir.parent))
    return 0


def cmd_new_pipeline(args: argparse.Namespace) -> int:
    pipelines_dir: Path = args.pipelines_dir
    pipelines_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    out_path = pipelines_dir / f"{slug}.py"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    out_path.write_text(_pipeline_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    print(f"  Edit the file, then use it with:")
    print(f"    from tracebi.pipeline_registry import get_runner")
    print(f'    runner = get_runner("{slug}")')
    return 0


def _pipeline_plan(runner) -> list[str]:
    """
    Every registered layer, upstream-first, each appearing once.

    ``execution_order`` resolves the chain for a single layer. Concatenating
    each layer's chain and keeping the first occurrence gives a valid order
    for the whole pipeline: within any chain a layer's upstreams precede it,
    and deduplicating on first sight can only move a layer earlier.
    """
    plan: list[str] = []
    for layer in runner.layers():
        for step in runner.execution_order(layer["name"]):
            if step not in plan:
                plan.append(step)
    return plan


def cmd_run_pipeline(args: argparse.Namespace) -> int:
    """
    Run a pipeline from the command line.

    This is the execution plane's entry point. Until it existed the only way
    to execute a layer was ``POST /api/pipelines/{name}/layers/{layer}/run``,
    which meant the web server had to be running — and had to be the thing
    doing the work — for any data to be produced. That is what tied batch
    execution to the serving process and made deployments where the two are
    separate (a scheduled job writing to Postgres, a stateless API reading
    from it) impossible to express. See NOTES.md, "Deployment planes".

    Any external scheduler can now drive this: cron, a Kubernetes CronJob,
    Airflow, a CI job. TraceBi does not need to own the schedule.
    """
    import getpass

    from tracebi.audit import set_actor
    from tracebi.pipeline_registry import get_runner, list_pipelines

    # Attribute CLI-driven runs too. A cron job or CI step runs as some
    # account, and "who ran this" should answer that rather than shrug at
    # everything the web UI did not trigger.
    try:
        set_actor(getpass.getuser(), role="cli")
    except Exception:  # noqa: BLE001 — no controlling user (some containers)
        set_actor(None, role="cli")

    try:
        runner = get_runner(args.name)
    except KeyError as exc:
        print(str(exc).strip("\"'"), file=sys.stderr)
        known = list_pipelines()
        if not known:
            print(f"No pipelines found in {args.pipelines_dir}. "
                  'Scaffold one with: tracebi new-pipeline "My ETL"', file=sys.stderr)
        return 1

    if args.status:
        rows = runner.layers()
        if not rows:
            print(f"Pipeline '{args.name}' has no registered layers.")
            return 0
        width = max(len(r["name"]) for r in rows)
        for r in rows:
            # layers() returns registration data only — name, type, schedule,
            # depends_on. Run status is a separate DB read per layer, which is
            # what the web router does too.
            try:
                last = runner.last_run(r["name"])
            except Exception as exc:  # noqa: BLE001
                status, when = f"error: {type(exc).__name__}", ""
            else:
                status = (last or {}).get("status") or "never run"
                when = (last or {}).get("completed_at") or (last or {}).get("started_at") or ""
            print(f"  {r['name']:<{width}}  {r['type']:<12} {status:<10} {when}")
        return 0

    if args.layer:
        if not runner.has_layer(args.layer):
            print(f"Layer '{args.layer}' is not registered in pipeline '{args.name}'. "
                  f"Available: {[r['name'] for r in runner.layers()]}", file=sys.stderr)
            return 1
        chain = runner.execution_order(args.layer) if args.refresh else [args.layer]
    else:
        chain = _pipeline_plan(runner)

    if not chain:
        print(f"Pipeline '{args.name}' has no registered layers.")
        return 0

    print(f"[tracebi] {args.name}: {' → '.join(chain)}")
    failed: list[str] = []
    for step in chain:
        try:
            runner.execute_layer(step)
        except Exception as exc:  # noqa: BLE001 — report and keep going
            # Downstream layers read what upstream wrote, so a failure part
            # way through leaves the rest resting on stale data. Report every
            # failure rather than stopping at the first, and exit non-zero so
            # whatever scheduler invoked this can act on it.
            failed.append(step)
            print(f"[tracebi] {step} FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)

    if failed:
        print(f"[tracebi] {len(failed)} of {len(chain)} layer(s) failed: "
              f"{', '.join(failed)}", file=sys.stderr)
        return 1

    print(f"[tracebi] {len(chain)} layer(s) completed.")
    return 0


def cmd_list_pipelines(args: argparse.Namespace) -> int:
    pipelines_dir: Path = args.pipelines_dir
    if not pipelines_dir.is_dir():
        print(f"No pipelines directory at {pipelines_dir}")
        return 0
    files = sorted(p for p in pipelines_dir.glob("*.py") if not p.name.startswith("_"))
    if not files:
        print(f"No pipeline files found in {pipelines_dir}")
        return 0
    for p in files:
        print(p.relative_to(pipelines_dir.parent))
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """
    Serve the agent gateway over the Model Context Protocol.

    stdio by default, which is what a locally-configured agent speaks;
    --transport http for a remote one. Models come from the same project
    conventions as every other command (./models, or TRACEBI_MODELS_DIR).
    """
    from tracebi.mcp_server import serve

    try:
        serve(transport=args.transport, port=args.port)
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


# ── Argparse wiring ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracebi",
        description="TraceBi — code-first, traceable BI.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tracebi {_tracebi_version()}",
    )
    parser.add_argument(
        "--requests-dir",
        type=Path,
        default=_default_requests_dir(),
        help="Directory holding request scripts (default: ./requests).",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=_default_models_dir(),
        help="Directory holding model definitions (default: ./models).",
    )
    parser.add_argument(
        "--pipelines-dir",
        type=Path,
        default=_default_pipelines_dir(),
        help="Directory holding pipeline definitions (default: ./pipelines).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser(
        "init",
        help="Scaffold a new TraceBi project (models/, pipelines/, reports/, "
             "sample report, .gitignore).",
    )
    p_init.add_argument("project", help="Target directory name.")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing files.")
    p_init.set_defaults(func=cmd_init)

    p_new = sub.add_parser("new-request", help="Scaffold a new request script.")
    p_new.add_argument("title", help='Free-form title, e.g. "Open orders by region".')
    p_new.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new.add_argument(
        "--notebook", action="store_true",
        help="Scaffold a Jupyter notebook (.ipynb) instead of a .py script.",
    )
    p_new.set_defaults(func=cmd_new_request)

    p_list = sub.add_parser("list-requests", help="List request scripts.")
    p_list.set_defaults(func=cmd_list_requests)

    p_run = sub.add_parser("run", help="Run a request script (.py or .ipynb).")
    p_run.add_argument("name", help="Request file name (suffix optional; tries .py then .ipynb).")
    p_run.add_argument(
        "--param", action="append", metavar="KEY=VALUE",
        help="Override a request_params() default (repeatable), "
             "e.g. --param period=2026-Q1",
    )
    p_run.set_defaults(func=cmd_run)

    p_spec = sub.add_parser(
        "spec",
        help="Work with report specs (a report as JSON): print the schema, "
             "validate a spec without running it, or render one.",
    )
    p_spec.add_argument("action", choices=["schema", "validate", "render"])
    p_spec.add_argument("file", nargs="?", help="Path to a spec .json file.")
    p_spec.add_argument("--output", help="Output path for `render`.")
    p_spec.set_defaults(func=cmd_spec)

    p_context = sub.add_parser(
        "context",
        help="Print the framework's vocabulary as JSON (section and panel "
             "types, DataSet verbs, measures, operators, conventions).",
    )
    p_context.add_argument("--model", help="Also include this model's schema.")
    p_context.add_argument("--compact", action="store_true",
                           help="Single-line JSON.")
    p_context.set_defaults(func=cmd_context)

    p_serve = sub.add_parser(
        "serve",
        help="Serve this project's web UI (models, reports, pipelines, "
             "dashboards) at http://127.0.0.1:8000.",
    )
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true",
                         help="Restart on file changes (development).")
    p_serve.set_defaults(func=cmd_serve)

    p_dev = sub.add_parser(
        "dev",
        help="Watch a request script and serve a live HTML preview that "
             "reloads on every save.",
    )
    p_dev.add_argument("name", help="Request file name (suffix optional; tries .py then .ipynb).")
    p_dev.add_argument("--port", type=int, default=8001,
                       help="Port for the preview server (default 8001).")
    p_dev.add_argument("--no-browser", action="store_true",
                       help="Do not open the browser automatically.")
    p_dev.set_defaults(func=cmd_dev)

    p_validate = sub.add_parser(
        "validate",
        help="Sanity-check the project: layout, plus load every model in "
             "models/ and verify its dimension keys are unique.",
    )
    p_validate.set_defaults(func=cmd_validate)

    p_new_model = sub.add_parser("new-model", help="Scaffold a new model definition.")
    p_new_model.add_argument("title", help='Free-form title, e.g. "Sales Model".')
    p_new_model.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new_model.set_defaults(func=cmd_new_model)

    p_list_models = sub.add_parser("list-models", help="List model definition files.")
    p_list_models.set_defaults(func=cmd_list_models)

    p_new_pipeline = sub.add_parser("new-pipeline", help="Scaffold a new pipeline definition.")
    p_new_pipeline.add_argument("title", help='Free-form title, e.g. "Sales Pipeline".')
    p_new_pipeline.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new_pipeline.set_defaults(func=cmd_new_pipeline)

    p_list_pipelines = sub.add_parser("list-pipelines", help="List pipeline definition files.")
    p_list_pipelines.set_defaults(func=cmd_list_pipelines)

    p_run_pipeline = sub.add_parser(
        "run-pipeline",
        help="Run a pipeline's layers (the execution plane — no web server needed).",
    )
    p_run_pipeline.add_argument("name", help="Pipeline name, as listed by list-pipelines.")
    p_run_pipeline.add_argument(
        "--layer",
        help="Run only this layer instead of the whole pipeline.",
    )
    p_run_pipeline.add_argument(
        "--refresh", action="store_true",
        help="With --layer, run its upstream chain first.",
    )
    p_run_pipeline.add_argument(
        "--status", action="store_true",
        help="Show each layer and its last run without executing anything.",
    )
    p_run_pipeline.set_defaults(func=cmd_run_pipeline)

    p_mcp = sub.add_parser(
        "mcp",
        help="Serve the agent gateway over the Model Context Protocol.",
    )
    p_mcp.add_argument(
        "--transport", choices=("stdio", "http"), default="stdio",
        help="stdio for a local agent (default); http for a remote one.",
    )
    p_mcp.add_argument(
        "--port", type=int, default=8765,
        help="Port for --transport http (default 8765).",
    )
    p_mcp.set_defaults(func=cmd_mcp)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
