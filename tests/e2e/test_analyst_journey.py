"""The analyst's journey, phase by phase:

    tracebi init → run-transform → validate → report build → verify

and then the two things the receipt exists to catch: a number edited in the
shipped file, and the warehouse changing under a built report. The first test
is the shorter road the README prints: init's own next steps, typed as printed.
"""

import json

from tests.e2e.conftest import manifests, run_cli


def test_the_steps_init_prints_work_as_printed(tmp_path, monkeypatch, isolated):
    proj = tmp_path / "proj"
    code, out = run_cli("init", str(proj))
    assert code == 0, out
    monkeypatch.chdir(proj)

    printed = [line.split("#")[0].split()[1:] for line in out.splitlines()
               if line.strip().startswith("tracebi ")]
    assert [step[0] for step in printed] == ["run-pipeline", "verify", "serve"], out
    for step in printed:
        if step[0] == "serve":           # it would not return; the web journeys serve it
            continue
        code, out = run_cli(*step)
        assert code == 0, out
    assert "REPRODUCES" in out           # the last step run was the verify
    assert (proj / "output" / "sample_model" / "sample_dashboard.html").is_file()


def _build(proj):
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    code, out = run_cli("validate")
    assert code == 0 and "Project looks good" in out, out
    code, out = run_cli("report", "build", "sample_model/sample_dashboard")
    assert code == 0, out
    [manifest] = manifests(proj)
    return manifest, proj / "output" / "sample_model" / "sample_dashboard.html"


def test_the_first_run_ends_in_reproduces(scaffolded):
    manifest, html = _build(scaffolded)
    assert html.stat().st_size > 0

    code, out = run_cli("verify", str(manifest), "--strict", "--contracts")
    assert code == 0, out
    assert "REPRODUCES" in out
    assert "satisfied" in out and "unchanged" in out     # the sink contract re-ran

    code, out = run_cli("verify", "--file", str(html))
    assert code == 0, out
    assert "FILE INTACT" in out


def test_a_number_edited_in_the_shipped_file_is_caught(scaffolded):
    _, html = _build(scaffolded)
    page = html.read_text()
    edited = page.replace("16888.05,10", "18888.05,10", 1)
    assert edited != page, "the KPI total moved; update the edit"
    html.write_text(edited)

    code, out = run_cli("verify", "--file", str(html))
    assert code != 0
    assert "FILE ALTERED" in out


def test_a_warehouse_change_under_a_built_report_is_caught(scaffolded):
    manifest, _ = _build(scaffolded)
    orders = scaffolded / "inputs" / "orders.csv"
    orders.write_text(orders.read_text().replace('"$1,198.80"', '"$2,198.80"', 1))
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out

    code, out = run_cli("verify", str(manifest), "--strict")
    assert code != 0, out
    assert "REPRODUCES —" not in out


def test_new_scaffolds_join_the_loop(scaffolded):
    """A model and a report scaffolded from the CLI build and reproduce."""
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    code, out = run_cli("new-report", "Regional Review")
    assert code == 0, out
    code, out = run_cli("report", "build", "regional_review")
    assert code == 0, out
    manifest = scaffolded / "output" / "regional_review.html.manifest.json"
    code, out = run_cli("verify", str(manifest))
    assert code == 0 and "REPRODUCES" in out, out


def test_a_report_in_a_folder_builds_by_its_path(scaffolded):
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    code, out = run_cli("new-report", "Finance/Weekly")
    assert code == 0, out
    code, out = run_cli("report", "build", "finance/weekly")
    assert code == 0, out
    assert (scaffolded / "output" / "finance" / "weekly.html").is_file()


def test_a_measure_with_its_own_filter_is_stamped_and_reproduces(scaffolded):
    """The scaffolded model declares a measure with its own filter; a report
    binds it, and the receipt shows the filter and re-checks clean. The
    filtered figure is the one the rows say: a subset of the unfiltered total."""
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out

    report = scaffolded / "reports" / "sample_model" / "sample_dashboard" / "report.json"
    doc = json.loads(report.read_text())
    doc["data"]["large"] = {"model": "sample_model", "query": {
        "fact": "fact_orders", "measures": ["large_order_revenue", "revenue"]}}
    report.write_text(json.dumps(doc, indent=2))

    code, out = run_cli("report", "build", "sample_model/sample_dashboard")
    assert code == 0, out
    [manifest] = manifests(scaffolded)
    code, out = run_cli("verify", str(manifest), "--strict")
    assert code == 0 and "REPRODUCES" in out, out

    receipt = json.loads(manifest.read_text())
    [binding] = [b for b in receipt["embedded_data"] if b["name"] == "large"]
    assert binding["query_spec"]["measures"] == ["large_order_revenue", "revenue"]
    [measure] = [m for m in receipt["semantic_contract"]["sample_model"]["slice"]["measures"]
                 if m["name"] == "large_order_revenue"]
    assert measure["filters"] == {"qty": {"gte": 10}}

    from tracebi.model_registry import get_model
    both = get_model("sample_model").query(
        fact="fact_orders", measures=["large_order_revenue", "revenue"]).to_pandas()
    assert 0 < both["large_order_revenue"].iloc[0] < both["revenue"].iloc[0]


def test_a_filter_on_a_column_the_fact_lacks_is_refused_by_name(scaffolded):
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    model_file = scaffolded / "models" / "sample_model.yaml"
    text = model_file.read_text()
    assert "filters: {qty: {gte: 10}}" in text
    model_file.write_text(text.replace("filters: {qty: {gte: 10}}",
                                       "filters: {quantity: {gte: 10}}"))
    report = scaffolded / "reports" / "sample_model" / "sample_dashboard" / "report.json"
    doc = json.loads(report.read_text())
    doc["data"]["large"] = {"model": "sample_model", "query": {
        "fact": "fact_orders", "measures": ["large_order_revenue"]}}
    report.write_text(json.dumps(doc, indent=2))

    code, out = run_cli("report", "build", "sample_model/sample_dashboard")
    assert code != 0
    assert "large_order_revenue" in out and "quantity" in out, out
