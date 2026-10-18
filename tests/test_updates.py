"""
Clients learning about, and getting, a newer TraceBi (tracebi/_updates.py).

GitHub is never contacted: a local HTTP server stands in for the
releases/latest endpoint via TRACEBI_UPDATE_URL.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tracebi import _updates


@pytest.fixture
def feed(monkeypatch, tmp_path):
    """A fake releases/latest endpoint; set .release to change its answer."""
    state = {"release": {"tag_name": "v9.9.0", "html_url": "https://example.test/r/v9.9.0",
                         "published_at": "2026-09-25T00:00:00Z", "body": "- Faster\n- Better",
                         "assets": [{"name": "tracebi-9.9.0-py3-none-any.whl",
                                     "browser_download_url": "https://example.test/tracebi-9.9.0-py3-none-any.whl"}]},
             "hits": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["hits"] += 1
            body = json.dumps(state["release"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("TRACEBI_UPDATE_CHECK", "1")
    monkeypatch.setenv("TRACEBI_UPDATE_URL", f"http://127.0.0.1:{server.server_port}/latest")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(_updates, "get_version", lambda: "0.6.0")
    monkeypatch.setattr(_updates, "_last_attempt", 0.0)   # no throttle carried between tests
    yield state
    server.shutdown()


def test_a_newer_release_says_how_each_install_updates(feed, monkeypatch):
    for kind, needle in [("pip", 'pip install --upgrade "https://example.test/tracebi-9.9.0-py3-none-any.whl"'),
                         ("docker", "TRACEBI_VERSION=9.9.0 docker compose -f deploy/compose.yml pull"),
                         ("checkout", "git checkout v9.9.0")]:
        monkeypatch.setattr(_updates, "install_kind", lambda k=kind: k)
        st = _updates.status(force=True)
        assert st["available"] is True and st["latest"] == "9.9.0"
        assert needle in st["command"], (kind, st["command"])


def test_off_means_no_request(feed, monkeypatch):
    monkeypatch.setenv("TRACEBI_UPDATE_CHECK", "0")
    st = _updates.status(force=True)
    assert st["checked"] is False and st["latest"] is None and feed["hits"] == 0
