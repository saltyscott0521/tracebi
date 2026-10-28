"""The chart engine (Apache ECharts), in a real browser.

Every declared chart type (bar, barh, line, area, pie, scatter) is drawn by
ECharts from the stamped rows, through tracebi.js's one option builder. These
pin what a reader relies on: a tooltip that shows the row's own value in the
page's format, a click that writes the page's selection, colours that follow
the series rather than its position, a legend that cannot hide the last
series, arrow keys that read every value, the author's marks and notes, a
drag that zooms, short ticks with a unit that never rescales, bars that carry
their own values, the readout's way to the trace, and a canvas chart that
prints as vectors.

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
    "week": [f"W{i + 1:02d}" for i in range(16)],
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
                        attributes=["region", "quarter", "product", "week"])
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
     data-tb-x="dim_sale.quarter" data-tb-y="revenue" data-tb-unit=" u"></div>
<div id="pie" data-tb-figure="chart" data-tb-binding="by_product" data-tb-type="pie"
     data-tb-x="dim_sale.product" data-tb-y="revenue"></div>
<div id="scatter" data-tb-figure="chart" data-tb-binding="by_region" data-tb-type="scatter"
     data-tb-x="cost" data-tb-y="revenue"></div>
<div id="stack" data-tb-figure="chart" data-tb-binding="by_quarter" data-tb-type="bar"
     data-tb-x="dim_sale.quarter" data-tb-y="revenue" data-tb-color="dim_sale.product"
     data-tb-stack></div>
<div id="weekly" data-tb-figure="chart" data-tb-binding="by_week" data-tb-type="area"
     data-tb-x="dim_sale.week" data-tb-y="revenue" data-tb-mark="max,last"
     data-tb-annotate="W05=Launch" data-tb-x-title="Week"></div>
<div id="facet" data-tb-figure="chart" data-tb-binding="by_quarter" data-tb-type="bar"
     data-tb-x="dim_sale.quarter" data-tb-y="revenue" data-tb-facet="dim_sale.product"></div>
<div class="tb-kpi" style="width:300px">
  <div id="spark" class="tb-spark" data-tb-figure="chart" data-tb-binding="totals_by_quarter"
       data-tb-type="area" data-tb-x="dim_sale.quarter" data-tb-y="revenue"
       data-tb-value-format="currency0"></div>
</div>
<div id="canvas" data-tb-figure="chart" data-tb-binding="by_product" data-tb-type="bar"
     data-tb-x="dim_sale.product" data-tb-y="revenue" data-tb-renderer="canvas"></div>
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
            "by_week": _query(["dim_sale.week"], order=["dim_sale.week"]),
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
    html = _build(tmp_path_factory.mktemp("charts"))
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
    page.mouse.move(0, 0)


# The chart's ECharts instance, read in the page: what it draws is its option.
_INST = ("window.__tbECharts.getInstanceByDom("
         "document.querySelector('#' + id + ' .tb-chart-host'))")


def _option(page, fid, expr):
    return page.evaluate(f"(id) => {{ const c = {_INST}; const o = c.getOption(); return {expr}; }}", fid)


def _point(page, fid, series, index):
    """The page coordinates of one data item: the middle of a bar, a point."""
    return page.evaluate(f"""([id, s, i]) => {{
        const c = {_INST}, host = document.querySelector('#' + id + ' .tb-chart-host');
        host.scrollIntoView({{block: 'center'}});
        const o = c.getOption(), ser = o.series[s], d = ser.data[i];
        const v = d !== null && typeof d === "object" ? d.value : d;
        const r = host.getBoundingClientRect();
        let x, y;
        if (ser.type === "pie") {{
          const l = c.getModel().getSeriesByIndex(s).getData().getItemLayout(i);
          const a = (l.startAngle + l.endAngle) / 2, m = (l.r + l.r0) / 2;
          x = l.cx + m * Math.cos(a); y = l.cy + m * Math.sin(a);
        }} else {{
          const flat = o.yAxis[0].type === "category";
          [x, y] = c.convertToPixel({{seriesIndex: s}},
            flat ? [v * 0.5, i] : [i, ser.type === "bar" ? v * 0.5 : v]);
        }}
        return [r.left + x, r.top + y]; }}""", [fid, series, index])


def _hover(page, fid, series, index):
    x, y = _point(page, fid, series, index)
    page.mouse.move(x, y)
    tip = page.locator(f"#{fid} .tb-echart-tip").first
    page.wait_for_function(
        "(id) => { const t = document.querySelector('#' + id + ' .tb-echart-tip');"
        " return t && t.style.display !== 'none' && t.style.opacity !== '0'"
        " && t.querySelector('.tb-chart-tip-title'); }", arg=fid)
    return tip


def test_the_tooltip_shows_the_rows_own_value_in_the_pages_format(page):
    _reset(page)
    tip = _hover(page, "bar", 0, 0)
    # East has the most revenue (the binding orders by -revenue): 1200+1500+1700+1600.
    assert tip.locator(".tb-chart-tip-title").inner_text() == "East"
    assert tip.locator("strong").inner_text() == "$6,000"
    # The chart is a figure a reader reaches: labelled, a keyboard stop.
    host = page.locator("#bar .tb-chart-host")
    assert host.get_attribute("role") == "img" and host.get_attribute("tabindex") == "0"
    assert "Revenue by Region" in host.get_attribute("aria-label")
    assert page.errors == []


def test_a_click_selects_and_colour_follows_the_series(page):
    _reset(page)
    colours = _option(page, "line", "o.series.map((s) => [s.name, s.itemStyle.color])")
    page.mouse.click(*_point(page, "bar", 0, 1))            # West
    assert page.locator("#f-region").input_value() == "West"
    # The clicked chart keeps every region and draws the others back
    # (cross-highlighting), so another can be shift-clicked in.
    page.wait_for_function(f"""() => {{ const id = 'bar'; const o = {_INST}.getOption();
        return o.series[0].data.filter((d) => d && d.itemStyle && d.itemStyle.opacity < 1).length === 3; }}""")
    assert _option(page, "bar", "o.xAxis[0].data.length") == 4
    page.mouse.click(*_point(page, "bar", 0, 1))            # the same bar again clears it
    assert page.locator("#f-region").input_value() == "All"
    page.wait_for_function(f"""() => {{ const id = 'bar'; const o = {_INST}.getOption();
        return !o.series[0].data.some((d) => d && d.itemStyle && d.itemStyle.opacity < 1); }}""")
    # Product B picked, the B line keeps B's colour instead of taking the
    # first slot's, and the A line recedes.
    page.select_option("#f-product", "B")
    page.wait_for_function(f"""() => {{ const id = 'line'; const o = {_INST}.getOption();
        return o.series.some((s) => s.name === 'A' && s.lineStyle.opacity < 1); }}""")
    now = _option(page, "line", "o.series.map((s) => [s.name, s.itemStyle.color, s.lineStyle.opacity])")
    assert [[n, c] for n, c, _ in now] == colours
    assert [n for n, _, op in now if op is not None and op < 1] == ["A"]
    _reset(page)


def test_the_legend_toggles_series_but_never_hides_the_last(page):
    _reset(page)
    legend = page.locator("#barh .tb-legend-item")
    count = "o.series.length"
    assert legend.count() == 2 and _option(page, "barh", count) == 2
    legend.nth(0).click()
    page.wait_for_function(f"() => {{ const id = 'barh'; return {_INST}.getOption().series.length === 1; }}")
    assert legend.nth(0).get_attribute("aria-pressed") == "false"
    legend.nth(1).click()                               # the last visible one stays
    assert legend.nth(1).get_attribute("aria-pressed") == "true"
    assert _option(page, "barh", count) == 1
    legend.nth(0).click()
    page.wait_for_function(f"() => {{ const id = 'barh'; return {_INST}.getOption().series.length === 2; }}")


def test_arrow_keys_read_each_value_aloud(page):
    _reset(page)
    page.locator("#pie .tb-chart-host").focus()
    page.keyboard.press("ArrowRight")
    live = page.locator("#pie .tb-sr-only")
    first = live.inner_text()
    page.keyboard.press("ArrowRight")
    second = live.inner_text()
    # Product A: every A row's revenue; B likewise. Each slice is one row.
    assert {first, second} == {"A: Revenue 7,870", "B: Revenue 5,000"}
    # The readout follows the keys.
    assert page.locator("#pie .tb-echart-tip .tb-chart-tip-title").inner_text() in ("A", "B")
    page.keyboard.press("Escape")


def test_stacked_bars_list_each_rows_own_value_never_a_total(page):
    _reset(page)
    assert _option(page, "stack", "o.series.map((s) => s.stack)") == ["total0", "total0"]
    # Q1 holds A (1200+400) and B (900+300): the readout lists each row's own
    # value, never the 2,800 the stack reaches.
    tip = _hover(page, "stack", 0, 0)
    assert sorted(tip.locator(".tb-chart-tip-row strong").all_inner_texts()) == ["1,200", "1,600"]
    assert "2,800" not in tip.inner_text()


def _texts(page, fid):
    return page.locator(f"#{fid} .tb-chart-host svg text").all_text_contents()


def test_marks_and_annotations_label_the_rows_own_values(page):
    _reset(page)
    texts = _texts(page, "weekly")
    # W09 has the most revenue (1,700) and W16 is the last week (380).
    assert "High 1,700" in texts and "380" in texts
    assert "Launch" in texts
    assert "Week" in texts


def test_drag_zooms_to_a_range_and_reset_returns(page):
    _reset(page)
    cats = "o.xAxis[0].data.length"
    x0, y = _point(page, "weekly", 0, 1)
    x1, _ = _point(page, "weekly", 0, 6)
    page.mouse.move(x0, y)
    page.mouse.down()
    page.mouse.move(x1, y, steps=6)
    page.mouse.up()
    page.wait_for_function(f"() => {{ const id = 'weekly'; return {_INST}.getOption().xAxis[0].data.length < 16; }}")
    assert 2 <= _option(page, "weekly", cats) < 16
    page.locator("#weekly .tb-legend-reset").click()
    page.wait_for_function(f"() => {{ const id = 'weekly'; return {_INST}.getOption().xAxis[0].data.length === 16; }}")
    assert page.locator("#weekly .tb-legend-reset").count() == 0


def test_currency_ticks_stay_short_and_a_unit_never_rescales(page):
    _reset(page)
    ticks = [t for t in _texts(page, "bar") if t.startswith("$") and "," not in t]
    assert "$6K" in ticks and "$0" in ticks, ticks
    tip = _hover(page, "area", 0, 0)
    # Q1 revenue is 1200+900+400+300 = 2,800: the unit is a suffix, not a scale.
    assert tip.locator("strong").inner_text() == "2,800 u"
    assert "1K u" in _texts(page, "area")


def test_bars_carry_their_own_values_in_the_pages_format(page):
    """A direct label is the row's stamped value through the figure's own
    format, never a rounded recomputation; small multiples carry none."""
    _reset(page)
    labels = [t for t in _texts(page, "bar") if "," in t]
    # Revenue by region, ordered -revenue: East 6,000, West 3,650, North 1,870, South 1,350.
    assert sorted(labels) == sorted(["$6,000", "$3,650", "$1,870", "$1,350"])
    assert _option(page, "facet", "o.series.some((s) => s.label && s.label.show)") is False
    assert _option(page, "facet", "o.grid.length") == 2


def test_the_tooltip_opens_the_receipt_at_its_figure(page):
    """The readout holds still while a pointer travels to its Trace link (in
    small steps, as a hand does): a readout that follows the cursor or hides
    on the way cannot be clicked."""
    _reset(page)
    _hover(page, "bar", 0, 2)
    link = page.locator("#bar .tb-chart-tip-receipt")
    link.wait_for(state="visible")
    at = link.bounding_box()
    page.mouse.move(at["x"] + at["width"] / 2, at["y"] + at["height"] / 2, steps=25)
    now = link.bounding_box()
    assert link.is_visible() and abs(now["x"] - at["x"]) < 2 and abs(now["y"] - at["y"]) < 2, (at, now)
    link.click()
    assert page.locator(".tb-receipt-drawer.tb-receipt-open").count() == 1
    assert page.locator(".tb-receipt-row--here").get_attribute("data-tb-receipt-fig") == "bar"
    page.locator(".tb-receipt-btn").click()               # close it again


def test_a_canvas_chart_prints_as_vectors(page):
    """data-tb-renderer="canvas" draws a canvas; printed, the chart is drawn
    by the SVG renderer, and by canvas again after."""
    _reset(page)
    host = "#canvas .tb-chart-host"
    assert page.locator(f"{host} canvas").count() == 1
    assert page.locator(f"{host} svg").count() == 0
    page.evaluate("() => window.dispatchEvent(new Event('beforeprint'))")
    page.wait_for_selector(f"{host} svg path", state="attached")
    assert page.locator(f"{host} canvas").count() == 0
    page.evaluate("() => window.dispatchEvent(new Event('afterprint'))")
    page.wait_for_selector(f"{host} canvas", state="attached")
    assert page.locator(f"{host} svg").count() == 0
    assert page.errors == []
