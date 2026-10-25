"""The reference project, end to end: both transforms sink, then EVERY report
in it — packages, folders, the JSON spec, the scenario —
builds and holds to the receipt bar. The showcase and the housing report are
the maintained demos; a feature that breaks either breaks this test, so the
demos can never quietly stop demoing.

Built once per module (the transforms take seconds); each test reads the
built project.
"""

import json
import os
import re
import shutil
import sys

import pytest

from tests.e2e.conftest import REFERENCE_PROJECT, run_cli

REPORTS = {
    "portfolio_model/portfolio_dashboard": "portfolio_model/portfolio_dashboard",
    "portfolio_model/portfolio_book": "portfolio_model/portfolio_book",
    "portfolio_model/portfolio_desk": "portfolio_model/portfolio_desk",
    "portfolio_model/portfolio_overview": "portfolio_model/portfolio_overview",
    "portfolio_model/portfolio_concentration": "portfolio_model/portfolio_concentration",
    "portfolio_model/portfolio_showcase": "portfolio_model/portfolio_showcase",
    "housing_model/affordability": "housing_model/affordability",
    "saas_model/mrr_dashboard": "saas_model/mrr_dashboard",
    "saas_model/cohort_brief": "saas_model/cohort_brief",
    "wealth_model/aum_by_branch": "wealth_model/aum_by_branch",
    "wealth_model/aum_by_region": "wealth_model/aum_by_region",
}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from tracebi import model_registry, pipeline_registry

    proj = tmp_path_factory.mktemp("ref") / "portfolio_project"
    shutil.copytree(REFERENCE_PROJECT, proj, ignore=shutil.ignore_patterns(
        "data", "output", ".tracebi", "explorations", "__pycache__", "*.duckdb"))
    saved = (os.getcwd(), model_registry._registry, model_registry._auto_discovered,
             pipeline_registry._registry, pipeline_registry._auto_discovered)
    model_registry._registry = model_registry.ModelRegistry()
    model_registry._auto_discovered = False
    pipeline_registry._registry = pipeline_registry.PipelineRegistry()
    pipeline_registry._auto_discovered = False
    os.chdir(proj)
    try:
        for transform in ("holdings_transform", "saas_transform", "affordability_transform",
                          "wealth_transform"):
            code, out = run_cli("run-transform", transform)
            assert code == 0, out
        for name in REPORTS:
            code, out = run_cli("report", "build", name)
            assert code == 0, f"{name}: {out}"
        yield proj
    finally:
        os.chdir(saved[0])
        (model_registry._registry, model_registry._auto_discovered,
         pipeline_registry._registry, pipeline_registry._auto_discovered) = saved[1:]


def _manifest(proj, name):
    return proj / "output" / f"{name}.html.manifest.json"


@pytest.mark.parametrize("name", sorted(REPORTS))
def test_every_report_reproduces_and_its_file_is_intact(built, name):
    manifest = _manifest(built, name)
    code, out = run_cli("verify", str(manifest), "--contracts")
    assert code == 0, out
    assert "REPRODUCES" in out
    code, out = run_cli("verify", "--file", str(built / "output" / f"{name}.html"))
    assert code == 0, out
    assert "FILE INTACT" in out


HOLDINGS_TABLES = ("dim_fund", "dim_issuer", "dim_rating", "fact_holdings", "dim_date",
                   "dim_flow_type", "fact_cashflows")


def test_the_sql_transform_and_its_pandas_escape_hatch_sink_identical_tables(built, tmp_path, monkeypatch):
    """The reference transform is SQL (holdings_transform.sql, which `built`
    ran); holdings_transform_pandas.py does the same work in pandas. Run into a
    second copy of the project, every table they sink fingerprints the same,
    row order included, read back through the connector load path the model
    and the certificate use. So a report reads the same numbers whichever
    form fed it, and the pandas file stays an honest example of the escape hatch."""
    from tracebi.connectors.duckdb_connector import DuckDBConnector
    from tracebi.model.dataset import frame_fingerprint

    other = tmp_path / "pandas_project"
    shutil.copytree(REFERENCE_PROJECT, other, ignore=shutil.ignore_patterns(
        "data", "output", ".tracebi", "explorations", "__pycache__", "*.duckdb"))
    monkeypatch.chdir(other)
    code, out = run_cli("run-transform", "holdings_transform_pandas")
    assert code == 0 and "form: python" in out, out

    def fingerprints(root):
        wh = DuckDBConnector("warehouse", database=str(root / "data" / "warehouse.duckdb"))
        try:
            return {t: frame_fingerprint(wh.load(t)) for t in HOLDINGS_TABLES}
        finally:
            wh.disconnect()

    assert fingerprints(built) == fingerprints(other)
    # And the two forms' contracts certify the same tables with the same checks.
    sql_rec, pandas_rec = (json.loads((root / "data" / "warehouse.contracts.json").read_text())
                           ["transforms"]["holdings"] for root in (built, other))
    assert sql_rec["tables"] == pandas_rec["tables"]
    assert [(c["check"], c["table"], c["params"]) for c in sql_rec["checks"]] == [
        (c["check"], c["table"], c["params"]) for c in pandas_rec["checks"]]
    # Neither copy has TRACEBI_CRM_URL, so both read the CRM's committed
    # snapshot, through the same loader, and their certificates say so.
    sql_src, pandas_src = (rec["sources"]["crm.issuer_ratings"] for rec in (sql_rec, pandas_rec))
    for src in (sql_src, pandas_src):
        assert src["source_fallback"] == "csv" and src["fallback"] == "inputs/issuer_ratings.csv"
        assert "TRACEBI_CRM_URL" in src["reason"] and src["rows"] == 12
    assert sql_src["fingerprint"] == pandas_src["fingerprint"]


def test_without_the_crm_the_snapshot_feeds_the_ratings_and_the_trace_says_so(built, monkeypatch):
    """The reference project reads one table from a Postgres CRM. With no
    TRACEBI_CRM_URL (a fresh clone, CI's default) the demo still builds: the
    committed snapshot stands in, the certificate and every report trace say
    the CRM was not reached, and verify --contracts re-reads the snapshot.
    The app lists the connection without resolving it, and the model's
    Transform tab shows the -- source: line it ran. Data's Sources says the
    CRM is not connected here (200, no traceback) and which transform reads
    it, while the bank and billing databases that ship are, by their
    defaults; its Warehouse names who wrote dim_rating and what fed it."""
    from tests.e2e.conftest import release_warehouses, serve_app
    from tracebi.web import discovery

    rec = json.loads((built / "data" / "warehouse.contracts.json").read_text())["transforms"]["holdings"]
    assert rec["sources"]["crm.issuer_ratings"]["source_fallback"] == "csv"
    manifest = json.loads(_manifest(built, "portfolio_model/portfolio_showcase").read_text())
    rating = manifest["transform_contracts"]["dim_rating"]
    assert rating["status"] == "satisfied"
    assert rating["sources"]["crm.issuer_ratings"]["source_fallback"] == "csv"
    assert "reason" not in rating["sources"]["crm.issuer_ratings"]

    code, out = run_cli("verify", str(_manifest(built, "portfolio_model/portfolio_showcase")),
                        "--contracts")
    assert code == 0, out
    assert re.search(r"✓ unchanged\s+holdings: crm\.issuer_ratings \(the CSV snapshot", out), out

    c = serve_app(monkeypatch, models=True)
    try:
        # After serve_app: importing the app registers what it finds, so the
        # Sources list is read from a scan of this project's own folder.
        monkeypatch.setattr(discovery, "_live_connections", {})
        discovery.register_connections("connections")
        listed = c.get("/api/connectors").json()
        [crm] = [x for x in listed if x["name"] == "crm"]
        assert crm["url"] == "${TRACEBI_CRM_URL}" and crm["declared_in"] == "connections/crm.yaml"
        # Sources lists what feeds the warehouse, never the warehouse itself;
        # each by its label and its database, and where it lives as a place:
        # the variable that sets it (never read to say more), or the file the
        # connection's default names.
        assert sorted(x["name"] for x in listed if not x["warehouse"]) == ["bank", "billing", "crm"]
        assert (crm["label"], crm["dialect"]) == ("CRM (Postgres)", "postgresql")
        assert (crm["storage"]["where"], crm["storage"]["variable"]) == (
            "set by TRACEBI_CRM_URL", "TRACEBI_CRM_URL")
        [bank] = [x for x in listed if x["name"] == "bank"]
        assert (bank["label"], bank["dialect"]) == ("Core banking (SQLite file)", "sqlite")
        assert bank["storage"]["kind"] == "file" and bank["storage"]["where"].endswith("inputs/bank.sqlite")
        shown = c.get("/api/pipelines/portfolio_model/source").text
        assert "-- source: crm.issuer_ratings fallback: inputs/issuer_ratings.csv" in shown

        # Who reads the CRM, from the transform files: the SQL transform and
        # its pandas twin, each naming the one table.
        read_by = c.get("/api/connectors/crm").json()["read_by"]
        assert {"name": "holdings_transform", "tables": ["issuer_ratings"]} in read_by["transforms"]
        assert read_by["models"] == []
        tables = c.get("/api/connectors/crm/tables")
        assert tables.status_code == 200
        assert tables.json() == {"connected": False, "variable": "TRACEBI_CRM_URL",
                                 "reason": "TRACEBI_CRM_URL is not set"}
        # The inputs/ folder: the snapshot is read by the same transform.
        files = {f["path"]: f for f in c.get("/api/inputs").json()["files"]}
        assert "holdings_transform" in files["inputs/issuer_ratings.csv"]["read_by"]
        # A data file opens as a table; a script beside it does not.
        assert files["inputs/issuer_ratings.csv"]["table"] is True
        assert files["inputs/seed_crm.py"]["table"] is False
        assert files["inputs/holdings.csv"]["size"] > 0

        # One warehouse, the one tracebi.yaml declares, and every model reads
        # it: no model keeps a DuckDB file of its own.
        from tracebi.project_config import read_config
        assert read_config(str(built))["warehouse"] == {
            "tier": "file", "location": "data/warehouse.duckdb"}
        listed = c.get("/api/models").json()
        assert sorted(m["name"] for m in listed) == [
            "housing_model", "portfolio_model", "saas_model", "wealth_model"]
        assert all(m["connectors"] == ["warehouse"] for m in listed), listed
        names = {x["name"] for x in c.get("/api/connectors").json()}
        assert {"crm", "bank", "billing"} <= names and "housing_warehouse" not in names, names

        # The two databases that ship answer with no variable set: the
        # connection's default names the committed SQLite file, and the
        # wealth certificate records a live load of each of the bank's tables.
        bank = c.get("/api/connectors/bank/tables").json()
        assert bank["connected"] is True, bank
        assert sorted(t["name"] for t in bank["tables"]) == [
            "accounts", "activities", "branches", "clients", "holdings", "products"]
        assert c.get("/api/connectors/billing/tables").json()["connected"] is True
        loads = json.loads((built / "data" / "warehouse.contracts.json").read_text())[
            "transforms"]["wealth_transform"]["sources"]
        assert sorted(loads) == [f"bank.{t}" for t in (
            "accounts", "activities", "branches", "clients", "holdings", "products")]
        assert all(r["connection"] == "bank" and "source_fallback" not in r
                   for r in loads.values()), loads

        # The warehouse page: one section per warehouse, and dim_rating says
        # who wrote it, who reads it and its checks. What the run read is said
        # once, of the transform's group: the certificate records a run's
        # inputs, not which table each fed.
        whs = {w["name"]: w for w in c.get("/api/warehouse").json()["warehouses"]}
        assert set(whs) == {"warehouse"}
        assert whs["warehouse"]["tier"] == "file" and whs["warehouse"]["engine_version"]
        rating = next(t for t in whs["warehouse"]["tables"] if t["name"] == "dim_rating")
        assert rating["written_by"]["transform"] == "holdings_transform"
        assert rating["written_by"]["contract"] == "holdings"
        assert rating["read_by"] == ["portfolio_model"]
        assert rating["contract"]["status"] == "satisfied"
        assert "fed_from" not in rating
        writers = {w["transform"]: w for w in whs["warehouse"]["writers"]}
        holdings = writers["holdings_transform"]
        assert "dim_rating" in holdings["tables"] and len(holdings["tables"]) == 7
        [fed] = holdings["read"]
        assert fed["ref"] == "crm.issuer_ratings" and fed["snapshot"] == "inputs/issuer_ratings.csv"
        assert holdings["file"] == "transforms/holdings_transform.contract.yaml" and holdings["note"]
        assert [r["ref"] for w in writers.values() for r in w["read"]].count("crm.issuer_ratings") == 1
        # Every model's tables sit in it, each written by a transform whose
        # sink satisfied its contract. A Python transform's contract is
        # matched to its file by the name it declares.
        tables = whs["warehouse"]["tables"]
        assert {t["written_by"]["transform"] for t in tables} == {
            "holdings_transform", "saas_transform", "affordability_transform",
            "wealth_transform"}
        assert {m for t in tables for m in t["read_by"]} == {
            "portfolio_model", "saas_model", "housing_model", "wealth_model"}
        assert {t["name"]: t["contract"]["status"] for t in tables} == {
            t["name"]: "satisfied" for t in tables}
        # A table's checks are named by the file that declares them (the
        # record itself is "holdings"), beside the transform's own note.
        view = {t["name"]: t for t in c.get("/api/connectors/warehouse/warehouse").json()["tables"]}
        assert view["dim_rating"]["contract"]["file"] == "transforms/holdings_transform.contract.yaml"
        assert view["dim_rating"]["contract"]["note"]
    finally:
        release_warehouses()


def test_one_table_api_reads_every_place_a_table_lives(built, monkeypatch):
    """Data's table page, by its API: one table addressed as (source, table)
    wherever it lives. A warehouse table pages, sorts, searches and filters
    in the engine (the answers are DuckDB's own), exports the same cut as
    CSV, profiles its dates, and says who wrote it, what that run read, the
    contract, the model that reads it and the reports built on it. A file
    under inputs/ answers rows, a path out of that folder does not exist, and
    the CRM with no URL is not connected (200). The model preview reads
    through the same engine, in its types."""
    import duckdb

    from tests.e2e.conftest import release_warehouses, serve_app
    from tracebi.web import discovery

    con = duckdb.connect(str(built / "data" / "warehouse.duckdb"), read_only=True)
    try:
        top5 = [r[0] for r in con.execute(
            "SELECT fair_value FROM fact_holdings ORDER BY fair_value DESC LIMIT 5").fetchall()]
        fund2 = con.execute("SELECT count(*) FROM fact_holdings WHERE fund_id = 2").fetchone()[0]
        csv_rows = con.execute(
            f"SELECT count(*) FROM read_csv_auto('{built / 'inputs' / 'holdings.csv'}')").fetchone()[0]
    finally:
        con.close()

    monkeypatch.delenv("TRACEBI_CRM_URL", raising=False)
    c = serve_app(monkeypatch, models=True)
    try:
        monkeypatch.setattr(discovery, "_live_connections", {})
        discovery.register_connections("connections")
        discovery.discover_library()
        # About this build says how each report is made: an app.jsx dashboard
        # or a template.html page.
        made = {r["name"]: r["made_from"] for r in c.get("/api/reports").json()}
        assert made["portfolio_model/portfolio_dashboard"] == "app.jsx"
        assert made["portfolio_model/portfolio_book"] == "template.html"
        base = "/api/tables/warehouse/fact_holdings"

        table = c.get(base).json()
        types = {col["name"]: col["type"] for col in table["columns"]}
        assert (table["kind"], table["rows"], table["rows_exact"]) == ("warehouse", 25, True)
        assert (types["fair_value"], types["maturity"]) == ("DOUBLE", "DATE")
        assert table["written_by"]["transform"] == "holdings_transform"
        assert table["contract"]["status"] == "satisfied"
        assert table["contract"]["file"] == "transforms/holdings_transform.contract.yaml"
        assert [(r["ref"], r["snapshot"]) for r in table["transform_read"]] == [
            ("crm.issuer_ratings", "inputs/issuer_ratings.csv")]
        assert table["read_by"] == ["portfolio_model"]
        used_by = {u["report"] for u in table["used_by"]}
        assert "portfolio_model/portfolio_dashboard" in used_by
        assert not any(r.startswith(("housing_model/", "saas_model/")) for r in used_by)

        page = c.get(f"{base}/rows", params={"sort": "fair_value", "desc": 1, "limit": 5}).json()
        names = [col["name"] for col in page["columns"]]
        assert [row[names.index("fair_value")] for row in page["rows"]] == top5
        assert (page["total"], page["total_exact"]) == (25, True)
        assert isinstance(page["rows"][0][names.index("maturity")], str)   # ISO, not a timestamp

        revolving = c.get(f"{base}/rows", params={"q": "Revolving"}).json()
        kinds = {row[names.index("instrument_type")] for row in revolving["rows"]}
        assert revolving["total"] == len(revolving["rows"]) > 0
        assert all("Revolving" in k for k in kinds), kinds

        where = json.dumps([{"column": "fund_id", "op": "eq", "value": 2}])
        assert c.get(f"{base}/rows", params={"where": where}).json()["total"] == fund2
        export = c.get(f"{base}/export.csv", params={"where": where})
        assert export.status_code == 200 and export.headers["content-type"].startswith("text/csv")
        assert len(export.text.strip().splitlines()) == fund2 + 1
        refused = c.get(f"{base}/rows", params={"where": json.dumps([{"column": "fund_id", "op": "like", "value": 2}])})
        assert refused.status_code == 422

        maturity = c.get(f"{base}/profile").json()["columns"]["maturity"]
        assert maturity["type"] == "DATE" and maturity["min"] < maturity["max"]

        held = c.get("/api/tables/inputs/holdings.csv/rows", params={"limit": 2}).json()
        assert held["total"] == csv_rows and len(held["rows"]) == 2
        assert c.get("/api/tables/inputs/..%2Fmodels%2Fportfolio_model.yaml/rows").status_code == 404

        assert c.get("/api/tables/crm/issuer_ratings/rows").json() == {
            "connected": False, "variable": "TRACEBI_CRM_URL", "reason": "TRACEBI_CRM_URL is not set"}

        preview = c.get("/api/models/portfolio_model/tables/fact_holdings/preview").json()
        assert preview["total_rows"] == 25 and preview["dtypes"]["maturity"] == "DATE"
    finally:
        release_warehouses()


def test_the_crm_credential_is_kept_on_the_server_and_never_shown(
        reference, monkeypatch, caplog):
    """Catches a credential store that leaks: a value in any response, a log
    line or the CLI's output; an open server (no sign-in, everyone admin by
    default) letting a stranger point the CRM at a host of their choosing;
    a status that says "missing" when the store holds the name, or "not set"
    when the store was written under another key."""
    import io
    import logging

    from tests.e2e.conftest import release_warehouses, serve_app
    from tracebi.web import discovery

    secret = "postgresql+psycopg://reader:throwaway-Pw-7Q2@127.0.0.1:9/crm"
    monkeypatch.delenv("TRACEBI_CRM_URL", raising=False)
    monkeypatch.delenv("TRACEBI_SECRET_KEY", raising=False)
    caplog.set_level(logging.DEBUG)
    c = serve_app(monkeypatch)
    bodies = []
    try:
        monkeypatch.setattr(discovery, "_live_connections", {})
        discovery.register_connections("connections")

        def row(name="TRACEBI_CRM_URL"):
            got = c.get("/api/credentials")
            bodies.append(got.text)
            return next(r for r in got.json()["credentials"] if r["name"] == name)

        before = row()
        assert before["set"] is False and before["source"] is None
        assert before["used_by"] == [{"kind": "connection", "name": "crm", "field": "url",
                                      "default": False}]
        assert c.get("/api/credentials").json()["can_change"] is False

        # No sign-in here: the write is refused and names the server command.
        refused = c.put("/api/credentials/TRACEBI_CRM_URL", json={"value": secret})
        bodies.append(refused.text)
        assert refused.status_code == 403
        assert refused.json()["detail"]["reason"] == \
            "credentials are set on the server: tracebi secret set TRACEBI_CRM_URL"
        assert not (reference / ".tracebi" / "secrets.yml.enc").exists()

        # On the server: the CLI, from stdin, never echoing it.
        monkeypatch.setattr("sys.stdin", io.StringIO(secret + "\n"))
        code, out = run_cli("secret", "set", "TRACEBI_CRM_URL", "--from-stdin")
        assert code == 0, out
        bodies.append(out)
        stored = (reference / ".tracebi" / "secrets.yml.enc").read_text()
        assert "throwaway" not in stored
        after = row()
        assert after["set"] is True and after["source"] == "store" and after["stored"] is True
        code, out = run_cli("secret", "list")
        bodies.append(out)
        assert "TRACEBI_CRM_URL · set in store · used by crm.url" in out, out
        audit = [r for r in c.get("/api/runs", params={"kind": "credential"}).json()]
        assert [(r["target"], r["status"]) for r in audit] == [("TRACEBI_CRM_URL", "set")]
        # The app says who set it and when, from that row, never the value.
        assert after["updated_at"] and after["updated_by"]

        # `tracebi secret edit` is the decrypted YAML in an editor: the editor
        # here is a script that adds a name and keeps the other; what it
        # wrote lands encrypted, and only the change is recorded.
        editor = reference / "editor.py"
        editor.write_text(
            "import sys, pathlib\n"
            "p = pathlib.Path(sys.argv[1]); t = p.read_text()\n"
            "assert 'TRACEBI_CRM_URL' in t and 'throwaway' in t, t\n"
            "p.write_text(t + 'TRACEBI_BANK_URL: sqlite:///inputs/other.sqlite\\n')\n")
        monkeypatch.setenv("EDITOR", f"{sys.executable} {editor}")
        code, out = run_cli("secret", "edit")
        assert code == 0 and "TRACEBI_BANK_URL set" in out and "CRM" not in out, out
        stored = (reference / ".tracebi" / "secrets.yml.enc").read_text()
        assert "throwaway" not in stored and "other.sqlite" not in stored
        code, out = run_cli("secret", "list")
        assert "TRACEBI_BANK_URL · set in store · used by bank.url" in out, out
        assert "TRACEBI_CRM_URL · set in store" in out, out
        audit = c.get("/api/runs", params={"kind": "credential"}).json()
        assert [(r["target"], r["status"]) for r in audit] == [
            ("TRACEBI_BANK_URL", "set"), ("TRACEBI_CRM_URL", "set")]
        assert run_cli("secret", "unset", "TRACEBI_BANK_URL")[0] == 0

        # The connection now resolves from the store; the test reaches for the
        # host and reports why it could not, with the password scrubbed.
        tested = c.post("/api/connectors/crm/test")
        bodies.append(tested.text)
        assert tested.status_code == 200 and tested.json()["ok"] is False
        bodies.append(c.get("/api/connectors/crm/tables").text)
        bodies.append(c.get("/api/connectors/crm").text)

        # The environment still wins over the store.
        monkeypatch.setenv("TRACEBI_CRM_URL", "postgresql+psycopg://127.0.0.1:9/env")
        assert row()["source"] == "environment"
        monkeypatch.delenv("TRACEBI_CRM_URL")
        (reference / ".env").write_text('TRACEBI_CRM_URL="postgresql+psycopg://127.0.0.1:9/dotenv"\n')
        assert row()["source"] == "dotenv"
        (reference / ".env").unlink()

        # Read under another key: said by name, never "not set".
        from cryptography.fernet import Fernet
        monkeypatch.setenv("TRACEBI_SECRET_KEY", Fernet.generate_key().decode())
        wrong = row()
        assert wrong["set"] is False and "different key" in wrong["problem"]
        tables = c.get("/api/connectors/crm/tables").json()
        assert "different key" in tables["reason"] and "variable" not in tables
    finally:
        release_warehouses()
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for text in [*bodies, logged]:
        assert "throwaway" not in text


def test_a_table_sourced_from_postgres_carries_its_source_to_the_trace(
        reference, postgres_url, monkeypatch):
    """The maintainer's ask: one star table whose source is a real relational
    database. The CRM is seeded in Postgres through its own connection, the
    pipeline runs the SQL transform (its -- source: line loads the table
    through the connector), and the certificate names the connection with
    the load's fingerprint and no fallback. A query by rating reads the sunk
    dim_rating with the fingerprint that certificate holds. verify
    --contracts reads the source unchanged; a rating changed in Postgres
    reads CHANGED, while every figure still reproduces (the warehouse did not
    move); with the variable unset the source is not checked, never green."""
    import runpy

    import psycopg

    from tracebi.model_registry import get_model

    monkeypatch.setenv("TRACEBI_CRM_URL", postgres_url)
    runpy.run_path(str(reference / "inputs" / "seed_crm.py"), run_name="__main__")
    code, out = run_cli("run-pipeline", "portfolio_model")
    assert code == 0, out

    rec = json.loads((reference / "data" / "warehouse.contracts.json").read_text())["transforms"]["holdings"]
    src = rec["sources"]["crm.issuer_ratings"]
    assert src["connection"] == "crm" and src["rows"] == 12
    assert re.fullmatch(r"[0-9a-f]{64}", src["fingerprint"]) and "source_fallback" not in src

    ratings = get_model("portfolio_model").query(
        "fact_holdings", ["fair_value"], dimensions=["dim_rating.rating"])
    [load] = [n for n in ratings.lineage if n.operation == "load" and n.source == "dim_rating"]
    assert load.metadata["input"]["fingerprint"] == rec["tables"]["dim_rating"]
    assert set(ratings.to_pandas()["dim_rating.rating"]) == {
        "B", "B+", "B-", "BB", "BB-", "CCC+", "Unrated"}

    manifest = _manifest(reference, "portfolio_model/portfolio_showcase")
    traced = json.loads(manifest.read_text())["transform_contracts"]["dim_rating"]
    assert traced["sources"]["crm.issuer_ratings"]["connection"] == "crm"
    code, out = run_cli("verify", str(manifest), "--contracts")
    assert code == 0 and "REPRODUCES" in out, out
    assert re.search(r"✓ unchanged\s+holdings: crm\.issuer_ratings\n", out), out

    with psycopg.connect(postgres_url.replace("+psycopg", "")) as con:
        con.execute("UPDATE issuer_ratings SET rating = 'B' "
                    "WHERE issuer = 'Kappa Energy Holdings, LLC'")
    code, out = run_cli("verify", str(manifest), "--contracts")
    assert code == 1, out
    assert re.search(r"✗ CHANGED\s+holdings: crm\.issuer_ratings", out), out
    assert "1 source(s) changed since the sink was certified" in out
    assert "✗ CHANGED      holdings: dim_rating" not in out     # the warehouse did not move

    monkeypatch.delenv("TRACEBI_CRM_URL")
    code, out = run_cli("verify", str(manifest), "--contracts")
    assert code == 0, out
    assert re.search(r"· not checked\s+holdings: crm\.issuer_ratings — .*TRACEBI_CRM_URL", out), out

    # The same URL kept in the project's credential store instead of the
    # environment: the transform's -- source: line reaches Postgres through
    # it, and the certificate records a live load, not the snapshot.
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(postgres_url))
    code, out = run_cli("secret", "set", "TRACEBI_CRM_URL", "--from-stdin")
    assert code == 0 and postgres_url not in out, out
    code, out = run_cli("run-pipeline", "portfolio_model")
    assert code == 0, out
    rec = json.loads((reference / "data" / "warehouse.contracts.json").read_text())["transforms"]["holdings"]
    assert rec["sources"]["crm.issuer_ratings"]["connection"] == "crm"
    assert "source_fallback" not in rec["sources"]["crm.issuer_ratings"]
    assert run_cli("secret", "unset", "TRACEBI_CRM_URL")[0] == 0

    # Data's Sources lists what the CRM holds, read on request through the
    # connection: issuer_ratings with its columns and the catalog's row
    # estimate (Postgres keeps one once the table is analysed; nothing is
    # counted row by row). The table API reads its rows through the same
    # connection, with an exact total for a filtered read.
    from tests.e2e.conftest import release_warehouses, serve_app
    from tracebi.web import discovery

    with psycopg.connect(postgres_url.replace("+psycopg", "")) as con:
        con.execute("ANALYZE issuer_ratings")
    monkeypatch.setenv("TRACEBI_CRM_URL", postgres_url)
    c = serve_app(monkeypatch)
    try:
        monkeypatch.setattr(discovery, "_live_connections", {})
        discovery.register_connections("connections")
        listed = c.get("/api/connectors/crm/tables").json()
        assert listed["connected"] is True, listed
        [ratings] = [t for t in listed["tables"] if t["name"] == "issuer_ratings"]
        assert {"issuer", "rating"} <= {col["name"] for col in ratings["columns"]}
        assert (ratings["rows"], ratings["rows_exact"]) == (12, False)
        table = c.get("/api/tables/crm/issuer_ratings").json()
        assert (table["kind"], table["rows"], table["rows_exact"]) == ("connection", 12, False)
        page = c.get("/api/tables/crm/issuer_ratings/rows", params={
            "sort": "issuer", "where": json.dumps([{"column": "rating", "op": "eq", "value": "B"}])}).json()
        names = [col["name"] for col in page["columns"]]
        assert page["total_exact"] is True and page["total"] == len(page["rows"]) > 0
        assert {row[names.index("rating")] for row in page["rows"]} == {"B"}
        issuers = [row[names.index("issuer")] for row in page["rows"]]
        assert issuers == sorted(issuers)
    finally:
        release_warehouses()


def test_the_working_preview_formats_numbers_like_the_build(built):
    """The dev preview and the Build-mode preview render the working state
    (`render_exploration`); a snapshot is the same render, on disk. It must
    carry the model's declared column formats the build embeds, or a table
    that ships as $35,736,396 and 100.4% previews as 35,736,396.18 and 1.00."""
    import re

    name = "portfolio_model/portfolio_overview"
    code, out = run_cli("report", "snapshot", name)
    assert code == 0, out

    def formats(path):
        html = path.read_text(encoding="utf-8")
        block = re.search(
            r'<script id="tracebi-formats" type="application/json">(.*?)</script>', html)
        assert block, f"{path.name} has no tracebi-formats block"
        return json.loads(block.group(1))

    shipped = formats(built / "output" / f"{name}.html")
    assert shipped["top_issuers"] == {
        "cost_basis": "currency0", "fair_value": "currency0", "mark": "percent"}
    assert formats(built / "output" / f"{name}.snapshot.html") == shipped


def test_every_model_keeps_its_reports_in_its_own_folder_and_has_a_pipeline(built):
    """The convention: reports/<model>/ holds a model's reports, and
    pipelines/<model>.py rebuilds its data and then those reports."""
    from tracebi.pipeline import model_pipeline
    from tracebi.pipeline.model_pipeline import reports_of

    models = sorted(p.stem for p in (built / "models").glob("*.yaml") if not p.stem.startswith("_"))
    assert models == ["housing_model", "portfolio_model", "saas_model", "wealth_model"]
    for model in models:
        names = reports_of(model)
        assert names, f"reports/{model}/ has no reports"
        assert (built / "pipelines" / f"{model}.yaml").is_file(), f"{model} has no pipeline"
        # ...and every report in the reference project sits under a model's folder
    everything = {name for names in map(reports_of, models) for name in names}
    assert everything == set(REPORTS), "a report sits outside its model's folder"
    assert model_pipeline  # exported at the top level for project pipelines


@pytest.mark.parametrize("model", ["portfolio_model", "housing_model", "saas_model",
                                   "wealth_model"])
def test_a_models_pipeline_rebuilds_its_data_then_its_reports(built, model):
    from tracebi.pipeline.model_pipeline import reports_of

    code, out = run_cli("run-pipeline", model)
    assert code == 0, out
    assert "transform" in out and "build" in out
    for name in reports_of(model):
        code, out = run_cli("verify", str(_manifest(built, name)), "--contracts")
        assert code == 0 and "REPRODUCES" in out, f"{name}: {out}"


def test_the_workflow_leaves_every_report_built_where_the_app_looks(reference, monkeypatch):
    """Catches a run_workflow.py that renders outside the app's build path: the
    library then opens on "Never built" beside data written a minute ago.
    After the workflow, the desk (what the library and Review read) has a
    build of every report the app lists, and every one reproduces.

    Then the desk's kept verdicts (tracebi/desk.py): catches a cache that makes
    every page load wait for the re-runs again, and one that serves a verdict
    older than its inputs, after the warehouse is rewritten or a receipt is
    edited, with nothing told to forget it."""
    import subprocess
    import sys
    import time

    from tests.e2e.conftest import release_warehouses, run_cli, serve_app
    from tracebi.web import discovery

    env = {k: v for k, v in os.environ.items() if not k.startswith("TRACEBI_")}
    done = subprocess.run([sys.executable, "run_workflow.py"], cwd=reference, env=env,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr or done.stdout

    monkeypatch.delenv("TRACEBI_CRM_URL", raising=False)
    c = serve_app(monkeypatch, models=True)
    try:
        discovery.discover_library()
        listed = {r["name"] for r in c.get("/api/reports").json()}
        assert listed == set(REPORTS)
        first = c.get("/api/desk").json()["builds"]
        builds = {b["report"]: b["verdict"] for b in first}
        assert builds == {name: "reproduces" for name in listed}
        # The workflow built in another process, so this one re-ran each.
        assert not any(b["cached"] for b in first)

        started = time.monotonic()
        second = c.get("/api/desk").json()["builds"]
        took = time.monotonic() - started
        assert {b["report"]: b["verdict"] for b in second} == builds
        assert all(b["cached"] for b in second)
        assert [b["computed_at"] for b in second] == [b["computed_at"] for b in first]
        assert took < 1.0, f"a desk read of kept verdicts took {took:.2f}s"

        # A transform rewrites the warehouse: every verdict is re-run, and
        # still reproduces (the transform is idempotent).
        release_warehouses()
        code, out = run_cli("run-transform", "saas_transform")
        assert code == 0, out
        after = c.get("/api/desk").json()["builds"]
        assert not any(b["cached"] for b in after)
        assert {b["report"]: b["verdict"] for b in after} == builds

        # Edit one receipt's recorded fingerprint (same length, so only its
        # modification time says so): its verdict changes on the next read.
        receipt = reference / "output" / "saas_model" / "mrr_dashboard.html.manifest.json"
        text = receipt.read_text(encoding="utf-8")
        recorded = re.search(r'"dataset_fingerprint": "[^"]*?([0-9a-f]{8})"', text)
        forged = "0" * 8 if recorded.group(1) != "0" * 8 else "1" * 8
        receipt.write_text(text.replace(
            recorded.group(0), recorded.group(0).replace(recorded.group(1) + '"', forged + '"'), 1),
            encoding="utf-8")
        verdicts = {b["report"]: b for b in c.get("/api/desk").json()["builds"]}
        assert verdicts["saas_model/mrr_dashboard"]["verdict"] == "not_reproduced"
        assert verdicts["saas_model/mrr_dashboard"]["cached"] is False
        assert verdicts["saas_model/cohort_brief"]["cached"] is True

        # The desk's headline numbers (each build's `values`; the home draws
        # none) are what each build printed, never computed here:
        # each is a value figure of the built page, under its own id and in the
        # page's own words. Catches a number read from the wrong figure, or one
        # made up where the page carries none (no series, no sparkline).
        for name, b in verdicts.items():
            html = (reference / "output" / f"{name}.html").read_text(encoding="utf-8")
            for v in b["values"]:
                assert f'id="{v["id"]}"' in html and f'>{v["text"]}<' in html, (name, v)
                assert v["spark"] is None or len(v["spark"]) > 1
        fair_value = next(v for v in verdicts["portfolio_model/portfolio_showcase"]["values"]
                          if v["id"] == "kpi-fv")
        assert (fair_value["label"], fair_value["delta"] != "") == ("Fair value", True)
        showcase = (reference / "output" / "portfolio_model" / "portfolio_showcase.html").read_text()
        assert f'id="kpi-fv">{fair_value["text"]}<' in showcase

        # Covers (tracebi/reports/cover.py). Catches a workflow that ships the
        # library with no pictures, a cover served stale or uncached, and one
        # that outlives the build that could not take it.
        _covers_ship_with_the_workflow(c, reference, first, monkeypatch)
    finally:
        release_warehouses()


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _covers_ship_with_the_workflow(c, reference, builds, monkeypatch):
    from tracebi import cli
    from tracebi.reports import cover

    name = "saas_model/cohort_brief"
    # Whether this machine can take one: Playwright and Chromium both there.
    probe = reference / "output" / "_probe.html"
    probe.write_text('<html data-tb-ready="1"><body>probe</body></html>', encoding="utf-8")
    monkeypatch.delenv("TRACEBI_COVERS", raising=False)
    monkeypatch.setattr(cover, "_unavailable", None)
    took, why = cover.capture_cover(str(probe))
    for leftover in (probe, reference / "output" / "_probe.cover.png"):
        leftover.unlink(missing_ok=True)
    if took is None:
        # No browser: every tile is drawn by the app, from what the desk says.
        assert not any(b["cover"] for b in builds), why
        assert c.get(f"/api/reports/{name}/cover").status_code == 404
        return
    assert all(b["cover"] for b in builds)
    assert all(b["figure_kinds"] for b in builds)
    manifest = json.loads((reference / "output" / f"{name}.html.manifest.json").read_text())
    assert manifest["cover"].endswith("cohort_brief.cover.png")

    got = c.get(f"/api/reports/{name}/cover")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    assert _png_size(got.content) == (cover.WIDTH, cover.HEIGHT)
    tag = got.headers["etag"]
    assert c.get(f"/api/reports/{name}/cover", headers={"If-None-Match": tag}).status_code == 304

    # A build here, as Rebuild and a schedule do: a new picture, a new tag,
    # and the run row names it beside the page.
    code, out = run_cli("report", "build", name)
    assert code == 0 and "no cover" not in out, out
    again = c.get(f"/api/reports/{name}/cover", headers={"If-None-Match": tag})
    assert again.status_code == 200 and again.headers["etag"] != tag
    row = next(r for r in c.get("/api/runs", params={"target": name}).json()
               if r["kind"] == "report_build")
    assert row["detail"]["cover"].endswith("cohort_brief.cover.png")

    # A build that cannot take one removes the old picture and says why,
    # once: the library then draws the cover from the desk's figure kinds.
    monkeypatch.setenv("TRACEBI_COVERS", "0")
    monkeypatch.setattr(cli, "_cover_note_said", False)
    code, out = run_cli("report", "build", name)
    assert code == 0 and out.count("no cover: covers are off") == 1, out
    code, out = run_cli("report", "build", name)
    assert "no cover" not in out, out
    assert c.get(f"/api/reports/{name}/cover").status_code == 404
    desk = {b["report"]: b for b in c.get("/api/desk").json()["builds"]}
    assert desk[name]["cover"] is False
    assert set(desk[name]["figure_kinds"]) <= {"value", "chart", "table"}
    assert "cover" not in json.loads(
        (reference / "output" / f"{name}.html.manifest.json").read_text())


def test_the_showcase_carries_every_affordance(built):
    html = (built / "output" / "portfolio_model" / "portfolio_showcase.html").read_text()
    from tests.test_presentation_js import assert_built_receipt_rows
    assert_built_receipt_rows(html)
    for marker in ("data-tb-filter", "data-tb-search", "data-tb-download",
                   "tb-tabs", "tb-span-8", "tb-kpi--lead", 'id="tracebi-receipt"',
                   "tb-methodology", "data-tb-unverified",
                   "tb-semantic-contract-portfolio_model",
                   'id="tracebi-selection"',
                   'class="tb-total"',
                   "data-tb-sort", "data-tb-bars", "data-tb-direction",
                   "tb-table--freeze", "tb-footer-line", "tb-masthead",
                   "data-tb-period",
                   'id="fig-treemap"', "D3 7.9.0 (ISC)"):
        assert marker in html, f"showcase lost its {marker} affordance"
    assert "Working notes" not in html, "exploration must die at build"
    # The masthead's kicker and the footer name the model by its label; the
    # template writes no kicker, the build adds it (an app's kit reads it
    # from its mount point).
    assert '<p class="tb-kicker">Direct Lending Portfolio</p>' in html
    foot = html[html.index('class="tb-footer-line"'):]
    foot = foot[:foot.index("</p>")]
    assert " · Direct Lending Portfolio. " in foot and "portfolio_model" not in foot
    app = (built / "output" / "portfolio_model" / "portfolio_dashboard.html").read_text()
    assert 'data-tb-kicker="Direct Lending Portfolio"' in app
    # A page with a selection block asks the app to run its cut; it connects nowhere.
    assert "connect-src 'none'" in html and "connect-src 'self'" not in html
    # ...and its runtime never calls the app itself: served on its own at
    # /r/<name> (an opaque origin) a request to the API fails CORS on load.
    assert "/api/" not in html and "fetch(" not in html

    manifest = json.loads(_manifest(built, "portfolio_model/portfolio_showcase").read_text())
    assert manifest["schema_version"] == 2
    assert len(manifest["figures"]) >= 10
    assert manifest["transform_contracts"] and all(
        r.get("status") == "satisfied" for r in manifest["transform_contracts"].values())
    assert manifest["semantic_contract"]["portfolio_model"]["sha256"]
    assert manifest["methodology"]["transform_notes"]


def test_the_showcase_lineage_traces_each_query_to_only_what_it_used(built):
    """The receipt's lineage: each query names exactly the tables it read, a
    python-derived query is called out and never verifiable, and figures with
    no query behind them are shown apart."""
    from tracebi.reports.lineage_flow import report_flow

    manifest = json.loads(_manifest(built, "portfolio_model/portfolio_showcase").read_text())
    flow = report_flow(manifest)
    node = {n["id"]: n for n in flow["nodes"]}

    assert set(node["binding:top_sector"]["detail"]["tables"]) == {"fact_holdings", "dim_issuer"}
    assert set(node["binding:by_fund"]["detail"]["tables"]) == {"fact_holdings", "dim_fund"}
    assert node["binding:concentration"]["status"] == "derived"
    assert node["binding:concentration"]["detail"]["verifiable"] is False
    assert "figures:unverified" in node and flow["notes"][-1].startswith("A query marked python-derived")
    assert node["transform:holdings"]["status"] == "ok"      # the sink satisfied its contract
    # Every figure is on the graph exactly once.
    listed = [f["id"] for n in flow["nodes"] if n["kind"] in ("figures", "unverified")
              for f in n["detail"]["figures"]]
    assert sorted(listed) == sorted(f["id"] for f in manifest["figures"])


def test_a_showcase_control_recomputes_on_the_model(built):
    """Picking a sector re-runs the stamped queries on the model and the cut
    total matches a direct query — interactivity subsets, never computes."""
    from tracebi.model_registry import ModelRegistry
    from tracebi.reports.selection import evaluate_selection
    from tracebi.reports.template_package import TemplatePackage

    previous = os.getcwd()
    os.chdir(built)
    try:
        registry = ModelRegistry()
        registry.auto_discover(str(built / "models"))
        models = {"portfolio_model": registry.get("portfolio_model")}
        package = TemplatePackage(str(built / "reports" / "portfolio_model" / "portfolio_showcase"))
        base = evaluate_selection(package, models, {})
        control = next(c for c in base["controls"] if c["column"] == "dim_issuer.sector")
        assert len(control["included"]) > 1
        sector = control["included"][0]
        cut = evaluate_selection(package, models, {"dim_issuer.sector": sector})
        model = models["portfolio_model"]
        expected = model.query("fact_holdings", ["fair_value", "positions", "mark"],
                               filters={"dim_issuer.sector": sector})
    finally:
        os.chdir(previous)

    def cell(result, figure_id):
        return next(f for f in result["figures"] if f["id"] == figure_id)

    fair, detail = cell(cut, "kpi-fv"), cell(cut, "tbl-detail")
    assert fair["value"] != cell(base, "kpi-fv")["value"]
    assert 0 < len(detail["rows"]) < len(cell(base, "tbl-detail")["rows"])
    assert all(row["dim_issuer.sector"] == sector for row in detail["rows"])
    # The cut is the model's own answer to that query, byte for byte.
    assert fair["fingerprint"] == expected.fingerprint()
    assert cell(cut, "kpi-mark")["fingerprint"] == expected.fingerprint()


def test_the_housing_scenario_is_recorded_never_receipted(built):
    manifest = json.loads(_manifest(built, "housing_model/affordability").read_text())
    assert [s["name"] for s in manifest["scenarios"]] == ["today"]
    assert all(s["verifiable"] is False for s in manifest["scenarios"])
    ids = {f["id"] for f in manifest["figures"]}
    assert {"chart-ten-year", "ten-worst", "ten-best", "ten-today", "chart-paths",
            "chart-rate", "chart-pti", "chart-share"} <= ids
    assert not any(i.startswith("calc-") for i in ids), \
        "a scenario output must never be recorded as a figure"


def test_explore_speaks_the_models_language(built, monkeypatch):
    """Explore queries the model's named measures, offers a fact only the ones
    it can run, and writes the numbers the way a built report does."""
    from tests.e2e.conftest import release_warehouses, serve_app
    from tracebi.registry import registry

    c = serve_app(monkeypatch, models=True)
    try:
        # A measure is declared once on the model; the fact decides whether it
        # runs. Whatever a fact lists, its query answers — and nothing it
        # leaves out would have.
        info = c.get("/api/models/housing_model").json()
        offered = {f["name"]: set(f["runnable_measures"]) for f in info["facts"]}
        assert offered["fact_housing"] != offered["fact_ten_year"]
        for fact, names in offered.items():
            for measure in (m["name"] for m in info["measures"]):
                answer = c.post("/api/models/housing_model/query",
                                json={"fact": fact, "measures": [measure]})
                assert (answer.status_code == 200) == (measure in names), (
                    f"{fact}.{measure}: offered={measure in names}, query answered {answer.status_code}")

        # Likewise a dimension: a fact joins the ones in its foreign_keys, and
        # grouping by any other cannot run.
        joins = {f["name"]: set(f["foreign_keys"]) for f in info["facts"]}
        assert joins["fact_ten_year"] == {"dim_cohort", "dim_year"}
        for fact in offered:
            measure = sorted(offered[fact])[0]
            for dim in info["dimensions"]:
                answer = c.post("/api/models/housing_model/query", json={
                    "fact": fact, "measures": [measure],
                    "dimensions": [f"{dim['name']}.{dim['attributes'][0]}"]})
                assert (answer.status_code == 200) == (dim["name"] in joins[fact]), (
                    f"{fact} x {dim['name']}: joined={dim['name'] in joins[fact]}, "
                    f"query answered {answer.status_code}")

        # The named-measure query: the raw values are the model's own answer.
        body = {"fact": "fact_holdings", "measures": ["fair_value", "positions", "mark"],
                "dimensions": ["dim_issuer.sector"]}
        got = c.post("/api/models/portfolio_model/query", json=body).json()
        direct = registry.get_model("portfolio_model").query(
            "fact_holdings", body["measures"], dimensions=body["dimensions"])
        assert got["data"] == direct.to_pandas().to_dict(orient="records")

        # ...and the display text carries each measure's declared format.
        for raw, shown in zip(got["data"], got["display"]):
            assert shown["dim_issuer.sector"] == raw["dim_issuer.sector"]
            assert re.fullmatch(r"\$[\d,]+", shown["fair_value"]), shown
            assert re.fullmatch(r"\d+\.\d%", shown["mark"]), shown
            assert shown["positions"] == f"{raw['positions']:,}"

        # It is the very text the built overview report prints for that query.
        html = (built / "output" / "portfolio_model" / "portfolio_overview.html").read_text()
        top = c.post("/api/models/portfolio_model/query", json={
            "fact": "fact_holdings", "measures": ["fair_value", "cost_basis", "mark"],
            "dimensions": ["dim_issuer.issuer"], "order_by": ["-fair_value"], "limit": 8}).json()
        assert len(top["display"]) == 8
        for shown in top["display"]:
            for column in ("fair_value", "cost_basis", "mark"):
                assert f'<td class="tb-num">{shown[column]}</td>' in html

        # A result holding NaN (an empty total) or infinity (a division by zero)
        # is answered with missing values, not a 500: JSON has neither.
        empty = c.post("/api/models/portfolio_model/query", json={
            "fact": "fact_holdings", "measures": ["fair_value", "mark"],
            "filters": {"spread_bps": -1}})
        assert empty.status_code == 200
        assert empty.json()["data"] == [{"fair_value": None, "cost_basis": None, "mark": None}]
        assert empty.json()["display"] == [{"fair_value": "", "cost_basis": "", "mark": ""}]
        blown = c.post("/api/models/portfolio_model/query", json={
            "fact": "fact_holdings", "measures": {
                "fair_value": "sum", "inv": {"expr": "1 / (fair_value - fair_value)", "agg": "sum"}}})
        assert blown.status_code == 200
        assert blown.json()["data"][0]["inv"] is None
        assert blown.json()["data"][0]["fair_value"] > 0
        assert blown.json()["display"][0]["inv"] == ""
    finally:
        release_warehouses()


def test_every_reports_slice_answers_its_bindings_plans(built):
    """The slice is enough: in every reference report, each binding whose
    plan compiled, run by execute_plan over the slice embedded in the page
    (under the authored selection), matches the binding's stamped rows cell by
    cell (calc_plan.rows_match). Every other plan is fixed for a reason this
    round names, never because the slice lacks a column."""
    import base64
    import hashlib

    from tracebi.model.data_model import QuerySpec
    from tracebi.model_registry import ModelRegistry
    from tracebi.reports.calc_plan import execute_plan, first_mismatch, rows_match
    from tracebi.reports.parquet_embed import from_parquet_bytes
    from tracebi.reports.slice import _grain_strings

    legitimate = ("sql binding", "report.py", "having 'contains'")
    previous = os.getcwd()
    os.chdir(built)
    try:
        registry = ModelRegistry()
        registry.auto_discover(str(built / "models"))
        live = 0
        for name in REPORTS:
            manifest = json.loads(_manifest(built, name).read_text())
            html = (built / "output" / f"{name}.html").read_text()
            payload = json.loads(re.search(
                r'<script id="tracebi-calc-plans" type="application/json">(.*?)</script>',
                html).group(1))
            assert payload["bindings"] == manifest["plans"]
            frames = {}
            for rec in manifest["slice"].values():
                block = re.search(r'<script id="%s" type="application/json">(.*?)</script>'
                                  % re.escape(rec["block"]), html)
                raw = base64.b64decode(json.loads(block.group(1))["parquet_b64"])
                assert hashlib.sha256(raw).hexdigest() == rec["payload_sha256"]
                frames[(rec["model"], rec["fact"])] = from_parquet_bytes(raw)
            stamped = {r["name"]: r for r in manifest["embedded_data"]}
            for binding, plan in manifest["plans"].items():
                if "fixed" in plan:
                    assert any(w in plan["fixed"] for w in legitimate), (name, binding, plan)
                    continue
                model = registry.get(stamped[binding]["model"])
                got = execute_plan(plan, frames[(plan["model"], plan["fact"])],
                                   payload["authored_selection"])
                want = _grain_strings(model, model.execute(
                    QuerySpec.from_dict(stamped[binding]["query_spec"])).to_pandas())
                assert rows_match(got, want), (
                    name, binding, first_mismatch(got, want))
                live += 1
        assert live >= 45, f"only {live} bindings recompute from their slice"
    finally:
        os.chdir(previous)


def test_a_reports_embed_setting_bounds_what_it_carries(built, tmp_path):
    """embed: none ships the page as it was before slices; embed: model
    ships every fact at base grain with every attribute it reaches; a slice
    over embed_budget_mb fails the build naming the fix; a column of a type
    the page engine cannot show the same way fails the build naming it."""
    import pandas as pd

    from tracebi import DataModel, MemoryConnector
    from tracebi.model_registry import ModelRegistry
    from tracebi.reports.slice import SliceError
    from tracebi.reports.template_package import TemplatePackage

    showcase = built / "reports" / "portfolio_model" / "portfolio_showcase"
    declared = json.loads((showcase / "report.json").read_text())

    def variant(name, **keys):
        target = tmp_path / name
        shutil.copytree(showcase, target)
        (target / "report.json").write_text(json.dumps({**declared, **keys}))
        return TemplatePackage(str(target))

    previous = os.getcwd()
    os.chdir(built)
    try:
        registry = ModelRegistry()
        registry.auto_discover(str(built / "models"))
        models = {"portfolio_model": registry.get("portfolio_model")}

        out = tmp_path / "none.html"
        manifest = variant("none", embed="none").render(models, str(out))
        assert manifest.slice is None and manifest.plans is None
        page = out.read_text()
        # No block, and no engine to run one (the runtime's own source names
        # both ids, so the elements and the inlined engine are what count).
        assert 'id="tracebi-slice-' not in page and 'id="tracebi-calc-plans"' not in page
        assert "<!-- tracebi-calc.js" not in page

        manifest = variant("model", embed="model").render(
            models, str(tmp_path / "model.html"))
        rec = manifest.slice["fact_holdings"]
        assert rec["base_grain"] and rec["embed"] == "model"
        assert {"dim_fund.fund", "dim_issuer.issuer", "dim_issuer.sector"} <= set(rec["grain"])
        assert rec["rows"] == len(models["portfolio_model"].load("fact_holdings").to_pandas())

        with pytest.raises(SliceError, match='"embed": "none"') as refused:
            variant("tight", embed_budget_mb=0.0001).render(
                models, str(tmp_path / "tight.html"))
        assert "embed_budget_mb" in str(refused.value)
        assert not (tmp_path / "tight.html").exists()
    finally:
        os.chdir(previous)

    # A dimension attribute holding zoned timestamps: the page engine would
    # show them in the reader's zone, so a slice that needs it fails by name.
    package = tmp_path / "zoned"
    package.mkdir()
    (package / "report.json").write_text(json.dumps({"data": {"total": {
        "model": "zoned_model", "query": {"fact": "fact_t", "measures": ["amount"]}}}}))
    (package / "template.html").write_text(
        '<html><head></head><body><span data-tb-figure="value" data-tb-binding="total" '
        'data-tb-cell="amount"></span><select data-tb-filter data-tb-binding="total" '
        'data-tb-column="dim_t.at"></select></body></html>')
    model = DataModel("zoned_model")
    model.add_connector(MemoryConnector("mem", tables={
        "fact": pd.DataFrame({"t_id": [1, 2], "amount": [1.5, 2.5]}),
        "dim": pd.DataFrame({"t_id": [1, 2], "at": pd.to_datetime(
            ["2026-01-01", "2026-02-01"]).tz_localize("America/New_York")})}))
    model.add_table("fact", "mem", "fact").add_table("dim", "mem", "dim")
    model.add_dimension("dim_t", "dim", "t_id", ["at"])
    model.add_fact("fact_t", "fact", ["amount"], {"dim_t": "t_id"})
    model.add_measure("amount", column="amount", agg="sum")
    with pytest.raises(SliceError, match=r"slice column 'dim_t\.at'.*\"embed\": \"none\""):
        TemplatePackage(str(package)).render({"zoned_model": model},
                                             str(tmp_path / "zoned.html"))


# ── The live page ────────────────────────────────────────────────────────────

def test_verify_local_replays_what_every_page_recomputes(built, tmp_path):
    """verify --local: on every reference report the page engine and the
    server agree on every plan under the authored selection and one per
    filter; a slice block edited after the build is refused by its hash."""
    import shutil as _shutil

    node = _shutil.which("node")
    for name in REPORTS:
        code, out = run_cli("verify", str(_manifest(built, name)), "--local")
        assert code == 0, f"{name}: {out}"
        manifest = json.loads(_manifest(built, name).read_text())
        if manifest.get("slice"):
            assert ("reproduce" in out) if node else ("node not found" in out), f"{name}: {out}"
        else:
            assert "fixed at build" in out, f"{name}: {out}"

    showcase = built / "output" / "portfolio_model" / "portfolio_showcase.html"
    html = showcase.read_text()
    block = re.search(r'id="tracebi-slice-fact_holdings" type="application/json">'
                      r'\{[^<]*?"parquet_b64": "(.)', html)
    at = block.start(1) + 40
    swap = "A" if html[at] != "A" else "B"
    (tmp_path / "s.html").write_text(html[:at] + swap + html[at + 1:])
    (tmp_path / "s.html.manifest.json").write_text(
        _manifest(built, "portfolio_model/portfolio_showcase").read_text())
    code, out = run_cli("verify", str(tmp_path / "s.html.manifest.json"), "--local")
    assert code == 1 and "payload_sha256" in out, out


def _browser():
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    pw = sync_playwright().start()
    try:
        return pw, pw.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001 — no browser here: skip, never fail
        pw.stop()
        pytest.skip(f"Chromium is not installed: {exc}")


def _slices(built, name):
    """The page's slices as frames, its manifest's plans, and its calc payload."""
    import base64

    from tracebi.reports.parquet_embed import from_parquet_bytes

    html = (built / "output" / f"{name}.html").read_text()
    manifest = json.loads(_manifest(built, name).read_text())
    frames = {}
    for rec in (manifest.get("slice") or {}).values():
        body = re.search(r'<script id="%s" type="application/json">(.*?)</script>'
                         % re.escape(rec["block"]), html).group(1)
        frames[(rec["model"], rec["fact"])] = from_parquet_bytes(
            base64.b64decode(json.loads(body)["parquet_b64"]))
    return frames, manifest["plans"]


# Every figure the page draws, read the way a reader sees it: a value's text,
# a table's rows, a chart's svg (and its text and mark count, which a reload
# must reproduce exactly), with the live marks the runtime set.
_READ = """() => Array.from(document.querySelectorAll('[data-tb-figure][data-tb-binding]'))
  .filter(el => el.getAttribute('data-tb-figure') !== 'custom').map((el, i) => {
    const kind = el.getAttribute('data-tb-figure');
    const svg = el.querySelector('svg');
    return {key: el.id || ('#' + i), binding: el.getAttribute('data-tb-binding'), kind,
      cell: el.getAttribute('data-tb-cell'),
      value: kind === 'value' ? (el.querySelector('.tb-kpi-value') || el).textContent.trim() : null,
      rows: kind === 'table' ? Array.from(el.querySelectorAll('tbody tr')).map(r => r.textContent) : null,
      svg: svg ? svg.outerHTML : null,
      text: kind === 'chart' ? el.textContent : null,
      marks: svg ? svg.querySelectorAll('path, rect, circle').length : null,
      fixed: el.getAttribute('data-tb-fixed'),
      note: el.__tbLiveNote ? el.__tbLiveNote.textContent : null};
  })"""


def _undimmed(svg):
    """A chart's svg less what cross-highlighting adds (a class, a label)."""
    if svg is None:
        return None
    svg = re.sub(r' aria-label="(select|clear) [^"]*"', '', svg)
    return re.sub(r' (tb-dimmed|tb-picked)(?=[ "])', '', svg).replace(' class=""', '')


def _settle(page):
    page.wait_for_selector("html[data-tb-ready]")
    page.wait_for_timeout(900)     # chart transitions finish


def test_a_sector_recomputes_every_showcase_figure_in_the_file(built):
    """Opened from disk, the showcase is live: picking a sector recomputes
    every value, chart and table whose query that sector reaches, exactly
    where the data says the answer moves, from the slice the file carries.
    The report.py figure stays as built and says so; the chip reads Local;
    the address carries the selection, and opening it restores the view."""
    from tracebi.reports.calc_plan import execute_plan, rows_match

    name = "portfolio_model/portfolio_showcase"
    frames, plans = _slices(built, name)
    frame = frames[("portfolio_model", "fact_holdings")]
    sector = sorted(frame["dim_issuer.sector"].dropna().unique())[0]
    selection = {"dim_issuer.sector": [sector]}
    answers = {b: (execute_plan(p, frames[(p["model"], p["fact"])], {}),
                   execute_plan(p, frames[(p["model"], p["fact"])], selection))
               for b, p in plans.items() if "fixed" not in p}
    # Both facts are on the page, and the sector reaches both.
    assert {p["fact"] for p in plans.values() if "fixed" not in p} == {
        "fact_holdings", "fact_cashflows"}

    pw, browser = _browser()
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        url = (built / "output" / f"{name}.html").as_uri()
        page.goto(url)
        _settle(page)
        before = {f["key"]: f for f in page.evaluate(_READ)}
        assert page.locator(".tb-masthead .tb-verdict").first.text_content() == "Not checked"
        page.locator('select[data-tb-filter][data-tb-column="dim_issuer.sector"]').select_option(
            sector, force=True)
        _settle(page)
        after = {f["key"]: f for f in page.evaluate(_READ)}
        # A chart in a hidden tab redraws when its tab is shown.
        page.locator(".tb-tab-bar button", has_text="Cash flows").click()
        _settle(page)
        after.update({f["key"]: f for f in page.evaluate(_READ)
                      if f["binding"].startswith("flows")})
        page.locator(".tb-tab-bar button", has_text="Overview").click()

        kinds = set()
        for key, now in after.items():
            was, binding = before[key], now["binding"]
            if binding not in answers:
                assert "fixed" in plans[binding]
                assert now["fixed"] == plans[binding]["fixed"] == "report.py"
                # Its marks may recede for the sector picked (cross-highlighting,
                # presentation only); what it draws is as built.
                assert _undimmed(now["svg"]) == _undimmed(was["svg"])
                assert now["value"] == was["value"]
                assert now["note"] == "Fixed at build · report.py"
                continue
            authored, cut = answers[binding]
            kinds.add(now["kind"])
            assert now["fixed"] is None
            if now["kind"] == "value":
                moves = (len(cut) == 0
                         or not rows_match(authored[[now["cell"]]], cut[[now["cell"]]]))
                assert (now["value"] != was["value"]) == moves, (key, was["value"], now["value"])
            elif now["kind"] == "table":
                assert not rows_match(authored, cut)
                assert len(now["rows"]) == len(cut) and now["rows"] != was["rows"], key
            else:
                assert not rows_match(authored, cut)
                assert now["svg"] != was["svg"], key
        assert kinds == {"value", "table", "chart"}

        chip = page.locator(".tb-masthead .tb-verdict").first
        assert chip.text_content() == "Local"
        assert chip.get_attribute("title") == "Recomputed on this page from the embedded data"
        assert "sel=" in page.evaluate("location.hash")
        # The trace counts its own figure rows: one, the report.py chart, is fixed.
        summary = page.locator(".tb-receipt-local-summary").text_content()
        assert re.fullmatch(r"\d+ recomputed on this page · 1 fixed at build · 0 unchanged",
                            summary), summary

        again = browser.new_page(viewport={"width": 1440, "height": 900})
        again.goto(page.evaluate("location.href"))
        _settle(again)
        reread = {f["key"]: f for f in again.evaluate(_READ)}
        again.locator(".tb-tab-bar button", has_text="Cash flows").click()
        _settle(again)
        reread.update({f["key"]: f for f in again.evaluate(_READ)
                       if f["binding"].startswith("flows")})
        for key, now in after.items():
            for part in ("value", "rows", "text", "marks", "fixed"):
                assert reread[key][part] == now[part], (key, part)
        assert again.locator(".tb-masthead .tb-verdict").first.text_content() == "Local"

        # A field only one fact reaches: the flow type cuts the cash flows,
        # and every holdings figure keeps its built number and says why.
        flows = frames[("portfolio_model", "fact_cashflows")]
        flow_type = sorted(flows["dim_flow_type.flow_type"].dropna().unique())[0]
        typed = {"dim_flow_type.flow_type": [flow_type]}
        page.goto(url)
        _settle(page)
        built_view = {f["key"]: f for f in page.evaluate(_READ)}
        page.locator('select[data-tb-filter][data-tb-column="dim_flow_type.flow_type"]'
                     ).select_option(flow_type, force=True)
        _settle(page)
        reached = set()
        for key, now in {f["key"]: f for f in page.evaluate(_READ)}.items():
            plan = plans[now["binding"]]
            if "fixed" in plan:
                continue
            if plan["fact"] == "fact_holdings":
                assert now["value"] == built_view[key]["value"], key
                assert now["rows"] == built_view[key]["rows"], key
                assert page.locator(f'[data-tb-binding="{now["binding"]}"]'
                                    '[data-tb-unfiltered-by="dim_flow_type.flow_type"]'
                                    ).count() >= 1, key
            else:
                reached.add(now["binding"])
                cut = execute_plan(plan, flows, typed)
                if now["kind"] == "table":
                    assert len(now["rows"]) == len(cut), key
        assert reached == {"flows", "flows_by_month", "flows_by_fund"}
        assert page.get_by_text("Not filtered by Flow type").count() >= 1
        assert errors == []
    finally:
        browser.close()
        pw.stop()


def test_the_desks_page_filters_recompute_every_view(built):
    """The React lane: two page filters, one of them multiple, cut the desk's
    holdings to exactly the rows the slice says; a view the app mounts after
    the selection opens already recomputed; the hash keeps the view and the
    selection side by side."""
    from tracebi.reports.calc_plan import execute_plan

    name = "portfolio_model/portfolio_desk"
    frames, plans = _slices(built, name)
    frame = frames[("portfolio_model", "fact_holdings")]
    sector = sorted(frame["dim_issuer.sector"].dropna().unique())[-1]
    funds = sorted(frame["dim_fund.fund"].dropna().unique())[:2]
    selection = {"dim_issuer.sector": [sector], "dim_fund.fund": funds}
    holdings = execute_plan(plans["holdings"], frame, selection)
    totals = execute_plan(plans["totals"], frame, selection)
    assert 0 < len(holdings) < len(execute_plan(plans["holdings"], frame, {}))

    pw, browser = _browser()
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        url = (built / "output" / f"{name}.html").as_uri()
        page.goto(url)
        _settle(page)
        overview = page.locator('[data-tb-binding="totals"][data-tb-cell="positions"] .tb-kpi-value').first
        authored = overview.text_content()
        page.get_by_role("button", name="Holdings").click()
        page.wait_for_selector("select[data-tb-filter][multiple]")
        page.locator('select[data-tb-column="dim_issuer.sector"]').select_option(sector)
        page.locator('select[data-tb-column="dim_fund.fund"]').select_option(funds)
        _settle(page)
        assert page.locator("#holdings-table tbody tr").count() == len(holdings)
        shown = set(page.locator("#holdings-table tbody tr td:nth-child(3)").all_text_contents())
        assert shown == set(funds) & set(holdings["dim_fund.fund"])
        hash_ = page.evaluate("location.hash")
        assert "view=Holdings" in hash_ and "sel=" in hash_
        page.get_by_role("button", name="Overview").click()
        _settle(page)
        positions = page.locator('[data-tb-binding="totals"][data-tb-cell="positions"] .tb-kpi-value').first
        assert positions.text_content() != authored
        assert positions.text_content().replace(",", "") == str(int(totals["positions"][0]))
        assert page.locator(".tb-verdict[data-tb-verdict='local']").count() >= 1

        # The filters live in the sidebar, so the selection holds on every
        # view: each view, opened after it, shows one figure's query re-run
        # under it, exactly as execute_plan over the slice gives it.
        from tracebi.reports.calc_plan import first_mismatch
        for view, figure, binding in (("Overview", "kpi-unrealized", "totals"),
                                      ("Holdings", "holdings-table", "holdings"),
                                      ("Funds", "funds-table", "by_fund")):
            page.get_by_role("button", name=view).click()
            _settle(page)
            want = execute_plan(plans[binding], frame, selection)
            got = page.evaluate("(id) => window.tracebi.result(id)", figure)
            assert got["selection"] == selection, (view, got["selection"])
            assert first_mismatch(got, want) is None, (view, first_mismatch(got, want))
            if figure.endswith("-table"):
                assert page.locator(f"#{figure} tbody tr").count() == len(want), view
    finally:
        browser.close()
        pw.stop()


def test_the_saas_dashboard_recomputes_every_figure_by_plan(built):
    """The SaaS measures are period_end balances, and the page runs them: a
    plan picked in mrr_dashboard's filter recomputes every KPI, spark, chart
    and table exactly where execute_plan over the slice says (each month's
    latest balance, under the plan), none is fixed, and the chip reads Local.
    cohort_brief's slice reproduces on the server too."""
    from tracebi.reports.calc_plan import execute_plan, rows_match

    name = "saas_model/mrr_dashboard"
    frames, plans = _slices(built, name)
    frame = frames[("saas_model", "fact_account_month")]
    assert not [b for b, p in plans.items() if "fixed" in p]
    plan_name = sorted(frame["dim_plan.plan"].dropna().unique())[0]
    selection = {"dim_plan.plan": [plan_name]}
    answers = {b: (execute_plan(p, frame, {}), execute_plan(p, frame, selection))
               for b, p in plans.items()}

    pw, browser = _browser()
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto((built / "output" / f"{name}.html").as_uri())
        _settle(page)
        before = {f["key"]: f for f in page.evaluate(_READ)}
        page.locator('select[data-tb-filter][data-tb-column="dim_plan.plan"]').select_option(
            plan_name)
        _settle(page)
        after = {f["key"]: f for f in page.evaluate(_READ)}
        kinds = set()
        for key, now in after.items():
            was = before[key]
            authored, cut = answers[now["binding"]]
            kinds.add(now["kind"])
            assert now["fixed"] is None, key
            if now["kind"] == "value":
                moves = not rows_match(authored[[now["cell"]]], cut[[now["cell"]]])
                assert (now["value"] != was["value"]) == moves, (key, was["value"], now["value"])
            elif now["kind"] == "table":
                assert len(now["rows"]) == len(cut) and now["rows"] != was["rows"], key
                assert all(plan_name in row for row in now["rows"]), key
            else:
                assert not rows_match(authored, cut)
                assert now["svg"] != was["svg"], key
        assert {"value", "table", "chart"} <= kinds
        assert page.locator("[data-tb-fixed]").count() == 0
        assert page.locator(".tb-verdict[data-tb-verdict='local']").count() >= 1
        assert "sel=" in page.evaluate("location.hash")
        assert errors == []
    finally:
        browser.close()
        pw.stop()

    manifest = json.loads(_manifest(built, "saas_model/cohort_brief").read_text())
    assert manifest["slice"] and not [p for p in manifest["plans"].values() if "fixed" in p]
    code, out = run_cli("verify", str(_manifest(built, "saas_model/cohort_brief")), "--local")
    assert code == 0 and "reproduce" in out, out
