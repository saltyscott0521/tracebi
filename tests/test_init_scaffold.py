"""
The init scaffold is the product's first run — it must walk the three-phase
workflow end to end and finish with `tracebi verify` reading REPRODUCES.

These tests run the scaffolded project through subprocesses (the exact
commands the scaffolded README gives a new user), so they are hermetic: no
shared registry state with the rest of the suite.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tracebi import cli

pytest.importorskip("duckdb")


class TestInitScaffold:

    def test_mcp_config_prints_json_and_never_a_token(self, monkeypatch, capsys):
        monkeypatch.setenv("TRACEBI_MCP_TOKEN", "super-secret-token-xyz")
        assert cli.main(["mcp", "config", "--client", "cursor"]) == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["mcpServers"]["tracebi"] == {
            "command": "tracebi", "args": ["mcp"],
        }
        assert "super-secret-token-xyz" not in out

        assert cli.main([
            "mcp", "config", "--client", "claude-code",
            "--http", "http://127.0.0.1:8765/mcp",
        ]) == 0
        http_out = capsys.readouterr().out
        http = json.loads(http_out)
        server = http["mcpServers"]["tracebi"]
        assert server["type"] == "http"
        assert server["url"] == "http://127.0.0.1:8765/mcp"
        assert server["headers"]["Authorization"] == "Bearer ${TRACEBI_MCP_TOKEN}"
        assert "super-secret-token-xyz" not in http_out
        assert "command" not in server

        assert cli.main([
            "mcp", "config", "--client", "cursor",
            "--http", "http://127.0.0.1:8765/mcp",
        ]) == 0
        cursor_out = capsys.readouterr().out
        cursor = json.loads(cursor_out)
        assert cursor["mcpServers"]["tracebi"]["headers"]["Authorization"] == (
            "Bearer ${env:TRACEBI_MCP_TOKEN}"
        )
        assert "super-secret-token-xyz" not in cursor_out

        assert cli.main(["mcp", "config", "--client", "claude-desktop"]) == 0
        desktop = json.loads(capsys.readouterr().out)
        command = desktop["mcpServers"]["tracebi"]["command"]
        assert Path(command).is_absolute()

        assert cli.main([
            "mcp", "config", "--client", "claude-desktop",
            "--http", "http://127.0.0.1:8765/mcp",
        ]) == 1
        refused = capsys.readouterr()
        assert refused.out == ""
        assert "{" not in refused.err
        with pytest.raises(json.JSONDecodeError):
            json.loads(refused.err)
        assert refused.err.strip() == (
            "Add the URL as a custom connector in Claude Desktop "
            "(Settings → Connectors)."
        )
        assert "super-secret-token-xyz" not in refused.err


class TestReportSend:
    """`tracebi report send` — scheduled-delivery v1: distribution with the
    receipt attached, gated by verification.

    The honesty rule under test: distribution never outruns verification.
    A receipt that does not verify is refused; --force pastes the failing
    verdict INTO the body, so the red flag travels WITH the report — never
    silently. No test opens a socket: SMTP is faked at the smtplib seam or
    send_report is captured at the CLI seam.
    """

    _PASSING = {
        "verdict": "reproduces",
        "verdict_detail": "REPRODUCES — every checked section matches "
                          "the manifest",
        "exit_code": 0, "ok": True, "figures": [{"id": "kpi_total"}],
    }
    _FAILING = {
        "verdict": "not_reproduced",
        "verdict_detail": "NOT REPRODUCED — section(s) could not be shown "
                          "to reproduce; explain before anyone reads the "
                          "number",
        "exit_code": 1, "ok": False, "figures": [{"id": "kpi_total"}],
    }

    @pytest.fixture(scope="class")
    def proj(self, tmp_path_factory):
        """One scaffolded project with a sunk warehouse, shared by the
        class — each test rebuilds the report in-process (that is what
        `send` does) but the transform runs once."""
        proj = tmp_path_factory.mktemp("send") / "proj"
        assert cli.main(["init", str(proj)]) == 0
        out = subprocess.run(
            [sys.executable, "transforms/sample_transform.py"],
            capture_output=True, text=True, cwd=str(proj),
        )
        assert out.returncode == 0, out.stderr
        return proj

    def _env(self, monkeypatch, proj):
        monkeypatch.chdir(proj)
        monkeypatch.setenv("TRACEBI_SMTP_URL", "smtp://mail.example.com:2525")
        monkeypatch.setenv("TRACEBI_SMTP_FROM", "reports@example.com")
        monkeypatch.delenv("TRACEBI_SLACK_WEBHOOK", raising=False)

    def _fake_smtp(self, monkeypatch):
        """Capture the EmailMessage at the smtplib seam — no sockets."""
        import tracebi._delivery as delivery
        sent = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout=None, context=None):
                sent["host"], sent["port"] = host, port
                sent["ssl_context"] = context   # smtps must pass a verified ctx

            def starttls(self, context=None):
                sent["starttls_context"] = context

            def login(self, user, password):
                sent["login"] = (user, password)

            def send_message(self, msg):
                sent["msg"] = msg

            def quit(self):
                pass

        monkeypatch.setattr(delivery.smtplib, "SMTP", FakeSMTP)
        monkeypatch.setattr(delivery.smtplib, "SMTP_SSL", FakeSMTP)
        return sent

    def test_send_refuses_when_verify_fails(self, proj, monkeypatch, capsys):
        import tracebi._delivery as delivery
        import tracebi.verify as verify_mod
        self._env(monkeypatch, proj)
        monkeypatch.setattr(verify_mod, "verify_manifest",
                            lambda *a, **k: dict(self._FAILING))
        attempted = []
        monkeypatch.setattr(delivery, "send_report",
                            lambda *a, **k: attempted.append(a))
        rc = cli.main(["report", "send", "sample_model/sample_dashboard",
                       "--to", "a@example.com"])
        assert rc == 1
        assert not attempted, "a failing receipt must never be sent"
        assert "NOT REPRODUCED" in capsys.readouterr().err


    def test_starttls_uses_a_verified_context(self, proj, monkeypatch):
        """STARTTLS must pass an SSL context so the server certificate is
        verified — an unverified upgrade lets a MITM capture credentials."""
        import ssl

        import tracebi.verify as verify_mod
        self._env(monkeypatch, proj)
        monkeypatch.setattr(verify_mod, "verify_manifest",
                            lambda *a, **k: dict(self._PASSING))
        sent = self._fake_smtp(monkeypatch)
        cli.main(["report", "send", "sample_model/sample_dashboard", "--to", "a@example.com"])
        assert isinstance(sent.get("starttls_context"), ssl.SSLContext)

    def test_refuses_cleartext_credentials_when_no_starttls(self, tmp_path,
                                                            monkeypatch):
        """Server offers no STARTTLS and credentials are set: refuse to send
        them over an unencrypted link rather than leaking them."""
        import smtplib

        import tracebi._delivery as delivery
        from tracebi._delivery import send_report

        class NoTLS:
            def __init__(self, host, port, timeout=None, context=None):
                pass

            def starttls(self, context=None):
                raise smtplib.SMTPNotSupportedError("no starttls")

            def login(self, *a):
                raise AssertionError("credentials must not be sent in cleartext")

            def send_message(self, m):
                raise AssertionError("must not send after refusing")

            def quit(self):
                pass

        monkeypatch.setattr(delivery.smtplib, "SMTP", NoTLS)
        monkeypatch.setenv("TRACEBI_SMTP_URL",
                           "smtp://user:pass@mail.example.com:2525")
        monkeypatch.setenv("TRACEBI_SMTP_FROM", "reports@example.com")
        html = tmp_path / "r.html"
        html.write_text("<p>x</p>")
        man = tmp_path / "r.html.manifest.json"
        man.write_text("{}")
        with pytest.raises(RuntimeError, match="STARTTLS"):
            send_report(html, man, ["a@example.com"])
