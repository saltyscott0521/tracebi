"""The React lane (app.jsx), in a real browser under the report's CSP.

Pins what only a browser shows: the app compiles and runs with eval still
refused; a kit figure shows the stamped number in the page's format; a figure
the app mounts AFTER load (a view switch) is filled from the stamped rows and
answers the page's filter like any other; and a broken app says so instead of
shipping a blank page.

Skipped unless Playwright can launch Chromium.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.reports.template_package import TemplatePackage

_SALES = pd.DataFrame({
    "sale_id": list(range(6)),
    "region": ["East", "West", "North", "East", "West", "North"],
    "revenue": [1200.75, 900, 400, 1500, 800, 450],
})

_APP = """
import { useState } from "react";
import { Search } from "lucide-react";
import { Kpi, Table, Filter, useBinding } from "tracebi";

export default function App() {
  const [view, setView] = useState("Overview");
  const rows = useBinding("by_region");
  return (
    <div>
      <button id="go" onClick={() => setView("Detail")}><Search size={14} /> Detail</button>
      <p id="own">{rows.length} regions</p>
      {view === "Overview" ? (
        <div className="tb-grid">
          <Kpi binding="totals" cell="revenue" format="currency0" label="Revenue" />
        </div>
      ) : (
        <section>
          <Filter binding="by_region" column="dim_sale.region" />
          <Table binding="by_region" />
        </section>
      )}
    </div>
  );
}
"""


def _model() -> DataModel:
    model = DataModel("sales_model")
    model.add_connector(MemoryConnector("mem", tables={"sales": _SALES}))
    model.add_table("sales", connector="mem", source="sales")
    model.add_dimension("dim_sale", table_name="sales", key_col="sale_id",
                        attributes=["region"])
    model.add_fact("fact_sales", table_name="sales", measures=["revenue"],
                   foreign_keys={})
    model.add_measure("revenue", column="revenue", agg="sum")
    model.connect()
    return model


def _build(tmp: Path, app: str) -> Path:
    pkg = tmp / "app"
    pkg.mkdir()
    q = lambda dims: {"model": "sales_model", "query": {  # noqa: E731
        "fact": "fact_sales", "measures": ["revenue"], "dimensions": dims}}
    (pkg / "report.json").write_text(json.dumps({"name": "App", "data": {
        "totals": q([]), "by_region": q(["dim_sale.region"]),
        "by_sale": q(["dim_sale.region", "dim_sale.sale_id"])}}), encoding="utf-8")
    (pkg / "app.jsx").write_text(app, encoding="utf-8")
    out = tmp / "app.html"
    TemplatePackage(str(pkg)).render({"sales_model": _model()}, str(out))
    return out


@pytest.fixture(scope="module")
def browser():
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    pw = sync_playwright().start()
    try:
        b = pw.chromium.launch(headless=True)
    except Exception as exc:
        pw.stop()
        pytest.skip(f"Chromium is not installed: {exc}")
    yield b
    b.close()
    pw.stop()


def test_a_style_css_token_gives_way_to_the_dark_ground(browser, tmp_path):
    """On an app page tracebi.css sits in a cascade layer, so a style.css that
    sets :root tokens (an accent, a light ink) used to beat the dark ground:
    dark cards with near-black text. The dark tokens win, as on a template page."""
    out = _build(tmp_path, _APP)
    (tmp_path / "app" / "style.css").write_text(
        ":root { --tb-ink: #10201c; --tb-accent: #1f6f5c; --tb-dark-accent: #6cc3a8; }",
        encoding="utf-8")
    TemplatePackage(str(tmp_path / "app")).render({"sales_model": _model()}, str(out))
    page = browser.new_page(color_scheme="dark")
    page.goto(out.as_uri())
    tokens = page.evaluate("""() => { const s = getComputedStyle(document.documentElement);
        return [s.getPropertyValue('--tb-ink').trim(), s.getPropertyValue('--tb-accent').trim()]; }""")
    assert tokens[0] != "#10201c"
    assert tokens[1] == "#6cc3a8"
    light = browser.new_page(color_scheme="light")
    light.goto(out.as_uri())
    assert light.evaluate(
        "() => getComputedStyle(document.documentElement).getPropertyValue('--tb-ink').trim()"
    ) == "#10201c"


def test_an_echart_page_ships_echarts_and_a_plain_page_nothing_extra():
    """One runtime (Redact) for every page; ECharts (~0.9 MB) only on a page
    that draws a chart (<Chart>, <Spark>, <EChart>) or imports echarts, before
    the runtime that registers it, and Recharts only on a page that imports it."""
    from tracebi.reports.app_lane import libs_for
    assert libs_for({"react": ["useState"], "tracebi": ["Kpi"]}) == ["tailwind", "react"]
    assert libs_for({"tracebi": ["Kpi", "EChart"]}) == ["tailwind", "echarts-kit", "react"]
    assert libs_for({"tracebi": ["Spark"]}) == ["tailwind", "echarts-kit", "react"]
    assert libs_for({"echarts": ["*"]}) == ["tailwind", "echarts-kit", "react"]
    assert libs_for({"recharts": ["BarChart"]}) == ["tailwind", "react", "recharts"]
