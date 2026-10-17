"""The author's live loop: ``tracebi dev`` serving a report with its
workbench, a pin left in the workbench, the pin read and resolved from the
CLI (the agent's side of the protocol), and the review snapshot — which
verify refuses by name, because a draft is not a receipt.
"""

import http.server
import json
import socket
import threading
import time
import urllib.request

import pytest

from tests.e2e.conftest import run_cli


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def dev(scaffolded, monkeypatch):
    """`tracebi dev sample_model/sample_dashboard` on a spare port, shut down after."""
    from tracebi import _dev_server

    servers = []

    class _Tracked(http.server.ThreadingHTTPServer):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            servers.append(self)

    monkeypatch.setattr(http.server, "ThreadingHTTPServer", _Tracked)
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    port = _free_port()
    thread = threading.Thread(target=_dev_server.serve_dev, daemon=True, kwargs={
        "target": str(scaffolded / "reports" / "sample_model" / "sample_dashboard"),
        "port": port, "open_browser": False})
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/__status", timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    yield base
    for server in servers:
        server.shutdown()
    thread.join(timeout=5)    # serve_dev returns once shutdown; its watcher stops with it


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read().decode()


def test_an_author_previews_pins_and_resolves(dev, scaffolded):
    preview = _get(dev + "/")
    assert "Sample Dashboard" in preview
    state = json.loads(_get(dev + "/__workbench/state.json"))
    assert {f["id"] for f in state["figures"]} >= {"kpi-revenue", "chart-by-region"}

    pin = urllib.request.Request(
        dev + "/__workbench/pin", method="POST",
        data=json.dumps({"id": "kpi-revenue", "note": "label this net"}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pin, timeout=5) as r:
        assert json.loads(r.read())["ok"] is True

    code, out = run_cli("report", "pins", "sample_model/sample_dashboard")
    assert code == 0 and "kpi-revenue" in out and "label this net" in out, out
    code, out = run_cli("report", "pins", "sample_model/sample_dashboard",
                        "--resolve", "kpi-revenue", "--note", "relabelled")
    assert code == 0, out
    code, out = run_cli("report", "pins", "sample_model/sample_dashboard")
    assert "no open pins" in out, out


def test_layout_recipes_scaffold_and_build(scaffolded):
    """new-report writes a page to be read (editorial by default, or a named
    layout); new-dashboard writes an app people work in."""
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out

    code, out = run_cli("new-report", "Mosaic", "--layout", "mosaic")
    assert code != 0, out
    assert "mosaic" in out
    for name in ("editorial", "brief", "dashboard", "tabbed"):
        assert name in out
    assert not (scaffolded / "reports" / "mosaic").exists()

    code, out = run_cli("new-report", "Weekly", "--reports-dir",
                        str(scaffolded / "plain"))
    assert code == 0, out
    plain = scaffolded / "plain" / "weekly"
    # A report is editorial: a headline, a standfirst, the byline's build
    # time, and numbers bound into the prose — so it builds with no numeral
    # typed in, and verifies.
    article = (plain / "template.html").read_text()
    for marker in ('class="tb-article"', "tb-kicker", "tb-dek", "data-tb-built",
                   "tb-lede", "<figcaption>", "tb-pullstat", "data-tb-methodology"):
        assert marker in article, marker
    assert not (plain / "app.jsx").exists()
    code, out = run_cli("report", "build", "weekly", "--reports-dir", str(scaffolded / "plain"))
    assert code == 0, out

    # A dashboard is an app (the React lane).
    code, out = run_cli("new-dashboard", "Weekly", "--reports-dir",
                        str(scaffolded / "dash"))
    assert code == 0, out
    dash = scaffolded / "dash" / "weekly"
    assert "<Kpi lead" in (dash / "app.jsx").read_text()
    # The same bindings: a report and a dashboard read the same queries.
    assert (json.loads((plain / "report.json").read_text())["data"]
            == json.loads((dash / "report.json").read_text())["data"])
    assert not (dash / "template.html").exists()
    assert not (dash / "style.css").exists()
    assert not (dash / "script.js").exists()
    code, out = run_cli("report", "build", "weekly", "--reports-dir", str(scaffolded / "dash"))
    assert code == 0, out

    code, out = run_cli("new-report", "Weekly Brief", "--layout", "brief")
    assert code == 0, out
    brief = (scaffolded / "reports" / "weekly_brief" / "template.html").read_text()
    assert "tb-cols-2" not in brief
    assert "tb-lede" in brief and "tb-grid" in brief and "tb-card" in brief
    code, out = run_cli("report", "build", "weekly_brief")
    assert code == 0, out

    code, out = run_cli("new-report", "Weekly", "--layout", "tabbed")
    assert code == 0, out
    tabbed = (scaffolded / "reports" / "weekly" / "template.html").read_text()
    assert "tb-tabs" in tabbed and "data-tb-tab" in tabbed
    assert 'data-tb-tab="Overview"' in tabbed and 'data-tb-tab="Detail"' in tabbed
    code, out = run_cli("report", "build", "weekly")
    assert code == 0, out
    built = (scaffolded / "output" / "weekly.html").read_text()
    assert "tb-tabs" in built and "data-tb-tab" in built

    # The look a builder was asked about: a dark, compact sidebar dashboard
    # with the title at the top of the sidebar. It builds, and the answers
    # are attributes the runtime and the stylesheet read.
    code, out = run_cli("new-report", "Desk", "--nav", "side", "--mode", "dark",
                        "--density", "compact", "--title-at", "nav")
    assert code == 0, out
    desk = (scaffolded / "reports" / "desk" / "template.html").read_text()
    assert ('<html lang="en" data-tb-mode="dark" data-tb-density="compact" '
            'data-tb-width="full">') in desk
    assert '<div class="tb-tabs" data-tb-nav="side">' in desk
    assert '<header class="tb-title" data-tb-title="nav">' in desk
    # The whole page sits inside the sidebar's first tab: the KPIs follow it.
    assert desk.index('data-tb-tab="Overview"') < desk.index('class="tb-kpi"')
    code, out = run_cli("report", "build", "desk")
    assert code == 0, out
    built = (scaffolded / "output" / "desk.html").read_text()
    assert 'data-tb-mode="dark"' in built and "data-tb-built" in built

    # The same answers for an app: its look rides in report.json (an app has
    # no <html> of its own), the sidebar holds the title, and it builds.
    code, out = run_cli("new-dashboard", "Desk App", "--nav", "side", "--mode", "dark",
                        "--density", "compact", "--title-at", "nav")
    assert code == 0, out
    app_dir = scaffolded / "reports" / "desk_app"
    decl = json.loads((app_dir / "report.json").read_text())
    assert decl["look"] == {"mode": "dark", "density": "compact"}
    assert "<aside" in (app_dir / "app.jsx").read_text()
    code, out = run_cli("report", "build", "desk_app")
    assert code == 0, out
    built = (scaffolded / "output" / "desk_app.html").read_text()
    assert '<html lang="en" data-tb-app data-tb-mode="dark" data-tb-density="compact">' in built

    code, out = run_cli("context")
    assert code == 0, out
    payload = json.loads(out)
    look = payload["presentation"]["layout"]["look"]
    assert "--nav top|side" in look["scaffold"]
    recipes = payload["presentation"]["layout"]["recipes"]
    assert set(recipes) == {"editorial", "brief", "dashboard", "tabbed"}
    for name, text in recipes.items():
        assert f"--layout {name}" in text


_APP_JSX = """import { useState } from "react";
import { BarChart, Bar } from "recharts";
import { TrendingUp } from "lucide-react";
import { Kpi, Chart, Table, useBinding } from "tracebi";

export default function App() {
  const [view, setView] = useState("Overview");
  const regions = useBinding("by_region");
  return (
    <main className="flex gap-6 p-6">
      <nav><button onClick={() => setView("Detail")}><TrendingUp size={16} /> Detail</button></nav>
      {view === "Overview" ? (
        <div className="tb-grid">
          <Kpi lead binding="kpis" cell="revenue" format="currency0" label="Revenue" />
          <Chart binding="by_region" x="dim_region.region" y="revenue" />
        </div>
      ) : (
        <>
          <Table binding="by_region" sort />
          <BarChart width={400} height={200} data={regions}><Bar dataKey="revenue" /></BarChart>
        </>
      )}
    </main>
  );
}
"""


def test_an_app_jsx_report_builds_claims_and_verifies(scaffolded):
    """The React lane: a package whose page is app.jsx builds to one file,
    records the kit figures as claims, and verifies like any report. An
    import from outside the kit, or a kit figure naming a binding the
    report does not declare, fails the build instead of shipping."""
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    pkg = scaffolded / "reports" / "regions_app"
    pkg.mkdir()
    (pkg / "report.json").write_text(json.dumps({"name": "Regions App", "data": {
        "kpis": {"model": "sample_model",
                 "query": {"fact": "fact_orders", "measures": ["revenue"]}},
        "by_region": {"model": "sample_model", "query": {
            "fact": "fact_orders", "measures": ["revenue"],
            "dimensions": ["dim_region.region"], "order_by": ["-revenue"]}},
    }}), encoding="utf-8")
    (pkg / "app.jsx").write_text(_APP_JSX, encoding="utf-8")

    code, out = run_cli("report", "build", "regions_app")
    assert code == 0, out
    built = (scaffolded / "output" / "regions_app.html").read_text()
    assert 'id="tracebi-app"' in built and "TraceBi-credit: Recharts" in built
    # Only the icons the app imports ride in the page.
    icons = json.loads(built.split('id="tracebi-icons">', 1)[1].split("</script>", 1)[0])
    assert list(icons) == ["TrendingUp"]
    manifest_path = scaffolded / "output" / "regions_app.html.manifest.json"
    claims = {f["id"]: f["binding"] for f in json.loads(manifest_path.read_text())["figures"]}
    assert claims == {"fig-value-kpis-revenue": "kpis",
                      "fig-chart-by_region-revenue": "by_region",
                      "fig-table-by_region": "by_region"}
    assert "This page is an app." in built
    code, out = run_cli("verify", str(manifest_path))
    assert code == 0, out

    (pkg / "app.jsx").write_text(_APP_JSX.replace('"recharts"', '"chart.js"'), encoding="utf-8")
    code, out = run_cli("report", "build", "regions_app")
    assert code != 0 and '"chart.js", which is not in the TraceBi kit' in out

    (pkg / "app.jsx").write_text(_APP_JSX.replace('binding="kpis"', 'binding="kpi"'),
                                 encoding="utf-8")
    code, out = run_cli("report", "build", "regions_app")
    assert code != 0 and "kpi" in out

    # A number typed into the app's text is refused, as in a template.html.
    (pkg / "app.jsx").write_text(_APP_JSX.replace("</nav>", "<p>Up 1250 units.</p></nav>", 1),
                                 encoding="utf-8")
    code, out = run_cli("report", "build", "regions_app")
    assert code != 0 and "typed into app.jsx" in out, out


def test_dashboards_by_job(scaffolded, tmp_path, monkeypatch):
    """--job picks what a dashboard is for, and each one builds and verifies.
    A trend asks for a time dimension: without one it says so and starts
    from totals; with one, the latest period and the series are its bindings."""
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    code, out = run_cli("new-dashboard", "Regions Board", "--job", "leaderboard")
    assert code == 0, out
    decl = json.loads((scaffolded / "reports" / "regions_board" / "report.json").read_text())
    assert decl["data"]["top10"]["query"]["limit"] == 10
    code, out = run_cli("report", "build", "regions_board")
    assert code == 0, out
    code, out = run_cli("verify", str(scaffolded / "output" / "regions_board.html.manifest.json"))
    assert code == 0, out

    code, out = run_cli("new-dashboard", "Sample Trend", "--job", "trend")
    assert code == 0 and "no time dimension" in out, out

    saas = tmp_path / "saas"
    code, out = run_cli("init", str(saas), "--template", "saas-metrics")
    assert code == 0, out
    monkeypatch.chdir(saas)
    code, out = run_cli("run-transform", "saas_transform")
    assert code == 0, out
    code, out = run_cli("new-dashboard", "MRR Trend", "--job", "trend")
    assert code == 0, out
    data = json.loads((saas / "reports" / "mrr_trend" / "report.json").read_text())["data"]
    assert data["by_period"]["query"]["dimensions"] == ["dim_month.month"]
    assert data["latest"]["query"]["order_by"] == ["-dim_month.month"]
    code, out = run_cli("report", "build", "mrr_trend")
    assert code == 0, out
    claims = {f["id"] for f in json.loads(
        (saas / "output" / "mrr_trend.html.manifest.json").read_text())["figures"]}
    assert {"fig-spark-by_period-ending_mrr", "kpi-latest-period"} <= claims

    # A scorecard: every measure the fact runs (up to four), each a KPI with
    # its trend — and labels spell the business acronym (Ending MRR).
    code, out = run_cli("new-dashboard", "Scorecard", "--job", "scorecard")
    assert code == 0, out
    data = json.loads((saas / "reports" / "scorecard" / "report.json").read_text())["data"]
    assert len(data["totals"]["query"]["measures"]) == 4
    assert data["by_period"]["query"]["dimensions"] == ["dim_month.month"]
    assert 'label="Ending MRR"' in (saas / "reports" / "scorecard" / "app.jsx").read_text()
    code, out = run_cli("report", "build", "scorecard")
    assert code == 0, out
    claims = {f["id"] for f in json.loads(
        (saas / "output" / "scorecard.html.manifest.json").read_text())["figures"]}
    assert {"fig-value-totals-ending_mrr", "fig-spark-by_period-customers"} <= claims

    # A monitor: the latest month of every measure and a watch list, lowest first.
    code, out = run_cli("new-dashboard", "Health", "--job", "monitor")
    assert code == 0, out
    data = json.loads((saas / "reports" / "health" / "report.json").read_text())["data"]
    assert data["latest"]["query"]["order_by"] == ["-dim_month.month"]
    assert data["watch"]["query"]["order_by"] == ["ending_mrr"]
    code, out = run_cli("report", "build", "health")
    assert code == 0, out
    code, out = run_cli("verify", str(saas / "output" / "health.html.manifest.json"))
    assert code == 0, out

    # A funnel: count measures (not money, not rates) as stages, widest first,
    # each conversion a report-level ratio — stamped, and written as a percent.
    sales = tmp_path / "sales"
    code, out = run_cli("init", str(sales), "--template", "sales-pipeline")
    assert code == 0, out
    monkeypatch.chdir(sales)
    code, out = run_cli("run-transform", "sales_pipeline_transform")
    assert code == 0, out
    code, out = run_cli("new-dashboard", "Deal Funnel", "--job", "funnel")
    assert code == 0, out
    decl = json.loads((sales / "reports" / "deal_funnel" / "report.json").read_text())
    assert decl["data"]["stages"]["query"]["measures"] == [
        "closed_deals", "won_deals", "won_deals_conversion"]
    assert decl["measures"]["sales_pipeline_model"]["won_deals_conversion"]["ratio"] == [
        "won_deals", "closed_deals"]
    code, out = run_cli("report", "build", "deal_funnel")
    assert code == 0, out
    built = (sales / "output" / "deal_funnel.html").read_text()
    formats = json.loads(built.split('id="tracebi-formats" type="application/json">', 1)[1]
                         .split("</script>", 1)[0])
    assert formats["stages"]["won_deals_conversion"] == "percent"
    code, out = run_cli("verify", str(sales / "output" / "deal_funnel.html.manifest.json"))
    assert code == 0, out


def test_themes_and_the_house_style(scaffolded):
    """A report names a shipped theme and the page carries it, over the
    project default that `theme use` writes; an unknown name fails the
    build. The house style init writes reaches the agent through context."""
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    code, out = run_cli("theme", "list")
    assert code == 0 and "ocean" in out and "midnight" in out, out

    code, out = run_cli("theme", "use", "sand")
    assert code == 0, out
    assert "--tb-accent: #44403c" in (scaffolded / "reports" / "_theme.css").read_text()
    code, out = run_cli("theme", "use", "ocean")
    assert code != 0 and "--force" in out

    code, out = run_cli("new-report", "Teal", "--theme", "ocean")
    assert code == 0, out
    assert json.loads((scaffolded / "reports" / "teal" / "report.json").read_text())[
        "theme"] == "ocean"
    code, out = run_cli("report", "build", "teal")
    assert code == 0, out
    page = (scaffolded / "output" / "teal.html").read_text()
    # The project default first, then the report's theme over it.
    assert page.index("--tb-accent: #44403c") < page.index("--tb-accent: #0e7490")

    decl_path = scaffolded / "reports" / "teal" / "report.json"
    decl = json.loads(decl_path.read_text())
    decl["theme"] = "neon"
    decl_path.write_text(json.dumps(decl))
    code, out = run_cli("report", "build", "teal")
    assert code != 0 and "unknown theme 'neon'" in out

    code, out = run_cli("context", "--brief")
    assert code == 0, out
    style = json.loads(out)["house_style"]
    assert style["file"] == "reports/_style.md" and "## Rules" in style["text"]


def test_status_and_the_review_snapshot(scaffolded):
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    code, out = run_cli("report", "status", "sample_model/sample_dashboard")
    assert code == 0, out
    assert "9 figure(s) — 9 query-backed, 0 python-derived, 0 unverified" in out

    code, out = run_cli("report", "snapshot", "sample_model/sample_dashboard")
    assert code == 0, out
    snapshot = scaffolded / "output" / "sample_model" / "sample_dashboard.snapshot.html"
    assert snapshot.is_file()
    assert not (scaffolded / "output" / "sample_model" / "sample_dashboard.snapshot.html.manifest.json").exists()
    code, out = run_cli("verify", "--file", str(snapshot))
    assert code != 0, "a review snapshot is not a receipt"


@pytest.mark.parametrize("flags", [[], ["--app"]])
def test_dev_opens_the_web_app_on_the_report_in_build_mode(scaffolded, monkeypatch, flags):
    """`tracebi dev <name>`: one command, the app in dev mode, pointed at that
    report with Build already on (the agent's chat goes beside it). `--app` is the
    old spelling of the same thing and still works."""
    import os
    import urllib.parse

    seen = {}

    class _Timer:                       # the browser opens a moment after the server is up
        def __init__(self, delay, fn):
            seen["open"] = fn

        def start(self):
            pass

    monkeypatch.setattr("threading.Timer", _Timer)
    monkeypatch.setattr("webbrowser.open", lambda url: seen.setdefault("browser", url))
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: seen.update(app=app, **kw))
    # The command sets this in the process; recording it here makes pytest undo it.
    monkeypatch.setenv("TRACEBI_DEV_MODE", "0")

    code, out = run_cli("dev", "sample_model/sample_dashboard", *flags, "--port", "8765")
    assert code == 0, out
    assert os.environ["TRACEBI_DEV_MODE"] == "1", "Build mode needs the server in dev mode"
    assert seen["app"] == "tracebi.web.api.main:app" and seen["port"] == 8765
    assert seen["host"] == "127.0.0.1", "dev-state endpoints stay on loopback"
    url = "http://127.0.0.1:8765/reports?" + urllib.parse.urlencode(
        {"r": "sample_model/sample_dashboard", "build": "1"})
    assert url in out
    seen["open"]()
    assert seen["browser"] == url

    code, out = run_cli("dev", "nope", *flags)
    assert code == 1 and "not found" in out


@pytest.fixture
def no_server(monkeypatch):
    """Neither server can start: record which one `tracebi dev` reached for."""
    seen = {}
    monkeypatch.setattr("webbrowser.open", lambda url: None)
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: seen.update(app=app, **kw))
    monkeypatch.setattr("tracebi._dev_server.serve_dev", lambda target, **kw: seen.update(
        classic=target, **kw) or 0)
    monkeypatch.setenv("TRACEBI_DEV_MODE", "0")   # the command sets it; pytest undoes it
    return seen


def test_dev_with_no_name_opens_the_app_where_the_agents_exhibits_land(scaffolded, no_server):
    """No report yet: the app, in dev mode, on Reports, where the project feed is."""
    import os

    code, out = run_cli("dev", "--no-browser", "--port", "8766")
    assert code == 0, out
    assert os.environ["TRACEBI_DEV_MODE"] == "1"
    assert no_server["app"] == "tracebi.web.api.main:app" and no_server["port"] == 8766
    assert no_server["host"] == "127.0.0.1" and "classic" not in no_server
    assert "http://127.0.0.1:8766/reports\n" in out
    assert "tracebi.workbench.show" in out


def test_dev_classic_keeps_the_old_preview_server(scaffolded, no_server):
    code, out = run_cli("dev", "sample_model/sample_dashboard", "--classic", "--port", "8767")
    assert code == 0, out
    assert str(no_server["classic"]).endswith("sample_model/sample_dashboard") and no_server["port"] == 8767
    assert "app" not in no_server

    no_server.clear()
    code, out = run_cli("dev", "--classic")
    assert code == 0, out
    assert no_server["classic"] is None and "app" not in no_server, "no name is the discovery workbench"


def test_dev_without_the_web_extra_falls_back_to_the_classic_preview(scaffolded, no_server, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "uvicorn", None)       # `import uvicorn` now fails
    for args in (["dev", "sample_model/sample_dashboard"], ["dev"]):
        no_server.clear()
        code, out = run_cli(*args)
        assert code == 0, out
        assert "classic" in no_server and "app" not in no_server
        assert "pip install 'tracebi[web]'" in out and "Traceback" not in out
