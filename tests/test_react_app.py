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
        "totals": q([]), "by_region": q(["dim_sale.region"])}}), encoding="utf-8")
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


def _open(browser, html: Path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(html.as_uri())
    page.wait_for_function("() => document.documentElement.getAttribute('data-tb-ready') === '1'")
    page.errors = errors
    return page


def test_kit_figures_hydrate_including_ones_mounted_after_load(browser, tmp_path):
    page = _open(browser, _build(tmp_path, _APP))
    assert page.locator(".tb-kpi .tb-kpi-value").inner_text() == "$5,251"
    assert page.locator("#own").inner_text() == "3 regions"
    assert page.locator("svg.lucide-search").count() == 1

    page.click("#go")
    table = page.locator("#fig-table-by_region")
    table.locator("tbody tr").first.wait_for()
    assert table.locator("tbody tr").count() == 3
    page.select_option("select[data-tb-filter]", "West")
    assert table.locator("tbody tr").count() == 1
    assert "1,700" in table.locator("tbody tr").inner_text()
    assert page.errors == []


def test_a_broken_app_says_so_instead_of_a_blank_page(browser, tmp_path):
    page = _open(browser, _build(tmp_path, _APP.replace(
        "const rows = useBinding", "const rows = undefinedThing(); const _r = useBinding")))
    alert = page.locator(".tb-app-error")
    assert alert.count() == 1
    assert "undefinedThing" in alert.inner_text()
