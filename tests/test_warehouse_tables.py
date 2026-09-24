"""Warehouse table metadata: CLI and describe_table, with no row scan."""

from __future__ import annotations

import json

import duckdb

from tracebi.cli import main
from tracebi.connectors.duckdb_connector import DuckDBConnector
from tracebi.mcp_server import gateway_describe_table


def _warehouse(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    con = duckdb.connect(str(data / "warehouse.duckdb"))
    con.execute("CREATE TABLE orders (id INTEGER, name VARCHAR)")
    con.execute("INSERT INTO orders VALUES (1, 'acme')")
    con.close()


def _spy(monkeypatch) -> list[str]:
    """Record every SQL string. ``load`` reading rows is a failure.

    DuckDB's connection refuses assigning ``execute``, so the spy wraps
    ``duckdb.connect`` and returns a proxy.
    """
    seen: list[str] = []
    real_connect = duckdb.connect

    class _Proxy:
        def __init__(self, con):
            self._con = con

        def execute(self, sql, *args, **kwargs):
            text = sql if isinstance(sql, str) else str(sql)
            seen.append(text)
            folded = " ".join(text.split()).upper()
            if not folded.startswith("DESCRIBE") and "INFORMATION_SCHEMA" not in folded:
                if "ORDERS" in folded:
                    raise AssertionError(f"query reads table rows: {text}")
            return self._con.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._con, name)

    def connect(*args, **kwargs):
        return _Proxy(real_connect(*args, **kwargs))

    def load(self, *args, **kwargs):
        raise AssertionError("load() reads table rows")

    monkeypatch.setattr(duckdb, "connect", connect)
    monkeypatch.setattr(DuckDBConnector, "load", load)
    return seen


def test_cli_and_tool_list_and_describe_without_reading_rows(tmp_path, monkeypatch, capsys):
    _warehouse(tmp_path, monkeypatch)
    seen = _spy(monkeypatch)

    listed = gateway_describe_table()
    assert listed["ok"] is True
    # Other tests may have left connectors in the process registry. The
    # warehouse file is the one that actually has this table.
    warehouse = next(
        c for c in listed["connectors"]
        if c.get("tables") and "orders" in c["tables"]
    )
    assert warehouse["name"] == "warehouse"

    described = gateway_describe_table(table="orders")
    assert described["ok"] is True
    match = next(m for m in described["columns"] if m["connector"] == "warehouse")
    columns = {c["name"]: c["dtype"] for c in match["columns"]}
    assert columns["id"].upper().startswith("INTEGER")
    assert "VARCHAR" in columns["name"].upper()
    assert "rows" not in described

    assert main(["warehouse", "tables", "--json"]) == 0
    cli_listed = json.loads(capsys.readouterr().out)
    assert any(
        c.get("tables") and "orders" in c["tables"]
        for c in cli_listed["connectors"]
    )

    assert main(["warehouse", "tables", "--table", "orders", "--json"]) == 0
    cli_described = json.loads(capsys.readouterr().out)
    cli_match = next(
        m for m in cli_described["columns"] if m["connector"] == "warehouse"
    )
    names = [c["name"] for c in cli_match["columns"]]
    assert names == ["id", "name"]
    assert seen  # the spy was in the path
    assert all("COUNT(" not in q.upper() for q in seen)


def test_cli_text_lists_the_table(tmp_path, monkeypatch, capsys):
    _warehouse(tmp_path, monkeypatch)
    assert main(["warehouse", "tables"]) == 0
    out = capsys.readouterr().out
    assert "warehouse" in out
    assert "orders" in out
