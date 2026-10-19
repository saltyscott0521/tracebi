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
        for transform in ("holdings_transform", "saas_transform", "affordability_transform"):
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
    assert models == ["housing_model", "portfolio_model", "saas_model"]
    for model in models:
        names = reports_of(model)
        assert names, f"reports/{model}/ has no reports"
        assert (built / "pipelines" / f"{model}.yaml").is_file(), f"{model} has no pipeline"
        # ...and every report in the reference project sits under a model's folder
    everything = {name for names in map(reports_of, models) for name in names}
    assert everything == set(REPORTS), "a report sits outside its model's folder"
    assert model_pipeline  # exported at the top level for project pipelines


@pytest.mark.parametrize("model", ["portfolio_model", "housing_model", "saas_model"])
def test_a_models_pipeline_rebuilds_its_data_then_its_reports(built, model):
    from tracebi.pipeline.model_pipeline import reports_of

    code, out = run_cli("run-pipeline", model)
    assert code == 0, out
    assert "transform" in out and "build" in out
    for name in reports_of(model):
        code, out = run_cli("verify", str(_manifest(built, name)), "--contracts")
        assert code == 0 and "REPRODUCES" in out, f"{name}: {out}"


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
        assert joins["fact_ten_year"] == {"dim_cohort"}
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
    finally:
        browser.close()
        pw.stop()


def test_the_saas_dashboard_recomputes_every_figure_by_plan(built):
    """The SaaS measures are period_end balances, and the page runs them: a
    plan picked in mrr_dashboard's filter recomputes every KPI, spark, chart
    and table exactly where execute_plan over the slice says (each month's
    latest balance, under the plan), none is fixed, and the chip reads Local.
    cohort_brief has no control; its slice still reproduces on the server."""
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
