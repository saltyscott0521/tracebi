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
import re
import runpy
import sys
from datetime import date
from pathlib import Path
from typing import Optional

try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version
except ImportError:  # pragma: no cover — Python <3.8 unsupported
    _pkg_version = None  # type: ignore
    PackageNotFoundError = Exception  # type: ignore


def _tracebi_version() -> str:
    if _pkg_version is None:
        return "unknown"
    try:
        return _pkg_version("tracebi")
    except PackageNotFoundError:
        return "unknown"


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
    .add(TextSection(title="Summary", content="Write your narrative here.", style="heading1"))
)


# ── 3. Render ───────────────────────────────────────────────────────────────

def run():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, "{slug}")
    ExcelRenderer().render(report, base + ".xlsx")
    HTMLRenderer().render(report, base + ".html")
    print(f"Saved: {{base}}.xlsx / .html")


# ── 4. Optional: expose to the web UI ──────────────────────────────────────
try:
    from tracebi.web import register

    @register.report("{slug}", description="Short description of this report.")
    def _factory():
        return report
except ImportError:
    pass


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
                    "# Pull the shared project model if the web server registered one\n",
                    "try:\n",
                    "    from tracebi.web import register\n",
                    "    model = register.get_default_model()\n",
                    "except ImportError:\n",
                    "    model = None\n",
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
                    '    .add(TextSection(title="Summary", content="Write your narrative here.", style="heading1"))\n',
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
                    "# from tracebi.web import register\n",
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

# ── Register with the web layer (optional) ───────────────────────────────────
try:
    from tracebi.web import register
    register.model(model)
except ImportError:
    pass
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

# ── Register with the web layer (optional) ───────────────────────────────────
try:
    from tracebi.web import register
    register.pipeline("{slug}", runner)
except ImportError:
    pass
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

_INIT_TRACEBI_YAML = """\
# tracebi.yaml — project configuration.
#
# Wire connectors, output destinations, and schedules here. Values of the form
# ${ENV_VAR} are interpolated from the environment (and .env via python-dotenv)
# so credentials never live in this file.

project: my_project

connectors:
  # Example: a SQLite connector backed by a local file. Swap the URL for
  # Postgres / MySQL / BigQuery / Snowflake when you wire your real data.
  sales_db:
    type: sql
    url:  ${TRACEBI_SALES_DB_URL:-sqlite:///data/sales.db}

reports:
  output_dir: output
  formats:
    - html
    - xlsx
"""

_INIT_SAMPLE_REQUEST = '''"""
Sample report — runs against an in-memory DataFrame so you can see TraceBi
working immediately. Replace MemoryConnector with SQLConnector / CSVConnector
once you wire your real data source in tracebi.yaml.

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
    .description("Replace this with your own data — see tracebi.yaml.")
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
├── tracebi.yaml      Project config (connectors, output, schedules)
├── .env.example      Copy to `.env` and fill in credentials
├── requests/         Report scripts — copy sample_report.py to add more
├── data/             Local databases / cached files (gitignored)
└── output/           Rendered reports (gitignored)
```

## Run the sample report

```bash
pip install "tracebi[analyst]"
tracebi run sample_report
open output/sample_report.html
```

## Wire your own data

1. Copy `.env.example` to `.env` and add your database URL.
2. Edit `tracebi.yaml` to point at your connector.
3. Copy `requests/sample_report.py` to `requests/my_report.py` and adapt.
4. `tracebi run my_report`.
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

    (target / "requests").mkdir(parents=True, exist_ok=True)
    (target / "data").mkdir(exist_ok=True)
    (target / "output").mkdir(exist_ok=True)

    files = {
        target / ".gitignore":              _INIT_GITIGNORE,
        target / ".env.example":            _INIT_ENV_EXAMPLE,
        target / "tracebi.yaml":            _INIT_TRACEBI_YAML,
        target / "README.md":               _init_project_readme(target.name),
        target / "requests" / "sample_report.py": _INIT_SAMPLE_REQUEST,
    }
    for path, content in files.items():
        if path.exists() and not args.force:
            print(f"skipping existing {path}", file=sys.stderr)
            continue
        path.write_text(content, encoding="utf-8")

    print(f"Initialised TraceBi project at {target}")
    print(f"  cd {target.name} && tracebi run sample_report")
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
    cwd = Path.cwd()
    problems: list[str] = []
    ok: list[str] = []

    yaml_path = cwd / "tracebi.yaml"
    if yaml_path.is_file():
        ok.append(f"✓ tracebi.yaml found at {yaml_path}")
    else:
        problems.append("✗ tracebi.yaml not found in current directory")

    requests_dir = args.requests_dir
    if requests_dir.is_dir():
        scripts = [p for p in requests_dir.glob("*.py") if not p.name.startswith("_")]
        ok.append(f"✓ requests/ contains {len(scripts)} script(s)")
    else:
        problems.append(f"✗ requests/ directory missing at {requests_dir}")

    env_path = cwd / ".env"
    if env_path.is_file():
        ok.append("✓ .env file found")
    else:
        ok.append("· .env not present (only needed if you use ${ENV_VAR} interpolation)")

    for line in ok:
        print(line)
    for line in problems:
        print(line, file=sys.stderr)

    return 0 if not problems else 1


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
        help="Scaffold a new TraceBi project (tracebi.yaml, .env.example, "
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
        help="Sanity-check the current directory: tracebi.yaml, requests/, .env.",
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

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
