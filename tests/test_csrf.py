"""The same-origin CSRF guard.

A browser cross-site POST carries an Origin and must be refused; a request with
no Origin (curl, the CLI) is not a browser CSRF and passes. Safe methods are
never blocked.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tracebi.web.api.csrf import CSRFMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(CSRFMiddleware)

    @app.post("/x")
    def _post():
        return {"ok": True}

    @app.get("/x")
    def _get():
        return {"ok": True}

    return TestClient(app)


def test_cross_origin_post_is_refused():
    r = _client().post("/x", headers={"Origin": "http://evil.example.com"})
    assert r.status_code == 403
    assert "CSRF" in r.json()["detail"]


def test_allowed_frontend_origin_passes():
    r = _client().post("/x", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200


def test_no_origin_passes():
    # curl / CLI / server-to-server send no Origin — not a browser CSRF.
    assert _client().post("/x").status_code == 200


def test_same_origin_passes():
    # TestClient's default Host is 'testserver'; a matching Origin is same-origin.
    r = _client().post("/x", headers={"Origin": "http://testserver"})
    assert r.status_code == 200


def test_safe_methods_are_never_blocked():
    r = _client().get("/x", headers={"Origin": "http://evil.example.com"})
    assert r.status_code == 200


def test_env_extends_the_allow_list(monkeypatch):
    monkeypatch.setenv("TRACEBI_ALLOWED_ORIGINS", "https://app.example.com")
    r = _client().post("/x", headers={"Origin": "https://app.example.com"})
    assert r.status_code == 200
