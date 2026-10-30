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
"""

import json

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
