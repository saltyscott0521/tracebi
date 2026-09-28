"""The scheduled-report journey: a report.json ``schedule`` block, then
``tracebi schedule run`` does build → verify → email → record. Only the mail
server is faked (at smtplib, the network boundary); everything above it runs
for real, including the verify that must pass before anything is sent.
"""

import json
import smtplib

import pytest

from tests.e2e.conftest import run_cli


class _Outbox:
    sent: list = []

    def __init__(self, host, port, timeout=None, **_):
        self.host, self.port = host, port

    def starttls(self, context=None):
        raise smtplib.SMTPNotSupportedError     # a local relay with no TLS

    def send_message(self, msg):
        _Outbox.sent.append(msg)

    def quit(self):
        pass


@pytest.fixture
def scheduled(scaffolded, monkeypatch):
    _Outbox.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _Outbox)
    monkeypatch.setenv("TRACEBI_SMTP_URL", "smtp://localhost:2525")
    monkeypatch.setenv("TRACEBI_SMTP_FROM", "reports@example.com")
    decl = scaffolded / "reports" / "sample_dashboard" / "report.json"
    spec = json.loads(decl.read_text())
    spec["schedule"] = {"cron": "0 7 * * MON", "to": ["team@example.com"]}
    decl.write_text(json.dumps(spec))
    code, out = run_cli("run-transform", "sample_transform")
    assert code == 0, out
    return scaffolded


def _runs(proj):
    return [json.loads(line) for line in
            (proj / "output" / "schedule_runs.jsonl").read_text().splitlines()]


def test_a_scheduled_report_is_built_verified_emailed_and_recorded(scheduled):
    code, out = run_cli("schedule", "list")
    assert code == 0 and "sample_dashboard" in out and "0 7 * * MON" in out, out

    code, out = run_cli("schedule", "run", "sample_dashboard")
    assert code == 0, out
    [msg] = _Outbox.sent
    assert msg["To"] == "team@example.com"
    assert any(part.get_filename() == "sample_dashboard.html"
               for part in msg.iter_attachments())

    [record] = _runs(scheduled)
    assert record["verdict"] == "reproduces"
    assert record["recipients"] == ["team@example.com"]
    assert record["error"] is None


def test_sending_without_a_mail_server_says_what_to_set(scheduled, monkeypatch):
    monkeypatch.delenv("TRACEBI_SMTP_URL")
    code, out = run_cli("report", "send", "sample_dashboard", "--to", "team@example.com")
    assert code != 0
    assert "TRACEBI_SMTP_URL" in out
    assert _Outbox.sent == []
