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


def test_a_failed_run_is_recorded_not_raised(tmp_path):
    rec = sched.run_schedule({"report": "missing", **SCHEDULE},
                             reports_dir=tmp_path / "reports",
                             output_dir=tmp_path / "output")
    assert rec["status"] == sched.FAILED
    assert "No report 'missing'" in rec["error"]
    assert sched.last_runs(tmp_path / "output")["missing"]["status"] == sched.FAILED


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
