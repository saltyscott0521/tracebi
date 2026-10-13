"""A custom script that rewrites a stamped figure is caught, and the receipt says so.

Skipped when Chromium is not installed (see test_table_window.py). A report's
``script.js`` may draw anything, but a stamped number is a claim: if the script
changes what the page shows for one, the receipt must not keep vouching for the
text the runtime wrote.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.reports.template_package import TemplatePackage

_SCRIPT = """
tracebi.ready(function () {
  setTimeout(function () {
    document.getElementById("kpi-a").querySelector(".tb-kpi-value").textContent = "999";
  }, 600);
});
"""


def _model() -> DataModel:
    model = DataModel("m")
    model.add_connector(MemoryConnector("mem", tables={"t": pd.DataFrame({"k": [1, 2], "amount": [10, 20]})}))
    model.add_table("t", connector="mem", source="t")
    model.add_dimension("dim_t", table_name="t", key_col="k", attributes=["k"])
    model.add_fact("fact_t", table_name="t", measures=["amount"], foreign_keys={})
    model.add_measure("amount", column="amount", agg="sum")
    model.connect()
    return model


def _build(tmp_path: Path, script: str) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    figure = ('<div class="tb-kpi" data-tb-figure="value" data-tb-binding="total" '
              'data-tb-cell="amount" id="kpi-{0}"><span class="tb-kpi-label">Amount {0}</span>'
              '<span class="tb-kpi-value"></span></div>')
    (pkg / "report.json").write_text(json.dumps({
        "name": "Integrity", "author": "t",
        "data": {"total": {"model": "m", "query": {"fact": "fact_t", "measures": ["amount"]}}},
    }), encoding="utf-8")
    (pkg / "template.html").write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Integrity</title></head><body>"
        + figure.format("a") + figure.format("b") + "</body></html>", encoding="utf-8")
    (pkg / "script.js").write_text(script, encoding="utf-8")
    out = tmp_path / "out.html"
    TemplatePackage(str(pkg)).render({"m": _model()}, str(out))
    return out


def _browser():
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(headless=True)
    except Exception as exc:
        pw.stop()
        pytest.skip(f"Chromium is not installed: {exc}")
    return pw, browser


def _drawer_rows(page) -> dict[str, str]:
    page.locator(".tb-receipt-btn").click()
    return {row.get_attribute("data-tb-receipt-fig"): row.inner_text()
            for row in page.locator(".tb-receipt-row").all()}


def test_the_receipt_says_which_figure_a_script_changed(tmp_path: Path) -> None:
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_default_timeout(60_000)
        page.goto(_build(tmp_path, _SCRIPT).as_uri())
        page.wait_for_function("() => document.querySelector('#kpi-a .tb-kpi-value').textContent === '999'")
        stamped = page.locator("#kpi-b .tb-kpi-value").inner_text()
        assert stamped == "30"
        page.wait_for_function("() => document.querySelector('#kpi-a').hasAttribute('data-tb-script-changed')")
        rows = _drawer_rows(page)
        assert "changed on the page by a custom script" in rows["kpi-a"]
        assert "custom script" not in rows["kpi-b"]
    finally:
        browser.close()
        pw.stop()


def test_a_report_with_no_script_is_not_flagged(tmp_path: Path) -> None:
    pw, browser = _browser()
    try:
        page = browser.new_page()
        page.set_default_timeout(60_000)
        page.goto(_build(tmp_path, "/* nothing */").as_uri())
        page.wait_for_function("() => document.documentElement.hasAttribute('data-tb-ready')")
        page.wait_for_timeout(1200)
        rows = _drawer_rows(page)
        assert rows and not any("custom script" in text for text in rows.values())
    finally:
        browser.close()
        pw.stop()
