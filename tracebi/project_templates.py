"""Named starters for ``tracebi init --template``.

The copy logic lives here so ``cli.py`` only branches on the flag. Each
starter is a directory of files under ``tracebi/_scaffold/templates/``
(sample data, transform, model, report packages). Shared project files
— gitignore, env example, ``AGENTS.md``, MCP config — are the same ones
default ``init`` writes.
"""

from __future__ import annotations

import json
import sys
from importlib.resources import files
from pathlib import Path

# Public name → bundle directory under ``_scaffold/templates/``.
_BUNDLES: dict[str, str] = {
    "saas-metrics": "saas_metrics",
}

# Accepted spellings → public name.
_ALIASES: dict[str, str] = {
    "saas-metrics": "saas-metrics",
    "saas_metrics": "saas-metrics",
}

_CATALOG: list[dict] = [
    {
        "name": "saas-metrics",
        "aliases": ["saas_metrics"],
        "summary": (
            "Account-month subscriptions: ending MRR, logo churn "
            "(a ratio of totals), and a signup-cohort cut."
        ),
        "model": "saas_model",
        "reports": [
            "saas_model/mrr_dashboard",
            "saas_model/cohort_brief",
        ],
        "sample": "inputs/subscriptions.csv",
        "transform": "transforms/saas_transform.py",
        "next": (
            "tracebi connect <name> --kind postgres|snowflake|bigquery|duckdb, "
            "then re-point models/saas_model.py at your tables."
        ),
    },
]


def known_template_names() -> list[str]:
    """Public template names, sorted. This is the refusal list."""
    return sorted(_BUNDLES)


def resolve_template(name: str) -> str | None:
    """Map a flag value to its public name, or None when it is unknown."""
    return _ALIASES.get(name.strip())


def template_catalog() -> list[dict]:
    """The ``templates.known`` list in ``tracebi context``."""
    return [dict(entry) for entry in _CATALOG]


def _scaffold_text(name: str) -> str:
    return files("tracebi").joinpath("_scaffold", name).read_text(encoding="utf-8")


def _mcp_json() -> str:
    return json.dumps(
        {"mcpServers": {"tracebi": {"command": "tracebi", "args": ["mcp"]}}},
        indent=2,
    ) + "\n"


def _bundle_files(bundle_id: str) -> dict[Path, str]:
    root = files("tracebi").joinpath("_scaffold", "templates", bundle_id)
    out: dict[Path, str] = {}

    def walk(node, prefix: Path) -> None:
        for child in sorted(node.iterdir(), key=lambda p: p.name):
            if child.name in {"__pycache__", ".DS_Store"}:
                continue
            rel = prefix / child.name
            if child.is_dir():
                walk(child, rel)
            elif child.is_file():
                out[rel] = child.read_text(encoding="utf-8")

    walk(root, Path())
    return out


def _readme(project: str, template: str) -> str:
    entry = next(item for item in _CATALOG if item["name"] == template)
    reports = "\n".join(f"tracebi report build {name}" for name in entry["reports"])
    verifies = "\n".join(
        f"tracebi verify output/{name}.html.manifest.json --strict --contracts"
        for name in entry["reports"]
    )
    report_lines = "\n".join(f"├── reports/{name}/" for name in entry["reports"])
    return f"""\
# {project}

A TraceBi project. Scaffolded by `tracebi init --template {template}`.

{entry["summary"]}
The file `{entry["sample"]}` is a small synthetic sample so the loop runs
before you have a warehouse.

## Next step — your own data

1. `{entry["next"].split(", then ")[0]}`
   tests the warehouse, writes the secret to `.env`, and writes
   `models/_connections/<name>.py`.
2. Re-point `models/{entry["model"]}.py` at those tables (the connector
   and the `source=` names). Or draft a fresh model with
   `tracebi new-model "SaaS" --from <name> --tables ...` and edit every
   line marked `# DRAFT: review` before a report depends on it.

## Run the sample loop

```bash
python {entry["transform"]}
{reports}
{verifies}
tracebi serve
```

`verify` re-runs the recorded queries. `--contracts` re-runs the sink
contract. The claim on the transform is "the sink satisfied its contract".

## Layout

```
{project}/
├── {entry["sample"]}
├── {entry["transform"]}
├── models/{entry["model"]}.py
{report_lines}
├── data/             warehouse (gitignored)
└── output/           rendered HTML + manifest receipts
```
"""


def init_template_project(project: Path, template: str, *, force: bool) -> int:
    """Scaffold *project* from *template*. Same empty-dir / ``--force`` rules as init."""
    canonical = resolve_template(template)
    if canonical is None:
        known = ", ".join(known_template_names())
        print(
            f"unknown template {template!r}. Known templates: {known}.",
            file=sys.stderr,
        )
        return 1

    target = Path(project).resolve()
    if target.exists() and any(target.iterdir()):
        if not force:
            print(
                f"refusing to init into non-empty {target}; "
                f"pass --force to override",
                file=sys.stderr,
            )
            return 1

    for d in ("inputs", "transforms", "models", "pipelines", "reports",
              "data", "output"):
        (target / d).mkdir(parents=True, exist_ok=True)

    entry = next(item for item in _CATALOG if item["name"] == canonical)
    to_write: dict[Path, str] = {
        target / ".gitignore": _scaffold_text("init_gitignore.txt"),
        target / ".env.example": _scaffold_text("init_env_example.txt"),
        target / "README.md": _readme(target.name, canonical),
        target / "AGENTS.md": _scaffold_text("init_agents.md"),
        target / ".mcp.json": _mcp_json(),
        target / ".cursor" / "mcp.json": _mcp_json(),
        target / "pipelines" / ".gitkeep": "",
    }
    for rel, content in _bundle_files(_BUNDLES[canonical]).items():
        to_write[target / rel] = content

    for path, content in to_write.items():
        if path.exists() and not force:
            print(f"skipping existing {path}", file=sys.stderr)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(f"Initialised TraceBi project at {target} (template {canonical})")
    print(f"  cd {target.name}")
    print(f"  python {entry['transform']}")
    for name in entry["reports"]:
        print(f"  tracebi report build {name}")
    first = entry["reports"][0]
    print(
        f"  tracebi verify output/{first}.html.manifest.json "
        f"--strict --contracts"
    )
    print(f"  Next: {entry['next']}")
    return 0
