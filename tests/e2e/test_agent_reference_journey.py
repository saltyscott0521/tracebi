"""The author_report prompt's own steps, walked over the gateway against a copy
of the reference workspace, the one a new user opens:

    describe the workspace → read_transform → propose a change to
    holdings_transform that adds a column → a passing dry run → an admin
    approves it → a model draft, from the published copy, adds a measure →
    model_impact → publish it → a report draft → preview → publish → build →
    verify

The tools are the plain functions the MCP server registers, called in the
order the prompt names them. The reference connections let agents read the
tables their transforms read, so each step is one an agent can take; with the
CRM's table taken off that list, the transform says which line blocks a change
instead of offering one.

The second journey is an agent's first day on the same workspace, five tasks a
person asks for, each decided from tool output only (the field run of
2026-10-30): a number and whether it is checked; a wealth dashboard whose
trend needs a new dimension; a CRM table brought into the portfolio and onto
the desk; a reviewer's pin that doubts a KPI; and what breaks if a table goes.
"""

import json
import os

from tests.e2e.conftest import follow_run, run_cli, serve_app

# The column the change adds, and the measure the model then declares over it.
_ADDED = "k.fair_value - k.cost AS gain"
_MEASURE = """\
  - name: total_gain
    column: gain
    agg: sum
    description: Total gain over cost, from the column the transform adds
    format: currency0
"""


def test_an_agent_walks_author_report_on_the_reference_workspace(reference, monkeypatch):
    from tracebi import mcp_server as gw

    monkeypatch.delenv("TRACEBI_CRM_URL", raising=False)     # the CRM's snapshot stands in
    code, out = run_cli("run-transform", "holdings_transform")
    assert code == 0, out

    # The prompt names the route that needs no files: drafts, then publish.
    import asyncio
    prompt = json.dumps(asyncio.run(gw.build_server(token=None).get_prompt(
        "author_report", {"question": "What is the book's gain over cost?"})).model_dump())
    for step in ("start_draft(kind='reports'", "write_draft_file(kind='reports'",
                 "preview_draft(kind='reports'", "publish_draft(kind='reports'",
                 "get_context(topic='presentation')"):
        assert step in prompt, step

    # 1. Context: the brief tier, then the page grammar as its own topic.
    brief = gw.gateway_context(model="portfolio_model", brief=True)
    assert "presentation" not in brief and "presentation" in brief["brief"]["omitted"]
    assert "topic=" in brief["brief"]["fetch"]
    full = gw.gateway_context()
    assert len(json.dumps(gw.gateway_context(brief=True), default=str)) <= 0.45 * len(
        json.dumps(full, default=str)), "the brief tier is no longer brief"
    grammar = gw.gateway_context(topic="presentation")
    assert grammar["topic"] == "presentation" and "figure_attributes" in grammar["presentation"]
    assert "unknown topic" in gw.gateway_context(topic="nope")["errors"][0]

    # a. The workspace, as agents see it: the transform may be changed.
    described = gw.gateway_describe_project()
    [node] = [n for n in described["nodes"] if n["id"] == "transform:holdings_transform"]
    assert node["passport"]["agents"]["text"] == "May propose a change"
    assert not {"lane", "chip", "sub", "open"} & set(node)       # the map's own fields stay in the app
    read = gw.gateway_read_transform("holdings_transform")
    assert read["ok"] and read["change"].startswith("propose_transform(name='holdings_transform'")
    assert [s["snapshot"] for s in read["last_run"]["sources"]] == ["inputs/issuer_ratings.csv"]

    # b. A change that does not parse answers with that, and only that.
    broken = gw.gateway_propose_transform(
        "holdings_transform", read["text"].replace("CREATE OR REPLACE TABLE", "CREATE OR REPLAC"),
        read["contract_yaml"], "typo", change=True)
    assert broken["ok"] is False and len(broken["errors"]) == 1, broken
    assert "does not parse" in broken["errors"][0]

    # The change: fact_holdings carries each position's gain over cost.
    sql = read["text"].replace("k.par, k.cost, k.fair_value, k.spread_bps, k.maturity",
                               f"k.par, k.cost, k.fair_value, k.spread_bps, k.maturity,\n       {_ADDED}")
    assert sql != read["text"]
    proposed = gw.gateway_propose_transform("holdings_transform", sql, read["contract_yaml"],
                                            "Each position carries its gain over cost", change=True)
    assert proposed["ok"] is True and proposed["dry_run"]["ok"] is True, proposed
    assert "start_draft(kind='models', path='portfolio_model', from_published=true)" in proposed["note"]
    states = {t["name"]: t for t in proposed["dry_run"]["tables"]}
    fact = states["fact_holdings"]
    assert fact["state"] == "changed" and "gain" in fact["sample"][0]
    # A table the change leaves as it was carries no rows: the warehouse holds them.
    assert states["dim_fund"]["state"] == "unchanged" and "sample" not in states["dim_fund"]

    # c. An admin approves it; it runs once and the column lands.
    app = serve_app(monkeypatch, models=True)
    approved = app.post(f"/api/code-requests/{proposed['request_id']}/approve")
    assert approved.status_code == 200, approved.text
    [run] = approved.json()["runs"]
    assert run["pipeline"] == "portfolio_model", run      # the pipeline that runs it, once
    log, settled = follow_run(app, "portfolio_model", run["run_id"])
    assert settled["status"] == "succeeded", log
    landed = gw.gateway_describe_table("fact_holdings")
    assert "gain" in [c["name"] for c in landed["columns"][0]["columns"]], landed

    # d. The model draft starts from the published copy, adds the measure.
    path = "portfolio_model"
    started = gw.gateway_start_draft("models", path)
    assert started["ok"] is True and started["differs_from_published"] is False, started
    [(name, text)] = gw.gateway_read_draft("models", path)["files"].items()
    text = text.replace("    measures: [par, cost, fair_value, spread_bps]",
                        "    measures: [par, cost, fair_value, spread_bps, gain]")
    text = text.replace("measures:\n  - name: fair_value", "measures:\n" + _MEASURE
                        + "  - name: fair_value", 1)
    assert "total_gain" in text
    assert gw.gateway_write_draft_file("models", path, name, text)["ok"] is True
    assert gw.gateway_preview_draft("models", path)["ok"] is True
    impact = gw.gateway_model_impact(path)
    assert impact["ok"] is True, impact
    assert impact["impact"]["reports"] and not any(
        r["status"] == "breaks" for r in impact["impact"]["reports"]), impact
    published = gw.gateway_publish_draft("models", path, note="total_gain",
                                         accept_impact=impact["impact"]["needs_acceptance"])
    assert published["ok"] is True and published["status"] == "published", published

    # 2–3. Query the new measure, then the report as a draft over the gateway.
    stamped = gw.gateway_query("portfolio_model", "fact_holdings", ["total_gain", "fair_value"])
    assert stamped["rows"] and stamped["fingerprint"], stamped
    report = "portfolio_model/gain_brief"
    started = gw.gateway_start_draft("reports", report)
    assert started["ok"] is True and gw.gateway_read_draft("reports", report)["files"] == {}
    spec = {"name": "Gain over cost", "data": {"totals": stamped["binding"]}}
    page = ('<!doctype html><html><head><title>Gain over cost</title></head><body>'
            '<article class="tb-article"><h1>Gain over cost</h1><div class="tb-grid">'
            '<div class="tb-kpi" data-tb-figure="value" data-tb-binding="totals" '
            'data-tb-cell="total_gain"><span class="tb-kpi-label">Gain</span>'
            '<span class="tb-kpi-value"></span></div></div></article></body></html>')
    for file, content in (("report.json", json.dumps(spec)), ("template.html", page)):
        assert gw.gateway_write_draft_file("reports", report, file, content)["ok"] is True
    preview = gw.gateway_preview_draft("reports", report)
    assert preview["ok"] is True, preview
    done = gw.gateway_publish_draft("reports", report, note="the book's gain over cost")
    assert done["ok"] is True and done["status"] == "published", done

    # 4–5. Build and verify the published package.
    built = gw.gateway_build_report(report)
    assert built["ok"] is True, built
    verdict = gw.gateway_verify_manifest(built["manifest_path"])
    assert verdict["verdict"] == "reproduces", verdict

    # Starting a draft that already exists says what an agent can do about it.
    again = gw.gateway_start_draft("models", path)
    assert again["ok"] is False and "write_draft_file" in again["errors"][0]

    # Off the allowlist, the CRM's table blocks a change: both surfaces name the line.
    crm = reference / "connections" / "crm.yaml"
    crm.write_text(crm.read_text().split("agents:")[0])
    blocked = "line 22: -- source: crm.issuer_ratings"
    hint = gw.gateway_read_transform("holdings_transform")["change"]
    assert hint.startswith("not proposable") and blocked in hint, hint
    [node] = [n for n in gw.gateway_describe_project()["nodes"]
              if n["id"] == "transform:holdings_transform"]
    agents = node["passport"]["agents"]
    assert agents["blocked"] == [blocked]
    assert agents["text"] == "May read it; a change is blocked by line 22 (crm.issuer_ratings)"
    assert "propose_transform(change=true)" not in agents["tools"]


# ── An agent's first day: five tasks, decided from tool output only ────────

_WATCHLIST_CSV = """\
issuer,reason,added_on,analyst
"Epsilon Health Partners, LLC",Covenant headroom under 10%,2025-04-22,R. Patel
"Kappa Energy Holdings, LLC",Liquidity: revolver fully drawn,2025-06-03,M. Chen
"Sigma Logistics Holdings, LLC",Customer concentration,2025-04-08,R. Patel
"Theta Retail Brands, LLC",Same-store sales decline,2025-02-26,J. Okafor
"""
_WATCHLIST_SQL = """
DROP TABLE IF EXISTS issuer_watchlist;
CREATE TABLE issuer_watchlist (issuer text PRIMARY KEY, reason text NOT NULL,
                               added_on date NOT NULL, analyst text NOT NULL);
INSERT INTO issuer_watchlist (issuer, reason, added_on, analyst) VALUES
    ('Epsilon Health Partners, LLC',  'Covenant headroom under 10%',     '2025-04-22', 'R. Patel'),
    ('Kappa Energy Holdings, LLC',    'Liquidity: revolver fully drawn', '2025-06-03', 'M. Chen'),
    ('Sigma Logistics Holdings, LLC', 'Customer concentration',          '2025-04-08', 'R. Patel'),
    ('Theta Retail Brands, LLC',      'Same-store sales decline',        '2025-02-26', 'J. Okafor');
"""


def _approve(app, request_id):
    """The admin approves a code request in the app; its run must succeed."""
    approved = app.post(f"/api/code-requests/{request_id}/approve")
    assert approved.status_code == 200, approved.text
    for run in approved.json()["runs"]:
        log, settled = follow_run(app, run["pipeline"], run["run_id"])
        assert settled["status"] == "succeeded", log


def _scan():
    """The running server's live-discovery tick: the library as it is on disk."""
    from tracebi.web.discovery import rescan_library
    rescan_library("models", "pipelines", "connections")


def _replace(text, old, new):
    assert old in text, old
    return text.replace(old, new, 1)


def _without_dim_rating(text):
    """The model file with every dim_rating entry (table, dimension, key) gone."""
    out, skip = [], False
    for line in text.splitlines(keepends=True):
        if line.startswith("  - name: dim_rating"):
            skip = True
            continue
        if skip and line.startswith("    "):
            continue
        skip = False
        if line.strip() != "dim_rating: rating_id":
            out.append(line)
    return "".join(out)


def test_an_agent_does_five_tasks_on_its_first_day(reference, monkeypatch):
    import asyncio

    from tracebi import mcp_server as gw
    from tracebi.workbench import add_pin, workbench_dir

    monkeypatch.delenv("TRACEBI_CRM_URL", raising=False)     # the CRM's snapshot stands in
    for pipeline in ("portfolio_model", "wealth_model"):     # the library, built as shipped
        code, out = run_cli("run-pipeline", pipeline)
        assert code == 0, out
    app = serve_app(monkeypatch, models=True)
    _scan()
    server = gw.build_server(token=None)

    def prompt(name, **args):
        return json.dumps(asyncio.run(server.get_prompt(name, args)).model_dump())

    # 1. "What's our largest exposure by sector, and is that number checked?"
    said = prompt("answer_question", question="largest exposure by sector; is it checked?")
    assert "list_models" in said and "downstream(node=" in said and "describe_table" in said
    models = gw.gateway_models()["models"]
    assert "fund holds in an issuer" in models["portfolio_model"]["description"]
    assert "sector" in json.dumps(gw.gateway_model_info("portfolio_model")["dimensions"])
    answer = gw.gateway_query("portfolio_model", "fact_holdings", ["fair_value"],
                              dimensions=["dim_issuer.sector"], order_by=["-fair_value"])
    assert answer["rows"][0]["dim_issuer.sector"] == "Consumer", answer["rows"]
    shown = gw.gateway_downstream("measure:portfolio_model:fair_value")
    assert shown["ok"] is True, shown
    [dash] = [r for r in shown["reports"] if r["name"] == "portfolio_model/portfolio_dashboard"]
    assert dash["trust"]["text"] == "Reproduces", dash         # a verdict, not "Not checked"
    assert any(f["binding"] == "by_sector" for f in dash["figures"])
    listed = {r["module"]: r for r in gw.gateway_reports()["reports"]}
    assert listed["portfolio_model/portfolio_dashboard"]["built"]["manifest_path"] \
        == dash["manifest_path"]
    verdict = gw.gateway_verify_manifest(dash["manifest_path"])
    [by_sector] = [s for s in verdict["sections"] if s["section"] == "by_sector"]
    assert verdict["verdict"] == "reproduces"
    assert by_sector["expected_fingerprint"] == answer["fingerprint"]   # the same number
    for table in ("fact_holdings", "dim_issuer"):
        [match] = gw.gateway_describe_table(table)["columns"]
        assert match["contract"]["status"] == "satisfied", match
        assert match["contract"]["writer"] == "holdings_transform"

    # 2. "A dashboard for the wealth team: AUM by region with a trend, and the
    # branches." Holdings are one snapshot; activity has a month, but no
    # dimension groups by it: a trade calendar from the transform, then the model.
    assert gw.gateway_query("wealth_model", "fact_activities", ["activity_volume"],
                            dimensions=["fact_activities.trade_date"])["ok"] is False
    read = gw.gateway_read_transform("wealth_transform")
    sql = read["text"] + ("\nCREATE OR REPLACE TABLE wealth_dim_date AS\n"
                          "SELECT DISTINCT trade_date FROM wealth_fact_activities "
                          "ORDER BY trade_date;\n")
    checks = read["contract_yaml"] + ("  - unique: wealth_dim_date\n    columns: [trade_date]\n"
                                      "  - foreign_key: wealth_fact_activities\n"
                                      "    column: trade_date\n"
                                      "    refers_to: [wealth_dim_date, trade_date]\n")
    proposed = gw.gateway_propose_transform("wealth_transform", sql, checks,
                                            "a trade calendar", change=True)
    assert proposed["dry_run"]["ok"] is True, proposed
    _approve(app, proposed["request_id"])
    [calendar] = gw.gateway_describe_table("wealth_dim_date")["columns"]
    assert calendar["columns"] == [{"name": "trade_date", "dtype": "VARCHAR"}]   # '2025-07'
    assert gw.gateway_start_draft("models", "wealth_model")["ok"] is True
    [(file, text)] = gw.gateway_read_draft("models", "wealth_model")["files"].items()
    text = _replace(text, "    source: wealth_dim_account\n",
                    "    source: wealth_dim_account\n  - name: wealth_dim_date\n"
                    "    connector: warehouse\n    source: wealth_dim_date\n")
    text = _replace(text, "    attributes: [account_type, opened]\n",
                    "    attributes: [account_type, opened]\n  - name: dim_date\n"
                    "    table: wealth_dim_date\n    key: trade_date\n"
                    "    attributes: [trade_date]\n")
    text = _replace(text, "    measures: [units, amount]\n    foreign_keys:\n",
                    "    measures: [units, amount]\n    foreign_keys:\n"
                    "      dim_date: trade_date\n")
    grain = ("time_grains:\n  - dimension: dim_date\n    name: month\n"
             "    source: trade_date\n    grain: month\n")
    gw.gateway_write_draft_file("models", "wealth_model", file, text + grain)
    # A grain over text compiles, and every query by it would fail: preview says so.
    refused = gw.gateway_preview_draft("models", "wealth_model")
    assert refused["ok"] is False, refused
    assert "holds as VARCHAR, not a date" in refused["errors"][0], refused
    gw.gateway_write_draft_file("models", "wealth_model", file, text)   # the month as it is
    assert gw.gateway_preview_draft("models", "wealth_model")["ok"] is True
    assert gw.gateway_model_impact("wealth_model")["impact"]["needs_acceptance"] is False
    assert gw.gateway_publish_draft("models", "wealth_model", note="trade month")["ok"] is True
    data = {
        "totals": ("fact_holdings", ["market_value", "clients"], []),
        "by_region": ("fact_holdings", ["market_value"], ["dim_branch.region"]),
        "trend": ("fact_activities", ["activity_volume"], ["dim_date.trade_date"]),
        "branches": ("fact_holdings", ["market_value", "clients"],
                     ["dim_branch.branch", "dim_branch.region"]),
    }
    spec = {"name": "Wealth team", "data": {}}
    for name, (fact, measures, dims) in data.items():
        stamped = gw.gateway_query("wealth_model", fact, measures, dimensions=dims,
                                   order_by=[dims[0]] if dims else None)
        assert stamped["ok"] is True, stamped
        spec["data"][name] = stamped["binding"]
    app_jsx = ('import { Masthead, Kpi, Chart, Table, Footer } from "tracebi";\n'
               'export default function App() {\n  return (<div>\n'
               '    <Masthead title="Wealth team" />\n'
               '    <Kpi lead binding="totals" cell="market_value" label="Assets under management" />\n'
               '    <Chart binding="trend" type="line" x="dim_date.trade_date" y="activity_volume" />\n'
               '    <Chart binding="by_region" type="barh" x="dim_branch.region" y="market_value" />\n'
               '    <Table binding="branches" />\n    <Footer />\n  </div>);\n}\n')
    report = "wealth_model/wealth_team"
    assert gw.gateway_start_draft("reports", report)["ok"] is True
    for name, content in (("report.json", json.dumps(spec)), ("app.jsx", app_jsx)):
        assert gw.gateway_write_draft_file("reports", report, name, content)["ok"] is True
    assert gw.gateway_preview_draft("reports", report)["ok"] is True
    assert gw.gateway_publish_draft("reports", report, note="wealth team")["status"] == "published"
    built = gw.gateway_build_report(report)
    assert built["ok"] is True, built
    # The join, per table, in a few words; the manifest keeps what each run read.
    assert built["transform_contracts"]["wealth_dim_date"]["status"] == "satisfied"
    assert set(built["transform_contracts"]["wealth_dim_date"]) <= {
        "status", "writer", "transform", "checks", "checked_at"}
    assert gw.gateway_verify_manifest(built["manifest_path"])["verdict"] == "reproduces"

    # 3. "Our CRM now has issuer_watchlist: bring it into the portfolio and show
    # the watch-listed issuers on the desk." The person adds the table (seeded,
    # with its committed snapshot) and ticks it for agents; the CRM is not
    # reachable here, so the snapshot stands in.
    (reference / "inputs" / "issuer_watchlist.csv").write_text(_WATCHLIST_CSV, encoding="utf-8")
    seed = reference / "inputs" / "seed_crm.sql"
    seed.write_text(seed.read_text(encoding="utf-8") + _WATCHLIST_SQL, encoding="utf-8")
    crm = reference / "connections" / "crm.yaml"
    crm.write_text(_replace(crm.read_text(), "tables: [issuer_ratings]",
                            "tables: [issuer_ratings, issuer_watchlist]"))
    unreachable = gw.gateway_list_source_tables("crm")
    assert unreachable["ok"] is False and unreachable["variable"] == "TRACEBI_CRM_URL"
    assert unreachable["snapshots"] == {"issuer_ratings": "inputs/issuer_ratings.csv"}
    assert unreachable["unread_inputs"] == ["inputs/issuer_watchlist.csv"], unreachable
    assert "fallback: inputs/<file>.csv" in unreachable["note"]
    read = gw.gateway_read_transform("holdings_transform")
    assert read["other_forms"] == ["transforms/holdings_transform_pandas.py"]
    head = "-- source: crm.issuer_ratings fallback: inputs/issuer_ratings.csv\n"
    sql = _replace(read["text"], head, head + "-- source: crm.issuer_watchlist "
                                             "fallback: inputs/issuer_watchlist.csv\n")
    sql = _replace(sql, "SELECT row_number() OVER (ORDER BY issuer, sector) AS issuer_id, "
                        "issuer, sector\nFROM (SELECT DISTINCT issuer, sector FROM keyed)\n",
                   "SELECT row_number() OVER (ORDER BY i.issuer, i.sector) AS issuer_id, i.issuer,\n"
                   "       i.sector, w.reason AS watch_reason, w.analyst AS watch_analyst\n"
                   "FROM (SELECT DISTINCT issuer, sector FROM keyed) i\n"
                   "LEFT JOIN crm.issuer_watchlist w USING (issuer)\n")
    proposed = gw.gateway_propose_transform("holdings_transform", sql, read["contract_yaml"],
                                            "dim_issuer carries the CRM watchlist", change=True)
    assert proposed["dry_run"]["ok"] is True, proposed
    assert proposed["dry_run"]["sources"]["crm.issuer_watchlist"]["snapshot"] \
        == "inputs/issuer_watchlist.csv"
    assert "holdings_transform_pandas.py is another form" in proposed["note"]
    _approve(app, proposed["request_id"])
    assert gw.gateway_start_draft("models", "portfolio_model")["ok"] is True
    [(file, text)] = gw.gateway_read_draft("models", "portfolio_model")["files"].items()
    text = _replace(text, "        synonyms: [industry]\n",
                    "        synonyms: [industry]\n      - watch_reason\n      - watch_analyst\n")
    gw.gateway_write_draft_file("models", "portfolio_model", file, text)
    assert gw.gateway_preview_draft("models", "portfolio_model")["ok"] is True
    impact = gw.gateway_model_impact("portfolio_model")["impact"]
    assert gw.gateway_publish_draft("models", "portfolio_model", note="the CRM watchlist",
                                    accept_impact=impact["needs_acceptance"])["ok"] is True
    watched = gw.gateway_query(
        "portfolio_model", "fact_holdings", ["fair_value"],
        dimensions=["dim_issuer.issuer", "dim_issuer.watch_reason"],
        filters={"dim_issuer.watch_reason": {"not_null": True}}, order_by=["-fair_value"])
    assert len(watched["rows"]) == 4, watched
    desk = "portfolio_model/portfolio_desk"
    assert gw.gateway_start_draft("reports", desk)["ok"] is True
    files = gw.gateway_read_draft("reports", desk)["files"]
    spec = json.loads(files["report.json"])
    spec["data"]["watchlisted"] = watched["binding"]
    page = _replace(files["app.jsx"], "function Holdings() {",
                    "function Watchlisted() {\n  return <Table binding=\"watchlisted\" "
                    "id=\"watchlisted-table\" />;\n}\n\nfunction Holdings() {")
    page = _replace(page, "      </div>\n    </>\n  );\n}\n\nfunction Watchlisted",
                    "      </div>\n      <Watchlisted />\n    </>\n  );\n}\n\nfunction Watchlisted")
    for name, content in (("report.json", json.dumps(spec)), ("app.jsx", page)):
        assert gw.gateway_write_draft_file("reports", desk, name, content)["ok"] is True
    assert gw.gateway_preview_draft("reports", desk)["ok"] is True
    assert gw.gateway_publish_draft("reports", desk, note="the CRM watchlist")["ok"] is True
    built = gw.gateway_build_report(desk)
    assert "watchlisted-table" in [f["id"] for f in built["figures"]], built
    assert gw.gateway_verify_manifest(built["manifest_path"])["verdict"] == "reproduces"

    # 4. A reviewer pinned the dashboard's fair-value KPI: "looks off". The
    # prompt names the drafts route, and says a doubt is checked before anything
    # changes: the KPI is the whole book, the funds add up to it.
    dashboard = "portfolio_model/portfolio_dashboard"
    add_pin(workbench_dir(os.getcwd(), dashboard), "kpi-fair-value",
            note="The fair-value KPI looks off: do the funds add up to it?")
    said = prompt("address_pins", report=dashboard)
    assert "start_draft(kind='reports'" in said and "doubts a number" in said
    state = gw.gateway_workbench_state(dashboard)
    [pin] = state["pins"]
    [figure] = [f for f in state["figures"] if f["id"] == pin["id"]]
    total = gw.gateway_query("portfolio_model", "fact_holdings", [figure["cell"]])
    by_fund = gw.gateway_query("portfolio_model", "fact_holdings", ["fair_value"],
                               dimensions=["dim_fund.fund"])
    assert round(sum(r["fair_value"] for r in by_fund["rows"]), 2) \
        == round(total["rows"][0]["fair_value"], 2)
    assert gw.gateway_start_draft("reports", dashboard)["ok"] is True
    page = gw.gateway_read_draft("reports", dashboard)["files"]["app.jsx"]
    page = _replace(page, 'context="administrator marks" id="kpi-fair-value"',
                    'context="the whole book, every fund" id="kpi-fair-value"')
    gw.gateway_write_draft_file("reports", dashboard, "app.jsx", page)
    assert gw.gateway_preview_draft("reports", dashboard)["ok"] is True
    assert gw.gateway_publish_draft("reports", dashboard, note="pin kpi-fair-value")["ok"] is True
    built = gw.gateway_build_report(dashboard)
    assert gw.gateway_verify_manifest(built["manifest_path"])["verdict"] == "reproduces"
    assert gw.gateway_resolve_pin(dashboard, pin["id"], note=(
        f"the whole book, the funds sum to it ({total['fingerprint'][:8]})"))["ok"] is True
    assert gw.gateway_workbench_state(dashboard)["pins"] == []

    # 5. "What breaks if we drop dim_rating?" The builds answer at once; a
    # what-if model draft proves it, and goes once it has.
    _scan()
    breaks = gw.gateway_downstream("table:warehouse.dim_rating")
    assert [r["name"] for r in breaks["reports"]] == ["portfolio_model/portfolio_showcase"], breaks
    assert {f["binding"] for f in breaks["reports"][0]["figures"]} >= {"by_rating", "watched"}
    assert gw.gateway_downstream("table:warehouse.nope")["ok"] is False
    again = gw.gateway_start_draft("models", "portfolio_model")
    assert "delete_draft(kind='models', path='portfolio_model')" in again["errors"][0]
    [(file, text)] = gw.gateway_read_draft("models", "portfolio_model")["files"].items()
    gw.gateway_write_draft_file("models", "portfolio_model", file, _without_dim_rating(text))
    proved = gw.gateway_model_impact("portfolio_model")["impact"]
    assert {r["report"] for r in proved["reports"] if r["status"] == "breaks"} \
        == {"portfolio_model/portfolio_showcase"}, proved
    assert gw.gateway_delete_draft("models", "portfolio_model")["ok"] is True
    assert gw.gateway_read_draft("models", "portfolio_model")["ok"] is False
    assert gw.gateway_delete_draft("models", "portfolio_model")["ok"] is False
