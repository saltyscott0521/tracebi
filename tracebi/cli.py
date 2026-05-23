"""
TraceBi CLI.

Usage:
    tracebi new-request "Open orders by region"   # scaffolds requests/<slug>.py
    tracebi list-requests                          # show all request scripts
    tracebi run <name>                             # run a request and render outputs

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


# Resolve the requests/ folder relative to the user's current working
# directory by default. Override with --requests-dir.
def _default_requests_dir() -> Path:
    return Path.cwd() / "requests"


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
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer

# Prefer the shared project DataModel if the web layer registered one;
# otherwise build your own here (see commented imports below).
try:
    from tracebi.web import register
    model = register.get_default_model()
except ImportError:
    model = None

if model is None:
    from tracebi import DataModel  # noqa: F401
    # model = DataModel("MyModel")
    # model.add_connector(...)
    # model.add_table("orders", connector="...", source="...")
    pass


# ── 1. Build DataSets ───────────────────────────────────────────────────────
# orders = model.load("orders", filter={{"status": "shipped"}})


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
                    "from tracebi.reports.report import Report, TextSection, TableSection, ChartSection\n",
                    "from tracebi.reports.html_renderer import HTMLRenderer\n",
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
                    "# Build DataSets with model.load(...) — every step adds a lineage node\n",
                    "# orders = model.load(\"orders\", filter={\"status\": \"shipped\"})\n",
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


# ── Commands ────────────────────────────────────────────────────────────────

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
    if not name.endswith(".py"):
        name = name + ".py"
    path = requests_dir / name
    if not path.is_file():
        print(f"Request not found: {path}", file=sys.stderr)
        return 1
    print(f"Running {path}…")
    runpy.run_path(str(path), run_name="__main__")
    return 0


# ── Argparse wiring ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tracebi",
        description="TraceBi — code-first, traceable BI.",
    )
    parser.add_argument(
        "--requests-dir",
        type=Path,
        default=_default_requests_dir(),
        help="Directory holding request scripts (default: ./requests).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

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

    p_run = sub.add_parser("run", help="Run a .py request script.")
    p_run.add_argument("name", help="Request file name (with or without .py).")
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
