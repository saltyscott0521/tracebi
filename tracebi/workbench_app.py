"""
The workbench inside the agent: an MCP App (``ui://tracebi/workbench``).

A host that renders MCP Apps (the ``io.modelcontextprotocol/ui`` extension)
shows this beside the chat when the agent calls a tool that declares it
(``preview_draft``, ``workbench_state``, ``build_report``). The page is one
self-contained file, ``workbench_app.html``: no network, the report itself in
a sandboxed frame inside it, and the workbench's own chrome around it (figure
status, open pins, what the agent last did).

The panel calls back through the host bridge, and only these two tools are
for it (``_meta.ui.visibility: ["app"]``, so a host keeps them out of the
agent's list; a client that did not negotiate Apps is not shown them at all):

* :func:`view` — read-only. The working page (a draft's preview, or a package
  rendered with its exploration blocks kept, as the app's Build panel shows
  it), the figures and their status, the open pins and the feed, and a
  ``version``. The panel polls it with ``since=<version>`` and gets
  ``changed: false`` back until something it shows changes.
* :func:`pin` — writes one pin to the report path's ``pins.json``, the file
  ``workbench_state`` and ``address_pins`` read. Nothing else: the panel
  never writes the report, publishes or approves.

Everything here is dev-state, as in :mod:`tracebi.workbench`: no receipt, no
build, no manifest.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional

#: The app resource every authoring tool names in ``_meta.ui.resourceUri``.
APP_URI = "ui://tracebi/workbench"

#: The tools the panel calls; hidden from the agent.
APP_TOOLS = ("workbench_view", "workbench_pin")

#: The feed entries the panel shows, newest first.
FEED_SHOWN = 12

#: A figure id a pin may name: what ``data-tb-figure`` ids are made of.
_FIGURE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def app_html() -> str:
    """The panel: one HTML file, everything inline."""
    return (Path(__file__).with_name("workbench_app.html")).read_text(encoding="utf-8")


def _base_url() -> str:
    return (os.environ.get("TRACEBI_PUBLIC_URL") or "").strip().rstrip("/")


def report_url(report: str) -> str:
    """Where a person opens a report's workbench without MCP Apps: the app's
    report page (``tracebi dev <name>`` opens the same one). A bare path when
    ``TRACEBI_PUBLIC_URL`` is unset."""
    return f"{_base_url()}/reports/{report}" if report else f"{_base_url()}/data"


class Target:
    """What the panel shows: a draft, a library package, or the workspace feed."""

    def __init__(self, report: str, draft: bool, owner: str):
        from tracebi.workbench import DISCOVERY_NAME, discovery_dir, workbench_dir

        self.report, self.draft, self.owner = report, draft, owner
        self.package: Optional[Path] = None
        if not report or report == DISCOVERY_NAME:
            self.report, self.draft = "", False
            self.wb = discovery_dir(os.getcwd())
            self.link = report_url("")
            return
        override = os.environ.get("TRACEBI_WORKBENCH_DIR")
        if draft:
            from tracebi import drafts
            self.package = drafts._exists(owner, "reports", report)   # validates the path
            self.wb = override or workbench_dir(os.getcwd(), report)
            self.link = drafts.draft_url(owner, "reports", report)
            return
        from tracebi.report_paths import open_report, report_name_for_dir
        opened = open_report(report, purpose="view")
        if opened.name_error:
            raise ValueError(opened.name_error)
        if opened.package_dir is None:
            raise ValueError(f"no artifact package at {opened.path} — the workbench "
                             f"shows reports/<name>/ packages and report drafts")
        self.package = Path(opened.package_dir)
        self.wb = override or workbench_dir(os.getcwd(), report_name_for_dir(str(self.package)))
        self.link = report_url(report)

    def describe(self) -> dict:
        return {"report": self.report, "draft": self.draft, "link": self.link}


def _version(target: Target) -> str:
    """Everything the panel shows, as a cheap stat digest (the same idea as
    :func:`tracebi.workbench.package_version`, over this target's files)."""
    from tracebi.workbench import EXHIBITS_FILE, PINS_FILE, discovery_dir, package_version

    digest = hashlib.sha1()
    if target.package is not None:
        digest.update(package_version(str(target.package)).encode())
    for path in (Path(target.wb) / PINS_FILE, Path(target.wb) / EXHIBITS_FILE,
                 Path(discovery_dir(os.getcwd())) / EXHIBITS_FILE):
        try:
            st = path.stat()
        except OSError:
            continue
        digest.update(f"{path}:{st.st_mtime_ns}:{st.st_size}\n".encode())
    return digest.hexdigest()[:16]


def _feed(target: Target) -> list[dict]:
    """What the agent did (the workspace feed's agent lines) and what the
    report's own code showed, newest first, as text: a query's rows stay in the
    agent's result and the app, never in this chrome."""
    from tracebi.workbench import discovery_dir, read_exhibits

    seen = []
    dirs = {target.wb, discovery_dir(os.getcwd())}
    for wb in dirs:
        for ex in read_exhibits(wb):
            seen.append({"at": ex.get("at"), "name": ex.get("name") or ex.get("kind"),
                         "text": ex.get("note") or ex.get("text") or "",
                         "agent": ex.get("source") == "agent"})
    seen.sort(key=lambda e: e.get("at") or "", reverse=True)
    return seen[:FEED_SHOWN]


def _page(target: Target, models: dict) -> str:
    """The working page: exploration kept, rendered in memory, nothing written."""
    from tracebi.workbench import show_off

    with show_off():
        if target.draft:
            from tracebi import drafts
            return drafts.render_preview(target.owner, "reports", target.report, models)
        from tracebi.reports.template_package import TemplatePackage
        page, _inputs, _outputs = TemplatePackage(str(target.package)).render_exploration(models)
        return page


def view(report: str, draft: bool, since: str, owner: str, models: dict) -> dict:
    """The panel's one read. ``changed: false`` when *since* is current."""
    from tracebi.workbench import collect_state, discovery_dir, heartbeat, show_off

    target = Target(report, draft, owner)
    # While the panel is open, what the agent does posts to the workspace feed
    # (post_agent_action follows the same heartbeat as tracebi dev's).
    heartbeat(discovery_dir(os.getcwd()))
    version = _version(target)
    if since and since == version:
        return {"ok": True, "changed": False, "version": version}
    out: dict = {"ok": True, "changed": True, "version": version,
                 "target": target.describe(), "feed": _feed(target), "errors": []}
    if target.package is None:                      # the workspace feed only
        from tracebi.workbench import collect_feed
        feed = collect_feed(os.getcwd())
        out.update(html=None, figures=[], pins=_pins(feed["pins"]), resolved=[])
        return out
    if target.draft:
        from tracebi import drafts
        models = drafts.preview_models(owner, models)
    try:
        out["html"] = _page(target, models)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 — a broken page is shown, not raised
        out["html"] = None
        out["errors"].append(f"the page did not render: {type(exc).__name__}: "
                             f"{str(exc).splitlines()[0] if str(exc) else ''}")
    with show_off():
        state = collect_state(str(target.package), models, wb_dir=target.wb)
    out["figures"] = [
        {k: f[k] for k in ("id", "kind", "binding", "cell", "provenance", "unbound", "pinned")
         if k in f}
        for f in state.get("figures") or []]
    out["pins"] = _pins(state.get("pins") or [])
    out["resolved"] = [{"id": p.get("id"), "note": p.get("note") or "",
                        "resolved_note": p.get("resolved_note") or ""}
                       for p in (state.get("resolved") or [])[-5:]]
    if state.get("render_error"):
        out["errors"].append(state["render_error"])
    out["errors"] += [f"binding {b['name']}: {b['error'].splitlines()[0]}"
                      for b in state.get("bindings") or [] if b.get("error")]
    return out


def _pins(pins: list[dict]) -> list[dict]:
    return [{"id": p.get("id"), "kind": p.get("kind") or "figure",
             "note": p.get("note") or ""} for p in pins]


def pin(report: str, draft: bool, figure: str, note: str, owner: str) -> dict:
    """Pin the person's note on one figure (or, with no figure, leave it as a
    note). Writes the report path's ``pins.json`` and nothing else; returns the
    pin and the message the panel sends the agent."""
    from tracebi.workbench import NOTE_MAX, add_pin, leave_note

    target = Target(report, draft, owner)
    note = (note or "").strip()[:NOTE_MAX]
    where = f"the draft of {target.report}" if target.draft else (target.report or "the workspace")
    if figure:
        if not _FIGURE_ID.match(figure):
            raise ValueError("a figure id is letters, digits and _ . : - (at most 120)")
        made = next(p for p in add_pin(target.wb, figure, note=note) if p["id"] == figure)
        message = f"Pinned on {figure} in {where}: {note or '(no note)'}"
    else:
        made = leave_note(target.wb, note)              # refuses an empty note
        message = f"A note in the workbench for {where}: {note}"
    tools = (f"workbench_state(report={target.report!r}"
             + (", draft=true" if target.draft else "") + ")") if target.report \
        else "workbench_state()"
    return {"ok": True, "pin": {"id": made["id"], "note": made.get("note") or ""},
            "message": f"{message}\n(Read it with {tools}; resolve_pin when done.)"}
