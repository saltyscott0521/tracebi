"""Your own data: connect a DuckDB warehouse, draft a model, query the total."""

import duckdb

from tracebi.model_registry import get_model


def _star(path):
    con = duckdb.connect(str(path))
    con.execute("create table dim_customer (customer_id integer, name varchar)")
    con.execute("insert into dim_customer values (1, 'Ada'), (2, 'Bea')")
    con.execute("create table dim_product (product_id integer, name varchar)")
    con.execute("insert into dim_product values (10, 'Widget'), (20, 'Gadget')")
    con.execute(
        "create table fact_sales ("
        "sale_id integer, customer_id integer, product_id integer, amount double)"
    )
    con.execute(
        "insert into fact_sales values (1, 1, 10, 5.0), (2, 1, 20, 7.5), (3, 2, 10, 2.5)"
    )
    con.close()


def test_connect_then_draft_a_model_that_loads(scaffolded, cli, monkeypatch):
    # A previous test in this process may have loaded another connection,
    # and load_dotenv does not override a variable that is already set.
    monkeypatch.delenv("TRACEBI_WH_DATABASE", raising=False)
    db = scaffolded / "sales.duckdb"
    _star(db)

    code, out = cli("connect", "wh", "--kind", "duckdb", "--database", str(db))
    assert code == 0, out
    assert "3 tables" in out
    assert str(db) not in out
    # A warehouse inside the project is a path in the file; nothing to hide.
    declared = (scaffolded / "connections" / "wh.yaml").read_text(encoding="utf-8")
    assert "database: sales.duckdb" in declared
    assert not (scaffolded / "models" / "_connections").exists()

    code, out = cli(
        "new-model", "Sales", "--from", "wh",
        "--tables", "fact_sales,dim_customer,dim_product",
    )
    assert code == 0, out
    # The draft is the declarative form the reference models use, not Python.
    assert not (scaffolded / "models" / "sales.py").exists()
    model_text = (scaffolded / "models" / "sales.yaml").read_text(encoding="utf-8")
    assert "# DRAFT: review" in model_text
    assert str(db) not in model_text
    assert "connection: wh" in model_text
    assert "connection 'wh'" in out

    code, out = cli("list-models")
    assert code == 0, out
    assert "models/sales.yaml" in out
    assert "_connections" not in out

    model = get_model("sales")
    info = model.info()
    links = {(r["left_key"], r["right_table"]) for r in info["relationships"]}
    assert ("customer_id", "dim_customer") in links
    assert ("product_id", "dim_product") in links
    measures = {item["name"]: item for item in info["measures"]}
    assert measures["amount"]["agg"] == "sum"

    total = model.query(fact="fact_sales", measures=["amount"]).to_pandas()
    assert float(total["amount"].iloc[0]) == 15.0
    by_name = model.query(
        fact="fact_sales", measures=["amount"], dimensions=["dim_customer.name"],
    ).to_pandas().set_index("dim_customer.name")
    assert float(by_name.loc["Ada", "amount"]) == 12.5
    assert float(by_name.loc["Bea", "amount"]) == 2.5


def test_a_draft_from_the_workspace_warehouse_reads_type_warehouse(scaffolded, cli):
    # `tracebi init` declares connections/warehouse.yaml over the file the
    # transforms sink into; a draft from it reads the warehouse on any tier.
    db = scaffolded / "data" / "warehouse.duckdb"
    db.parent.mkdir(exist_ok=True)
    _star(db)
    code, out = cli("new-model", "Orders", "--from", "warehouse", "--tables", "fact_sales,dim_customer")
    assert code == 0, out
    assert "type: warehouse" in out
    text = (scaffolded / "models" / "orders.yaml").read_text(encoding="utf-8")
    assert "    type: warehouse" in text and "connection:" not in text
    total = get_model("orders").query(fact="fact_sales", measures=["amount"]).to_pandas()
    assert float(total["amount"].iloc[0]) == 15.0
