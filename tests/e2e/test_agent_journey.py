"""The agent journey over the MCP gateway, against a scaffolded project:

    get_context → list models → a stamped query → validate a spec (wrong, then
    right) → render it → verify the receipt → build the report package →
    fetch the artifact back

plus the gateway's two security promises: a report name can't climb out of
``reports/``, and fetch can't read outside the output root. The tools are the
same plain functions the MCP server registers.
"""

import json
import re

from tests.e2e.conftest import run_cli


def _spec(fact, measure="revenue"):
    return {"name": "Agent Brief", "sections": [
        {"type": "table", "title": "Revenue by region",
         "data": {"model": "sample_model", "query": {
             "fact": fact, "measures": [measure],
             "dimensions": ["dim_region.region"]}}}]}


def test_an_agent_authors_verifies_and_delivers_a_report(scaffolded):
    from tracebi import mcp_server as gw
    from tracebi.model_registry import get_model

    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out

    context = gw.gateway_context(model="sample_model", brief=True)
    assert "sample_model" in json.dumps(context)

    models = gw.gateway_models()
    assert "sample_model" in json.dumps(models)
    info = gw.gateway_model_info("sample_model")
    fact = info["facts"][0]["name"]

    # A stamped query: the fingerprint is the model's own answer.
    stamped = gw.gateway_query("sample_model", fact, ["revenue"],
                               dimensions=["dim_region.region"])
    direct = get_model("sample_model").query(fact, ["revenue"],
                                             dimensions=["dim_region.region"])
    assert stamped["fingerprint"] == direct.fingerprint()
    assert stamped["lineage"]

    # Validate: a wrong measure is caught before anything runs, and named.
    bad = gw.gateway_validate_spec(_spec(fact, "no_such_measure"))
    assert bad["ok"] is False and "no_such_measure" in json.dumps(bad)
    good = gw.gateway_validate_spec(_spec(fact))
    assert good["ok"] is True, good

    rendered = gw.gateway_render_spec(_spec(fact), output_dir="output")
    assert rendered["ok"] is True, rendered
    verified = gw.gateway_verify_manifest(rendered["manifest_path"])
    assert verified["verdict"] == "reproduces", verified
    assert verified["summary"]["reproduces"] == len(rendered["dataset_fingerprints"])

    built = gw.gateway_build_report("sample_model/sample_dashboard")
    assert built["ok"] is True, built
    assert built["transform_contracts"], "the build joins the sink contract"
    fetched = gw.gateway_fetch_artifact(built["output_path"])
    assert "tracebi-receipt" in json.dumps(fetched)


def test_an_agent_starts_a_report_in_the_house_theme_the_person_chose(scaffolded):
    """The person picked Nightdesk when offered the three: start_draft writes it
    into report.json, the agent keeps it beside its binding, and the built page
    opens dark in Nightdesk's tokens. A name that is no house theme is refused
    naming the three."""
    from tracebi import mcp_server as gw

    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    path = "sample_model/desk_brief"
    refused = gw.gateway_start_draft("reports", path, theme="atlas")
    assert refused["ok"] is False and "ledger, nightdesk, signal" in refused["errors"][0]
    started = gw.gateway_start_draft("reports", path, theme="nightdesk")
    assert started["ok"] is True, started
    declared = json.loads(gw.gateway_read_draft("reports", path)["files"]["report.json"])
    assert declared == {"theme": "nightdesk"}

    fact = gw.gateway_model_info("sample_model")["facts"][0]["name"]
    stamped = gw.gateway_query("sample_model", fact, ["revenue"])
    declared.update(name="Desk Brief", data={"totals": stamped["binding"]})
    page = ('<!doctype html><html><head><title>Desk Brief</title></head><body>'
            '<div class="tb-grid"><div class="tb-kpi tb-kpi--lead" data-tb-figure="value" '
            'data-tb-binding="totals" data-tb-cell="revenue"><span class="tb-kpi-label">'
            'Revenue</span><span class="tb-kpi-value"></span></div></div></body></html>')
    for name, text in (("report.json", json.dumps(declared)), ("template.html", page)):
        wrote = gw.gateway_write_draft_file("reports", path, name, text)
        assert wrote["ok"] is True, wrote
    published = gw.gateway_publish_draft("reports", path, note="a desk brief")
    assert published["ok"] is True, published
    assert json.loads((scaffolded / "reports" / path / "report.json").read_text())[
        "theme"] == "nightdesk"

    built = gw.gateway_build_report(path)
    assert built["ok"] is True, built
    html = open(built["output_path"], encoding="utf-8").read()
    assert re.search(r'<html[^>]*data-tb-mode="dark"', html)       # dark first
    assert re.search(r'<html[^>]*data-tb-density="compact"', html)
    assert "/* nightdesk: " in html and 'font-family:"Geist Mono"' in html
    assert '--tb-font-num: "Geist Mono", var(--tb-mono);' in html

def test_the_gateway_refuses_paths_outside_the_project(scaffolded):
    from tracebi import mcp_server as gw

    escaped = gw.gateway_build_report("../../etc/passwd")
    assert escaped["ok"] is False and ".." in escaped["errors"][0]
    fetched = gw.gateway_fetch_artifact("/etc/passwd")
    assert fetched["ok"] is False and "escapes" in fetched["errors"][0]


_SHOP_SQL = """\
-- source: shop.orders
-- source: shop.customers
CREATE OR REPLACE TABLE dim_shop_customer AS
SELECT customer_id, region FROM shop.customers;
CREATE OR REPLACE TABLE fact_shop_orders AS
SELECT order_id, customer_id, amount FROM shop.orders;
"""

_SHOP_CONTRACT = """\
note: Orders and customers from the shop database, as they are.
checks:
  - rows: fact_shop_orders
    at_least: 3
  - foreign_key: fact_shop_orders
    column: customer_id
    refers_to: [dim_shop_customer, customer_id]
"""


def _shop(root):
    """A shop database the person connected, agents allowed two of its three tables."""
    import sqlite3

    with sqlite3.connect(root / "inputs" / "shop.sqlite") as db:
        db.executescript(
            "CREATE TABLE customers (customer_id INTEGER, region TEXT);"
            "INSERT INTO customers VALUES (1, 'North'), (2, 'South');"
            "CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, amount REAL);"
            "INSERT INTO orders VALUES (10, 1, 5.5), (11, 2, 7.0), (12, 1, 2.25);"
            "CREATE TABLE salaries (person TEXT, salary REAL);"
            "INSERT INTO salaries VALUES ('ann', 1.0);")
    (root / "connections" / "shop.yaml").write_text(
        "name: shop\ntype: sql\nurl: sqlite:///inputs/shop.sqlite\n"
        "agents:\n  tables: [orders, customers]\n")


def test_an_agent_onboards_a_source_through_an_approved_transform(scaffolded, monkeypatch):
    """A person connected a database and allowed agents two of its three
    tables. The agent sees only those two, proposes a transform over them as a
    code request, and nothing lands until an admin approves it: then the
    transform runs once and its tables are in the warehouse. A proposal that
    reads the third table is refused before anything is stored."""
    import sqlite3

    import duckdb

    from tests.e2e.conftest import serve_app
    from tracebi import mcp_server as gw

    _shop(scaffolded)

    shop = next(c for c in gw.gateway_list_connections()["connections"] if c["name"] == "shop")
    assert shop["type"] == "sql" and sorted(shop["agent_tables"]) == ["customers", "orders"]
    listed = gw.gateway_list_source_tables("shop")
    assert sorted(t["name"] for t in listed["tables"]) == ["customers", "orders"], listed
    # A table agents may not read answers exactly as one that is not there.
    hidden = gw.gateway_describe_source_table("shop", "salaries")
    assert hidden == {"ok": False, "error": "Table 'salaries' not found in connection 'shop'."}
    assert gw.gateway_describe_source_table("shop", "nothing")["error"].startswith(
        "Table 'nothing' not found")
    orders = gw.gateway_describe_source_table("shop", "orders", sample=2)
    assert orders["ok"] is True and orders["total"] == 3 and len(orders["sample"]) == 2
    assert orders["profile"]["columns"]["customer_id"]["distinct"] == 2

    refused = gw.gateway_propose_transform(
        "shop_salaries", "-- source: shop.salaries\nCREATE TABLE s AS SELECT * FROM shop.salaries;",
        _SHOP_CONTRACT, "pay by person")
    assert refused["ok"] is False
    assert "no table shop.salaries among those agents may read" in refused["errors"][0]
    assert not (scaffolded / ".tracebi" / "requests").exists()   # nothing stored

    proposed = gw.gateway_propose_transform("shop_orders", _SHOP_SQL, _SHOP_CONTRACT,
                                            "Orders by customer, for a sales model")
    assert proposed["ok"] is True, proposed
    assert proposed["review_url"].endswith("/review")
    assert not (scaffolded / "transforms" / "shop_orders.sql").exists()   # nothing runs yet
    # It ran once against a throwaway copy, and only there.
    assert proposed["dry_run"]["summary"] == "Dry run: 2 tables, checks 2 of 2 passed"
    assert not (scaffolded / "data" / "warehouse.duckdb").exists()

    approved = serve_app(monkeypatch).post(
        f"/api/code-requests/{proposed['request_id']}/approve")
    assert approved.status_code == 200, approved.text
    assert {"transform": "shop_orders", "status": "ok"} in approved.json()["runs"]
    # Not a git repository: approved all the same, and the request says why no commit.
    assert approved.json()["commit_sha"] is None
    assert "not inside a git work tree" in approved.json()["commit_note"]
    assert (scaffolded / "transforms" / "shop_orders.contract.yaml").is_file()
    with duckdb.connect(str(scaffolded / "data" / "warehouse.duckdb"), read_only=True) as wh:
        assert wh.execute("SELECT sum(amount) FROM fact_shop_orders").fetchone()[0] == 14.75

    # The project as a graph: the agent's describe_project is the app's
    # /api/graph, and the person's allowlist is what it says agents may read.
    from tracebi.web import discovery

    app = serve_app(monkeypatch, models=True)
    monkeypatch.setattr(discovery, "_live_connections", {})
    discovery.register_connections("connections")
    graph = app.get("/api/graph").json()
    described = gw.gateway_describe_project()
    assert described["summary"] == graph["summary"]
    agents = {n["id"]: n["passport"]["agents"]["state"] for n in described["nodes"]
              if n["id"].startswith("source_table:shop.")}
    assert agents == {"source_table:shop.customers": "ok", "source_table:shop.orders": "ok",
                      "source_table:shop.salaries": "none"}
    assert ["source:shop", "transform:shop_orders"] in described["edges"]

    # Saving back: the sunk table goes out to the connection it came from.
    out = gw.gateway_export_table("warehouse", "fact_shop_orders", "shop")
    assert out["ok"] is True and out["rows"] == 3, out
    with sqlite3.connect(scaffolded / "inputs" / "shop.sqlite") as db:
        assert db.execute("SELECT count(*) FROM fact_shop_orders").fetchone()[0] == 3
    # Or to a prefix, as Parquet; a local one stays inside the project.
    out = gw.gateway_export_table("warehouse", "dim_shop_customer", "exports/shop")
    assert out["ok"] is True, out
    assert duckdb.sql(f"SELECT count(*) FROM '{out['written']}'").fetchall()[0][0] == 2
    escaped = gw.gateway_export_table("warehouse", "dim_shop_customer", "../elsewhere")
    assert escaped["ok"] is False and "inside the workspace" in escaped["errors"][0]


_SHOP_MODEL = """\
name: shop_model
connectors:
  - name: warehouse
    connection: warehouse
tables:
  - name: fact_shop_orders
    connector: warehouse
    source: fact_shop_orders
  - name: dim_shop_customer
    connector: warehouse
    source: dim_shop_customer
dimensions:
  - name: dim_shop_customer
    table: dim_shop_customer
    key: customer_id
    attributes: [region]
facts:
  - name: fact_shop_orders
    table: fact_shop_orders
    measures: [amount]
    foreign_keys:
      dim_shop_customer: customer_id
measures:
  - name: amount
    column: amount
    agg: sum
"""

# The change: each order carries its customer's region.
_SHOP_SQL_REGION = _SHOP_SQL.replace(
    "SELECT order_id, customer_id, amount FROM shop.orders;",
    "SELECT o.order_id, o.customer_id, o.amount, c.region\n"
    "FROM shop.orders o JOIN shop.customers c USING (customer_id);")


def _git(root, *args):
    import subprocess

    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_an_agent_changes_a_transform_after_a_dry_run_and_approval_commits_it(
        scaffolded, monkeypatch):
    """The agent reads a transform that exists, proposes a change that adds a
    column, and sees it run against a throwaway copy: the new column in the
    sample rows, the checks passed, the warehouse untouched. The reviewer gets
    the diff and the dry run. A change that drops a table a model reads, or
    touches a Python transform, is refused; one whose checks fail is stored
    but cannot be approved. Approving the good one in a git workspace makes
    one commit (author the agent, committer the approver, the request's
    trailer), and only then does the warehouse change."""
    import shutil

    import duckdb
    import pytest

    from tests.e2e.conftest import serve_app
    from tracebi import mcp_server as gw

    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    _shop(scaffolded)
    (scaffolded / "transforms" / "shop_orders.sql").write_text(_SHOP_SQL)
    (scaffolded / "transforms" / "shop_orders.contract.yaml").write_text(_SHOP_CONTRACT)
    code, out = run_cli("run-transform", "shop_orders")
    assert code == 0, out
    (scaffolded / "models" / "shop_model.yaml").write_text(_SHOP_MODEL)
    _git(scaffolded, "init", "-q", "-b", "main")
    _git(scaffolded, "add", "-A")
    _git(scaffolded, "-c", "user.name=t", "-c", "user.email=t@x", "commit", "-q", "-m", "workspace")

    # Read what exists: its code, what its last run read, and its lineage. Never rows.
    read = gw.gateway_read_transform("shop_orders")
    assert read["ok"] and read["form"] == "sql" and read["text"] == _SHOP_SQL
    assert read["contract_yaml"] == _SHOP_CONTRACT
    assert read["tables"] == ["dim_shop_customer", "fact_shop_orders"]
    assert [s["ref"] for s in read["last_run"]["sources"]] == ["shop.orders", "shop.customers"]
    assert read["lineage"]["fact_shop_orders"]["amount"]["from"] == ["shop.orders.amount"]
    assert "change=true" in read["change"]
    assert gw.gateway_read_transform("nope") == {
        "ok": False, "error": "Transform 'nope' not found in transforms/."}
    assert "tracebi push" in gw.gateway_read_transform("sample_transform")["change"]
    graph = gw.gateway_describe_project()
    [node] = [n for n in graph["nodes"] if n["id"] == "transform:shop_orders"]
    assert node["name"] == "shop_orders" and "read_transform" in node["passport"]["agents"]["tools"]

    # Refused before anything is stored: a Python transform, a dropped table a model reads.
    python = gw.gateway_propose_transform("sample_transform", _SHOP_SQL, _SHOP_CONTRACT,
                                          "rewrite", change=True)
    assert python["ok"] is False and "tracebi push" in python["errors"][0]
    dropped = gw.gateway_propose_transform(
        "shop_orders", _SHOP_SQL.split("CREATE OR REPLACE TABLE fact_shop_orders")[0]
        .replace("dim_shop_customer", "dim_customer"), "checks:\n  - rows: dim_customer\n",
        "rename the dimension", change=True)
    assert dropped["ok"] is False
    assert any("no longer writes dim_shop_customer, which model shop_model reads" in e
               for e in dropped["errors"]), dropped
    assert any("fact_shop_orders, which model shop_model" in e for e in dropped["errors"])
    assert not (scaffolded / ".tracebi" / "requests").exists()

    warehouse = scaffolded / "data" / "warehouse.duckdb"
    before = warehouse.stat().st_mtime_ns
    proposed = gw.gateway_propose_transform("shop_orders", _SHOP_SQL_REGION, _SHOP_CONTRACT,
                                            "Each order carries its region", change=True)
    assert proposed["ok"] is True, proposed
    dry = proposed["dry_run"]
    assert dry["ok"] is True and dry["summary"] == "Dry run: 2 tables, checks 2 of 2 passed", dry
    [fact] = [t for t in dry["tables"] if t["name"] == "fact_shop_orders"]
    assert [c["name"] for c in fact["columns"]] == ["order_id", "customer_id", "amount", "region"]
    assert fact["rows"] == 3 and {r["region"] for r in fact["sample"]} == {"North", "South"}
    assert dry["lineage"]["fact_shop_orders"]["region"]["from"] == ["shop.customers.region"]
    assert all(c["passed"] for c in dry["checks"])
    # Nothing real moved: the warehouse file, its columns, the scratch copy gone.
    assert warehouse.stat().st_mtime_ns == before
    with duckdb.connect(str(warehouse), read_only=True) as wh:
        assert "region" not in [r[0] for r in wh.execute("DESCRIBE fact_shop_orders").fetchall()]
    assert not (scaffolded / ".tracebi" / "dryrun").exists()

    # The reviewer's payload: the diff against the published file, and the dry run.
    app = serve_app(monkeypatch)
    review = app.get(f"/api/code-requests/{proposed['request_id']}").json()
    sql_file = next(f for f in review["files"] if f["path"] == "transforms/shop_orders.sql")
    assert not sql_file["new"] and "+FROM shop.orders o JOIN shop.customers c" in sql_file["diff"]
    assert "-SELECT order_id, customer_id, amount FROM shop.orders;" in sql_file["diff"]
    assert review["dry_run"]["summary"] == dry["summary"]
    assert review["dry_run"]["tables"] == dry["tables"]

    # A failing check: stored, shown failed, and it cannot be approved.
    failing = gw.gateway_propose_transform(
        "shop_orders", _SHOP_SQL_REGION,
        _SHOP_CONTRACT.replace("at_least: 3", "exactly: 99"), "Each order, region", change=True)
    assert failing["ok"] is True and failing["dry_run"]["ok"] is False
    assert failing["dry_run"]["summary"] == "Dry run: 2 tables, checks 1 of 2 passed"
    [bad] = [c for c in failing["dry_run"]["checks"] if not c["passed"]]
    assert bad["check"] == "rows" and bad["observed"] == 3
    listed = {r["id"]: r for r in app.get("/api/code-requests").json()["requests"]}
    assert listed[failing["request_id"]]["dry_run"] == {
        "ok": False, "summary": failing["dry_run"]["summary"]}
    refused = app.post(f"/api/code-requests/{failing['request_id']}/approve")
    assert refused.status_code == 422 and "dry run did not pass" in refused.text

    # Approval: one commit of exactly those files, then the warehouse changes.
    head = _git(scaffolded, "rev-parse", "HEAD").strip()
    approved = app.post(f"/api/code-requests/{proposed['request_id']}/approve")
    assert approved.status_code == 200, approved.text
    done = approved.json()
    assert {"transform": "shop_orders", "status": "ok"} in done["runs"]
    assert done["commit_sha"] == _git(scaffolded, "rev-parse", "HEAD").strip() != head
    assert _git(scaffolded, "rev-list", "--count", f"{head}..HEAD").strip() == "1"
    shown = _git(scaffolded, "log", "-1", "--format=%an <%ae>%n%cn <%ce>%n%B")
    approver = done["decided_by"] or "tracebi"
    assert shown.splitlines()[:3] == [
        "mcp:agent <mcp:agent@tracebi.local>", f"{approver} <{approver}@tracebi.local>",
        "transforms: shop_orders — Each order carries its region"]
    assert f"TraceBi-Request: {proposed['request_id']}" in shown
    # The contract came back unchanged, so the SQL is the one file that moved.
    assert _git(scaffolded, "show", "--name-only", "--format=", "HEAD").split() == [
        "transforms/shop_orders.sql"]
    assert _git(scaffolded, "status", "--porcelain", "--", "transforms").strip() == ""
    with duckdb.connect(str(warehouse), read_only=True) as wh:
        assert "region" in [r[0] for r in wh.execute("DESCRIBE fact_shop_orders").fetchall()]
