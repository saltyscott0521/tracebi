"""What the desk puts in front of a person.

Pins, exploration drafts, receipts whose verdict is not ``reproduces``,
and sinks that are ``stale`` or ``no_contract``. Read-only. A failure in
one group does not drop the others.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping, Optional


def review(project_root: str, models: Optional[Mapping[str, Any]] = None) -> dict:
    """The review list for *project_root*.

    ``open`` is the newest built artifact whose verdict is ``reproduces``,
    so Desk can open that file. ``builds`` is every built report on disk
    with its build time and verdict, newest first. The other lists are
    what still needs a person. ``models`` is what ``verify_manifest``
    re-runs against; a missing model becomes an ``error`` verdict rather
    than an empty desk.
    """
    root = os.path.abspath(project_root)
    opened, verdicts, builds = _verdicts(root, models or {})
    warehouse = os.path.join(root, "data", "warehouse.duckdb")
    return {
        "pins": _pins(root),
        "drafts": _drafts(root),
        "verdicts": verdicts,
        "sinks": _sinks(warehouse),
        "warehouse": os.path.isfile(warehouse),
        "open": opened,
        "builds": builds,
    }


def _rel(root: str, path: str) -> str:
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return path


def _pins(root: str) -> list[dict]:
    from tracebi.workbench import read_pins

    base = os.path.join(root, ".tracebi", "workbench")
    if not os.path.isdir(base):
        return []
    found: list[dict] = []
    for name in sorted(os.listdir(base)):
        directory = os.path.join(base, name)
        if not os.path.isdir(directory):
            continue
        for pin in read_pins(directory):
            if not isinstance(pin, dict):
                continue
            found.append({
                "report": name,
                "id": pin.get("id"),
                "note": pin.get("note") or "",
                "at_seq": pin.get("at_seq"),
            })
    return found


def _drafts(root: str) -> list[dict]:
    reports = os.environ.get("TRACEBI_REPORTS_DIR", "reports")
    if not os.path.isabs(reports):
        reports = os.path.join(root, reports)
    if not os.path.isdir(reports):
        return []
    drafts: list[dict] = []
    for entry in sorted(os.listdir(reports)):
        template = os.path.join(reports, entry, "template.html")
        if not os.path.isfile(template):
            continue
        try:
            text = open(template, encoding="utf-8").read()
        except OSError:
            continue
        if (
            'data-tb-stage="exploration"' in text
            or "data-tb-stage='exploration'" in text
        ):
            drafts.append({
                "report": entry,
                "path": _rel(root, template),
            })
    return drafts


def _built_at(path: str) -> Optional[str]:
    """ISO-8601 UTC modification time of *path*, or None when unreadable."""
    from datetime import datetime, timezone

    try:
        return datetime.fromtimestamp(
            os.path.getmtime(path), tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def _verdicts(
    root: str, models: Mapping[str, Any],
) -> tuple[Optional[dict], list[dict], list[dict]]:
    from tracebi.verify import verify_manifest

    output = os.path.join(root, "output")
    if not os.path.isdir(output):
        return None, [], []
    waiting: list[dict] = []
    builds: list[dict] = []
    opened: Optional[dict] = None
    opened_mtime = -1.0
    suffix = ".html.manifest.json"
    for name in sorted(os.listdir(output)):
        if not name.endswith(suffix):
            continue
        path = os.path.join(output, name)
        report = name[: -len(suffix)]
        html_path = os.path.join(output, report + ".html")
        try:
            with open(path, encoding="utf-8") as fh:
                manifest = json.load(fh)
            if not isinstance(manifest, dict):
                raise ValueError("manifest is not an object")
            result = verify_manifest(manifest, models)
            verdict = result.get("verdict") or "error"
            detail = result.get("verdict_detail")
        except Exception as exc:  # noqa: BLE001 — one bad receipt stays on the list
            verdict = "error"
            detail = f"{type(exc).__name__}: {exc}"
        row = {
            "report": report,
            "verdict": verdict,
            "detail": detail,
            "path": _rel(root, path),
        }
        if os.path.isfile(html_path):
            builds.append({
                "report": report,
                "verdict": verdict,
                "built_at": _built_at(html_path),
            })
        if verdict == "reproduces":
            if os.path.isfile(html_path):
                try:
                    mtime = os.path.getmtime(html_path)
                except OSError:
                    mtime = 0.0
                if mtime >= opened_mtime:
                    opened_mtime = mtime
                    opened = {
                        "report": report,
                        "verdict": "reproduces",
                        "html_path": _rel(root, html_path),
                        "manifest_path": _rel(root, path),
                    }
            continue
        waiting.append(row)
    builds.sort(key=lambda b: b["built_at"] or "", reverse=True)
    return opened, waiting, builds


def _sinks(warehouse: str) -> list[dict]:
    if not os.path.isfile(warehouse):
        return []
    rows: list[dict] = []
    recorded: set[str] = set()
    try:
        from tracebi.contracts import check_fingerprints

        for row in check_fingerprints(warehouse):
            table = row.get("table")
            if not table:
                continue
            recorded.add(table)
            if not row.get("matches"):
                rows.append({
                    "table": table,
                    "status": "stale",
                    "transform": row.get("transform"),
                })
    except Exception:  # noqa: BLE001 — a locked warehouse must not blank the desk
        return rows
    try:
        import duckdb

        con = duckdb.connect(warehouse, read_only=True)
        try:
            names = [
                r[0] for r in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            ]
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — listing tables is best-effort
        return rows
    for table in names:
        if table not in recorded:
            rows.append({"table": table, "status": "no_contract"})
    return rows
