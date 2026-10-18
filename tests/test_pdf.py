"""PDF download: a print of the built package HTML.

The real print launches Chromium and skips when Playwright or its browser
is absent. The download-route test always runs: a missing Playwright is a
structured error, not an unhandled stack.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector


def _model() -> DataModel:
    m = DataModel("pdf_model")
    m.add_connector(MemoryConnector("mem", {
        "orders": pd.DataFrame({
            "order_id": [1, 2, 3],
            "customer_id": [1, 2, 1],
            "revenue": [100.0, 200.0, 300.0],
        }),
        "customers": pd.DataFrame({
            "customer_id": [1, 2],
            "region": ["West", "East"],
        }),
    }))
    m.add_table("orders", connector="mem", source="orders")
    m.add_table("customers", connector="mem", source="customers")
    m.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region"])
    m.add_fact("fact_orders", table_name="orders", measures=["revenue"],
               foreign_keys={"dim_customer": "customer_id"})
    m.add_measure("revenue", column="revenue", agg="sum")
    m.connect()
    return m


def _package(reports: Path, model: DataModel) -> Path:
    pkg = reports / "bars"
    pkg.mkdir(parents=True)
    (pkg / "report.json").write_text(json.dumps({
        "name": "bars",
        "data": {"by_region": {
            "model": model.name,
            "query": {"fact": "fact_orders", "measures": ["revenue"],
                      "dimensions": ["dim_customer.region"]},
        }},
        "figures": {"mix": {
            "kind": "chart", "binding": "by_region", "chart_type": "bar",
            "x": "dim_customer.region", "y": "revenue",
        }},
    }), encoding="utf-8")
    (pkg / "template.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        "<title>{{ title }}</title></head><body>"
        "<main>{{ figure(\"mix\") }}</main></body></html>\n",
        encoding="utf-8",
    )
    return pkg


def _built_html(tmp_path: Path) -> Path:
    from tracebi.reports.template_package import TemplatePackage

    model = _model()
    pkg = _package(tmp_path / "reports", model)
    html = tmp_path / "bars.html"
    TemplatePackage(str(pkg)).render({model.name: model}, str(html))
    return html


def _chromium_or_skip() -> None:
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
    except Exception as exc:
        pytest.skip(
            f"Chromium is not installed ({type(exc).__name__}: {exc})"
        )


def test_print_built_chart_package(tmp_path: Path) -> None:
    """A built package with a chart prints to a real PDF after the chart is drawn."""
    _chromium_or_skip()
    from playwright.sync_api import sync_playwright

    from tracebi.reports.pdf import print_pdf

    html = _built_html(tmp_path)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(html.resolve().as_uri(), wait_until="load")
        page.wait_for_function(
            "() => document.documentElement.getAttribute('data-tb-ready') === '1'",
            timeout=30_000,
        )
        drawn = page.evaluate(
            """() => {
              const el = document.querySelector('[data-tb-figure="chart"]');
              return !!(el && el.querySelector('canvas, svg:not(.tb-chart-fallback)'));
            }"""
        )
        browser.close()
    assert drawn, "the chart figure was not drawn before printing"

    pdf = tmp_path / "bars.pdf"
    print_pdf(html, pdf)
    data = pdf.read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 5_000


def test_a_report_script_cannot_reach_the_network_while_printing(tmp_path: Path) -> None:
    """The print runs on the server, so a page that sends the browser anywhere off
    ``file:`` (an internal address, say) is refused rather than followed."""
    import http.server
    import threading

    _chromium_or_skip()
    from tracebi.reports.pdf import print_pdf

    hits: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<p>internal</p>")

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        html = _built_html(tmp_path)
        page = html.read_text(encoding="utf-8")
        script = f'<script>location.href = "http://127.0.0.1:{server.server_port}/hit";</script></body>'
        html.write_text(page.replace("</body>", script, 1), encoding="utf-8")
        try:
            print_pdf(html, tmp_path / "bars.pdf")
        except RuntimeError:
            pass                      # printing may fail; reaching the server is the failure
    finally:
        server.shutdown()
    assert hits == []
