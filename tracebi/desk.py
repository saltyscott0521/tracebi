"""What the desk puts in front of a person.

Pins, exploration drafts, receipts whose verdict is not ``reproduces``,
and sinks that are ``stale`` or ``no_contract``. Read-only. A failure in
one group does not drop the others.
"""

from __future__ import annotations

import json
import os
import threading
from collections import OrderedDict
from typing import Any, Mapping, Optional


def review(project_root: str, models: Optional[Mapping[str, Any]] = None,
           fresh: bool = False) -> dict:
    """The review list for *project_root*.

    ``open`` is the newest built artifact whose verdict is ``reproduces``,
    so Desk can open that file. ``builds`` is every built report on disk
    with its build time and verdict, newest first. The other lists are
    what still needs a person. ``models`` is what ``verify_manifest``
    re-runs against; a missing model becomes an ``error`` verdict rather
    than an empty desk. Each verdict and build row carries ``computed_at``
    (when its re-run happened) and ``cached`` (whether this read reused it;
    see :func:`verdict`). ``fresh`` re-runs every one.
    """
    root = os.path.abspath(project_root)
    opened, verdicts, builds = _verdicts(root, models or {}, fresh)
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
    from tracebi.workbench import PINS_FILE, read_pins

    base = os.path.join(root, ".tracebi", "workbench")
    if not os.path.isdir(base):
        return []
    found: list[dict] = []
    # A report in a folder keeps its workbench at .tracebi/workbench/<folder>/<name>,
    # so walk down to every directory that holds a pins file.
    for directory, dirs, files in sorted(os.walk(base)):
        dirs.sort()
        if PINS_FILE not in files:
            continue
        name = os.path.relpath(directory, base).replace(os.sep, "/")
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
    from pathlib import Path

    from tracebi.report_paths import library_roots

    drafts: list[dict] = []
    for label, reports_root in library_roots():
        reports = reports_root if reports_root.is_absolute() else Path(root) / reports_root
        reports = str(reports)
        if not os.path.isdir(reports):
            continue
        for directory, dirs, files in sorted(os.walk(reports)):
            dirs[:] = sorted(d for d in dirs if not d.startswith((".", "_")))
            if "template.html" not in files or directory == reports:
                continue
            entry = os.path.relpath(directory, reports).replace(os.sep, "/")
            if label:
                entry = f"{label}/{entry}"
            template = os.path.join(directory, "template.html")
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
    root: str, models: Mapping[str, Any], fresh: bool = False,
) -> tuple[Optional[dict], list[dict], list[dict]]:
    output = os.path.join(root, "output")
    if not os.path.isdir(output):
        return None, [], []
    waiting: list[dict] = []
    builds: list[dict] = []
    opened: Optional[dict] = None
    opened_mtime = -1.0
    suffix = ".html.manifest.json"
    # output/finance/weekly.html belongs to the report "finance/weekly".
    manifests = sorted(
        os.path.relpath(os.path.join(d, n), output).replace(os.sep, "/")
        for d, _, names in os.walk(output) for n in names if n.endswith(suffix))
    for name in manifests:
        path = os.path.join(output, name)
        report = name[: -len(suffix)]
        html_path = os.path.join(output, report + ".html")
        checked = verdict(path, models, fresh=fresh)
        verdict_ = checked["verdict"]
        when = {"computed_at": checked["computed_at"], "cached": checked["cached"]}
        row = {
            "report": report,
            "verdict": verdict_,
            "detail": checked["detail"],
            "path": _rel(root, path),
            **when,
        }
        if os.path.isfile(html_path):
            builds.append({
                "report": report,
                "verdict": verdict_,
                "built_at": _built_at(html_path),
                **when,
            })
        if verdict_ == "reproduces":
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


# ── The verdict cache ────────────────────────────────────────────────────
# A verdict is a re-run of a build's recorded queries (tracebi/verify.py,
# the oracle), never a stored claim older than its inputs. Re-running every
# build on every desk read cost seconds per page load, so a verdict is kept
# exactly while nothing it was computed from has changed: the manifest file,
# each model it names (its file, or the object when it has none), and every
# connector those models read (the warehouse file's size and modification
# time, or the object tier's Parquet listing) with the contracts certificate
# beside it. Any change gives a new key, and the next read re-runs it. An
# input that cannot say when it changed (the remote tier, a SQL, CSV or
# in-memory connector) makes the verdict uncacheable: it is re-run on every
# read, as before. A re-run that hit an error (a locked warehouse, a timeout)
# is not kept either, since it says nothing about the inputs.
#
# The cache is process-local: a second worker keeps its own and computes its
# own verdicts. That costs it its first read and never serves it a stale one.

_VERDICT_CACHE_MAX = 256
# manifest path -> (key, entry); least recently used first.
_verdict_cache: "OrderedDict[str, tuple[tuple, dict]]" = OrderedDict()
_verdict_lock = threading.Lock()


def invalidate() -> None:
    """Forget every cached verdict, so the next read re-runs each one."""
    with _verdict_lock:
        _verdict_cache.clear()


def verdict(manifest_path: str, models: Mapping[str, Any],
            fresh: bool = False) -> dict:
    """The desk's verdict on the build whose receipt is *manifest_path*:
    ``{verdict, detail, computed_at, cached}``.

    Reused while :func:`verdict_key` is unchanged and ``fresh`` is false;
    otherwise re-run by :func:`tracebi.verify.verify_manifest` and kept when
    the key allows. Never raises: an unreadable receipt is an ``error``.
    """
    from datetime import datetime, timezone

    from tracebi.verify import ERROR, verify_manifest

    path = os.path.abspath(manifest_path)
    # Stamp the manifest before reading it: a rewrite in between is then
    # kept under the older key, which the next read no longer matches.
    try:
        before = os.stat(path)
    except OSError:
        before = None
    key = None
    try:
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        if not isinstance(manifest, dict):
            raise ValueError("manifest is not an object")
        key = verdict_key(path, before, manifest, models)
        if key is not None and not fresh:
            with _verdict_lock:
                hit = _verdict_cache.get(path)
                if hit is not None and hit[0] == key:
                    _verdict_cache.move_to_end(path)
                    return {**hit[1], "cached": True}
        result = verify_manifest(manifest, models)
        entry = {"verdict": result.get("verdict") or "error",
                 "detail": result.get("verdict_detail")}
        if (result.get("summary") or {}).get(ERROR):
            key = None
    except Exception as exc:  # noqa: BLE001 — one bad receipt stays on the list
        entry = {"verdict": "error", "detail": f"{type(exc).__name__}: {exc}"}
        key = None
    entry["computed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with _verdict_lock:
        if key is None:
            _verdict_cache.pop(path, None)
        else:
            _verdict_cache[path] = (key, entry)
            _verdict_cache.move_to_end(path)
            while len(_verdict_cache) > _VERDICT_CACHE_MAX:
                _verdict_cache.popitem(last=False)
    return {**entry, "cached": False}


def warm(manifest_path: str, models: Mapping[str, Any]) -> None:
    """Re-run and keep the verdict of a build just written, so the next desk
    read is instant. Never raises: a failure to warm never fails a build."""
    try:
        verdict(manifest_path, models, fresh=True)
    except Exception:  # noqa: BLE001 — warming is an optimisation only
        pass


def _stat_stamp(path: str) -> Optional[tuple]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _connector_stamp(connector: Any) -> Optional[tuple]:
    """What changes when the data *connector* reads changes, or None when it
    cannot say (then the verdict is not kept)."""
    from tracebi.connectors.duckdb_connector import DuckDBConnector
    from tracebi.contracts import contracts_path
    from tracebi.model.engine import _file_stamp

    if not isinstance(connector, DuckDBConnector):
        return None
    wh = getattr(connector, "warehouse", None)
    if wh is None or wh.tier == "file":
        path = os.path.abspath(connector.database)
        stamp = _file_stamp(path)
        if stamp[0] is None:   # not a file (":memory:", or gone)
            return None
        return (path, stamp, _stat_stamp(contracts_path(path)))
    stamp = wh.stamp()
    if stamp is None:          # the remote tier cannot say when it changed
        return None
    return (str(connector.database), stamp, _stat_stamp(contracts_path(connector.database)))


def _manifest_models(manifest: Mapping[str, Any]) -> list[str]:
    """Every model a manifest's recorded queries name."""
    from tracebi.verify import _walk_sections

    names: set[str] = set()
    for section in _walk_sections(manifest.get("sections") or []):
        for node in section.get("dataset_lineage") or []:
            md = node.get("metadata") if isinstance(node, dict) else None
            if isinstance(md, dict) and isinstance(md.get("model"), str):
                names.add(md["model"])
    return sorted(names)


def verdict_key(manifest_path: str, manifest_stat: Optional[os.stat_result],
                manifest: Mapping[str, Any], models: Mapping[str, Any]) -> Optional[tuple]:
    """The inputs a verdict on *manifest* is computed from, or None when one of
    them cannot say whether it changed. Equal keys mean a re-run would read
    exactly what the last one read."""
    from tracebi.model_registry import model_path

    if manifest_stat is None:
        return None
    parts: list = [(os.path.abspath(manifest_path),
                    manifest_stat.st_mtime_ns, manifest_stat.st_size)]
    try:
        for name in _manifest_models(manifest):
            model = models.get(name)
            if model is None:
                # Its error names the models there are.
                parts.append((name, None, tuple(sorted(models))))
                continue
            file = model_path(name)
            stamps = []
            for connector in model.connectors():
                stamp = _connector_stamp(connector)
                if stamp is None:
                    return None
                stamps.append(stamp)
            # A model registered in memory has no file to stamp; the object
            # stands in for it.
            parts.append((name, file, _stat_stamp(file) if file else id(model),
                          tuple(stamps)))
    except Exception:  # noqa: BLE001 — an input that cannot be stamped is not kept
        return None
    return tuple(parts)


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
