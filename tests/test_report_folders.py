"""
Reports in folders (epic E6, step 1).

A report in a folder is named by its path below ``reports/``
(``finance/weekly_summary``), so two folders can each hold a report of the same
name. The done-when from docs/strategy/epics.md: two folders each hold a
``weekly_summary``; both are discovered, build, open and schedule
independently, and nothing a name turns into can climb out of ``reports/`` or
``output/``.
"""

import json

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.report_paths import output_html, report_name_error

_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title></head>
<body><h1>{title}</h1>
<span data-tb-figure="value" data-tb-binding="totals" data-tb-cell="revenue"
      id="total"></span>
</body></html>
"""


def _package(root, rel, title, region, schedule=None):
    pkg = root / "reports" / rel
    pkg.mkdir(parents=True)
    decl = {"name": title, "data": {"totals": {"model": "folder_model", "query": {
        "fact": "fact_orders", "measures": ["revenue"],
        "filters": {"dim_region.region": region}}}}}
    if schedule:
        decl["schedule"] = schedule
    (pkg / "report.json").write_text(json.dumps(decl), encoding="utf-8")
    (pkg / "template.html").write_text(_TEMPLATE.format(title=title), encoding="utf-8")


@pytest.fixture
def model():
    m = DataModel("folder_model").add_connector(MemoryConnector("fm", tables={
        "orders": pd.DataFrame({"order_id": [1, 2, 3], "region_id": [1, 1, 2],
                                "revenue": [100.0, 50.0, 7.0]}),
        "regions": pd.DataFrame({"region_id": [1, 2], "region": ["East", "West"]}),
    }))
    m.add_table("orders", connector="fm", source="orders")
    m.add_table("regions", connector="fm", source="regions")
    m.add_dimension("dim_region", table_name="regions", key_col="region_id",
                    attributes=["region"])
    m.add_fact("fact_orders", table_name="orders", measures=["revenue"],
               foreign_keys={"dim_region": "region_id"})
    m.add_measure("revenue", column="revenue", agg="sum")
    m.connect()
    return m


@pytest.fixture
def project(tmp_path, monkeypatch, model):
    """Two folders each holding a weekly_summary, plus one top-level report."""
    from tracebi import cli, model_registry

    _package(tmp_path, "finance/weekly_summary", "Finance weekly", "East",
             schedule={"cron": "0 7 * * MON"})
    _package(tmp_path, "ops/weekly_summary", "Ops weekly", "West")
    _package(tmp_path, "top_level", "Top level", "East")
    (tmp_path / "reports" / "finance" / "notes.txt").write_text("not a report")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_load_project_models", lambda: {model.name: model})
    monkeypatch.setattr(model_registry, "list_models", lambda: [model.name])
    monkeypatch.setattr(model_registry, "get_model", lambda _n: model)
    return tmp_path


def test_discovery_names_reports_by_their_path(project):
    from tracebi.registry import registry
    from tracebi.web import discovery

    discovery.clear_discovery_report()
    found = discovery.auto_discover(str(project / "reports"))
    assert {"finance/weekly_summary", "ops/weekly_summary", "top_level"} <= set(found)
    listed = {r["name"] for r in registry.list_reports()}
    assert {"finance/weekly_summary", "ops/weekly_summary", "top_level"} <= listed


def test_same_named_reports_build_to_separate_files(project):
    from tracebi import cli
    from tracebi.verify import FILE_INTACT, verify_file

    for name in ("finance/weekly_summary", "ops/weekly_summary"):
        assert cli.main(["report", "build", name,
                         "--reports-dir", str(project / "reports")]) == 0
    finance = project / "output" / "finance" / "weekly_summary.html"
    ops = project / "output" / "ops" / "weekly_summary.html"
    # Each file is its own report: its own title and its own region's number.
    assert "Finance weekly" in finance.read_text() and 'id="total">150<' in finance.read_text()
    assert "Ops weekly" in ops.read_text() and 'id="total">7<' in ops.read_text()
    for html in (finance, ops):
        manifest = json.loads(html.with_name(html.name + ".manifest.json").read_text())
        assert verify_file(html.read_text(), manifest)["verdict"] == FILE_INTACT


def test_the_web_api_opens_a_report_in_a_folder(project):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tracebi.web import discovery
    from tracebi.web.api.routers import reports as reports_router

    discovery.auto_discover(str(project / "reports"))
    app = FastAPI()
    app.include_router(reports_router.router, prefix="/api")
    client = TestClient(app)

    names = {r["name"] for r in client.get("/api/reports").json()}
    assert {"finance/weekly_summary", "ops/weekly_summary"} <= names
    finance = client.get("/api/reports/finance/weekly_summary/built")
    ops = client.get("/api/reports/ops/weekly_summary/built")
    assert finance.status_code == 200 and ops.status_code == 200, finance.text
    assert "Finance weekly" in finance.json()["html"]
    assert "Ops weekly" in ops.json()["html"]
    source = client.get("/api/reports/ops/weekly_summary/source").json()
    assert any(f["path"].endswith("ops/weekly_summary/report.json")
               for f in source["files"])
    assert client.get("/api/reports/finance/nope/built").status_code == 404


def test_schedules_and_the_desk_see_folders(project):
    from tracebi import cli
    from tracebi.desk import review
    from tracebi.schedule import discover_schedules

    schedules, errors = discover_schedules(project / "reports")
    assert errors == []
    assert [s["report"] for s in schedules] == ["finance/weekly_summary"]

    for name in ("finance/weekly_summary", "ops/weekly_summary"):
        cli.main(["report", "build", name, "--reports-dir", str(project / "reports")])
    builds = {b["report"] for b in review(str(project))["builds"]}
    assert {"finance/weekly_summary", "ops/weekly_summary"} <= builds


@pytest.mark.parametrize("name", [
    "", "/etc/passwd", "../x", "finance/../../x", "finance/", "a//b",
    ".hidden/x", "finance/_private", "a\\b",
])
def test_a_name_can_never_leave_reports(name):
    assert report_name_error(name) is not None
    with pytest.raises(ValueError):
        output_html("output", name)


def test_good_names_map_to_folders_under_output():
    assert report_name_error("finance/month_end/close") is None
    assert output_html("out", "finance/month_end/close").replace("\\", "/") == \
        "out/finance/month_end/close.html"
    assert output_html("out", "top").replace("\\", "/") == "out/top.html"


def test_the_cli_refuses_a_climbing_name(project, capsys):
    from tracebi import cli

    assert cli.main(["report", "build", "../escape",
                     "--reports-dir", str(project / "reports")]) == 1
    assert "invalid report name" in capsys.readouterr().err


def test_new_report_can_create_a_report_in_a_folder(project):
    from tracebi import cli

    assert cli.main(["new-report", "Finance/Month end/Close pack",
                     "--reports-dir", str(project / "reports")]) == 0
    pkg = project / "reports" / "finance" / "month_end" / "close_pack"
    assert (pkg / "report.json").is_file()
    assert json.loads((pkg / "report.json").read_text())["name"] == "Close pack"
