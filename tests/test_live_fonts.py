"""Live-view fonts: on the server / dev preview, not in the offline file."""

from __future__ import annotations

import json

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tracebi import DataModel, MemoryConnector
from tracebi.reports.live_fonts import live_font_css, with_live_fonts
from tracebi.reports.template_package import TemplatePackage
import tracebi.model_registry as model_registry
from tracebi.web.api.routers import reports as reports_router
from tracebi.web.discovery import _register_template_package


def _model():
    df = pd.DataFrame({"region": ["NE"], "revenue": [100.0]})
    m = DataModel("live_font_model")
    m.add_connector(MemoryConnector("lf_mem", tables={"t": df}))
    m.add_table("t", connector="lf_mem", source="t")
    m.add_dimension("dim_r", table_name="t", key_col="region",
                    attributes=["region"])
    m.add_fact("f", table_name="t", measures=["revenue"], foreign_keys={})
    m.add_measure("total", column="revenue", agg="sum")
    m.connect()
    return m


def _package(tmp_path):
    pkg = tmp_path / "live_fonts_demo"
    pkg.mkdir()
    (pkg / "report.json").write_text(json.dumps({
        "name": "live_fonts_demo",
        "data": {
            "kpi": {"model": "live_font_model",
                    "query": {"fact": "f", "measures": ["total"]}},
        },
    }))
    (pkg / "template.html").write_text(
        "<html><head><title>live</title></head><body>"
        '<div id="fig-kpi" data-tb-figure="value" data-tb-binding="kpi" '
        'data-tb-cell="total"></div>'
        "</body></html>"
    )
    return pkg


def test_built_file_stays_on_system_ui(tmp_path):
    model = _model()
    out = tmp_path / "out.html"
    TemplatePackage(str(_package(tmp_path))).render(
        {"live_font_model": model}, str(out))
    html = out.read_text(encoding="utf-8")
    assert "system-ui" in html
    assert "tracebi live fonts" not in html
    assert "font/woff2;base64," not in html


def test_with_live_fonts_injects_faces_once():
    css = live_font_css()
    assert "Source Sans 3" in css and "Source Code Pro" in css
    assert "font/woff2;base64," in css
    page = "<html><head><title>x</title></head><body>hi</body></html>"
    once = with_live_fonts(page)
    twice = with_live_fonts(once)
    assert once.count("Source Sans 3") == twice.count("Source Sans 3")
    assert once.count("tracebi live fonts") == 1
    assert "Source Sans 3" in once and "--tb-font" in once


def test_view_endpoints_inject_download_does_not(tmp_path, monkeypatch):
    monkeypatch.setattr(reports_router, "_ARTIFACT_CACHE", {})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "output").mkdir()
    model_registry.register(_model())
    pkg = _package(tmp_path)
    assert _register_template_package(str(pkg), "live_fonts_demo")["status"] == \
        "registered"
    app = FastAPI()
    app.include_router(reports_router.router, prefix="/api")
    app.include_router(reports_router.share_router)
    client = TestClient(app)

    built = client.get("/api/reports/live_fonts_demo/built")
    assert built.status_code == 200, built.text
    assert "tracebi live fonts" in built.json()["html"]
    assert "font/woff2;base64," in built.json()["html"]

    share = client.get("/r/live_fonts_demo")
    assert share.status_code == 200
    assert "tracebi live fonts" in share.text

    download = client.get("/api/reports/live_fonts_demo/download?format=html")
    assert download.status_code == 200
    assert "tracebi live fonts" not in download.text
    assert "font/woff2;base64," not in download.text
    assert "system-ui" in download.text

    # On-disk artifact matches the download, not the live view.
    disk = (tmp_path / "output" / "live_fonts_demo.html").read_text(encoding="utf-8")
    assert "tracebi live fonts" not in disk
    assert disk == download.text
