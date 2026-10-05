"""The author's live loop: ``tracebi dev`` serving a report with its
workbench, a pin left in the workbench, the pin read and resolved from the
CLI (the agent's side of the protocol), and the review snapshot — which
verify refuses by name, because a draft is not a receipt.
"""

import http.server
import json
import socket
import threading
import time
import urllib.request

import pytest

from tests.e2e.conftest import run_cli


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def dev(scaffolded, monkeypatch):
    """`tracebi dev sample_model/sample_dashboard` on a spare port, shut down after."""
    from tracebi import _dev_server

    servers = []

    class _Tracked(http.server.ThreadingHTTPServer):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            servers.append(self)

    monkeypatch.setattr(http.server, "ThreadingHTTPServer", _Tracked)
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    port = _free_port()
    thread = threading.Thread(target=_dev_server.serve_dev, daemon=True, kwargs={
        "target": str(scaffolded / "reports" / "sample_model" / "sample_dashboard"),
        "port": port, "open_browser": False})
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/__status", timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    yield base
    for server in servers:
        server.shutdown()
    thread.join(timeout=5)    # serve_dev returns once shutdown; its watcher stops with it


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.read().decode()


def test_an_author_previews_pins_and_resolves(dev, scaffolded):
    preview = _get(dev + "/")
    assert "Sample Dashboard" in preview
    state = json.loads(_get(dev + "/__workbench/state.json"))
    assert {f["id"] for f in state["figures"]} >= {"kpi-revenue", "chart-by-region"}

    pin = urllib.request.Request(
        dev + "/__workbench/pin", method="POST",
        data=json.dumps({"id": "kpi-revenue", "note": "label this net"}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pin, timeout=5) as r:
        assert json.loads(r.read())["ok"] is True

    code, out = run_cli("report", "pins", "sample_model/sample_dashboard")
    assert code == 0 and "kpi-revenue" in out and "label this net" in out, out
    code, out = run_cli("report", "pins", "sample_model/sample_dashboard",
                        "--resolve", "kpi-revenue", "--note", "relabelled")
    assert code == 0, out
    code, out = run_cli("report", "pins", "sample_model/sample_dashboard")
    assert "no open pins" in out, out


def test_layout_recipes_scaffold_and_build(scaffolded):
    """`--layout` writes a named page, and the default stays the dashboard."""
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out

    code, out = run_cli("new-report", "Mosaic", "--layout", "mosaic")
    assert code != 0, out
    assert "mosaic" in out
    for name in ("brief", "dashboard", "tabbed"):
        assert name in out
    assert not (scaffolded / "reports" / "mosaic").exists()

    code, out = run_cli("new-report", "Weekly", "--reports-dir",
                        str(scaffolded / "plain"))
    assert code == 0, out
    code, out = run_cli("new-report", "Weekly", "--layout", "dashboard",
                        "--reports-dir", str(scaffolded / "dash"))
    assert code == 0, out
    plain = scaffolded / "plain" / "weekly"
    dash = scaffolded / "dash" / "weekly"
    assert (plain / "template.html").read_bytes() == (dash / "template.html").read_bytes()
    assert (plain / "report.json").read_bytes() == (dash / "report.json").read_bytes()
    assert not (dash / "style.css").exists()
    assert not (dash / "script.js").exists()

    code, out = run_cli("new-report", "Weekly Brief", "--layout", "brief")
    assert code == 0, out
    brief = (scaffolded / "reports" / "weekly_brief" / "template.html").read_text()
    assert "tb-cols-2" not in brief
    assert "tb-lede" in brief and "tb-grid" in brief and "tb-card" in brief
    code, out = run_cli("report", "build", "weekly_brief")
    assert code == 0, out

    code, out = run_cli("new-report", "Weekly", "--layout", "tabbed")
    assert code == 0, out
    tabbed = (scaffolded / "reports" / "weekly" / "template.html").read_text()
    assert "tb-tabs" in tabbed and "data-tb-tab" in tabbed
    assert 'data-tb-tab="Overview"' in tabbed and 'data-tb-tab="Detail"' in tabbed
    code, out = run_cli("report", "build", "weekly")
    assert code == 0, out
    built = (scaffolded / "output" / "weekly.html").read_text()
    assert "tb-tabs" in built and "data-tb-tab" in built

    code, out = run_cli("context")
    assert code == 0, out
    payload = json.loads(out)
    recipes = payload["presentation"]["layout"]["recipes"]
    assert set(recipes) == {"brief", "dashboard", "tabbed"}
    for name, text in recipes.items():
        assert f"--layout {name}" in text


def test_status_and_the_review_snapshot(scaffolded):
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    code, out = run_cli("report", "status", "sample_model/sample_dashboard")
    assert code == 0, out
    assert "8 figure(s) — 8 query-backed, 0 python-derived, 0 unverified" in out

    code, out = run_cli("report", "snapshot", "sample_model/sample_dashboard")
    assert code == 0, out
    snapshot = scaffolded / "output" / "sample_model" / "sample_dashboard.snapshot.html"
    assert snapshot.is_file()
    assert not (scaffolded / "output" / "sample_model" / "sample_dashboard.snapshot.html.manifest.json").exists()
    code, out = run_cli("verify", "--file", str(snapshot))
    assert code != 0, "a review snapshot is not a receipt"


def test_dev_app_opens_the_web_app_on_the_report_in_build_mode(scaffolded, monkeypatch):
    """`tracebi dev <name> --app`: one command, the app in dev mode, pointed at
    that report with Build already on (the agent's chat goes beside it)."""
    import os
    import urllib.parse

    seen = {}

    class _Timer:                       # the browser opens a moment after the server is up
        def __init__(self, delay, fn):
            seen["open"] = fn

        def start(self):
            pass

    monkeypatch.setattr("threading.Timer", _Timer)
    monkeypatch.setattr("webbrowser.open", lambda url: seen.setdefault("browser", url))
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: seen.update(app=app, **kw))
    # The command sets this in the process; recording it here makes pytest undo it.
    monkeypatch.setenv("TRACEBI_DEV_MODE", "0")

    code, out = run_cli("dev", "sample_model/sample_dashboard", "--app", "--port", "8765")
    assert code == 0, out
    assert os.environ["TRACEBI_DEV_MODE"] == "1", "Build mode needs the server in dev mode"
    assert seen["app"] == "tracebi.web.api.main:app" and seen["port"] == 8765
    assert seen["host"] == "127.0.0.1", "dev-state endpoints stay on loopback"
    url = "http://127.0.0.1:8765/reports?" + urllib.parse.urlencode(
        {"r": "sample_model/sample_dashboard", "build": "1"})
    assert url in out
    seen["open"]()
    assert seen["browser"] == url

    code, out = run_cli("dev", "nope", "--app")
    assert code == 1 and "not found" in out
