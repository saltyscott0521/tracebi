"""The agent-eval scorer accepts a real package and rejects a broken one."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.agent.score import format_table, score_all  # noqa: E402

_PROJECT = Path(__file__).resolve().parent.parent / "examples" / "portfolio_project"


def _copy_project(tmp_path: Path) -> Path:
    dest = tmp_path / "portfolio_project"
    shutil.copytree(
        _PROJECT, dest,
        ignore=shutil.ignore_patterns("data", "output", ".tracebi", "__pycache__"),
    )
    subprocess.run(
        [sys.executable, "transforms/holdings_transform.py"],
        cwd=dest, check=True,
    )
    return dest


def test_scorer_passes_portfolio_book_and_fails_a_literal(tmp_path):
    project = _copy_project(tmp_path)
    broken = project / "reports" / "broken_book"
    shutil.copytree(project / "reports" / "portfolio_book", broken)
    template = broken / "template.html"
    template.write_text(
        template.read_text(encoding="utf-8").replace(
            "<main class=\"book\">",
            "<main class=\"book\">\n<p>The total is 99999.</p>",
        ),
        encoding="utf-8",
    )
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "book.md").write_text(
        "A report of fair value by sector.\n", encoding="utf-8",
    )
    (cases / "book.json").write_text(json.dumps({
        "report": "portfolio_book",
        "figures": ["custom"],
        "measures": ["fair_value"],
        "dimensions": ["dim_issuer.sector"],
        "forbid": ["data-tb-unverified"],
    }), encoding="utf-8")
    (cases / "broken.md").write_text(
        "Same report, with a typed total.\n", encoding="utf-8",
    )
    (cases / "broken.json").write_text(json.dumps({
        "report": "broken_book",
        "figures": ["custom"],
        "measures": ["fair_value"],
        "forbid": ["data-tb-unverified"],
    }), encoding="utf-8")

    rows = score_all(project, cases)
    table = format_table(rows)
    assert "book" in table and "pass" in table.split("book")[1].split("\n")[0]
    by_id = {case_id: (ok, reason) for case_id, ok, reason in rows}
    assert by_id["book"][0] is True
    assert by_id["broken"] == (False, "numeric literal outside a figure")
