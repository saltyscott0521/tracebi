"""The agent journey over the MCP gateway, against a scaffolded project:

    get_context → list models → a stamped query → validate a spec (wrong, then
    right) → render it → verify the receipt → build the report package →
    fetch the artifact back

plus the gateway's two security promises: a report name can't climb out of
``reports/``, and fetch can't read outside the output root. The tools are the
same plain functions the MCP server registers.
"""

import json

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

    with sqlite3.connect(scaffolded / "inputs" / "shop.sqlite") as db:
        db.executescript(
            "CREATE TABLE customers (customer_id INTEGER, region TEXT);"
            "INSERT INTO customers VALUES (1, 'North'), (2, 'South');"
            "CREATE TABLE orders (order_id INTEGER, customer_id INTEGER, amount REAL);"
            "INSERT INTO orders VALUES (10, 1, 5.5), (11, 2, 7.0), (12, 1, 2.25);"
            "CREATE TABLE salaries (person TEXT, salary REAL);"
            "INSERT INTO salaries VALUES ('ann', 1.0);")
    (scaffolded / "connections" / "shop.yaml").write_text(
        "name: shop\ntype: sql\nurl: sqlite:///inputs/shop.sqlite\n"
        "agents:\n  tables: [orders, customers]\n")

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

    approved = serve_app(monkeypatch).post(
        f"/api/code-requests/{proposed['request_id']}/approve")
    assert approved.status_code == 200, approved.text
    assert {"transform": "shop_orders", "status": "ok"} in approved.json()["runs"]
    assert (scaffolded / "transforms" / "shop_orders.contract.yaml").is_file()
    with duckdb.connect(str(scaffolded / "data" / "warehouse.duckdb"), read_only=True) as wh:
        assert wh.execute("SELECT sum(amount) FROM fact_shop_orders").fetchone()[0] == 14.75

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
    assert escaped["ok"] is False and "inside the project" in escaped["errors"][0]
