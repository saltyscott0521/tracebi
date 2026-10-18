"""GET /api/status: each check flips when its condition changes."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from tracebi.web.api.auth import _required_role
from tracebi.web.api.routers.status import collect_checks


def _by_name(checks: list[dict]) -> dict[str, dict]:
    return {check["name"]: check for check in checks}


def _body(tmp_path: Path, monkeypatch) -> dict:
    """A tiny app, so this file never imports ``tracebi.web.api.main``.

    ``TestPipelineRunEndpoint`` rebinds the registry before the pipelines
    router is first imported. Importing the real app here would bind that
    router first and the later test would 404.
    """
    import tracebi
    from fastapi import FastAPI

    from tracebi.web.api.routers.status import router

    monkeypatch.chdir(tmp_path)
    app = FastAPI(version=tracebi.__version__)
    app.include_router(router, prefix="/api")
    response = TestClient(app).get("/api/status")
    assert response.status_code == 200
    return response.json()


def test_route_returns_version_and_the_six_checks(tmp_path, monkeypatch):
    import tracebi

    body = _body(tmp_path, monkeypatch)
    assert body["version"] == tracebi.__version__
    assert set(_by_name(body["checks"])) == {
        "output_writable", "discovery", "models_loaded",
        "email_configured", "schedules_in_server", "auth",
    }


def test_email_check_flips_and_never_echoes_the_url(monkeypatch):
    secret = "smtp://leak-user:leak-pass@mail.example:2525"
    monkeypatch.delenv("TRACEBI_SMTP_URL", raising=False)
    monkeypatch.delenv("TRACEBI_SMTP_FROM", raising=False)
    off = _by_name(collect_checks())["email_configured"]
    assert off["ok"] is False
    assert off["detail"] == {
        "TRACEBI_SMTP_URL": False, "TRACEBI_SMTP_FROM": False,
    }

    monkeypatch.setenv("TRACEBI_SMTP_URL", secret)
    monkeypatch.setenv("TRACEBI_SMTP_FROM", "reports@example.com")
    on = _by_name(collect_checks())["email_configured"]
    assert on["ok"] is True
    assert on["detail"] == {
        "TRACEBI_SMTP_URL": True, "TRACEBI_SMTP_FROM": True,
    }
    dumped = json.dumps(collect_checks())
    assert secret not in dumped
    assert "mail.example" not in dumped
    assert "leak-user" not in dumped
    assert "leak-pass" not in dumped
    assert "reports@example.com" not in dumped


def test_auth_posture_flips_and_omits_the_password(monkeypatch):
    monkeypatch.delenv("TRACEBI_AUTH_PROXY_HEADER", raising=False)
    monkeypatch.delenv("TRACEBI_AUTH_USER", raising=False)
    monkeypatch.delenv("TRACEBI_AUTH_PASS", raising=False)
    off = _by_name(collect_checks())["auth"]["detail"]
    assert off.startswith("auth posture: off")

    monkeypatch.setenv("TRACEBI_AUTH_USER", "ada")
    monkeypatch.setenv("TRACEBI_AUTH_PASS", "super-secret-auth-pass")
    line = _by_name(collect_checks())["auth"]["detail"]
    assert "auth posture: Basic" in line
    assert "super-secret-auth-pass" not in line
    assert "super-secret-auth-pass" not in json.dumps(collect_checks())


def test_response_never_contains_the_smtp_url(tmp_path, monkeypatch):
    secret = "smtp://leak-user:leak-pass@mail.example:2525"
    monkeypatch.setenv("TRACEBI_SMTP_URL", secret)
    monkeypatch.setenv("TRACEBI_SMTP_FROM", "reports@example.com")
    body = _body(tmp_path, monkeypatch)
    dumped = json.dumps(body)
    assert secret not in dumped
    assert "mail.example" not in dumped
    assert os.environ["TRACEBI_SMTP_URL"] not in dumped
