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


def test_without_javascript_the_figures_still_read(browser, tmp_path):
    """An email preview or a phone's file viewer runs no script: the page
    shows the kit figures as built — the KPI with its label and number, the
    table's rows — instead of a blank page. With script, the app replaces
    that view, so no figure id is on the page twice."""
    html = _build(tmp_path, _APP)
    still = browser.new_context(java_script_enabled=False).new_page()
    still.goto(html.as_uri())
    kpi = still.locator(".tb-app-static .tb-kpi")
    assert kpi.locator(".tb-kpi-label").inner_text() == "Revenue"
    assert kpi.locator(".tb-kpi-value").inner_text() == "$5,251"
    assert still.locator(".tb-app-static #fig-table-by_region tbody tr").count() == 3

    page = _open(browser, html)
    assert page.locator(".tb-app-static").count() == 0
    assert page.evaluate(
        "() => { const ids = [...document.querySelectorAll('[id]')].map(e => e.id);"
        " return ids.length - new Set(ids).size; }") == 0


_APP_STATE = """
import { Kpi, Table, Filter, Segmented, useUrlState } from "tracebi";

export default function App() {
  const [view, setView] = useUrlState("view", "Totals");
  return (
    <div>
      <Segmented options={["Totals", "Sales"]} value={view} onChange={setView} />
      <Filter column="dim_sale.region" label="Region" />
      <Kpi binding="totals" cell="revenue" format="currency0" label="Revenue" />
      <Table binding="by_region" />
      {view === "Sales" && <Table binding="by_sale" />}
    </div>
  );
}
"""


def test_a_page_filter_reaches_every_binding_and_the_view_rides_in_the_url(browser, tmp_path):
    """One filter with no binding subsets every binding that has the column —
    tables mounted later too — and leaves the KPI the stamped total. The
    segmented choice is kept in the URL, so a reload opens on it."""
    html = _build(tmp_path, _APP_STATE)
    page = _open(browser, html)
    page.select_option("select[data-tb-filter]", "West")
    assert page.locator("#fig-table-by_region tbody tr").count() == 1
    assert page.locator(".tb-kpi-value").inner_text() == "$5,251"

    page.get_by_role("radio", name="Sales").click()
    sales = page.locator("#fig-table-by_sale tbody tr")
    sales.first.wait_for()
    assert sales.count() == 2          # the West's two sales, filtered on arrival
    assert "view=Sales" in page.evaluate("() => location.hash")

    page.reload()
    page.wait_for_function("() => document.documentElement.getAttribute('data-tb-ready') === '1'")
    assert page.get_by_role("radio", name="Sales").get_attribute("aria-checked") == "true"
    assert page.locator("#fig-table-by_sale").count() == 1
    assert page.errors == []


_APP_VIEWS = """
import { Kpi, Table, useUrlState, usePrinting } from "tracebi";

export default function App() {
  const [view] = useUrlState("view", "Totals");
  const printing = usePrinting();
  const Totals = () => <Kpi binding="totals" cell="revenue" format="currency0" label="Revenue" />;
  const Sales = () => <Table binding="by_sale" />;
  return printing ? <><Totals /><Sales /></> : (view === "Totals" ? <Totals /> : <Sales />);
}
"""


def test_printing_renders_every_view_filled(browser, tmp_path):
    """While the page prints (Ctrl+P, or the PDF build, which dispatches
    beforeprint), an app with views shows all of them — the hidden ones'
    figures filled by then, not on the next frame — and goes back after."""
    html = _build(tmp_path, _APP_VIEWS)
    page = _open(browser, html)
    assert page.locator("#fig-table-by_sale").count() == 0
    rows = page.evaluate("""() => {
      window.dispatchEvent(new Event('beforeprint'));
      return document.querySelectorAll('#fig-table-by_sale tbody tr').length;
    }""")
    assert rows == 6
    assert page.locator(".tb-kpi-value").inner_text() == "$5,251"
    page.evaluate("() => window.dispatchEvent(new Event('afterprint'))")
    assert page.locator("#fig-table-by_sale").count() == 0
    assert page.errors == []
