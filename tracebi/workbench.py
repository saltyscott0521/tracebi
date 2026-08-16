"""
The workbench — dev-state for the artifact authoring loop (architecture v2 §2.5).

Two shared primitives live here, deliberately outside the dev server:

* :func:`show` — the notebook-cell-output equivalent, callable from
  ``report.py`` or any exploration code. It appends an *exhibit* to the
  session's feed so the workbench becomes the agent's show surface ("steer
  from chat, see results in the portal"). It is a **no-op unless**
  ``TRACEBI_WORKBENCH_DIR`` is set, so a build or CI run ignores it
  entirely, and it never raises — a broken exhibit must not kill a build.

* :func:`collect_state` — THE one state builder. The dev server's
  ``/__workbench`` page, ``tracebi report status``, and the MCP
  ``workbench_state`` tool all consume this dict; factoring it here keeps
  the three surfaces honest copies of one another. Per-binding resolution
  errors are captured *into* the state rather than raised — the workbench
  is where a broken working state becomes visible, so it must render one.

**Hard rule (v2 §2.5): everything here is dev-state.** Exhibits and pins
live under ``.tracebi/workbench/`` in the project, carry no receipts, and
never enter builds or manifests. Nothing in this module writes to a
warehouse or mints a fingerprint claim.
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime
from typing import Optional

EXHIBITS_FILE = "exhibits.jsonl"
PINS_FILE = "pins.json"

#: The feed cap — the workbench is a lab log of the session, not an archive.
EXHIBIT_CAP = 100


def workbench_dir(project_root: str, report_name: str) -> str:
    """``<project_root>/.tracebi/workbench/<report_name>``, created on demand."""
    path = os.path.join(project_root, ".tracebi", "workbench", report_name)
    os.makedirs(path, exist_ok=True)
    return path


# ── The exhibit feed ────────────────────────────────────────────────────────


def show(obj=None, note: Optional[str] = None, name: Optional[str] = None) -> None:
    """Append one exhibit to the workbench feed — the notebook-cell output.

    Accepts a pandas DataFrame (excerpt + dtypes + shape recorded), a string
    (a markdown/code note), or — via ``show(name="binding")`` — a binding
    name the workbench renders from its own data panel. Zero ceremony::

        from tracebi.workbench import show
        show(df, note="after dropping the 9 null-mark funds")

    A **no-op** when ``TRACEBI_WORKBENCH_DIR`` is unset (builds and CI
    ignore it entirely), and never raises: a broken exhibit is dropped with
    a stderr note, never a dead build. Exhibits carry no receipts.
    """
    wb = os.environ.get("TRACEBI_WORKBENCH_DIR")
    if not wb:
        return
    try:
        import pandas as pd

        if isinstance(obj, pd.DataFrame):
            entry = {
                "kind": "frame",
                "name": name,
                "note": note,
                "columns": [str(c) for c in obj.columns],
                "dtypes": {str(c): str(t) for c, t in obj.dtypes.items()},
                "shape": [int(obj.shape[0]), int(obj.shape[1])],
                "rows": _json_safe_records(obj, 50),
            }
        elif isinstance(obj, str):
            entry = {"kind": "note", "text": obj, "note": note}
        elif obj is None and name:
            entry = {"kind": "binding", "name": name, "note": note}
        else:
            entry = {"kind": "note", "text": repr(obj), "note": note}
        _append_exhibit(wb, entry)
    except Exception as exc:  # noqa: BLE001 — by contract, show() never raises
        print(f"[tracebi workbench] exhibit dropped: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)


def auto_entry(wb_dir: str, text: str) -> None:
    """A one-line dev-loop event ("binding X updated · …") for the feed.

    Same never-raise contract as :func:`show` — feed bookkeeping must not
    kill a rebuild.
    """
    try:
        _append_exhibit(wb_dir, {"kind": "auto", "text": text})
    except Exception as exc:  # noqa: BLE001 — same contract as show()
        print(f"[tracebi workbench] auto-entry dropped: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)


def _append_exhibit(wb_dir: str, entry: dict) -> None:
    """Append one JSON line with a monotonically increasing ``seq``."""
    os.makedirs(wb_dir, exist_ok=True)
    path = os.path.join(wb_dir, EXHIBITS_FILE)
    record = {"seq": _next_seq(path),
              "at": datetime.now().isoformat(timespec="seconds")}
    record.update({k: v for k, v in entry.items() if v is not None})
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _next_seq(path: str) -> int:
    last = 0
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    last = max(last, int(json.loads(line).get("seq", 0)))
                except (ValueError, TypeError):
                    continue    # a torn line must not stop the feed
    return last + 1


def last_seq(wb_dir: str) -> int:
    """The newest exhibit's seq (0 when the feed is empty) — what a pin
    records as ``at_seq``."""
    return _next_seq(os.path.join(wb_dir, EXHIBITS_FILE)) - 1


def read_exhibits(wb_dir: str, cap: int = EXHIBIT_CAP) -> list[dict]:
    """The feed, newest first, capped. Torn lines are skipped, not fatal."""
    path = os.path.join(wb_dir, EXHIBITS_FILE)
    if not os.path.isfile(path):
        return []
    entries: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
    entries.sort(key=lambda e: e.get("seq", 0), reverse=True)
    return entries[:cap]


# ── Pins — the one portal→chat gesture ──────────────────────────────────────


def read_pins(wb_dir: str) -> list[dict]:
    """``pins.json`` as a list of ``{id, note, at_seq}`` (empty when absent)."""
    path = os.path.join(wb_dir, PINS_FILE)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            pins = json.load(f)
    except (ValueError, OSError):
        return []
    return pins if isinstance(pins, list) else []


def write_pins(wb_dir: str, pins: list[dict]) -> None:
    os.makedirs(wb_dir, exist_ok=True)
    with open(os.path.join(wb_dir, PINS_FILE), "w", encoding="utf-8") as f:
        json.dump(pins, f, indent=2)


# ── JSON-safe previews ──────────────────────────────────────────────────────


def _json_safe(value):
    """One cell, made JSON-serialisable — NaN/NaT become null (bug #3)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass                    # arrays and other non-scalars fall through
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "item"):  # numpy scalar → python scalar
        try:
            return _json_safe(value.item())
        except (ValueError, AttributeError):
            pass
    return str(value)


def _json_safe_records(df, limit: int) -> list[dict]:
    """First *limit* rows as JSON-safe records (presentation only — the
    numbers themselves live in the stamped triple, never here)."""
    return [
        {str(col): _json_safe(v) for col, v in row.items()}
        for _idx, row in df.head(limit).iterrows()
    ]


# ── The one state builder ───────────────────────────────────────────────────


def collect_state(package_dir: str, models: dict) -> dict:
    """Build the full workbench state for one artifact package (v2 §2.5).

    The dict every workbench surface renders from — the dev server's
    ``/__workbench`` page, ``tracebi report status``, and the MCP
    ``workbench_state`` tool. Resolves every binding and runs ``report.py``,
    capturing per-binding failures *into* the state; renders the page in
    memory (exploration kept, ids assigned) to extract the figure claims;
    joins the exhibit feed and pins. Nothing is written except the
    on-demand workbench directory itself — dev-state only, no receipts.
    """
    from tracebi.reports.embed import stamp
    from tracebi.reports.figures import (
        FigureError, assign_figure_ids, extract_figures, lint_numeric_literals,
    )
    from tracebi.reports.html_renderer import HTMLRenderer
    from tracebi.reports.report import Report, TableSection
    from tracebi.reports.stack import figures_config
    from tracebi.reports.template_package import REPORT_PY, TemplatePackage

    pkg = TemplatePackage(str(package_dir))

    # ── Resolve bindings; a failure is state, not an exception ──────────────
    report = Report(pkg.name)
    inputs = []
    errors: dict[str, str] = {}
    for bname, ref in pkg.bindings.items():
        model = (models or {}).get(ref.model)
        try:
            if model is None:
                raise ValueError(
                    f"model '{ref.model}' is not loaded. "
                    f"Available: {sorted(models or {})}."
                )
            sd = stamp(model, ref.query, name=bname)
        except Exception as exc:  # noqa: BLE001 — captured into the state
            errors[bname] = f"{type(exc).__name__}: {exc}"
            continue
        inputs.append(sd)
        report.add(TableSection(title=bname, dataset=sd.dataset, id=bname))

    outputs = []
    if pkg.report_py_path is not None:
        try:
            outputs = pkg._apply_report_py(report, inputs)
        except Exception as exc:  # noqa: BLE001 — captured into the state
            errors[REPORT_PY] = f"{type(exc).__name__}: {exc}"

    # ── Render in memory (snapshot-style) and extract the figure claims ─────
    figs = []
    page = None
    render_error = None
    try:
        renderer = HTMLRenderer(
            template=pkg.template_html,
            template_context={"bindings": list(pkg.bindings)},
        )
        page = renderer.to_html(report)
        page, _warnings = assign_figure_ids(page)
    except Exception as exc:  # noqa: BLE001 — captured into the state
        render_error = f"{type(exc).__name__}: {exc}"
        page = None
    if page is not None:
        try:
            figs = extract_figures(page)
        except FigureError as exc:
            render_error = f"{type(exc).__name__}: {exc}"

    # ── Figures: provenance (figures_config rules) + coverage ───────────────
    # Keyed by the DIRECTORY name, not the declaration's "name" — the
    # directory is the stable address the dev server and discovery share.
    wb = os.environ.get("TRACEBI_WORKBENCH_DIR") or workbench_dir(
        os.getcwd(), os.path.basename(os.path.normpath(str(package_dir))))
    pins = read_pins(wb)
    pinned_ids = {p.get("id") for p in pins}
    output_names = {sd.name for sd in outputs}
    resolved = {sd.name for sd in inputs} | output_names

    coverage = {"total": len(figs), "verified": 0, "derived": 0,
                "unverified": 0, "unbound_errors": 0}
    figures_state = []
    for f, cfg in zip(figs, figures_config(figs, output_names)):
        unbound = not f.unverified and (not f.binding or f.binding not in resolved)
        if f.unverified:
            coverage["unverified"] += 1
        elif unbound:
            coverage["unbound_errors"] += 1
        elif f.binding in output_names:
            coverage["derived"] += 1
        else:
            coverage["verified"] += 1
        entry = {"id": f.id, "kind": f.kind, "binding": f.binding,
                 "provenance": cfg["provenance"], "pinned": f.id in pinned_ids}
        if f.cell:
            entry["cell"] = f.cell
        if f.note:
            entry["note"] = f.note
        if unbound:
            entry["unbound"] = True
        figures_state.append(entry)

    # ── Data panel: one card per binding, declaration order then outputs ────
    used_by: dict[str, list[str]] = {}
    for f in figs:
        if f.binding:
            used_by.setdefault(f.binding, []).append(f.id)

    by_name = {sd.name: sd for sd in inputs}
    bindings_state = []
    for bname in pkg.bindings:
        if bname in errors:
            bindings_state.append({"name": bname, "source": "query",
                                   "error": errors[bname],
                                   "used_by": used_by.get(bname, [])})
        else:
            bindings_state.append(_binding_state(by_name[bname], "query", used_by))
    for sd in outputs:
        bindings_state.append(_binding_state(sd, "python", used_by))
    if REPORT_PY in errors:
        bindings_state.append({"name": REPORT_PY, "source": "python",
                               "error": errors[REPORT_PY], "used_by": []})

    unused = [b["name"] for b in bindings_state
              if not b["used_by"] and b["name"] != REPORT_PY]

    state = {
        "name": pkg.name,
        "figures": figures_state,
        "coverage": coverage,
        "bindings": bindings_state,
        "unused_bindings": unused,
        "lint": {
            "numeric_literals_outside_figures":
                lint_numeric_literals(page) if page is not None else 0,
        },
        "exhibits": read_exhibits(wb),
        "pins": pins,
        "code": {
            "report.json": _read_optional(os.path.join(pkg.directory,
                                                       "report.json")),
            "report.py": _read_optional(pkg.report_py_path or ""),
            "script.js": pkg.script_js,
        },
    }
    if render_error:
        state["render_error"] = render_error
    return state


def _binding_state(sd, source: str, used_by: dict) -> dict:
    df = sd.dataset.to_pandas()
    return {
        "name": sd.name,
        "source": source,
        "rows": int(len(df)),
        "columns": [str(c) for c in df.columns],
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "fingerprint": sd.fingerprint[:12],
        "preview": _json_safe_records(df, 25),
        "used_by": used_by.get(sd.name, []),
    }


def _read_optional(path: str) -> str:
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""
