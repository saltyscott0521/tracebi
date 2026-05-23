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
    return f'''"""
{title}
{'=' * len(title)}

Scaffolded by ``tracebi new-request`` on {today}.
Fill in the four sections below, then run with:

    python requests/{_slugify(title)}.py
"""

import os
from tracebi import DataModel, MemoryConnector
from tracebi.reports.report import Report, TextSection, TableSection, ChartSection
from tracebi.reports.excel_renderer import ExcelRenderer
from tracebi.reports.html_renderer import HTMLRenderer


# ── 1. Connect ──────────────────────────────────────────────────────────────
model = DataModel("MyModel")
# model.add_connector(SQLConnector("db", url="..."))
# model.add_table("orders", connector="db", source="orders")


# ── 2. Build DataSets ───────────────────────────────────────────────────────
# orders = model.load("orders").filter("status == 'shipped'")


# ── 3. Build Report ─────────────────────────────────────────────────────────
report = (
    Report("{title}")
    .author("Your Name")
    .description("Short description of this report.")
    .add(TextSection(title="Summary", content="Write your narrative here.", style="heading1"))
)


# ── 4. Render ───────────────────────────────────────────────────────────────

def run():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output")
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.join(output_dir, "{_slugify(title)}")
    ExcelRenderer().render(report, base + ".xlsx")
    HTMLRenderer().render(report, base + ".html")
    print(f"Saved: {{base}}.xlsx / .html")


if __name__ == "__main__":
    run()
'''


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_new_request(args: argparse.Namespace) -> int:
    requests_dir: Path = args.requests_dir
    requests_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.title)
    out_path = requests_dir / f"{slug}.py"
    if out_path.exists() and not args.force:
        print(f"refusing to overwrite existing {out_path}; pass --force to replace",
              file=sys.stderr)
        return 1

    out_path.write_text(_template_text(args.title), encoding="utf-8")
    print(f"Created {out_path}")
    return 0


def cmd_list_requests(args: argparse.Namespace) -> int:
    requests_dir: Path = args.requests_dir
    if not requests_dir.is_dir():
        print(f"No requests directory at {requests_dir}")
        return 0
    files = sorted(p for p in requests_dir.glob("*.py") if not p.name.startswith("_"))
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
    p_new.set_defaults(func=cmd_new_request)

    p_list = sub.add_parser("list-requests", help="List request scripts.")
    p_list.set_defaults(func=cmd_list_requests)

    p_run = sub.add_parser("run", help="Run a request script.")
    p_run.add_argument("name", help="Request file name (with or without .py).")
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
