"""The analyst's journey, exactly as the scaffolded README teaches it:

    tracebi init → run-transform → validate → report build → verify

and then the two things the receipt exists to catch: a number edited in the
shipped file, and the warehouse changing under a built report.
"""

from tests.e2e.conftest import manifests, run_cli


def _build(proj):
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    code, out = run_cli("validate")
    assert code == 0 and "Project looks good" in out, out
    code, out = run_cli("report", "build", "sample_dashboard")
    assert code == 0, out
    [manifest] = manifests(proj)
    return manifest, proj / "output" / "sample_dashboard.html"


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
