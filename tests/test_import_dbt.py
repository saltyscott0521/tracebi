"""``tracebi import dbt`` drafts a model from a manifest and does not run dbt."""

import ast
import runpy
from pathlib import Path

from tracebi.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "dbt" / "manifest.json"


def _run(monkeypatch, tmp_path, *argv):
    monkeypatch.chdir(tmp_path)
    return main(list(argv))


def _connection(tmp_path, name="demo"):
    path = tmp_path / "models" / "_connections" / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "from tracebi.connectors.memory_connector import MemoryConnector\n"
        f"connector = MemoryConnector({name!r}, tables={{}})\n",
        encoding="utf-8",
    )
    return path


def _calls(src: str, attr: str) -> list[ast.Call]:
    found = []
    for node in ast.walk(ast.parse(src)):
        func = getattr(node, "func", None)
        if isinstance(node, ast.Call) and isinstance(func, ast.Attribute) and func.attr == attr:
            found.append(node)
    return found


def test_import_dbt_drafts_tables_and_leaves_guesses_commented(tmp_path, monkeypatch):
    _connection(tmp_path)
    code = _run(
        monkeypatch, tmp_path,
        "import", "dbt", str(FIXTURE),
        "--connection", "demo", "--name", "dbt_marts",
    )
    assert code == 0
    path = tmp_path / "models" / "dbt_marts.py"
    src = path.read_text(encoding="utf-8")
    ast.parse(src)
    assert "load_dotenv" not in src
    assert "_connections/demo.py" in src
    assert "# DRAFT: review" in src
    assert "int_ephemeral" not in src
    assert "old_orders" not in src
    assert "raw_customers" not in src
    assert "stg_payments" in src
    assert not _calls(src, "add_relationship")
    assert not _calls(src, "add_measure")
    assert not _calls(src, "add_fact")
    assert not _calls(src, "add_dimension")
    assert any(
        line.lstrip().startswith("#") and "add_measure" in line and "amount" in line
        for line in src.splitlines()
    )
    assert not any("margin_pct" in line and "add_measure" in line for line in src.splitlines())
    assert any(line.lstrip().startswith("#") and "add_relationship" in line for line in src.splitlines())

    model = runpy.run_path(str(path))["model"]
    info = model.info()
    assert info["name"] == "dbt_marts"
    assert info["connectors"] == ["demo"]
    tables = {table["name"]: table["source"] for table in info["tables"]}
    assert tables["customers"] == "customers"
    assert tables["other_pkg__customers"] == "customers"
    assert tables["dim_customer"] == "dim_customer_v2"
    assert tables["orders"] == "orders"
    assert tables["stg_payments"] == "stg_payments"
    assert info["relationships"] == []
    assert info["measures"] == []
