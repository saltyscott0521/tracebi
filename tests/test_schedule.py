"""
Scheduled reports: a package's report.json "schedule" block, and
`tracebi schedule list | run | serve`.

The end-to-end cases run the scaffolded project in subprocesses (like
test_init_scaffold.py), so they share no registry state with the suite.
Delivery is stubbed inside the subprocess; nothing is emailed.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tracebi import cli
from tracebi import schedule as sched

pytest.importorskip("duckdb")

SCHEDULE = {"cron": "0 9 * * MON", "timezone": "America/New_York",
            "to": ["cfo@example.com"]}


# ── a scaffolded project ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    proj = tmp_path_factory.mktemp("sched") / "proj"
    assert cli.main(["init", str(proj)]) == 0
    out = subprocess.run([sys.executable, "transforms/sample_transform.py"],
                         capture_output=True, text=True, cwd=str(proj))
    assert out.returncode == 0, out.stderr
    return proj


@pytest.fixture
def scheduled(project, tmp_path):
    """A copy of the project whose sample report carries SCHEDULE."""
    proj = tmp_path / "proj"
    shutil.copytree(project, proj)
    rj = proj / "reports" / "sample_model" / "sample_dashboard" / "report.json"
    decl = json.loads(rj.read_text())
    decl["schedule"] = SCHEDULE
    rj.write_text(json.dumps(decl))
    return proj


def _runs(proj: Path) -> list[dict]:
    from tracebi.state import schedule_records
    return schedule_records(proj / "output")


@pytest.fixture(autouse=True)
def _no_real_retry_wait(monkeypatch):
    """Default retries must not call time.sleep. A test that asserts the
    delays replaces this with its own recorder. Slack delivery stays off
    unless a test sets it — a developer token must not reach the network."""
    monkeypatch.setattr(sched, "_sleep", lambda *_a, **_k: None)
    monkeypatch.delenv("TRACEBI_SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TRACEBI_SLACK_CHANNEL", raising=False)
    monkeypatch.delenv("TRACEBI_SLACK_WEBHOOK", raising=False)


def _enter(proj: Path, monkeypatch) -> None:
    """The build loads ``models/`` and the warehouse from the working directory."""
    monkeypatch.chdir(proj)


def _scheduled(proj: Path) -> dict:
    schedules, errors = sched.discover_schedules(proj / "reports")
    assert errors == []
    assert len(schedules) == 1
    return schedules[0]


class TestFailurePaths:
    """A failed run is a row in the log with a readable error, and nothing
    goes out that should not. These call ``run_schedule`` in-process: the
    CLI tests above spawn a child, and a child is invisible to coverage."""


    def test_a_schedule_cannot_force_a_bad_receipt(self, scheduled, monkeypatch):
        """``tracebi report send --force`` can send a failing receipt. A
        schedule block cannot: ``force`` is not a field, so the package is
        skipped, and a receipt that does not verify is refused with nothing
        sent."""
        rj = scheduled / "reports" / "sample_model" / "sample_dashboard" / "report.json"
        decl = json.loads(rj.read_text())
        decl["schedule"]["force"] = True
        rj.write_text(json.dumps(decl))
        schedules, errors = sched.discover_schedules(scheduled / "reports")
        assert schedules == []
        assert errors[0]["report"] == "sample_model/sample_dashboard"
        assert "unknown schedule field" in errors[0]["error"]
        assert "force" in errors[0]["error"]

        decl["schedule"].pop("force")
        rj.write_text(json.dumps(decl))
        _enter(scheduled, monkeypatch)
        sent = []
        monkeypatch.setattr(
            "tracebi._delivery.send_report",
            lambda *a, **k: sent.append(a) or ["nobody"],
        )
        monkeypatch.setattr(
            "tracebi.verify.verify_manifest",
            lambda *a, **k: {
                "verdict": "unexplained",
                "verdict_detail": "stub: did not reproduce",
                "exit_code": 1, "ok": False,
            },
        )
        rec = sched.run_schedule(
            _scheduled(scheduled),
            reports_dir=scheduled / "reports",
            output_dir=scheduled / "output",
        )
        assert sent == []
        assert rec["status"] == sched.REFUSED
        assert rec["error"] == "stub: did not reproduce"
        assert rec["recipients"] == []
        assert rec["attempts"] == 1


def _owner(proj: Path, **extra) -> dict:
    """The project's schedule, with *extra* written into the block."""
    rj = proj / "reports" / "sample_model" / "sample_dashboard" / "report.json"
    decl = json.loads(rj.read_text())
    decl["schedule"].update(extra)
    rj.write_text(json.dumps(decl))
    return _scheduled(proj)


def _break_build(proj: Path) -> None:
    rj = proj / "reports" / "sample_model" / "sample_dashboard" / "report.json"
    decl = json.loads(rj.read_text())
    binding = next(iter(decl["data"]))
    decl["data"][binding]["query"]["measures"] = ["not_a_measure"]
    rj.write_text(json.dumps(decl))


class TestOwnerAlerts:
    """An owner is emailed when a run ends failed, refused, or empty.
    The report's ``to`` list is not. No owner means no alert."""

    def _capture(self, monkeypatch):
        alerts = []
        sent = []
        monkeypatch.setattr(
            "tracebi._delivery.send_alert",
            lambda to, subject, body: alerts.append(
                {"to": to, "subject": subject, "body": body}),
        )
        monkeypatch.setattr(
            "tracebi._delivery.send_report",
            lambda *a, **k: sent.append(a) or ["nobody"],
        )
        return alerts, sent

    def test_a_failed_build_after_retries_alerts_the_owner(
            self, scheduled, monkeypatch):
        _enter(scheduled, monkeypatch)
        alerts, sent = self._capture(monkeypatch)
        _break_build(scheduled)
        block = _owner(scheduled, owner="ops@example.com")
        rec = sched.run_schedule(
            block, reports_dir=scheduled / "reports",
            output_dir=scheduled / "output",
        )
        assert sent == []
        assert rec["status"] == sched.FAILED
        assert rec["attempts"] == 3
        assert rec["alert"] == {
            "to": "ops@example.com", "sent": True, "error": None}
        [alert] = alerts
        assert alert["to"] == "ops@example.com"
        assert alert["subject"] == (
            "TraceBi: sample_model/sample_dashboard scheduled run failed")
        assert "not_a_measure" in alert["body"]
        assert "Attempts: 3" in alert["body"]
        assert "tracebi_runs (kind=schedule)" in alert["body"]


    def _refuse(self, monkeypatch):
        monkeypatch.setattr(
            "tracebi.verify.verify_manifest",
            lambda *a, **k: {
                "verdict": "unexplained",
                "verdict_detail": "stub: did not reproduce",
                "exit_code": 1, "ok": False,
            },
        )


class TestSlackFileDelivery:
    """A configured bot token and channel upload the built files. The
    webhook ping is a different path. Nothing here calls Slack."""

    def _stub(self, monkeypatch, slack):
        emailed = []
        monkeypatch.setattr(
            "tracebi._delivery.send_report",
            lambda *a, **k: emailed.append(a) or ["cfo@example.com"],
        )
        monkeypatch.setattr("tracebi._delivery.slack_send_report", slack)
        return emailed

    def _env(self, monkeypatch, channel="C0123"):
        monkeypatch.setenv("TRACEBI_SLACK_BOT_TOKEN", "xoxb-test")
        monkeypatch.setenv("TRACEBI_SLACK_CHANNEL", channel)


    def test_a_refused_receipt_is_not_uploaded(self, scheduled, monkeypatch):
        _enter(scheduled, monkeypatch)
        called = []
        self._stub(monkeypatch, lambda *a, **k: called.append(1))
        self._env(monkeypatch)
        monkeypatch.setattr(
            "tracebi.verify.verify_manifest",
            lambda *a, **k: {
                "verdict": "unexplained",
                "verdict_detail": "stub: did not reproduce",
                "exit_code": 1, "ok": False,
            },
        )
        rec = sched.run_schedule(
            _scheduled(scheduled),
            reports_dir=scheduled / "reports",
            output_dir=scheduled / "output",
        )
        assert called == []
        assert rec["status"] == sched.REFUSED
        assert "delivery" not in rec


def test_scheduler_fires_in_the_declared_timezone():
    pytest.importorskip("apscheduler")
    scheduler = sched.build_scheduler(
        [{"report": "weekly", **SCHEDULE}], job=lambda s: None, blocking=False)
    scheduler.start(paused=True)
    try:
        [job] = scheduler.get_jobs()
        assert job.id == "weekly"
        nxt = job.next_run_time
        assert (nxt.weekday(), nxt.hour, nxt.minute) == (0, 9, 0)
        assert str(nxt.tzinfo) == "America/New_York"
    finally:
        scheduler.shutdown(wait=False)


# The sample warehouse's regions, after the transform normalises them.
# Northeast is three orders; West is two. Midwest is in the filter so a
# missing recipient is recorded, and is not built.
_BURST = {
    "cron": "0 9 * * MON",
    "timezone": "America/New_York",
    "to": ["team@example.com"],
    "owner": "ops@example.com",
    "burst": {
        "filter": {"dim_region.region": ["Northeast", "West", "Midwest"]},
        "to": {
            "Northeast": ["ne@example.com"],
            "West": ["west@example.com"],
        },
    },
}


def _write_schedule(proj: Path, block: dict) -> None:
    rj = proj / "reports" / "sample_model" / "sample_dashboard" / "report.json"
    decl = json.loads(rj.read_text())
    decl["schedule"] = block
    rj.write_text(json.dumps(decl))


def _orders_in(html_path: Path) -> int:
    import csv as _csv
    import io
    import re
    html = html_path.read_text()
    block = re.search(
        r'<script[^>]*id="tracebi-data-kpis"[^>]*>(.*?)</script>',
        html, re.S).group(1)
    row = next(_csv.DictReader(io.StringIO(json.loads(block)["csv"])))
    return int(float(row["orders"]))


def _kpis_filters(manifest: dict) -> dict:
    for section in manifest.get("sections") or []:
        if section.get("id") != "kpis":
            continue
        lineage = section.get("dataset_lineage") or []
        return lineage[-1]["metadata"]["query_spec"]["filters"]
    raise AssertionError("manifest has no kpis section")


class TestBurst:


    def test_one_build_per_value_with_its_own_recipients(
            self, scheduled, monkeypatch):
        _enter(scheduled, monkeypatch)
        _write_schedule(scheduled, _BURST)
        sent = []

        def _send(html, _manifest, to, subject=None, verify_result=None):
            sent.append({"to": list(to), "html": Path(html).name})
            return list(to)

        monkeypatch.setattr("tracebi._delivery.send_report", _send)
        block = _scheduled(scheduled)
        rec = sched.run_schedule(
            block,
            reports_dir=scheduled / "reports",
            output_dir=scheduled / "output",
        )
        assert rec["status"] == sched.DELIVERED
        assert rec["verdict"] == "reproduces"
        assert rec["recipients"] == ["ne@example.com", "west@example.com"]
        assert "alert" not in rec
        by = {s["value"]: s for s in rec["slices"]}
        assert set(by) == {"Northeast", "West", "Midwest"}
        assert by["Northeast"]["status"] == sched.DELIVERED
        assert by["West"]["status"] == sched.DELIVERED
        assert by["Midwest"]["status"] == sched.SKIPPED
        assert by["Midwest"]["output"] is None
        assert by["Midwest"]["recipients"] == []
        out = scheduled / "output" / "sample_model"
        ne = out / "sample_dashboard--Northeast.html"
        west = out / "sample_dashboard--West.html"
        assert ne.is_file()
        assert (out / (ne.name + ".manifest.json")).is_file()
        assert west.is_file()
        assert (out / (west.name + ".manifest.json")).is_file()
        assert not (out / "sample_dashboard--Midwest.html").exists()
        assert not (out / "sample_dashboard.html").exists()
        assert sent == [
            {"to": ["ne@example.com"], "html": ne.name},
            {"to": ["west@example.com"], "html": west.name},
        ]
        assert _orders_in(ne) == 3
        assert _orders_in(west) == 2
        manifest = json.loads((out / (ne.name + ".manifest.json")).read_text())
        assert _kpis_filters(manifest) == {"dim_region.region": "Northeast"}
        assert _runs(scheduled) == [rec]
        assert "burst: dim_region.region" in sched.describe_schedule(block)
        assert "× 3" in sched.describe_schedule(block)
