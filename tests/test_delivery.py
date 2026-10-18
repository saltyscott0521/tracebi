"""Slack file delivery of a built report. Network is mocked; nothing here
reaches Slack."""

import json
import urllib.error
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from tracebi._delivery import slack_send_report

_TOKEN = "xoxb-secret"


class _Resp:
    def __init__(self, raw):
        self.status = 200
        self._raw = raw if isinstance(raw, bytes) else raw.encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _pages(tmp_path: Path):
    html = tmp_path / "weekly.html"
    manifest = tmp_path / "weekly.html.manifest.json"
    html.write_text(
        """
        <p><span data-tb-figure="value" id="val-region"
                 data-tb-cell="dim_region.region">North</span>
           led with
           <span data-tb-figure="value" id="val-revenue"
                 data-tb-cell="revenue">$1</span>.</p>
        <div class="tb-kpi" data-tb-figure="value" id="kpi-orders"
             data-tb-cell="orders">
          <span class="tb-kpi-label">Orders</span>
          <span class="tb-kpi-value">128</span>
          <span class="tb-kpi-context">count of orders</span>
        </div>
        <div class="tb-kpi" data-tb-figure="value" id="kpi-blank">
          <span class="tb-kpi-label">Blank</span>
          <span class="tb-kpi-value">—</span>
        </div>
        <div data-tb-figure="chart" id="chart-1">99999</div>
        """,
        encoding="utf-8")
    manifest.write_text(json.dumps({
        "report_name": "Weekly",
        "rendered_at": "2026-10-03T12:00:00+00:00",
        "figures": [
            {"id": "kpi-revenue", "kind": "value", "label": "Revenue",
             "formatted": "$10", "value": 10},
            {"id": "raw", "kind": "value", "label": "Raw", "value": 1234.5},
            {"id": "val-region", "kind": "value", "cell": "dim_region.region"},
            {"id": "kpi-orders", "kind": "value", "cell": "orders"},
            {"id": "kpi-blank", "kind": "value", "label": "Blank"},
            {"id": "missing", "kind": "value", "label": "Missing",
             "cell": "revenue"},
            {"id": "chart-1", "kind": "chart"},
            {"id": "sixth", "kind": "value", "label": "Sixth", "formatted": "6"},
        ],
    }), encoding="utf-8")
    return html, manifest


def _install(monkeypatch, *, fail=None):
    """Replace urlopen. *fail* is ``"api"`` or ``"upload"``."""
    calls = []

    def urlopen(req, timeout=None):
        calls.append(req)
        url = req.full_url
        if fail == "api" and url.endswith("/files.getUploadURLExternal"):
            return _Resp(json.dumps({"ok": False, "error": "invalid_auth"}))
        if url.endswith("/files.getUploadURLExternal"):
            name = parse_qs(req.data.decode())["filename"][0]
            fid = "Fhtml" if name.endswith(".html") else "Fman"
            return _Resp(json.dumps({
                "ok": True,
                "upload_url": f"https://files.example/upload/{fid}",
                "file_id": fid,
            }))
        if url.startswith("https://files.example/upload/"):
            if fail == "upload":
                raise urllib.error.HTTPError(url, 500, "no", None, None)
            return _Resp(b"OK")
        if url.endswith("/files.completeUploadExternal"):
            return _Resp(json.dumps({"ok": True, "files": []}))
        raise AssertionError(url)

    monkeypatch.setattr("tracebi._delivery.urllib.request.urlopen", urlopen)
    return calls


class TestSlackSendReport:


    def test_manifest_display_wins_over_the_page(self, tmp_path, monkeypatch):
        html = tmp_path / "r.html"
        man = tmp_path / "r.html.manifest.json"
        html.write_text(
            '<div class="tb-kpi" data-tb-figure="value" id="kpi">'
            '<span class="tb-kpi-label">Revenue</span>'
            '<span class="tb-kpi-value">WRONG</span></div>',
            encoding="utf-8")
        man.write_text(json.dumps({
            "report_name": "R", "rendered_at": "t",
            "figures": [{"id": "kpi", "kind": "value", "label": "Revenue",
                         "formatted": "$10"}],
        }), encoding="utf-8")
        _install(monkeypatch)
        text = slack_send_report(html, man, channel="C1", token=_TOKEN)
        assert "Revenue: $10" in text
        assert "WRONG" not in text
        assert "Verify:" not in text

    def test_a_slack_api_error_raises_without_the_token(
            self, tmp_path, monkeypatch):
        html, manifest = _pages(tmp_path)
        calls = _install(monkeypatch, fail="api")
        with pytest.raises(RuntimeError, match="invalid_auth"):
            slack_send_report(
                html, manifest, channel="C1", token=_TOKEN)
        assert _TOKEN not in "".join(
            str(c.full_url) + (c.data.decode() if c.data else "")
            for c in calls)
        assert not any(c.full_url.endswith("completeUploadExternal")
                       for c in calls)
