"""SQL calculations, end to end: a report binds a named SELECT over the
warehouse. It builds, its receipt records the SQL and labels it, ``verify``
reproduces it, and after the warehouse changes ``verify`` reports the drift.
"""

import json
import subprocess
import sys

from tests.e2e.conftest import manifests, run_cli

RUNNING = ("SELECT region_id, order_date, SUM(revenue) OVER (PARTITION BY region_id "
           "ORDER BY order_date) AS running_revenue FROM fact_orders")
BY_REGION = "SELECT region_id, {{ measure('revenue') }} AS revenue FROM fact_orders GROUP BY region_id"


def _declare(scaffolded, calcs, bindings):
    """Add these SQL calculations and bindings to the sample dashboard. Its
    report.json has no SQL calculation of its own; these tests add them."""
    report = scaffolded / "reports" / "sample_model" / "sample_dashboard" / "report.json"
    doc = json.loads(report.read_text())
    doc.setdefault("sql_calculations", {}).setdefault("sample_model", {}).update(calcs)
    doc["data"].update(bindings)
    report.write_text(json.dumps(doc, indent=2))


def _section(receipt, name):
    """The manifest section a binding was embedded as (its lineage lives there)."""
    [section] = [s for s in receipt["sections"] if s.get("id") == name]
    return section


def test_a_sql_calculation_reproduces_then_reports_drift_when_the_warehouse_changes(scaffolded):
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    _declare(scaffolded,
             {"running_revenue": RUNNING, "revenue_by_region": BY_REGION},
             {"running": {"model": "sample_model", "sql": "running_revenue"},
              "sql_by_region": {"model": "sample_model", "sql": "revenue_by_region"}})

    code, out = run_cli("report", "build", "sample_model/sample_dashboard")
    assert code == 0, out
    [manifest] = manifests(scaffolded)
    code, out = run_cli("verify", str(manifest), "--strict")
    assert code == 0 and "REPRODUCES" in out, out

    receipt = json.loads(manifest.read_text())
    [running] = [b for b in receipt["embedded_data"] if b["name"] == "running"]
    assert running["query_spec"] == {"sql": RUNNING}
    [query] = [n for n in _section(receipt, "running")["dataset_lineage"]
               if n.get("metadata", {}).get("query_spec")]
    assert query["metadata"]["sql_resolved"] == RUNNING
    resolved = _section(receipt, "sql_by_region")["dataset_lineage"][-1]["metadata"]["sql_resolved"]
    assert 'SUM("revenue")' in resolved and "{{" not in resolved

    labelled = receipt["semantic_contract"]["sample_model"]["slice"]["sql_calculations"]
    assert {(c["binding"], c["label"]) for c in labelled} == {
        ("running", "calculated in this report (SQL)"),
        ("sql_by_region", "calculated in this report (SQL)"),
    }

    # The warehouse changes under the same calculation: verify says so.
    subprocess.run(
        [sys.executable, "-c",
         "import duckdb; c = duckdb.connect('data/warehouse.duckdb'); "
         "c.execute('UPDATE fact_orders SET revenue = revenue + 1'); c.close()"],
        check=True, cwd=scaffolded)
    code, out = run_cli("verify", str(manifest))
    assert code != 0, out
    assert "running — input fingerprint(s) for table(s) fact_orders differ" in out, out
    assert "sql_by_region — input fingerprint(s) for table(s) fact_orders differ" in out, out


def test_a_calculation_that_writes_is_refused_when_the_report_builds(scaffolded):
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    _declare(scaffolded, {"wipe": "DELETE FROM fact_orders"},
             {"wiped": {"model": "sample_model", "sql": "wipe"}})

    code, out = run_cli("report", "build", "sample_model/sample_dashboard")
    assert code != 0
    assert "must start with SELECT or WITH" in out, out
