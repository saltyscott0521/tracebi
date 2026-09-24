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
import textwrap
from pathlib import Path

import pytest

from tracebi import cli
from tracebi import schedule as sched

pytest.importorskip("duckdb")

SCHEDULE = {"cron": "0 9 * * MON", "timezone": "America/New_York",
            "to": ["cfo@example.com"]}


# ── the block ───────────────────────────────────────────────────────────────

class TestParseScheduleBlock:
    def test_normalizes(self):
        got = sched.parse_schedule_block(
            {"cron": "0  9 * *   MON", "to": "a@x.com, b@x.com"}, path="r")
        assert got == {"cron": "0 9 * * MON", "timezone": None,
                       "to": ["a@x.com", "b@x.com"],
                       "refresh": {"transforms": [], "pipelines": []}}

    def test_recipients_are_optional(self):
        assert sched.parse_schedule_block({"cron": "0 9 * * *"}, path="r")["to"] == []

    @pytest.mark.parametrize("raw, fragment", [
        ("0 9 * * MON", "must be an object"),
        ({"cron": "0 9 * *"}, "five-field cron"),
        ({"cron": "0 9 * * MON", "every": "day"}, "unknown schedule field"),
        ({"cron": "0 9 * * MON", "to": ["not-an-address"]}, "email addresses"),
        ({"cron": "0 9 * * MON", "timezone": "Mars/Olympus"}, "unknown schedule timezone"),
        ({"cron": "0 9 * * MON", "refresh": ["t"]}, "'refresh' must be an object"),
        ({"cron": "0 9 * * MON", "refresh": {"models": ["m"]}}, "'refresh' must be an object"),
    ])
    def test_refuses(self, raw, fragment):
        with pytest.raises(ValueError, match=fragment):
            sched.parse_schedule_block(raw, path="reports/x/report.json")


# ── a scaffolded project ────────────────────────────────────────────────────

def _run(args, cwd, driver: str = ""):
    """`tracebi <args>` in *cwd*; *driver* is Python run first (stubs)."""
    code = textwrap.dedent(driver) + (
        "\nfrom tracebi import cli\n"
        f"raise SystemExit(cli.main({list(args)!r}))\n")
    return subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, cwd=str(cwd))


# Records each send in sent.json instead of emailing.
_STUB_SEND = """
import json, tracebi._delivery as d
def _send(html, manifest, to, subject=None, verify_result=None):
    json.dump({"to": list(to), "html": str(html)}, open("sent.json", "w"))
    return list(to)
d.send_report = _send
"""

_FAIL_VERIFY = """
import tracebi.verify as v
v.verify_manifest = lambda manifest, models, **k: {
    "verdict": "unexplained", "verdict_detail": "stub: did not reproduce",
    "exit_code": 1, "ok": False}
"""


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
    rj = proj / "reports" / "sample_dashboard" / "report.json"
    decl = json.loads(rj.read_text())
    decl["schedule"] = SCHEDULE
    rj.write_text(json.dumps(decl))
    return proj


def _runs(proj: Path) -> list[dict]:
    log = proj / "output" / sched.RUN_LOG
    return [json.loads(line) for line in log.read_text().splitlines()]


class TestDiscovery:
    def test_finds_scheduled_packages_only(self, scheduled):
        schedules, errors = sched.discover_schedules(scheduled / "reports")
        assert errors == []
        assert schedules == [{"report": "sample_dashboard", **SCHEDULE,
                              "refresh": {"transforms": [], "pipelines": []}}]

    def test_unscheduled_project_has_none(self, project):
        assert sched.discover_schedules(project / "reports") == ([], [])

    def test_broken_block_is_an_error_entry_not_a_crash(self, scheduled):
        rj = scheduled / "reports" / "sample_dashboard" / "report.json"
        decl = json.loads(rj.read_text())
        decl["schedule"] = {"cron": "weekly"}
        rj.write_text(json.dumps(decl))
        schedules, errors = sched.discover_schedules(scheduled / "reports")
        assert schedules == []
        assert errors[0]["report"] == "sample_dashboard"
        assert "five-field cron" in errors[0]["error"]


class TestScheduleRun:
    def test_list_names_the_schedule(self, scheduled):
        out = _run(["schedule", "list"], scheduled)
        assert out.returncode == 0, out.stderr
        assert "sample_dashboard" in out.stdout
        assert "America/New_York" in out.stdout
        assert "cfo@example.com" in out.stdout

    def test_no_send_builds_and_records(self, scheduled):
        out = _run(["schedule", "run", "sample_dashboard", "--no-send"],
                   scheduled, _STUB_SEND)
        assert out.returncode == 0, out.stderr
        assert not (scheduled / "sent.json").exists()
        assert (scheduled / "output" / "sample_dashboard.html").is_file()
        [rec] = _runs(scheduled)
        assert rec["status"] == sched.BUILT
        assert rec["verdict"] == "reproduces"
        assert rec["actor_role"] == "cli"

    def test_run_delivers_to_the_declared_recipients(self, scheduled):
        out = _run(["schedule", "run", "sample_dashboard"],
                   scheduled, _STUB_SEND)
        assert out.returncode == 0, out.stderr
        sent = json.loads((scheduled / "sent.json").read_text())
        assert sent["to"] == ["cfo@example.com"]
        [rec] = _runs(scheduled)
        assert rec["status"] == sched.DELIVERED
        assert rec["recipients"] == ["cfo@example.com"]

    def test_a_receipt_that_does_not_verify_is_refused_and_not_sent(self, scheduled):
        out = _run(["schedule", "run", "sample_dashboard"],
                   scheduled, _STUB_SEND + _FAIL_VERIFY)
        assert out.returncode == 1
        assert not (scheduled / "sent.json").exists()
        [rec] = _runs(scheduled)
        assert rec["status"] == sched.REFUSED
        assert rec["recipients"] == []

    def test_run_needs_a_schedule_block(self, project):
        out = _run(["schedule", "run", "sample_dashboard"], project)
        assert out.returncode == 1
        assert "no schedule block" in out.stderr

    def test_last_run_shows_in_list(self, scheduled):
        _run(["schedule", "run", "sample_dashboard", "--no-send"], scheduled)
        out = _run(["schedule", "list", "--json"], scheduled)
        [entry] = json.loads(out.stdout)
        assert entry["last_run"]["status"] == sched.BUILT


def _kpi_orders(proj: Path) -> int:
    import csv as _csv
    import io
    import re
    html = (proj / "output" / "sample_dashboard.html").read_text()
    block = re.search(r'<script[^>]*id="tracebi-data-kpis"[^>]*>(.*?)</script>',
                      html, re.S).group(1)
    row = next(_csv.DictReader(io.StringIO(json.loads(block)["csv"])))
    return int(float(row["orders"]))


class TestRefresh:
    """A schedule's refresh steps run before the build, so the report shows
    fresh data; a failed step stops the run before anything is built."""

    def _with_refresh(self, proj, transforms):
        rj = proj / "reports" / "sample_dashboard" / "report.json"
        decl = json.loads(rj.read_text())
        decl["schedule"]["refresh"] = {"transforms": transforms}
        rj.write_text(json.dumps(decl))

    def test_refresh_runs_the_transform_before_the_build(self, scheduled):
        # Baseline: a build before any new data.
        assert _run(["report", "build", "sample_dashboard"], scheduled).returncode == 0
        before = _kpi_orders(scheduled)
        # One new order lands in the raw input after the warehouse was built.
        csv = scheduled / "inputs" / "orders.csv"
        lines = csv.read_text().splitlines()
        new_row = "9999" + lines[1][lines[1].index(","):]
        csv.write_text("\n".join(lines + [new_row]) + "\n")

        self._with_refresh(scheduled, ["sample_transform"])
        out = _run(["schedule", "run", "sample_dashboard", "--no-send"], scheduled)
        assert out.returncode == 0, out.stderr
        [rec] = _runs(scheduled)
        assert rec["status"] == sched.BUILT
        assert [s["step"] for s in rec["refresh"]] == ["transform:sample_transform"]
        assert rec["refresh"][0]["ok"] is True
        # The built report's embedded, fingerprinted KPI data counts it.
        assert _kpi_orders(scheduled) == before + 1

    def test_a_failed_refresh_builds_and_sends_nothing(self, scheduled):
        self._with_refresh(scheduled, ["no_such_transform"])
        out = _run(["schedule", "run", "sample_dashboard"], scheduled, _STUB_SEND)
        assert out.returncode == 1
        [rec] = _runs(scheduled)
        assert rec["status"] == sched.FAILED
        assert "refresh transform 'no_such_transform' failed" in rec["error"]
        assert not (scheduled / "output" / "sample_dashboard.html").exists()
        assert not (scheduled / "sent.json").exists()


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

    def test_a_broken_build_is_recorded_and_not_sent(self, scheduled, monkeypatch):
        _enter(scheduled, monkeypatch)
        sent = []
        monkeypatch.setattr(
            "tracebi._delivery.send_report",
            lambda *a, **k: sent.append(a) or ["nobody"],
        )
        rj = scheduled / "reports" / "sample_dashboard" / "report.json"
        decl = json.loads(rj.read_text())
        binding = next(iter(decl["data"]))
        decl["data"][binding]["query"]["measures"] = ["not_a_measure"]
        rj.write_text(json.dumps(decl))

        rec = sched.run_schedule(
            _scheduled(scheduled),
            reports_dir=scheduled / "reports",
            output_dir=scheduled / "output",
        )
        assert sent == []
        assert rec["status"] == sched.FAILED
        assert rec["recipients"] == []
        assert "not_a_measure" in rec["error"]
        assert _runs(scheduled) == [rec]

    def test_a_failed_refresh_is_recorded_in_process(self, scheduled, monkeypatch):
        sent = []
        monkeypatch.setattr(
            "tracebi._delivery.send_report",
            lambda *a, **k: sent.append(a) or ["nobody"],
        )
        block = _scheduled(scheduled)
        block["refresh"] = {"transforms": ["no_such_transform"], "pipelines": []}
        rec = sched.run_schedule(
            block, reports_dir=scheduled / "reports",
            output_dir=scheduled / "output",
        )
        assert sent == []
        assert rec["status"] == sched.FAILED
        assert "refresh transform 'no_such_transform' failed" in rec["error"]
        assert rec["refresh"][0]["ok"] is False
        assert not (scheduled / "output" / "sample_dashboard.html").exists()

    def test_smtp_failure_is_recorded_and_not_delivered(self, scheduled, monkeypatch):
        _enter(scheduled, monkeypatch)

        def _boom(*args, **kwargs):
            raise RuntimeError("smtp refused the message")

        monkeypatch.setattr("tracebi._delivery.send_report", _boom)
        rec = sched.run_schedule(
            _scheduled(scheduled),
            reports_dir=scheduled / "reports",
            output_dir=scheduled / "output",
        )
        assert rec["status"] == sched.FAILED
        assert rec["recipients"] == []
        assert rec["error"] == "RuntimeError: smtp refused the message"
        assert _runs(scheduled)[-1]["error"] == rec["error"]

    def test_a_schedule_cannot_force_a_bad_receipt(self, scheduled, monkeypatch):
        """``tracebi report send --force`` can send a failing receipt. A
        schedule block cannot: ``force`` is not a field, so the package is
        skipped, and a receipt that does not verify is refused with nothing
        sent."""
        rj = scheduled / "reports" / "sample_dashboard" / "report.json"
        decl = json.loads(rj.read_text())
        decl["schedule"]["force"] = True
        rj.write_text(json.dumps(decl))
        schedules, errors = sched.discover_schedules(scheduled / "reports")
        assert schedules == []
        assert errors[0]["report"] == "sample_dashboard"
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

    def test_make_job_records_the_scheduler_actor(self, scheduled, monkeypatch):
        _enter(scheduled, monkeypatch)
        job = sched.make_job(scheduled / "reports", scheduled / "output")
        block = _scheduled(scheduled)
        block["to"] = []
        rec = job(block)
        assert rec["status"] == sched.BUILT
        assert rec["actor"] == "scheduler"
        assert rec["recipients"] == []


def test_last_runs_skips_a_broken_line(tmp_path):
    log = tmp_path / sched.RUN_LOG
    log.write_text('not json\n{"report": "weekly", "status": "failed"}\n',
                   encoding="utf-8")
    last = sched.last_runs(tmp_path)["weekly"]
    assert last["status"] == "failed"
    assert "last: failed" in sched.describe_schedule(
        {"report": "weekly", "cron": "0 9 * * MON", "to": [], "timezone": None},
        last,
    )
    assert sched.last_runs(tmp_path / "missing") == {}


def test_discover_on_a_missing_directory_is_empty(tmp_path):
    assert sched.discover_schedules(tmp_path / "nope") == ([], [])


def test_an_empty_timezone_is_refused():
    with pytest.raises(ValueError, match="IANA"):
        sched.parse_schedule_block(
            {"cron": "0 9 * * MON", "timezone": ""}, path="r")


def test_in_server_logs_a_skipped_package_and_starts_nothing(
        tmp_path, monkeypatch, caplog):
    import logging

    pkg = tmp_path / "reports" / "weekly"
    pkg.mkdir(parents=True)
    (pkg / "template.html").write_text("<p></p>", encoding="utf-8")
    (pkg / "report.json").write_text('{"schedule": {"cron": "nope"}}',
                                     encoding="utf-8")
    monkeypatch.setenv("TRACEBI_SCHEDULES_IN_SERVER", "1")
    monkeypatch.setenv("TRACEBI_REPORTS_DIR", str(tmp_path / "reports"))
    caplog.set_level(logging.INFO, logger="tracebi.schedule")
    assert sched.start_server_scheduler() is None
    assert "skipped weekly" in caplog.text
    assert "no schedules" in caplog.text


def test_a_failed_run_is_recorded_not_raised(tmp_path):
    rec = sched.run_schedule({"report": "missing", **SCHEDULE},
                             reports_dir=tmp_path / "reports",
                             output_dir=tmp_path / "output")
    assert rec["status"] == sched.FAILED
    assert "No report 'missing'" in rec["error"]
    assert sched.last_runs(tmp_path / "output")["missing"]["status"] == sched.FAILED


def _weekly_package(root: Path) -> None:
    pkg = root / "reports" / "weekly"
    pkg.mkdir(parents=True)
    (pkg / "template.html").write_text(
        "<!DOCTYPE html><html><body><p>weekly</p></body></html>",
        encoding="utf-8")
    (pkg / "report.json").write_text(json.dumps({
        "name": "weekly",
        "data": {"totals": {"model": "m", "query": {
            "fact": "f", "measures": ["n"]}}},
        "schedule": {"cron": "0 9 * * MON", "to": ["a@example.com"]},
    }), encoding="utf-8")


def _schedule_app():
    """The real schedule lifespan on a tiny app.

    Importing ``tracebi.web.api.main`` binds the routers to the global
    registry and breaks ``test_phase5.py`` when this file runs first.
    """
    from fastapi import FastAPI

    return FastAPI(lifespan=sched.server_lifespan)


def test_in_server_schedules_start_with_the_switch(tmp_path, monkeypatch, caplog):
    """Startup registers the package's job. It does not wait for cron."""
    import inspect
    import logging

    from fastapi.testclient import TestClient

    _weekly_package(tmp_path)
    monkeypatch.setenv("TRACEBI_SCHEDULES_IN_SERVER", "1")
    monkeypatch.setenv("TRACEBI_REPORTS_DIR", str(tmp_path / "reports"))
    # The MCP confinement root must not move the schedule log.
    monkeypatch.setenv("TRACEBI_OUTPUT_ROOT", str(tmp_path / "not-the-schedule-log"))
    app = _schedule_app()

    caplog.set_level(logging.INFO, logger="tracebi.schedule")
    with TestClient(app):
        scheduler = app.state.scheduler
        assert scheduler.running
        [job] = scheduler.get_jobs()
        assert job.id == "weekly"
        assert inspect.getclosurevars(job.func).nonlocals["output_dir"] == "output"
    assert scheduler.running is False
    text = caplog.text
    assert "weekly" in text
    assert "one process" in text


def test_in_server_schedules_stay_off_by_default(monkeypatch):
    monkeypatch.delenv("TRACEBI_SCHEDULES_IN_SERVER", raising=False)
    assert sched.start_server_scheduler() is None


def test_in_server_schedules_need_apscheduler(tmp_path, monkeypatch):
    import sys

    _weekly_package(tmp_path)
    monkeypatch.setenv("TRACEBI_SCHEDULES_IN_SERVER", "1")
    monkeypatch.setenv("TRACEBI_REPORTS_DIR", str(tmp_path / "reports"))
    for name in ("apscheduler", "apscheduler.schedulers",
                 "apscheduler.schedulers.background",
                 "apscheduler.schedulers.blocking",
                 "apscheduler.triggers", "apscheduler.triggers.cron"):
        monkeypatch.setitem(sys.modules, name, None)

    with pytest.raises(ImportError, match=r"tracebi\[pipeline\]"):
        sched.start_server_scheduler()


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
