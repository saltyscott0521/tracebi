"""The D3 chart engine, in a real browser.

Every declared chart type (bar, barh, line, area, pie, scatter) is drawn by
the inlined D3 from the stamped rows. These pin what a reader relies on: one
mark per row and no ECharts on the page, a tooltip that shows the row's own
value in the page's format, a click that filters through the page's own
control, colours that follow the series rather than its position, a legend
that cannot hide the last series, and arrow keys that read every value.

Skipped unless Playwright can launch Chromium. The CI job ``ui-smoke``
installs Chromium and runs this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.reports.template_package import TemplatePackage

_SALES = pd.DataFrame({
    "sale_id": list(range(16)),
    "region": ["East", "West", "North", "South"] * 4,
    "quarter": [q for q in ("Q1", "Q2", "Q3", "Q4") for _ in range(4)],
    "product": ["A", "B", "A", "B"] * 4,
    "revenue": [1200, 900, 400, 300, 1500, 800, 450, 350,
                1700, 950, 500, 320, 1600, 1000, 520, 380],
    "cost": [700, 600, 300, 200, 800, 500, 300, 250,
             900, 600, 350, 220, 850, 640, 360, 260],
})


def _model() -> DataModel:
    model = DataModel("sales_model")
    model.add_connector(MemoryConnector("mem", tables={"sales": _SALES}))
    model.add_table("sales", connector="mem", source="sales")
    model.add_dimension("dim_sale", table_name="sales", key_col="sale_id",
                        attributes=["region", "quarter", "product"])
    model.add_fact("fact_sales", table_name="sales",
                   measures=["revenue", "cost"], foreign_keys={})
    model.add_measure("revenue", column="revenue", agg="sum")
    model.add_measure("cost", column="cost", agg="sum")
    model.connect()
    return model


def _query(dims, measures=("revenue",), order=None):
    q = {"fact": "fact_sales", "measures": list(measures), "dimensions": list(dims)}
    if order:
        q["order_by"] = order
    return {"model": "sales_model", "query": q}


_FIGURES = """
<select id="f-region" data-tb-filter data-tb-binding="by_region"
        data-tb-column="dim_sale.region"></select>
<select id="f-product" data-tb-filter data-tb-binding="by_quarter"
        data-tb-column="dim_sale.product"></select>
<div id="bar" data-tb-figure="chart" data-tb-binding="by_region" data-tb-type="bar"
     data-tb-x="dim_sale.region" data-tb-y="revenue" data-tb-value-format="currency0"></div>
<div id="barh" data-tb-figure="chart" data-tb-binding="by_region" data-tb-type="barh"
     data-tb-x="dim_sale.region" data-tb-y="revenue,cost"></div>
<div id="line" data-tb-figure="chart" data-tb-binding="by_quarter" data-tb-type="line"
     data-tb-x="dim_sale.quarter" data-tb-y="revenue" data-tb-color="dim_sale.product"></div>
<div id="area" data-tb-figure="chart" data-tb-binding="totals_by_quarter" data-tb-type="area"
     data-tb-x="dim_sale.quarter" data-tb-y="revenue"></div>
<div id="pie" data-tb-figure="chart" data-tb-binding="by_product" data-tb-type="pie"
     data-tb-x="dim_sale.product" data-tb-y="revenue"></div>
<div id="scatter" data-tb-figure="chart" data-tb-binding="by_region" data-tb-type="scatter"
     data-tb-x="cost" data-tb-y="revenue"></div>
"""


def _build(tmp_path: Path) -> Path:
    pkg = tmp_path / "charts"
    pkg.mkdir()
    (pkg / "report.json").write_text(json.dumps({
        "name": "Charts",
        "data": {
            "by_region": _query(["dim_sale.region"], ("revenue", "cost"), ["-revenue"]),
            "by_quarter": _query(["dim_sale.quarter", "dim_sale.product"],
                                 order=["dim_sale.quarter"]),
            "totals_by_quarter": _query(["dim_sale.quarter"], order=["dim_sale.quarter"]),
            "by_product": _query(["dim_sale.product"]),
        },
    }), encoding="utf-8")
    (pkg / "template.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Charts</title>"
        "</head><body><main class=\"tb-page\" style=\"width:900px\">"
        + _FIGURES + "</main></body></html>", encoding="utf-8")
    out = tmp_path / "charts.html"
    TemplatePackage(str(pkg)).render({"sales_model": _model()}, str(out))
    return out


@pytest.fixture(scope="module")
def page(tmp_path_factory):
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    html = _build(tmp_path_factory.mktemp("d3"))
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(headless=True)
    except Exception as exc:
        pw.stop()
        pytest.skip(f"Chromium is not installed: {exc}")
    p = browser.new_page(viewport={"width": 1000, "height": 900},
                         reduced_motion="reduce")
    p.set_default_timeout(30_000)
    errors: list[str] = []
    p.on("pageerror", lambda exc: errors.append(str(exc)))
    p.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    p.goto(html.as_uri())
    p.wait_for_function("() => document.documentElement.getAttribute('data-tb-ready') === '1'")
    p.errors = errors
    yield p
    browser.close()
    pw.stop()


def _reset(page):
    for sel in ("#f-region", "#f-product"):
        if page.locator(sel).input_value() != "All":
            page.select_option(sel, "All")


def test_every_type_draws_one_mark_per_row_and_ships_no_echarts(page):
    assert page.evaluate("typeof window.echarts") == "undefined"
    assert page.evaluate("typeof window.d3") == "object"
    counts = {fig: page.locator(f"#{fig} .tb-mark").count()
              for fig in ("bar", "barh", "pie", "scatter")}
    # 4 regions; barh draws revenue and cost per region; 2 products.
    assert counts == {"bar": 4, "barh": 8, "pie": 2, "scatter": 4}
    assert page.locator("#line path.tb-line").count() == 2      # one per product
    assert page.locator("#line circle.tb-dot").count() == 8     # 4 quarters × 2
    assert page.locator("#area path.tb-area").count() == 1
    assert page.errors == []


def test_the_tooltip_shows_the_rows_own_value_in_the_pages_format(page):
    _reset(page)
    page.locator("#bar .tb-hit").first.hover()
    tip = page.locator("#bar .tb-chart-tip")
    tip.wait_for(state="visible")
    # East has the most revenue (the binding orders by -revenue): 1200+1500+1700+1600.
    assert tip.locator(".tb-chart-tip-title").inner_text() == "East"
    assert tip.locator("strong").inner_text() == "$6,000"


def test_a_click_filters_through_the_pages_control_and_colour_follows_the_series(page):
    _reset(page)
    colour_b = page.locator("#line path.tb-line").nth(1).get_attribute("stroke")
    page.locator("#bar .tb-hit").nth(1).click()          # West
    assert page.locator("#f-region").input_value() == "West"
    page.wait_for_function("() => document.querySelectorAll('#bar path.tb-mark').length === 1")
    page.locator("#bar .tb-hit").first.click()          # the same bar again clears it
    assert page.locator("#f-region").input_value() == "All"
    page.wait_for_function("() => document.querySelectorAll('#bar path.tb-mark').length === 4")
    # Filtered to product B, the B line is the only one left, and it keeps
    # B's colour instead of taking the first slot's.
    page.select_option("#f-product", "B")
    page.wait_for_function("() => document.querySelectorAll('#line path.tb-line').length === 1")
    assert page.locator("#line path.tb-line").get_attribute("stroke") == colour_b
    _reset(page)


def test_the_legend_toggles_series_but_never_hides_the_last(page):
    _reset(page)
    legend = page.locator("#barh .tb-legend-item")
    assert legend.count() == 2
    legend.nth(0).click()
    page.wait_for_function("() => document.querySelectorAll('#barh .tb-mark').length === 4")
    assert legend.nth(0).get_attribute("aria-pressed") == "false"
    legend.nth(1).click()                               # the last visible one stays
    assert legend.nth(1).get_attribute("aria-pressed") == "true"
    assert page.locator("#barh .tb-mark").count() == 4
    legend.nth(0).click()
    page.wait_for_function("() => document.querySelectorAll('#barh .tb-mark').length === 8")


def test_arrow_keys_read_each_value_aloud(page):
    _reset(page)
    page.locator("#pie svg").focus()
    page.keyboard.press("ArrowRight")
    live = page.locator("#pie .tb-sr-only")
    first = live.inner_text()
    page.keyboard.press("ArrowRight")
    second = live.inner_text()
    # Product A: every A row's revenue; B likewise. Each slice is one row.
    assert {first, second} == {"A: Revenue 7,870", "B: Revenue 5,000"}
