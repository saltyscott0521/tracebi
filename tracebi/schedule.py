"""
Scheduled reports — a report that runs and delivers itself.

A package opts in with a ``schedule`` block in its ``report.json``::

    "schedule": {
      "cron": "0 9 * * MON",
      "timezone": "America/New_York",
      "to": ["cfo@example.com", "ops@example.com"]
    }

``cron`` is required (five fields). ``timezone`` is an IANA name, default
UTC. ``to`` is optional: without it a run rebuilds the artifact and records
the run, and delivers nothing. ``refresh`` is optional::

    "refresh": {"transforms": ["holdings_transform"], "pipelines": ["sales_etl"]}

names what to run BEFORE the build so the report shows fresh data: each
transform (``tracebi run-transform``), then each pipeline (``tracebi
run-pipeline``), in order, each in a fresh process. A step that fails —
including a sink contract that refuses the new data — fails the run, and
nothing is built or sent.

The schedule lives in the repo beside the bindings, so a reviewer approves
*when* and *to whom* in the same pull request as *what*.

One run is: refresh → build → verify → deliver → record. It is ``tracebi report
send`` with the recipients read from the package, and the same rule —
distribution never outruns verification: a receipt that does not verify is
recorded as ``refused`` and nothing is sent. Every run appends one JSON line
to ``output/schedule_runs.jsonl``.

``tracebi schedule serve`` runs every schedule in one foreground process
(needs ``tracebi[pipeline]`` for APScheduler). Any external scheduler — cron,
a Kubernetes CronJob, CI — can instead call ``tracebi schedule run <name>``.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Union

#: Run outcomes. ``delivered`` and ``built`` are successes.
DELIVERED = "delivered"   # built, verified, sent
BUILT = "built"           # built and verified; no recipients, or --no-send
REFUSED = "refused"       # built; the receipt did not verify, nothing sent
FAILED = "failed"         # a refresh step failed, or the build, verify or send raised

RUN_LOG = "schedule_runs.jsonl"

_ALLOWED_KEYS = {"cron", "timezone", "to", "refresh"}
_REFRESH_KINDS = ("transforms", "pipelines")


def parse_schedule_block(raw, *, path: str) -> dict:
    """Validate a package's ``schedule`` block; return it normalized.

    Returns ``{"cron": str, "timezone": str | None, "to": list[str],
    "refresh": {"transforms": list[str], "pipelines": list[str]}}``.
    Raises ``ValueError`` naming *path* and the fix.
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"{path}: 'schedule' must be an object like "
            f"{{\"cron\": \"0 9 * * MON\", \"to\": [\"a@example.com\"]}}."
        )
    unknown = set(raw) - _ALLOWED_KEYS
    if unknown:
        raise ValueError(
            f"{path}: unknown schedule field(s): {sorted(unknown)}. "
            f"Allowed: {sorted(_ALLOWED_KEYS)}."
        )

    cron = raw.get("cron")
    if not isinstance(cron, str) or len(cron.split()) != 5:
        raise ValueError(
            f"{path}: schedule 'cron' must be a five-field cron expression "
            f"(minute hour day month day_of_week), e.g. \"0 9 * * MON\"; "
            f"got {cron!r}."
        )

    tz = raw.get("timezone")
    if tz is not None:
        if not isinstance(tz, str) or not tz:
            raise ValueError(f"{path}: schedule 'timezone' must be an IANA "
                             f"name such as \"Europe/London\".")
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(
                f"{path}: unknown schedule timezone {tz!r}. Use an IANA name "
                f"such as \"America/New_York\" (on a system with no time zone "
                f"database, `pip install tzdata`)."
            ) from None

    to = raw.get("to", [])
    if isinstance(to, str):
        to = [a.strip() for a in to.split(",") if a.strip()]
    if not isinstance(to, list) or any(
            not isinstance(a, str) or "@" not in a for a in to):
        raise ValueError(
            f"{path}: schedule 'to' must be a list of email addresses."
        )
    refresh = raw.get("refresh", {})
    if not isinstance(refresh, dict) or set(refresh) - set(_REFRESH_KINDS) or any(
            not isinstance(refresh.get(k, []), list)
            or not all(isinstance(n, str) and n for n in refresh.get(k, []))
            for k in _REFRESH_KINDS):
        raise ValueError(
            f"{path}: schedule 'refresh' must be an object like "
            f"{{\"transforms\": [\"holdings_transform\"], "
            f"\"pipelines\": [\"sales_etl\"]}}.")
    return {"cron": " ".join(cron.split()), "timezone": tz, "to": list(to),
            "refresh": {k: list(refresh.get(k, [])) for k in _REFRESH_KINDS}}


def discover_schedules(reports_dir: Union[str, Path]) -> tuple[list[dict], list[dict]]:
    """Every scheduled package under *reports_dir*.

    Returns ``(schedules, errors)``. Each schedule is the normalized block
    plus ``"report"`` (the package's path below *reports_dir*, e.g.
    ``finance/weekly``). A package that fails to
    load is an error entry ``{"report", "error"}``, not an exception — one
    broken package must not stop the others from running. Specs
    (``reports/<name>.json``) are not scheduled; migrate them to a package
    with ``tracebi migrate spec``.
    """
    from tracebi.reports.template_package import TemplatePackage

    reports_dir = Path(reports_dir)
    schedules: list[dict] = []
    errors: list[dict] = []
    if not reports_dir.is_dir():
        return schedules, errors
    for pkg in _package_dirs(reports_dir):
        name = pkg.relative_to(reports_dir).as_posix()   # "finance/weekly"
        try:
            package = TemplatePackage(str(pkg))
        except Exception as exc:  # noqa: BLE001 — report it, keep going
            errors.append({"report": name,
                           "error": f"{type(exc).__name__}: {exc}"})
            continue
        if package.schedule is not None:
            schedules.append({"report": name, **package.schedule})
    return schedules, errors


def _package_dirs(directory: Path) -> list[Path]:
    """Package directories below *directory*, in folders too: a directory
    with ``report.json`` is a package; any other is a folder to walk."""
    found: list[Path] = []
    for sub in sorted(p for p in directory.iterdir() if p.is_dir()):
        if sub.name.startswith(("_", ".")):
            continue
        if (sub / "report.json").is_file():
            found.append(sub)
        else:
            found.extend(_package_dirs(sub))
    return found


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_run(record: dict, output_dir: Union[str, Path]) -> Path:
    """Append *record* as one JSON line to ``<output_dir>/schedule_runs.jsonl``."""
    log = Path(output_dir) / RUN_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return log


def last_runs(output_dir: Union[str, Path]) -> dict[str, dict]:
    """The most recent recorded run per report (unreadable lines skipped)."""
    log = Path(output_dir) / RUN_LOG
    latest: dict[str, dict] = {}
    if not log.is_file():
        return latest
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and rec.get("report"):
            latest[rec["report"]] = rec
    return latest


def run_schedule(schedule: dict, *, reports_dir: Union[str, Path],
                 output_dir: Union[str, Path],
                 models_dir: Union[str, Path, None] = None,
                 send: bool = True) -> dict:
    """Run one schedule now: refresh → build → verify → deliver → record.

    Returns the run record (also appended to the run log). Never raises for
    a failed run — the failure is the record's ``status`` and ``error``, so
    a scheduler loop survives one bad report.
    """
    from tracebi.audit import get_actor

    name = schedule["report"]
    user, role = get_actor()
    record: dict = {
        "report": name, "started_at": _now(), "finished_at": None,
        "status": FAILED, "verdict": None, "recipients": [],
        "output": None, "error": None, "actor": user, "actor_role": role,
        "refresh": [],
    }
    try:
        _run(schedule, record, Path(reports_dir), Path(output_dir),
             models_dir, send)
    except Exception as exc:  # noqa: BLE001 — recorded, not raised
        record["status"] = FAILED
        record["error"] = f"{type(exc).__name__}: {exc}"
    record["finished_at"] = _now()
    record_run(record, output_dir)
    return record


def _run(schedule: dict, record: dict, reports_dir: Path, output_dir: Path,
         models_dir, send: bool) -> None:
    from tracebi.cli import _build_report_target, _resolve_report_target
    from tracebi.verify import load_models, verify_manifest

    name = schedule["report"]
    kind, path = _resolve_report_target(name, reports_dir)
    if not _refresh(schedule.get("refresh") or {}, record):
        return                           # status stays FAILED, error says why
    output = output_dir / f"{name}.html"
    _build_report_target(kind, path, output)
    manifest_path = output.with_name(output.name + ".manifest.json")
    record["output"] = str(output)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = verify_manifest(manifest, load_models(models_dir))
    record["verdict"] = result["verdict"]
    if result["exit_code"] != 0:
        record["status"] = REFUSED
        record["error"] = result["verdict_detail"]
        return

    to = schedule.get("to") or []
    if not (send and to):
        record["status"] = BUILT
        return

    from tracebi._delivery import send_report, slack_notify
    send_report(output, manifest_path, to, verify_result=result)
    record["status"] = DELIVERED
    record["recipients"] = list(to)

    webhook = os.environ.get("TRACEBI_SLACK_WEBHOOK")
    if webhook:
        try:
            slack_notify(webhook, f"{name} delivered on schedule · "
                                  f"{result['verdict'].upper().replace('_', ' ')}")
        except Exception as exc:  # noqa: BLE001 — the report already went out
            record["error"] = f"slack notify failed (report was sent): {exc}"


def _refresh(refresh: dict, record: dict) -> bool:
    """Run the schedule's refresh steps in order, each in a fresh process —
    the same commands a person runs, so a transform's sink contract still
    guards what lands. Returns False (with ``record["error"]`` set) at the
    first step that fails; later steps and the build do not run."""
    import subprocess
    import sys
    import time

    steps = [("transform", "run-transform", n) for n in refresh.get("transforms", [])]
    steps += [("pipeline", "run-pipeline", n) for n in refresh.get("pipelines", [])]
    for kind, command, name in steps:
        started = time.monotonic()
        proc = subprocess.run([sys.executable, "-m", "tracebi.cli", command, name],
                              capture_output=True, text=True)
        ok = proc.returncode == 0
        record["refresh"].append({"step": f"{kind}:{name}", "ok": ok,
                                  "seconds": round(time.monotonic() - started, 2)})
        if not ok:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
            record["error"] = (f"refresh {kind} '{name}' failed, so nothing was "
                               f"built or sent: " + " | ".join(tail))
            return False
    return True


def make_job(reports_dir: Union[str, Path], output_dir: Union[str, Path],
             models_dir: Union[str, Path, None] = None):
    """The job ``tracebi schedule serve`` and the web server both run.

    APScheduler calls it on a worker thread, which does not inherit the
    caller's :class:`~contextvars.ContextVar`, so the actor is set inside.
    """
    def job(schedule: dict) -> dict:
        from tracebi.audit import actor
        with actor("scheduler", role="cli"):
            return run_schedule(schedule, reports_dir=reports_dir,
                                output_dir=output_dir, models_dir=models_dir)
    return job


def start_server_scheduler():
    """Start in-server schedules when ``TRACEBI_SCHEDULES_IN_SERVER=1``.

    Returns the running scheduler, or ``None`` when the switch is off or
    the reports directory has no schedule blocks. A missing APScheduler
    raises ``ImportError`` naming ``tracebi[pipeline]`` — startup must not
    continue as if the schedules were running.
    """
    import logging
    import os

    if os.environ.get("TRACEBI_SCHEDULES_IN_SERVER") != "1":
        return None
    log = logging.getLogger("tracebi.schedule")
    reports_dir = os.environ.get("TRACEBI_REPORTS_DIR", "reports")
    # Same default as `tracebi schedule serve`. TRACEBI_OUTPUT_ROOT is the
    # MCP gateway's confinement root, not where schedule runs are recorded.
    output_dir = "output"
    models_dir = os.environ.get("TRACEBI_MODELS_DIR", "models")
    schedules, errors = discover_schedules(reports_dir)
    for err in errors:
        log.warning("skipped %s: %s", err["report"], err["error"])
    if not schedules:
        log.info("TRACEBI_SCHEDULES_IN_SERVER is on; no schedules in %s",
                 reports_dir)
        return None
    log.warning(
        "In-server schedules assume one process. With several workers, "
        "each process would send the email.")
    scheduler = build_scheduler(
        schedules, make_job(reports_dir, output_dir, models_dir),
        blocking=False)
    for s in schedules:
        log.info("%s", describe_schedule(s))
    scheduler.start()
    return scheduler


@asynccontextmanager
async def server_lifespan(app):
    """Start in-server schedules with the process and stop them on shutdown.

    The web app passes this to ``FastAPI(lifespan=...)``. Tests use the same
    function on a tiny app so they do not import ``tracebi.web.api.main``
    (that import binds the routers to the global registry).
    """
    scheduler = start_server_scheduler()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def build_scheduler(schedules: list[dict], job: Callable[[dict], object],
                    blocking: bool = True):
    """An APScheduler instance with one cron job per schedule (not started).

    *job* is called with the schedule dict at each fire time.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        raise ImportError(
            "tracebi schedule serve needs APScheduler. "
            "Install with: pip install 'tracebi[pipeline]'"
        ) from None

    scheduler = (BlockingScheduler if blocking else BackgroundScheduler)(
        timezone="UTC")
    for s in schedules:
        scheduler.add_job(
            func=job, args=[s],
            trigger=CronTrigger.from_crontab(s["cron"],
                                             timezone=s.get("timezone") or "UTC"),
            id=s["report"], name=s["report"],
            max_instances=1, coalesce=True, misfire_grace_time=300,
        )
    return scheduler


def describe_schedule(s: dict, last: Optional[dict] = None) -> str:
    """One human line for ``tracebi schedule list``."""
    to = ", ".join(s.get("to") or []) or "(build only)"
    tz = s.get("timezone") or "UTC"
    line = f"{s['report']:<28} {s['cron']:<16} {tz:<18} → {to}"
    if last:
        line += f"   last: {last.get('status')} {last.get('finished_at') or ''}"
    return line
