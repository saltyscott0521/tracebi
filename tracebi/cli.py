"""
TraceBi CLI.

Scaffolds and drives a project through the three-phase workflow — TRANSFORM
(``transforms/``) → MODEL (``models/``) → REPORT (``reports/``):

    tracebi init my_project                 # scaffold a new project
    tracebi run-transform <name>            # ① run a transform → sink the warehouse
    tracebi new-model "Sales Model"         # ② scaffold a model over the warehouse
    tracebi report build <name>             # ③ render an artifact package + receipt
    tracebi verify <manifest>               # re-run recorded queries; classify drift
    tracebi serve                           # browse the project
    tracebi mcp                             # agent gateway over MCP
    tracebi --version

Run ``tracebi --help`` for the full command list. The CLI stays thin — it
scaffolds files and drives the library; the behaviour lives in the library.
Its scaffold templates are data files under ``tracebi/_scaffold/`` (loaded by
:func:`_scaffold_text`), not inline string constants.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import runpy
import sys
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Optional

from tracebi._version import get_version as _tracebi_version


# Resolve the project folders relative to the user's current working
# directory by default, honouring the same TRACEBI_*_DIR env vars the server
# and gateway read (so the CLI and the server agree on where a project
# lives). Override per-invocation with the --*-dir flags.
def _scaffold_text(name: str) -> str:
    """Read a bundled scaffold template from ``tracebi/_scaffold/``.

    The init/new-report templates live as data files there rather than as
    inline string constants, so they read and diff as the file type they
    are. Anchored on the ``tracebi`` package so it resolves in a wheel.
    """
    return files("tracebi").joinpath("_scaffold", name).read_text(encoding="utf-8")


def _default_models_dir() -> Path:
    return Path(os.environ.get("TRACEBI_MODELS_DIR", "models"))


def _default_pipelines_dir() -> Path:
    return Path(os.environ.get("TRACEBI_PIPELINES_DIR", "pipelines"))


def _default_reports_dir() -> Path:
    return Path(os.environ.get("TRACEBI_REPORTS_DIR", "reports"))


def _default_transforms_dir() -> Path:
    return Path(os.environ.get("TRACEBI_TRANSFORMS_DIR", "transforms"))


def _slugify(title: str) -> str:
    """Convert "Open orders by region" → "open_orders_by_region"."""
    s = title.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "report"


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

import os

from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector
# from tracebi import CSVConnector, SQLConnector, MemoryConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Connectors ───────────────────────────────────────────────────────────────
# Default: the warehouse your phase-① transforms sink into. Swap for
# SQLConnector("{slug}_db", url=os.environ["{slug}_DB_URL".upper()]) etc. to
# model a database directly.
connector = DuckDBConnector("warehouse",
                            database=os.path.join(ROOT, "data", "warehouse.duckdb"))

# ── Model ─────────────────────────────────────────────────────────────────────
# The variable MUST be named `model` — the registry looks for it at load time.
model = DataModel("{model_name}")
model.add_connector(connector)
model.add_table("my_table", connector="warehouse", source="my_table")
# model.add_relationship(
#     name="orders_customers",
#     left_table="orders", right_table="customers", left_key="customer_id",
# )
# model.add_dimension("dim_customer", table_name="customers", key_col="customer_id",
#                     attributes=["region", "segment"])
# model.add_fact("fact_orders", table_name="orders", measures=["revenue", "qty"],
#                foreign_keys={{"dim_customer": "customer_id"}})

# Construction is declarative and lazy: importing this file must not touch
# the database (discovery imports every model file, and a connect here would
# open a connection — or fail outright — on every scan). A query is what
# connects. Do not call model.connect() at import time.

# Files in models/ are auto-discovered — by the web server, and by
# `get_model("{slug}")` from notebooks and scripts. An explicit
# `register.model(model)` is only needed for files living OUTSIDE models/.
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


def _transform_template_text(title: str) -> str:
    today = date.today().isoformat()
    slug = _slugify(title)
    return f'''\
"""
{title}
{'=' * len(title)}

Phase ① — TRANSFORM. Scaffolded by ``tracebi new-transform`` on {today}.

Ordinary, unconstrained pandas: read the raw pull, do whatever the data
needs — window functions, prose parsing, cleaning, dedupe — then SINK the
clean, star-shaped result into the warehouse. The framework does not
constrain this phase; the contract is not *how* you clean, it is *what
lands* — the named tables at the bottom of this file. Phase ② (models/)
reads those tables and never sees this code.

    python transforms/{slug}.py

Keep it idempotent: a rerun replaces the warehouse tables.
"""

from __future__ import annotations

import os

import pandas as pd

from tracebi.connectors.duckdb_connector import DuckDBConnector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WAREHOUSE = os.path.join(ROOT, "data", "warehouse.duckdb")


# This file is notebook-shaped: the `# %%` markers below are cell
# boundaries, and `# %% [markdown]` cells are prose. VS Code, Cursor,
# PyCharm, and Jupyter (via jupytext) open it AS a notebook — collapse
# cells, run cell-by-cell, write markdown beside code — while the file
# stays plain, reviewable Python that runs top-to-bottom with
# `python transforms/{slug}.py`. While `tracebi dev` serves, any cell can
# `tracebi.workbench.show(df, note=...)` to put its output in the portal.

# %% [markdown]
# ## Methodology
#
# Narrate the cleaning here — what gets dropped and why, how keys are
# chosen. Distill the load-bearing claims into the sink contract's
# `note=` at the bottom; they travel with the certificate.

# %%  Read the raw input (inputs/, an API pull, a SQL export…)
# df = pd.read_csv(os.path.join(ROOT, "inputs", "orders.csv"))  # ← your raw pull

# %%  Clean — any pandas you like; none of this is traced, by design
# df = df.dropna(subset=["id"]).drop_duplicates(subset=["id"])

# %%  Shape into star-schema tables (facts keyed to dimensions)
# dim_x = df[["x"]].drop_duplicates().rename_axis("x_id").reset_index()
# fact = df.merge(dim_x, on="x")[["id", "x_id", "value"]]

# %%  Sink — the contract: these named tables are what phase ② models
os.makedirs(os.path.dirname(WAREHOUSE), exist_ok=True)
wh = DuckDBConnector("warehouse", database=WAREHOUSE)
# wh.write(dim_x, "dim_x")
# wh.write(fact, "fact_{slug}")

# %%  Declare the sink CONTRACT (optional, recommended)
# Read-only SQL checks on what just landed, recorded beside the warehouse.
# A failed check raises; note= carries your stated methodology into the
# certificate. This certifies the SINK, never the pandas above.
# from tracebi.contracts import contract
# with contract("{slug}", warehouse=WAREHOUSE,
#               note="stated methodology: what was dropped, and why") as c:
#     c.rows("fact_{slug}", at_least=1)
#     c.unique("dim_x", ["x_id"])
#     c.not_null("fact_{slug}", ["id", "value"])
#     c.foreign_key("fact_{slug}", "x_id", refers_to=("dim_x", "x_id"))

# %%
print(f"sunk → {{WAREHOUSE}}")
'''


# ── init project scaffolding ────────────────────────────────────────────────

_INIT_GITIGNORE = _scaffold_text("init_gitignore.txt")

_INIT_ENV_EXAMPLE = _scaffold_text("init_env_example.txt")

_INIT_SAMPLE_CSV = _scaffold_text("init_sample_orders.csv")

_INIT_SAMPLE_TRANSFORM = _scaffold_text("init_sample_transform.py.txt")

_INIT_SAMPLE_MODEL = _scaffold_text("init_sample_model.py.txt")

# The sample report is an ARTIFACT PACKAGE — the one report lane — so the
# first page a new project renders demonstrates the real product: figure
# claims, the presentation stack, provenance badges, and a receipt that
# joins the sink contract. (A JSON spec still renders and `tracebi migrate
# spec` compiles one, but the scaffold must not teach the legacy form.)
_INIT_SAMPLE_REPORT_JSON = _scaffold_text("init_sample_report.json")

_INIT_SAMPLE_TEMPLATE_HTML = _scaffold_text("init_sample_template.html")

def _init_project_readme(project: str) -> str:
    return f"""\
# {project}

A TraceBi project. Scaffolded by `tracebi init`.

TraceBi is the trust layer for AI-generated analytics: work moves through
three phases, and from the model boundary onward every number carries a
receipt you can re-check.

```
⓪  INPUT       inputs/       raw pulls land here (API export · CSV · SQL dump)
①  TRANSFORM   transforms/   unconstrained pandas → SINK star tables
                                      ── freeze: data/warehouse.duckdb ──
②  MODEL       models/       a declarative star schema over the sink
                                      ── freeze: the model (the contract) ──
③  REPORT      reports/      artifact packages whose every figure claims a binding
```

## Install

TraceBi is not on PyPI — install it from GitHub:

```bash
pip install "tracebi[analyst] @ git+https://github.com/saltyscott0521/tracebi"
```

For the web UI and REST API as well (in addition to the analyst extras):

```bash
pip install "tracebi[analyst,web] @ git+https://github.com/saltyscott0521/tracebi"
```

(That install carries the API; the built React bundle is not in the repo the
installer builds from, so `/` explains how to build it. Every `/api/...`
route works either way.)

## Run the whole loop now

The scaffold is a complete working example — messy input included:

```bash
python transforms/sample_transform.py       # ① clean + sink → data/warehouse.duckdb
tracebi report build sample_dashboard       # ③ render → output/sample_dashboard.html + receipt
tracebi verify output/sample_dashboard.html.manifest.json   # every checked section: REPRODUCES
tracebi serve                               # browse it at http://127.0.0.1:8000
```

That last `verify` is the point: it re-runs the recorded queries against the
model and confirms the rendered numbers still reproduce. Every number drawn
through the model has a receipt; anything else must be marked as not having
one.

## Layout

```
{project}/
├── inputs/           Phase ⓪ — raw pulls (orders.csv is the sample)
├── transforms/       Phase ① — pandas that reads inputs/, sinks star tables
├── models/           Phase ② — each .py exposes `model` (a DataModel)
├── reports/          Phase ③ — ReportSpec .json, packages, and factories
├── pipelines/        PipelineRunner definitions — each .py exposes `runner`
├── scheduled/        Reports on a cron schedule
├── data/             The warehouse (gitignored)
├── output/           Rendered reports; *.manifest.json receipts stay tracked
└── .env.example      Copy to `.env` and fill in credentials
```

Everything in the artifact directories is discovered automatically — by
`tracebi serve`, and by notebooks via `get_model()` / `get_runner()`. There
is no registration file to edit.

Run `git init && git add . && git commit -m init` — manifests stamp the
commit (`git_sha`), which
is half the audit story.

## Wire your own data

1. Copy `.env.example` to `.env` and add your database URL.
2. Drop a raw pull in `inputs/` (or query it in your transform directly).
3. `tracebi new-transform "Orders Clean"` — write the pandas; end by sinking
   named tables to the warehouse. The framework does not constrain this
   phase; the contract is what lands.
4. `tracebi new-model "Sales"` — declare the star schema over those tables.
   `tracebi validate` confirms it loads and its dimension keys are unique.
5. Copy `reports/sample_dashboard/` (or `tracebi new-report "My Report"`),
   point its `report.json` bindings at your model, and put figures in the
   template: `data-tb-figure` + `data-tb-binding` on any element — spans in
   prose included. `tracebi dev my_report` opens the live loop (edit, watch,
   pin). Exploration happens *inside* the artifact — blocks marked
   `data-tb-stage="exploration"` die at the final build.

## Agents

The same contracts drive the agent surface: `tracebi context` emits the
vocabulary as JSON, `tracebi mcp` opens the gateway (validate a spec, query
a model, render, verify — read-and-compute only). An agent and an analyst
author against the same model and produce the same receipts. **`AGENTS.md`
in this project orients an AI agent working here** — point a fresh session at
it (most coding agents read it automatically).
"""


_INIT_AGENTS_MD = _scaffold_text("init_agents.md")


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

    # The full three-phase layout: the workflow folders (inputs/, transforms/)
    # plus every directory the server auto-discovers at startup. The scaffold
    # is a complete working example — the first thing a new user runs ends
    # with `tracebi verify` reading REPRODUCES.
    # No requests/ — the exploration story is the artifact's own:
    # `tracebi dev` + exploration blocks that die at build (architecture v2 §7).
    for d in ("inputs", "transforms", "models", "pipelines", "reports",
              "scheduled", "data", "output"):
        (target / d).mkdir(parents=True, exist_ok=True)

    files = {
        target / ".gitignore":              _INIT_GITIGNORE,
        target / ".env.example":            _INIT_ENV_EXAMPLE,
        target / "README.md":               _init_project_readme(target.name),
        target / "AGENTS.md":               _INIT_AGENTS_MD,
        target / "inputs" / "orders.csv":   _INIT_SAMPLE_CSV,
        target / "transforms" / "sample_transform.py": _INIT_SAMPLE_TRANSFORM,
        target / "models" / "sample_model.py": _INIT_SAMPLE_MODEL,
        target / "reports" / "sample_dashboard" / "report.json":
            _INIT_SAMPLE_REPORT_JSON,
        target / "reports" / "sample_dashboard" / "template.html":
            _INIT_SAMPLE_TEMPLATE_HTML,
    }
    # Keep the still-empty discovery directories in git so the layout
    # survives a clone.
    for d in ("pipelines", "scheduled"):
        files[target / d / ".gitkeep"] = ""

    for path, content in files.items():
        if path.exists() and not args.force:
            print(f"skipping existing {path}", file=sys.stderr)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(f"Initialised TraceBi project at {target}")
    print(f"  cd {target.name}")
    print(f"  git init && git add . && git commit -m init   # manifests stamp the commit (git_sha)")
    print(f"  python transforms/sample_transform.py  # ① clean + sink the sample input")
    print(f"  tracebi report build sample_dashboard  # ③ render + receipt")
    print(f"  tracebi verify output/sample_dashboard.html.manifest.json")
    print(f"  tracebi serve                          # browse at http://127.0.0.1:8000")
    print(f"AGENTS.md orients an AI agent working in this project.")
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

    payload = describe(brief=getattr(args, "brief", False))
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

    # render — one report form: compile the spec to the artifact package and
    # render it like a hand-authored package, so it gets figures, badges, the
    # receipt drawer, and a schema-2 manifest instead of the legacy bare HTML.
    import tempfile

    from tracebi.reports.compile_spec import compile_spec
    from tracebi.reports.template_package import TemplatePackage

    compiled = compile_spec(
        spec,
        theme_css=_report_theme_css(spec, extra_theme=getattr(args, "theme", None)),
        script_js=_report_script_js(spec),
    )
    out = Path(args.output or f"{_slugify(spec.name)}.html")
    with tempfile.TemporaryDirectory() as d:
        for fname, content in compiled.files.items():
            (Path(d) / fname).write_text(content, encoding="utf-8")
        TemplatePackage(d).render(models, str(out))
    for warning in compiled.warnings:
        print(f"  · {warning}")
    print(f"Rendered {spec.name} → {out}")
    return 0


def _web_app_importable() -> bool:
    """True when the FastAPI app package can be imported.

    ``tracebi serve`` boots ``tracebi.web.api.main:app``. The wheel ships that
    package, but an install predating the move out of the top-level ``web``
    package does not — checked up front so the failure is an actionable
    message instead of uvicorn's ModuleNotFoundError mid-boot. (The web app is
    not the same thing as the built UI: a wheel can ship the app with no
    bundle, which boots and explains itself at ``/``.)
    """
    import importlib.util

    try:
        return importlib.util.find_spec("tracebi.web.api.main") is not None
    except ImportError:
        return False


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
        for d in ("models", "pipelines", "reports")
        if (cwd / d).is_dir()
    }
    if not discovered:
        print(
            f"No TraceBi project found in {cwd}.\n"
            f"Expected at least one of: models/ pipelines/ reports/\n"
            f"Run `tracebi init .` to scaffold one, or cd to a project root.",
            file=sys.stderr,
        )
        return 1

    # The app reads artifact directories relative to the working directory,
    # so it must stay on sys.path for the discovery imports to resolve.
    # Inserted before the checks below so a checkout in cwd counts as one.
    sys.path.insert(0, str(cwd))

    if not _web_app_importable():
        print(
            "tracebi serve: the web app (tracebi.web.api) is not importable.\n"
            "Current wheels ship it inside the `tracebi` package; an install\n"
            "predating the move shipped it as a top-level `web` package.\n"
            "Upgrade, or run `tracebi serve` from a clone of the repo:\n"
            "    git clone https://github.com/saltyscott0521/tracebi\n"
            "or point PYTHONPATH at an existing checkout:\n"
            "    PYTHONPATH=/path/to/tracebi-checkout tracebi serve\n"
            "(TraceBi is not on PyPI; the library installs with:\n"
            '    pip install "tracebi[web] @ git+https://github.com/saltyscott0521/tracebi")',
            file=sys.stderr,
        )
        return 1

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "The web UI needs the web extras. TraceBi is not on PyPI —\n"
            "install from the repo:\n"
            '    pip install "tracebi[web] @ git+https://github.com/saltyscott0521/tracebi"',
            file=sys.stderr,
        )
        return 1

    # Don't drag the bundled demo app into someone else's project — it
    # references demo data they do not have. An app module is only needed
    # for connectors; opt in by setting TRACEBI_APP.
    os.environ.setdefault("TRACEBI_APP", "")

    summary = ", ".join(f"{n} {d}" for d, n in discovered.items() if n) or "no artifacts yet"
    print(f"TraceBi — serving {cwd.name} ({summary})")
    print(f"  http://{args.host}:{args.port}")

    import uvicorn
    uvicorn.run(
        "tracebi.web.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def cmd_dev(args: argparse.Namespace) -> int:
    # An artifact package under reports/ gets the artifact-native live loop with
    # the workbench. No name at all is DISCOVERY MODE — no report anchored, the
    # project-level workbench (warehouse, models, packages, exhibit feed) for
    # phases ① and ②.
    from tracebi._dev_server import serve_dev
    if args.name is None:
        return serve_dev(None, port=args.port,
                         open_browser=not args.no_browser)
    pkg_dir = _default_reports_dir() / args.name
    if (pkg_dir / "report.json").is_file() and \
            (pkg_dir / "template.html").is_file():
        return serve_dev(pkg_dir, port=args.port,
                         open_browser=not args.no_browser)
    print(f"Report package not found: {args.name}. Expected a package at "
          f"{pkg_dir} (report.json + template.html). Scaffold one with "
          f"`tracebi new-report`.", file=sys.stderr)
    return 1


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

    # ── Import every discoverable artifact and report what failed ────────
    # A file that raises on import is skipped at startup with only a
    # warning, so this is where it becomes visible.
    from tracebi.web.discovery import auto_discover, discovery_report

    for label in ("reports", "scheduled"):
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


def cmd_run_transform(args: argparse.Namespace) -> int:
    """
    Execute a phase-① transform — ``.py`` or ``.ipynb`` — top-to-bottom in
    a FRESH namespace.

    ``python transforms/<name>.py`` works for scripts already; this verb
    adds the notebook form and, for both, the honesty guarantee that
    matters at the sink: the warehouse comes from a clean top-to-bottom
    execution of the committed file, never from out-of-order kernel state.
    Transforms may be notebook-shaped ``.py`` (``# %%`` cells — every
    notebook editor opens them as notebooks) or literal ``.ipynb``, whose
    code cells are concatenated in order and executed fresh.
    """
    tdir = Path(os.environ.get("TRACEBI_TRANSFORMS_DIR", "transforms"))
    candidates = [tdir / args.name, tdir / f"{args.name}.py",
                  tdir / f"{args.name}.ipynb"]
    path = next((c for c in candidates if c.is_file()), None)
    if path is None:
        print(f"transform not found in {tdir}: {args.name}", file=sys.stderr)
        return 1
    print(f"Running {path} (top-to-bottom, fresh namespace)…")
    if path.suffix == ".ipynb":
        from tracebi._notebook import notebook_to_source
        source = notebook_to_source(path)
        ns: dict = {"__name__": "__main__", "__file__": str(path)}
        exec(compile(source, str(path), "exec"), ns)
    else:
        runpy.run_path(str(path), run_name="__main__")
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


def cmd_new_transform(args: argparse.Namespace) -> int:
    transforms_dir: Path = args.transforms_dir
    transforms_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    out_path = transforms_dir / f"{slug}.py"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    out_path.write_text(_transform_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    print(f"  Write the pandas, end by sinking named tables, then run it:")
    print(f"    python {out_path}")
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

    The http transport refuses to start until an auth decision is made:
    set TRACEBI_MCP_TOKEN (bearer auth) or pass --insecure explicitly.
    """
    from tracebi.mcp_server import GatewayAuthError, serve

    try:
        serve(transport=args.transport, port=args.port,
              insecure=args.insecure)
    except (ImportError, GatewayAuthError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


def cmd_verify_file(args: argparse.Namespace) -> int:
    """
    Offline check of a self-contained report ``.html`` (architecture §3.2).

    Recovers the exact fingerprinted bytes from every embedded data block and
    rehashes them — no model, no DataFrame rebuild — against a sibling
    ``<file>.manifest.json``. Catches a number edited in the shipped file, which
    ``verify <manifest>`` (query → model) cannot see. Exit 0 only when every
    embedded block matches the manifest.
    """
    from tracebi.verify import (
        FIGURE_MATCHES, FIGURE_UNVERIFIED_MARK, FILE_FIGURE_LABELS,
        FILE_MATCHES, FILE_STATUS_LABELS, REFUSED_SNAPSHOT, verify_file,
    )

    html_path = Path(args.verify_file)
    if not html_path.is_file():
        print(f"report file not found: {html_path}", file=sys.stderr)
        return 1

    manifest_path = (
        Path(args.file_manifest) if getattr(args, "file_manifest", None)
        else html_path.with_name(html_path.name + ".manifest.json")
    )
    if not manifest_path.is_file():
        print(f"no manifest found next to the report: expected {manifest_path}\n"
              "(pass --manifest <path> to point at it explicitly)",
              file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"manifest is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(manifest, dict):
        print(f"manifest must be a JSON object, got {type(manifest).__name__}",
              file=sys.stderr)
        return 1

    html = html_path.read_text(encoding="utf-8")
    result = verify_file(html, manifest)

    # A refused snapshot prints only the refusal — a header and "0 bindings
    # checked" would read like a check that ran and found little, and this
    # one deliberately did not run at all.
    if result["verdict"] == REFUSED_SNAPSHOT:
        print(result["verdict_detail"], file=sys.stderr)
        return result["exit_code"]

    name = result["report_name"] or html_path.name
    print(f"Verifying embedded data in '{name}' ({html_path})")
    print(f"  against manifest {manifest_path}")
    width = max(len(v) for v in FILE_STATUS_LABELS.values())
    for b in result["bindings"]:
        status = b["status"]
        mark = "✓" if status == FILE_MATCHES else "✗"
        line = f"{mark} {FILE_STATUS_LABELS[status]:<{width}}  {b['binding']}"
        if status != FILE_MATCHES:
            line += f" — {b['detail']}"
        print(line, file=sys.stdout if mark != "✗" else sys.stderr)

    # Figure cross-check rows (manifest schema 2) — the claims layer, so a
    # failure names the figure, not just the verdict.
    if result.get("figures"):
        fwidth = max(len(v) for v in FILE_FIGURE_LABELS.values())
        print()
        for f in result["figures"]:
            status = f["status"]
            ok = status in (FIGURE_MATCHES, FIGURE_UNVERIFIED_MARK)
            mark = "✓" if status == FIGURE_MATCHES else "·" if ok else "✗"
            line = (f"{mark} {FILE_FIGURE_LABELS[status]:<{fwidth}}  "
                    f"{f.get('figure')}")
            if not ok:
                line += f" — {f['detail']}"
            print(line, file=sys.stdout if mark != "✗" else sys.stderr)

    counts = ", ".join(
        f"{n} {FILE_STATUS_LABELS[status].lower()}"
        for status, n in result["summary"].items() if n
    ) or "no embedded data blocks"
    print(f"\n{len(result['bindings'])} binding(s) checked: {counts}")
    print(result["verdict_detail"],
          file=sys.stdout if result["exit_code"] == 0 else sys.stderr)
    return result["exit_code"]


def cmd_verify(args: argparse.Namespace) -> int:
    """
    Re-verify a rendered manifest: the other half of the stamp.

    Every recorded query in the manifest is re-run against the project's
    models and classified — REPRODUCES, SOURCE DRIFT (result differs and
    an input fingerprint moved), MODEL CHANGED (a table now loads from a
    different source/connector — a governance event), UNEXPLAINED (result
    differs but the inputs did not — the alarming case), or UNVERIFIABLE
    (no recorded query to re-run). One line per section, then a summary
    and the receipt-level verdict.

    Exit codes: 0 all reproduce/unverifiable · 2 diagnosed drift only ·
    1 anything unexplained, of unknown cause, errored, or a manifest with
    no data-bearing section at all (nothing was verified, so nothing passed).
    """
    from tracebi.verify import (
        FIGURE_STATUS_LABELS, REPRODUCES, STATUS_LABELS, UNVERIFIABLE,
        UNVERIFIED, load_models, verify_manifest,
    )

    # Two distinct checks under one verb (architecture §4). `--file` opens the
    # shipped .html and rehashes its embedded bytes against a sibling manifest
    # (embedded bytes → manifest); it never touches a model. The positional
    # `manifest` re-runs recorded queries (query → model). Neither implies the
    # other, so they are kept apart rather than merged.
    if getattr(args, "verify_file", None) is not None:
        return cmd_verify_file(args)
    if not args.manifest:
        print("verify: provide a manifest path, or --file <report.html>",
              file=sys.stderr)
        return 1

    path = Path(args.manifest)
    if not path.is_file():
        print(f"manifest not found: {path}", file=sys.stderr)
        return 1
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"manifest is not valid JSON: {exc}", file=sys.stderr)
        return 1
    if not isinstance(manifest, dict):
        print(f"manifest must be a JSON object, got {type(manifest).__name__}",
              file=sys.stderr)
        return 1

    models = load_models(args.verify_models_dir or args.models_dir)
    try:
        result = verify_manifest(manifest, models,
                                 strict=getattr(args, "strict", False))
    except Exception as exc:  # noqa: BLE001 — a corrupt receipt is a user error
        print(f"manifest could not be verified: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1
    if result.get("error"):
        print(result["error"], file=sys.stderr)
        return result["exit_code"]

    name = result["report_name"] or path.name
    print(f"Verifying '{name}' ({path})")
    width = max(len(v) for v in STATUS_LABELS.values())
    for s in result["sections"]:
        status = s["status"]
        mark = ("✓" if status == REPRODUCES
                else "·" if status == UNVERIFIABLE
                else "✗")
        line = f"{mark} {STATUS_LABELS[status]:<{width}}  {s['section']}"
        if status != REPRODUCES:
            line += f" — {s['detail']}"
        print(line, file=sys.stdout if mark != "✗" else sys.stderr)

    counts = ", ".join(
        f"{n} {STATUS_LABELS[status].lower()}"
        for status, n in result["summary"].items() if n
    ) or "no data-bearing sections"
    print(f"\n{len(result['sections'])} section(s) checked: {counts}")

    # Figure rollup (manifest schema 2): the claims layer, figures first.
    if result.get("figures"):
        fwidth = max(len(v) for v in FIGURE_STATUS_LABELS.values())
        print()
        for f in result["figures"]:
            status = f["status"]
            mark = ("✓" if status == REPRODUCES
                    else "·" if status in (UNVERIFIABLE, UNVERIFIED)
                    else "✗")
            line = (f"{mark} {FIGURE_STATUS_LABELS[status]:<{fwidth}}  "
                    f"{f['figure']}")
            if status != REPRODUCES:
                line += f" — {f['detail']}"
            print(line, file=sys.stdout if mark != "✗" else sys.stderr)

    exit_code = result["exit_code"]

    # The phase-① claim, reported beside the figure claims — never blended
    # (v2 §2.6). The recorded block says what the warehouse certified about
    # itself at BUILD time; it is informational here and moves no exit code.
    recorded_contracts = manifest.get("transform_contracts")
    if recorded_contracts:
        print("\nsink contracts (recorded at build):")
        for table, rec in sorted(recorded_contracts.items()):
            status = rec.get("status", "?")
            mark = "✓" if status == "satisfied" else "·"
            line = f"{mark} {status:<12} {table}"
            if status == "satisfied":
                line += f" — {rec.get('checks', 0)} check(s), transform '{rec.get('transform')}'"
            elif status == "stale":
                line += (f" — re-sunk after transform '{rec.get('transform')}' "
                         f"checked it; the certificate no longer describes "
                         f"this data")
            print(line)

    # --contracts: re-run the recorded checks against the CURRENT warehouse.
    # This is its own claim with its own exit: a check failing NOW means the
    # sink no longer satisfies its declared contract. It never says the
    # transform was verified, and it never colors a figure status.
    if getattr(args, "contracts", False):
        from tracebi.contracts import rerun_checks
        warehouses = sorted({
            c.database for m in models.values() for c in m.connectors()
            if isinstance(getattr(c, "database", None), str)
            and c.database != ":memory:"
            and type(c).__name__ == "DuckDBConnector"
        })
        rows = [r for wh in warehouses for r in rerun_checks(wh)]
        print("\nsink contracts (re-run now):")
        if not rows:
            print("· no contract record found beside the warehouse")
        failed_now = 0
        for r in rows:
            ok = r.get("passed_now")
            mark = "✓" if ok else "✗"
            desc = f"{r['check']}({r['table']}, {r.get('params')})"
            line = f"{mark} {'satisfied' if ok else 'VIOLATED':<12} {r['transform']}: {desc}"
            if not ok:
                line += f" — observed {r.get('observed_now', r.get('note'))}"
                failed_now += 1
            print(line, file=sys.stdout if ok else sys.stderr)
        if failed_now:
            print(f"{failed_now} check(s) the sink no longer satisfies.",
                  file=sys.stderr)
            exit_code = 1

    # Routed by exit code, not by verdict: a run that exits 0 must write
    # nothing to stderr, or CI wrappers that treat stderr as failure will
    # fail a receipt this command just called fine.
    print(result["verdict_detail"],
          file=sys.stdout if exit_code == 0 else sys.stderr)
    return exit_code


def cmd_migrate(args: argparse.Namespace) -> int:
    """
    ``tracebi migrate spec <file.json>`` — compile a JSON spec into an
    artifact package directory beside it.

    Emits alongside, never replaces: ``reports/sales.json`` compiles to
    ``reports/sales/``, sharing the stem — and at discovery the artifact
    directory *shadows* the same-named spec (with a warning naming both),
    so the migration is a cutover the moment the directory exists, and a
    rollback is deleting it. The spec's ``theme``/``script`` files compile
    into the package's ``style.css``/``script.js``.
    """
    from tracebi.reports.compile_spec import compile_spec
    from tracebi.spec import ReportSpec

    src = Path(args.path)
    if not src.is_file():
        print(f"spec not found: {src}", file=sys.stderr)
        return 1
    try:
        spec = ReportSpec.from_json(src.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a bad spec is a user error
        print(f"cannot read spec: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    # theme/script are filenames resolved against the reports directory —
    # the directory the spec itself lives in.
    theme_css, script_js = "", ""
    for field_name, value in (("theme", spec.theme), ("script", spec.script)):
        if not value:
            continue
        ref = src.parent / value
        if ref.is_file():
            content = ref.read_text(encoding="utf-8")
            if field_name == "theme":
                theme_css = content
            else:
                script_js = content
        else:
            print(f"warning: {field_name} file '{value}' not found beside the "
                  f"spec — not compiled in", file=sys.stderr)

    compiled = compile_spec(spec, theme_css=theme_css, script_js=script_js)

    target = src.parent / src.stem
    if target.exists() and not args.force:
        print(f"target already exists: {target}\n"
              f"Pass --force to overwrite it.", file=sys.stderr)
        return 1
    target.mkdir(parents=True, exist_ok=True)
    for fname, content in compiled.files.items():
        (target / fname).write_text(content, encoding="utf-8")

    print(f"Compiled {src.name} → {target}/")
    for fname in compiled.files:
        print(f"  {fname}")
    for w in compiled.warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"\nThe artifact now shadows the spec at discovery (delete the "
          f"directory to roll back). Next:\n"
          f"  tracebi report build {src.stem}\n"
          f"  tracebi dev {src.stem}")
    return 0


# ── Report generator: new-report / report build|preview ────────────────────

def _scaffold_binding() -> tuple[str, dict, str]:
    """A concrete ``(model_name, query_dict, note)`` for a starter package.

    So ``tracebi new-report`` renders out of the box, the query is derived from
    the first model in ``models/``: its first fact, first measure, and — when
    the model has one — a dimension attribute to slice by. With no model yet,
    a placeholder is emitted and the note tells the author to point it at one.
    """
    models = _load_project_models()
    for name, model in sorted(models.items()):
        try:
            info = model.info()
        except Exception:  # noqa: BLE001 — an unloadable model is not a scaffold source
            continue
        facts = info.get("facts") or []
        measures = info.get("measures") or []
        if not facts or not measures:
            continue
        query: dict = {"fact": facts[0]["name"],
                       "measures": [measures[0]["name"]]}
        dims = info.get("dimensions") or []
        for d in dims:
            if d.get("attributes"):
                query["dimensions"] = [f"{d['name']}.{d['attributes'][0]}"]
                break
        return info.get("name", name), query, ""
    return (
        "your_model",
        {"fact": "your_fact", "measures": ["your_measure"],
         "dimensions": ["your_dimension.attribute"]},
        "No model found in models/ — edit report.json's 'data' block to name a "
        "real model and query before running `tracebi report build`.",
    )


def _report_json_text(title: str, model: str, query: dict) -> str:
    declaration = {
        "name": title,
        "author": "",
        "description": "Freeform report package scaffolded by tracebi new-report.",
        "libs": ["echarts"],
        "data": {"rows": {"model": model, "query": query}},
    }
    return json.dumps(declaration, indent=2) + "\n"


_REPORT_TEMPLATE_HTML = _scaffold_text("report_template.html")

_REPORT_STYLE_CSS = _scaffold_text("report_style.css")

# Reads the embedded data and draws the table with DOM APIs only — the data
# never reaches innerHTML, so a hostile cell value cannot execute (architecture
# §5). The block is <script type="application/json">, parsed with JSON.parse.
_REPORT_SCRIPT_JS = _scaffold_text("report_script.js")


def cmd_new_report(args: argparse.Namespace) -> int:
    """
    Scaffold a freeform report package under ``reports/<name>/``.

    Four starter files — ``report.json`` (a data binding), ``template.html``,
    ``style.css``, ``script.js`` — that render a titled page with a table out of
    the box against the first model in ``models/``. A directory holding
    ``report.json`` + ``template.html`` is discovered as a report (architecture
    §7) and built with ``tracebi report build <name>``.
    """
    reports_dir: Path = args.reports_dir
    slug = _slugify(args.title)
    pkg_dir = reports_dir / slug
    if pkg_dir.exists() and not args.force:
        print(f"refusing to overwrite existing {pkg_dir}; pass --force to replace",
              file=sys.stderr)
        return 1
    pkg_dir.mkdir(parents=True, exist_ok=True)

    model, query, note = _scaffold_binding()
    (pkg_dir / "report.json").write_text(
        _report_json_text(args.title, model, query), encoding="utf-8")
    (pkg_dir / "template.html").write_text(
        _REPORT_TEMPLATE_HTML.replace("{{ title }}", args.title), encoding="utf-8")
    (pkg_dir / "style.css").write_text(_REPORT_STYLE_CSS, encoding="utf-8")
    (pkg_dir / "script.js").write_text(_REPORT_SCRIPT_JS, encoding="utf-8")

    print(f"Created {pkg_dir}/ (report.json, template.html, style.css, script.js)")
    if note:
        print(f"  {note}")
    else:
        print(f"  Bound to model '{model}'. Build it with:")
        print(f"    tracebi report build {slug}")
    return 0


def _resolve_report_target(name: str, reports_dir: Path) -> tuple[str, Path]:
    """Resolve *name* to a package directory or a spec file under ``reports/``.

    Looks for a ``reports/<name>/`` package first, then a ``reports/<name>.json``
    spec. Returns ``("package"|"spec", path)`` or raises ``FileNotFoundError``
    listing where it looked. All report forms live in one ``reports/`` folder.
    """
    pkg_dir = reports_dir / name
    if (pkg_dir / "report.json").is_file() and (pkg_dir / "template.html").is_file():
        return "package", pkg_dir
    spec_path = reports_dir / f"{name}.json"
    if spec_path.is_file():
        return "spec", spec_path
    raise FileNotFoundError(
        f"No report '{name}' found. Looked for a package or spec at:\n  "
        + "\n  ".join([str(pkg_dir), str(spec_path)])
    )


def _report_status(kind: str, path: Path, as_json: bool = False) -> int:
    """The earned state of an artifact, from the one workbench state builder.

    What a driving agent and CI call between edits: figures by provenance,
    coverage, unused bindings, pins — printed compact, or as the full state
    JSON with --json.
    """
    if kind != "package":
        print("status applies to artifact packages (reports/<name>/); "
              "verify a spec's receipt with `tracebi verify` instead.",
              file=sys.stderr)
        return 1
    from tracebi.workbench import collect_state

    state = collect_state(str(path), _load_project_models())
    if as_json:
        print(json.dumps(state, indent=2, default=str))
        return 0
    cov = state.get("coverage", {})
    parts = [f"{cov.get('verified', 0)} query-backed",
             f"{cov.get('derived', 0)} python-derived",
             f"{cov.get('unverified', 0)} unverified"]
    if cov.get("unbound_errors"):
        parts.append(f"{cov['unbound_errors']} unbound-ERROR")
    print(f"{state.get('name', path.name)}: {cov.get('total', 0)} figure(s) — "
          + ", ".join(parts))
    for f in state.get("figures", []):
        mark = {"verified": "✓", "derived": "·", "unverified": "·"}.get(
            f.get("provenance"), "✗")
        pin = " 📌" if f.get("pinned") else ""
        print(f"  {mark} {f.get('id')}  [{f.get('provenance')}]"
              f"{'  ← ' + f['binding'] if f.get('binding') else ''}{pin}")
    unused = state.get("unused_bindings") or []
    if unused:
        print(f"  ! unused binding(s): {', '.join(unused)}")
    errs = [b for b in state.get("bindings", []) if b.get("error")]
    for b in errs:
        print(f"  ✗ binding '{b['name']}' failed: {b['error']}", file=sys.stderr)
    return 1 if (cov.get("unbound_errors") or errs) else 0


def _snapshot_report_target(kind: str, path: Path, output: Path) -> int:
    """Write a review snapshot — the sendable working state (v2 §2.5).

    Packages only: a spec has no exploration blocks or code to review.
    The snapshot carries NO manifest, on purpose — a weaker-looking receipt
    is worse than none — and ``verify`` refuses the file by name.
    """
    if kind != "package":
        print("snapshot applies to artifact packages (reports/<name>/); "
              "a spec has no exploration state to snapshot — use build.",
              file=sys.stderr)
        return 1
    from tracebi.reports.template_package import TemplatePackage

    models = _load_project_models()
    TemplatePackage(str(path)).snapshot(models, str(output))
    print(f"Snapshot → {output}")
    print("  review copy: exploration blocks kept, code appendix attached, "
          "NO manifest — `tracebi verify` will refuse it by name.")
    return 0


def _build_report_target(kind: str, path: Path, output: Path,
                         theme: Optional[str] = None,
                         badges: bool = False) -> Path:
    """Render one report target to *output* (+ a sibling manifest). Returns output."""
    output.parent.mkdir(parents=True, exist_ok=True)
    models = _load_project_models()
    if kind == "package":
        from tracebi.reports.template_package import TemplatePackage
        TemplatePackage(str(path)).render(models, str(output), badges=badges)
    else:
        # A bare .json spec compiles to the artifact package, then renders like
        # a hand-authored one — the same one report form as a package.
        import tempfile

        from tracebi.reports.compile_spec import compile_spec
        from tracebi.reports.template_package import TemplatePackage
        from tracebi.spec import ReportSpec
        spec = ReportSpec.from_json(path.read_text(encoding="utf-8"))
        compiled = compile_spec(
            spec,
            theme_css=_report_theme_css(spec, extra_theme=theme),
            script_js=_report_script_js(spec),
        )
        with tempfile.TemporaryDirectory() as d:
            for fname, content in compiled.files.items():
                (Path(d) / fname).write_text(content, encoding="utf-8")
            TemplatePackage(d).render(models, str(output), badges=badges)
    return output


def _report_theme_css(spec, extra_theme: Optional[str] = None) -> str:
    """The spec's theme CSS (plus a --theme override file), resolved against
    the reports directory. Later layers win, so the flag stacks last."""
    parts = []
    for name in (getattr(spec, "theme", ""), extra_theme or ""):
        if not name:
            continue
        p = Path(name)
        if not p.is_file():
            p = _default_reports_dir() / name
        if not p.is_file():
            raise FileNotFoundError(
                f"theme file not found: {name} (looked in cwd and "
                f"{_default_reports_dir()})"
            )
        parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _report_script_js(spec) -> str:
    """The spec's script file, resolved against the reports directory."""
    name = getattr(spec, "script", "")
    if not name:
        return ""
    p = Path(name)
    if not p.is_file():
        p = _default_reports_dir() / name
    if not p.is_file():
        raise FileNotFoundError(
            f"script file not found: {name} (looked in cwd and "
            f"{_default_reports_dir()})"
        )
    return p.read_text(encoding="utf-8")


def _serve_file(html_path: Path, name: str, port: int, open_browser: bool) -> None:
    """Serve *html_path*'s directory over HTTP, as ``HTMLRenderer.serve`` does.

    The freeform ``.html`` is already built and self-contained, so preview
    serves that artifact statically rather than re-rendering it — the built-in
    renderers never touch the analyst's ``template.html``.
    """
    import http.server
    import threading
    import webbrowser

    directory = str(html_path.parent.resolve())
    url = f"http://localhost:{port}/{html_path.name}"

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=directory, **kw)

        def log_message(self, fmt, *a):  # silence request logs
            pass

    # Bind loopback, not "" (all interfaces): preview serves a directory of
    # rendered reports unauthenticated, and the URL already says localhost.
    server = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    print(f"\n  TraceBi Report — '{name}'")
    print(f"  Serving at {url}")
    print("  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
    finally:
        server.server_close()


def cmd_report(args: argparse.Namespace) -> int:
    """
    Build, preview, snapshot, or send a report — the build step
    (architecture §2), plus scheduled delivery v1.

        tracebi report build <name>      # → output/<name>.html + manifest
        tracebi report preview <name>    # build, then serve it locally
        tracebi report snapshot <name>   # review snapshot — NO manifest
        tracebi report send <name> --to a@b.com[,c@d]
                                         # build, verify, then email BOTH the
                                         # html and its manifest receipt

    A report is a package (``reports/<name>/``) or a spec
    (``reports/<name>.json``). Output defaults to ``output/<name>.html`` —
    self-contained, offline, and checkable with ``tracebi verify --file``.
    A snapshot keeps the exploration blocks, banners itself, appends a
    read-only code appendix, and writes NO manifest: it is the sendable
    working state, and ``verify`` refuses it by name.

    ``send`` builds exactly like ``build``, then verifies the manifest
    in-process and REFUSES to send while the receipt does not verify —
    distribution never outruns verification. ``--force`` sends anyway with
    the failing verdict pasted prominently into the body: the red flag
    travels WITH the report, never silently.
    """
    reports_dir: Path = args.reports_dir
    try:
        kind, path = _resolve_report_target(args.name, reports_dir)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.action == "send" and not getattr(args, "to", None):
        print("report send: --to is required "
              "(one or more addresses, comma-separated)", file=sys.stderr)
        return 1

    if args.action == "status":
        return _report_status(kind, path, as_json=getattr(args, "json", False))
    if args.action == "snapshot":
        output = (Path(args.output) if args.output
                  else Path.cwd() / "output" / f"{args.name}.snapshot.html")
        return _snapshot_report_target(kind, path, output)
    output = Path(args.output) if args.output else Path.cwd() / "output" / f"{args.name}.html"
    try:
        _build_report_target(kind, path, output,
                             theme=getattr(args, 'theme', None),
                             badges=getattr(args, 'badges', False))
    except Exception as exc:  # noqa: BLE001 — a build failure is the user's to fix
        print(f"failed to build report '{args.name}': "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    manifest = output.with_name(output.name + ".manifest.json")
    print(f"Rendered {args.name} ({kind}) → {output}")
    print(f"  manifest → {manifest}")

    if args.action == "send":
        return _report_send(args, output, manifest)
    if args.action == "preview":
        _serve_file(output, args.name, args.port, not args.no_browser)
    return 0


def _report_send(args: argparse.Namespace, output: Path,
                 manifest_path: Path) -> int:
    """The send action's second half: verification gates distribution.

    The build already happened, exactly as ``build``. The manifest is now
    verified in-process; a receipt that does not verify is refused —
    ``--force`` sends anyway with the failing verdict pasted prominently
    into the body (see :mod:`tracebi._delivery`), so the red flag travels
    WITH the report instead of the report outrunning it.
    """
    from tracebi._delivery import send_report, slack_notify
    from tracebi.verify import load_models, verify_manifest

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"report send: cannot read manifest {manifest_path}: {exc}",
              file=sys.stderr)
        return 1

    models = load_models(args.models_dir)
    try:
        result = verify_manifest(manifest, models)
    except Exception as exc:  # noqa: BLE001 — a corrupt receipt is a user error
        print(f"report send: manifest could not be verified: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    ok = result["exit_code"] == 0
    print(result["verdict_detail"], file=sys.stdout if ok else sys.stderr)
    if not ok and not getattr(args, "force", False):
        print(f"refusing to send '{args.name}': the receipt did not verify. "
              f"Distribution never outruns verification; --force sends "
              f"anyway with the verdict pasted into the body.",
              file=sys.stderr)
        return result["exit_code"] or 1

    to = [a.strip() for a in args.to.split(",") if a.strip()]
    try:
        send_report(output, manifest_path, to,
                    subject=getattr(args, "subject", None),
                    verify_result=result)
    except (RuntimeError, OSError) as exc:
        print(f"report send: {exc}", file=sys.stderr)
        return 1
    print(f"Sent {args.name} → {', '.join(to)} (html + manifest receipt)")

    webhook = os.environ.get("TRACEBI_SLACK_WEBHOOK")
    if webhook:
        n = len(result.get("figures") or result.get("sections") or [])
        text = (f"{args.name} delivered · "
                f"{result['verdict'].upper().replace('_', ' ')} · "
                f"{n} figures")
        try:
            slack_notify(webhook, text)
        except Exception as exc:  # noqa: BLE001 — the report already went out
            print(f"slack notify failed (the report was sent): {exc}",
                  file=sys.stderr)
    return 0


# ── Workbench sessions: export / clear ──────────────────────────────────────

def cmd_session(args: argparse.Namespace) -> int:
    """
    Save or reset a workbench session feed.

        tracebi session export [name]    # → explorations/<name>.html — ONE living record
        tracebi session clear [name]     # remove the feed and pins

    *name* defaults to the discovery session (``_discovery``); a package
    name addresses that package's session. The export is an exploration
    RECORD — the full feed, uncapped, as one self-contained lab-notebook
    HTML with NO manifest; ``tracebi verify`` refuses it by name. ``clear``
    is prompt-free, but refuses while a dev server's heartbeat for the
    session is fresh — the live watcher would keep posting over the reset.
    """
    import time

    from tracebi.workbench import (
        ACTIVE_FILE, DISCOVERY_NAME, EXHIBITS_FILE, HEARTBEAT_WINDOW,
        PINS_FILE,
    )

    name = args.name or DISCOVERY_NAME
    wb = os.path.join(os.getcwd(), ".tracebi", "workbench", name)

    if args.action == "export":

        from tracebi._session_export import export_session

        ext = "md" if getattr(args, "format", "html") == "md" else "html"
        # ONE living record per session, not a dated diary: the exploration
        # is the base document that evolves into the pipeline, so re-exports
        # overwrite the same file and git carries the timeline — each
        # iteration is a readable diff (the .md twin especially).
        fname = name.lstrip("_") or name
        out = Path(args.output) if args.output else (
            Path("explorations") / f"{fname}.{ext}")
        existed = out.exists()
        try:
            export_session(wb, str(out), title=args.title)
        except FileNotFoundError as exc:
            print(exc, file=sys.stderr)
            return 1
        print(f"{'Updated' if existed else 'Exported'} session '{name}' "
              f"→ {out}")
        print("  The living exploration record — re-export as it evolves; "
              "git is its timeline. verify refuses it by name.")
        return 0

    # clear
    try:
        age = time.time() - os.path.getmtime(os.path.join(wb, ACTIVE_FILE))
    except OSError:
        age = None
    if age is not None and age <= HEARTBEAT_WINDOW:
        print(f"session '{name}' has a live dev server (fresh heartbeat) — "
              f"stop the server first, then clear.", file=sys.stderr)
        return 1
    removed = [fname for fname in (EXHIBITS_FILE, PINS_FILE)
               if os.path.isfile(os.path.join(wb, fname))]
    for fname in removed:
        os.remove(os.path.join(wb, fname))
    if removed:
        print(f"Cleared session '{name}' ({', '.join(removed)}).")
    else:
        print(f"Session '{name}' has no feed or pins to clear.")
    return 0


# ── Argparse wiring ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracebi",
        description=("TraceBi — the trust layer for AI-generated analytics: "
                     "a code-first BI framework where every number has a receipt."),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tracebi {_tracebi_version()}",
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
        help="Scaffold a complete three-phase project (inputs/, transforms/, "
             "models/, reports/, …) whose sample loop ends in "
             "`tracebi verify` reading REPRODUCES.",
    )
    p_init.add_argument("project", help="Target directory name.")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite existing files.")
    p_init.set_defaults(func=cmd_init)

    p_spec = sub.add_parser(
        "spec",
        help="Work with report specs (a report as JSON): print the schema, "
             "validate a spec without running it, or render one.",
    )
    p_spec.add_argument("action", choices=["schema", "validate", "render"])
    p_spec.add_argument(
        "--theme",
        help="Extra CSS file stacked over the spec's own theme (later wins).",
    )
    p_spec.add_argument("file", nargs="?", help="Path to a spec .json file.")
    p_spec.add_argument("--output", help="Output path for `render`.")
    p_spec.set_defaults(func=cmd_spec)

    p_context = sub.add_parser(
        "context",
        help="Print the framework's vocabulary as JSON (section and panel "
             "types, DataSet verbs, measures, operators, conventions).",
    )
    p_context.add_argument("--model", help="Also include this model's schema.")
    p_context.add_argument(
        "--brief", action="store_true",
        help="The token-lean tier (~40%% of the payload): semantic model, "
             "figure grammar, contracts, conventions — everything the "
             "package-first loop needs. Omits the legacy section classes, "
             "DataSet verbs, and Python cheat sheets.",
    )
    p_context.add_argument("--compact", action="store_true",
                           help="Single-line JSON.")
    p_context.set_defaults(func=cmd_context)

    p_serve = sub.add_parser(
        "serve",
        help="Serve this project's web UI (models, reports, pipelines) "
             "at http://127.0.0.1:8000.",
    )
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true",
                         help="Restart on file changes (development).")
    p_serve.set_defaults(func=cmd_serve)

    p_dev = sub.add_parser(
        "dev",
        help="Live-preview a report while you edit it. An artifact package "
             "(reports/<name>/) gets the in-memory exploration render plus "
             "the workbench at /__workbench; with no name, DISCOVERY MODE "
             "serves the project-level workbench (warehouse tables, sink "
             "contracts, models, packages, exhibit feed) — the live surface "
             "before any report exists.",
    )
    p_dev.add_argument("name", nargs="?",
                       help="Package name under reports/. Omit for discovery "
                            "mode: the project-level workbench.")
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

    p_run_transform = sub.add_parser(
        "run-transform",
        help="Execute a phase-① transform (.py or .ipynb) top-to-bottom in "
             "a fresh namespace — the sink never comes from out-of-order "
             "kernel state. Notebook-shaped .py (# %% cells) and literal "
             ".ipynb both work.",
    )
    p_run_transform.add_argument(
        "name", help="Transform name under transforms/ (suffix optional).")
    p_run_transform.set_defaults(func=cmd_run_transform)

    p_new_transform = sub.add_parser(
        "new-transform",
        help="Scaffold a phase-① transform (transforms/<name>.py): pandas "
             "that reads a raw input and sinks star tables to the warehouse.",
    )
    p_new_transform.add_argument("title", help='Free-form title, e.g. "Orders Clean".')
    p_new_transform.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new_transform.add_argument(
        "--transforms-dir", type=Path, default=_default_transforms_dir(),
        help="Directory holding transforms (default: ./transforms).",
    )
    p_new_transform.set_defaults(func=cmd_new_transform)

    p_list_pipelines = sub.add_parser("list-pipelines", help="List pipeline definition files.")
    p_list_pipelines.set_defaults(func=cmd_list_pipelines)

    p_new_report = sub.add_parser(
        "new-report",
        help="Scaffold a freeform report package (reports/<name>/): report.json "
             "+ template.html + style.css + script.js.",
    )
    p_new_report.add_argument("title", help='Free-form title, e.g. "Portfolio Book".')
    p_new_report.add_argument("--force", action="store_true", help="Overwrite if exists.")
    p_new_report.add_argument("--reports-dir", type=Path, default=_default_reports_dir(),
                              help="Directory holding report packages (default: ./reports).")
    p_new_report.set_defaults(func=cmd_new_report)

    p_report = sub.add_parser(
        "report",
        help="Build a report package or spec to one self-contained .html + "
             "manifest, preview it locally, or send it (build → verify → "
             "email with the receipt attached).",
    )
    p_report.add_argument("action",
                          choices=["build", "preview", "snapshot", "status",
                                   "send"])
    p_report.add_argument("name", help="Report name (package dir or spec stem).")
    p_report.add_argument(
        "--to",
        help="With `send`: recipient address(es), comma-separated. Send "
             "builds like `build`, verifies the manifest in-process, and "
             "refuses to send unless the receipt verifies (--force "
             "overrides, pasting the verdict into the body). Email needs "
             "TRACEBI_SMTP_URL (smtp://user:pass@host:port or smtps://) "
             "and TRACEBI_SMTP_FROM; TRACEBI_SLACK_WEBHOOK adds a Slack "
             "ping. Scheduling is plain cron — a crontab line such as "
             "`0 7 * * MON cd /path/to/project && tracebi report send "
             "weekly --to team@example.com`, or a script under scheduled/ "
             "(the project's scheduled-jobs folder) that your scheduler "
             "runs. No daemon ships; the receipt does.",
    )
    p_report.add_argument(
        "--subject",
        help="With `send`: email subject (default: '[tracebi] <report name>').",
    )
    p_report.add_argument(
        "--force", action="store_true",
        help="With `send`: send even when the receipt does not verify. The "
             "failing verdict is pasted prominently into the email body — "
             "a red flag travels WITH the report, never silently.",
    )
    p_report.add_argument("--output", help="Output .html path (default: output/<name>.html).")
    p_report.add_argument(
        "--json", action="store_true",
        help="With `status`: print the full workbench state as JSON (what "
             "the workbench page and the MCP workbench_state tool consume).",
    )
    p_report.add_argument(
        "--badges", action="store_true",
        help="Render the per-figure provenance badges on the page. Off by "
             "default — the receipt drawer carries provenance in one place. "
             "The manifest is unaffected either way.",
    )
    p_report.add_argument(
        "--theme",
        help="Extra CSS file stacked over the spec's own theme (later wins). "
             "Spec targets only; packages carry their own style.css.",
    )
    p_report.add_argument("--reports-dir", type=Path, default=_default_reports_dir(),
                          help="Directory holding report packages (default: ./reports).")
    p_report.add_argument("--port", type=int, default=8080,
                          help="Port for `preview` (default 8080).")
    p_report.add_argument("--no-browser", action="store_true",
                          help="With `preview`, do not open the browser.")
    p_report.set_defaults(func=cmd_report)

    p_session = sub.add_parser(
        "session",
        help="Save or reset a workbench session feed. `session export "
             "[name]` renders the FULL feed (uncapped) to one exploration-"
             "record HTML — a lab notebook, not a report: no manifest, and "
             "`tracebi verify` refuses it by name. `session clear [name]` "
             "removes the feed and pins (refused while a dev server's "
             "heartbeat is fresh). Name defaults to the discovery session.",
    )
    p_session.add_argument("action", choices=["export", "clear"])
    p_session.add_argument(
        "name", nargs="?", default=None,
        help="Session name: a package name, or omit for the discovery "
             "session (_discovery).",
    )
    p_session.add_argument(
        "-o", "--output",
        help="Output .html path for `export` "
             "(default: explorations/<name>.<ext> — one living record per "
             "session; re-exports overwrite it and git carries the "
             "timeline).",
    )
    p_session.add_argument(
        "--title",
        help="Page title (default: '<session> — exploration record').",
    )
    p_session.add_argument(
        "--format", choices=["html", "md"], default="html",
        help="Export format: self-contained HTML (default; charts render, "
             "verify refuses it by name) or the Markdown twin — the "
             "git-review format: raw markdown notes verbatim, tables for "
             "frames and sketches, made for reading in a pull request. An "
             "explicit -o extension (.md/.html) also selects the format.",
    )
    p_session.set_defaults(func=cmd_session)

    p_migrate = sub.add_parser(
        "migrate",
        help="Migrate legacy report forms to the artifact package. "
             "`migrate spec <file.json>` compiles a JSON spec into "
             "reports/<stem>/ (report.json bindings + template.html of "
             "default-component figures) alongside the original.",
    )
    p_migrate.add_argument("what", choices=["spec"])
    p_migrate.add_argument("path", help="Path to a reports/<name>.json spec.")
    p_migrate.add_argument("--force", action="store_true",
                           help="Overwrite an existing target directory.")
    p_migrate.set_defaults(func=cmd_migrate)

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
    p_mcp.add_argument(
        "--insecure", action="store_true",
        help="Serve --transport http without authentication. Deliberate "
             "opt-out: without it, http requires TRACEBI_MCP_TOKEN.",
    )
    p_mcp.set_defaults(func=cmd_mcp)

    p_verify = sub.add_parser(
        "verify",
        help="Re-run every recorded query in a rendered manifest and "
             "classify each section: reproduces, source drift, model changed, "
             "unexplained, or unverifiable. Exits 0 only when something was actually "
             "checked and nothing failed.",
    )
    p_verify.add_argument(
        "manifest", nargs="?", default=None,
        help="Path to a *.manifest.json file (query → model check). "
             "Omit when using --file.",
    )
    # A wholly separate offline check: the shipped .html's embedded bytes vs
    # the manifest (architecture §3.2). Kept apart from the positional so
    # neither can be mistaken for the other.
    p_verify.add_argument(
        "--strict", action="store_true",
        help="Fail unless every FIGURE in a schema-2 manifest reproduces — "
             "the CI gate for a finalized report.",
    )
    p_verify.add_argument(
        "--file", dest="verify_file", default=None,
        help="Path to a self-contained report *.html*; rehash its embedded "
             "data against a sibling <file>.manifest.json (no model needed).",
    )
    p_verify.add_argument(
        "--contracts", action="store_true",
        help="Also re-run the warehouse's recorded sink contracts against "
             "the current warehouse. A separate claim, reported separately: "
             "it says whether today's sink still satisfies its declared "
             "contract — never that the transform was verified.",
    )
    p_verify.add_argument(
        "--manifest", dest="file_manifest", default=None,
        help="With --file: the manifest to check against, if it is not the "
             "sibling <file>.manifest.json.",
    )
    # Distinct dest: a subparser option sharing dest with a main-parser
    # option would clobber an already-parsed `tracebi --models-dir X verify`.
    p_verify.add_argument(
        "--models-dir", type=Path, default=None, dest="verify_models_dir",
        help="Directory holding model definitions (default: ./models).",
    )
    p_verify.set_defaults(func=cmd_verify)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
