"""
Live-preview server for ``tracebi dev <name>`` — form-aware (v2 §2.5).

An **artifact package** (``reports/<name>/``) gets the artifact-native loop:
the working state is rendered in memory on every change — exploration blocks
KEPT, badges on, stage ``exploration`` — and served alongside THE WORKBENCH
at ``/__workbench``: figures with provenance and copy-addresses, per-binding
data with quick-charts, the exhibit feed (``tracebi.workbench.show``), pins,
code, and lint. The watcher scans the package directory, ``models/``,
``transforms/``, and ``reports/_theme.css``; the served pages poll
``/__status`` and reload when anything changed. Errors render as a styled
traceback page that also auto-reloads once the code is fixed.

A **legacy request script** keeps today's single-file behavior, with a
deprecation note (``requests/`` is deprecated; removed in 0.8).

Everything here is dev-state by construction: nothing this server renders or
records exists in builds or manifests, and no receipts are minted.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

_REFRESH_SNIPPET = """
<script>
(function () {
  var current = __VERSION__;
  setInterval(function () {
    fetch("/__status")
      .then(function (r) { return r.json(); })
      .then(function (s) { if (s.version !== current) location.reload(); })
      .catch(function () {});
  }, 1000);
})();
</script>
"""

_ERROR_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>tracebi dev — error</title>
<style>
body {{ font-family: 'Segoe UI', Calibri, Arial, sans-serif; background: #f5f7fa;
       padding: 40px; color: #1a1a2e; }}
.box {{ max-width: 900px; margin: 0 auto; background: #fff; border-radius: 6px;
        box-shadow: 0 2px 16px rgba(0,0,0,0.08); overflow: hidden; }}
.head {{ background: #C62828; color: #fff; padding: 18px 24px; }}
.head h1 {{ font-size: 16px; margin: 0; }}
.head p {{ font-size: 12px; margin: 6px 0 0 0; opacity: 0.9; }}
pre {{ margin: 0; padding: 20px 24px; font-size: 12px; line-height: 1.5;
      overflow-x: auto; white-space: pre-wrap; }}
</style></head>
<body><div class="box">
<div class="head"><h1>{title}</h1>
<p>{file} — fix the code and save; this page reloads automatically.</p></div>
<pre>{trace}</pre>
</div></body></html>"""


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def render_request(path: Path) -> str:
    """Run the request and return report HTML, or a styled error page."""
    try:
        from tracebi._request_runner import execute_request
        from tracebi.reports.html_renderer import HTMLRenderer
        report = execute_request(path)
        return HTMLRenderer.for_project().to_html(report)
    except (Exception, SystemExit):
        return _ERROR_PAGE.format(
            title="Request script failed",
            file=_esc(path.name),
            trace=_esc(traceback.format_exc()),
        )


def _inject_refresh(html: str, version: int) -> str:
    snippet = _REFRESH_SNIPPET.replace("__VERSION__", str(version))
    if "</body>" in html:
        return html.replace("</body>", snippet + "</body>", 1)
    return html + snippet


# ── The two target forms ────────────────────────────────────────────────────


def _project_models() -> dict:
    """Every model in models/, loaded FRESH — the watcher watches models/,
    so an edited model file must re-exec on the next rebuild, which the
    process-global registry's cache would prevent. A file that fails to load
    is skipped with a stderr note; a binding that needs it reports the miss."""
    from tracebi.model_registry import ModelRegistry

    reg = ModelRegistry()
    models: dict = {}
    for stem in reg.auto_discover(os.environ.get("TRACEBI_MODELS_DIR", "models")):
        try:
            m = reg.get(stem)
        except Exception as exc:  # noqa: BLE001 — surfaced, not fatal to the loop
            print(f"  model '{stem}' failed to load: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        models[m.name] = m
        models.setdefault(stem, m)
    return models


class _RequestTarget:
    """A legacy request script — today's loop, deprecated (removed in 0.8)."""

    workbench = False

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.label = self.path.name

    def render(self) -> str:
        return render_request(self.path)

    def watch_paths(self) -> list[Path]:
        return [self.path]


class _PackageTarget:
    """An artifact package — the in-memory exploration render + workbench."""

    workbench = True

    def __init__(self, directory: Path) -> None:
        from tracebi.workbench import workbench_dir

        self.directory = Path(directory)
        self.name = self.directory.name
        self.label = self.name
        self.wb_dir = workbench_dir(os.getcwd(), self.name)
        # Per-binding fingerprints from the previous build: an auto-entry is
        # appended only when a fingerprint CHANGED, so the feed reads as a
        # log of actual data movement, not of every keystroke.
        self._fingerprints: dict[str, str] = {}
        self._primed = False

    def render(self) -> str:
        from tracebi.reports.template_package import TemplatePackage

        # show() calls in report.py land in this session's feed — the env
        # var is set only around the build, so nothing outside dev sees it.
        previous = os.environ.get("TRACEBI_WORKBENCH_DIR")
        os.environ["TRACEBI_WORKBENCH_DIR"] = self.wb_dir
        try:
            models = _project_models()
            pkg = TemplatePackage(str(self.directory))
            page, inputs, outputs = pkg.render_exploration(models)
        except (Exception, SystemExit):
            return _ERROR_PAGE.format(
                title="Report package failed",
                file=_esc(self.name),
                trace=_esc(traceback.format_exc()),
            )
        finally:
            if previous is None:
                os.environ.pop("TRACEBI_WORKBENCH_DIR", None)
            else:
                os.environ["TRACEBI_WORKBENCH_DIR"] = previous
        self._note_fingerprints(inputs + outputs)
        return page

    def _note_fingerprints(self, stamped) -> None:
        from tracebi.workbench import auto_entry

        for sd in stamped:
            if self._primed and self._fingerprints.get(sd.name) != sd.fingerprint:
                auto_entry(
                    self.wb_dir,
                    f"binding {sd.name} updated · "
                    f"{len(sd.dataset.to_pandas())} rows · "
                    f"{sd.fingerprint[:12]}",
                )
            self._fingerprints[sd.name] = sd.fingerprint
        self._primed = True

    def watch_paths(self) -> list[Path]:
        reports_dir = Path(os.environ.get("TRACEBI_REPORTS_DIR", "reports"))
        return [
            self.directory,
            Path(os.environ.get("TRACEBI_MODELS_DIR", "models")),
            Path(os.environ.get("TRACEBI_TRANSFORMS_DIR", "transforms")),
            reports_dir / "_theme.css",
        ]

    def state(self) -> dict:
        """The workbench state — collect_state, degraded to an error state
        rather than a 500 when even loading the package fails."""
        from tracebi.workbench import collect_state

        try:
            return collect_state(str(self.directory), _project_models())
        except Exception as exc:  # noqa: BLE001 — the panel must show the break
            return {
                "name": self.name,
                "error": f"{type(exc).__name__}: {exc}",
                "figures": [],
                "coverage": {"total": 0, "verified": 0, "derived": 0,
                             "unverified": 0, "unbound_errors": 0},
                "bindings": [], "unused_bindings": [],
                "lint": {"numeric_literals_outside_figures": 0},
                "exhibits": [], "pins": [], "code": {},
            }


def _scan_signature(paths) -> tuple:
    """(max mtime, file count) across files and directory trees — a change
    in either means something to rebuild. Files mid-atomic-save are skipped
    for this tick and picked up on the next."""
    latest = 0.0
    count = 0
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for root, _dirs, files in os.walk(p):
                for fn in files:
                    try:
                        latest = max(latest,
                                     os.path.getmtime(os.path.join(root, fn)))
                        count += 1
                    except OSError:
                        continue
        elif p.is_file():
            try:
                latest = max(latest, p.stat().st_mtime)
                count += 1
            except OSError:
                continue
    return (latest, count)


def _file_sig(path: str):
    try:
        st = os.stat(path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


# ── The workbench page (dev-only; never injected into build output) ─────────

_WORKBENCH_PAGE = """<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>workbench</title>
<style>
__TRACEBI_CSS__
</style>
<style>
/* Workbench page layer — stacked after tracebi.css, so later wins. */
body { max-width: 1100px; }
.wb-badge { position: static; }        /* .tb-badge is corner-absolute */
.wb-badge--error { color: #b91c1c; background: #fdeaea;
                   border-color: #f2b8b8; }
.wb-bar { height: 8px; background: var(--tb-rule); border-radius: 999px;
          overflow: hidden; margin: 4px 0 16px; }
.wb-bar > div { height: 100%; background: #1e6b34; }
.wb-row { display: flex; align-items: center; flex-wrap: wrap;
          gap: var(--tb-space-2); padding: 6px 0;
          border-bottom: 1px solid var(--tb-rule); }
.wb-card { border: 1px solid var(--tb-rule); border-radius: var(--tb-radius);
           padding: var(--tb-space-3); margin: var(--tb-space-3) 0; }
.wb-card .wb-row { border-bottom: 0; }
.wb-meta { color: var(--tb-muted); font-size: 0.85em; }
.wb-error { color: #C62828; white-space: pre-wrap; }
.wb-warn { color: #8a5a00; }
.wb-btn { font: inherit; font-size: 0.8em; padding: 2px 8px; cursor: pointer;
          border: 1px solid var(--tb-rule); border-radius: var(--tb-radius);
          background: #f6f7f9; }
.wb-btn--pinned { background: #fdf3d7; border-color: #ecd393; }
.wb-chart { height: 260px; margin-top: var(--tb-space-2); }
.wb-table-wrap { max-height: 320px; overflow: auto; }
select { font: inherit; font-size: 0.85em; }
</style>
</head>
<body>
<h1 id="wb-title">workbench</h1>
<p class="wb-meta">Dev-state only — nothing on this page exists in builds or
manifests, and no receipts are minted here. <a href="/">← report preview</a></p>
<div id="wb-error"></div>
<h2>Figures</h2>
<div id="wb-coverage"></div>
<div id="wb-figures"></div>
<h2>Data</h2>
<div id="wb-data"></div>
<h2>Feed</h2>
<div id="wb-feed"></div>
<h2>Code</h2>
<div id="wb-code"></div>
<h2>Lint</h2>
<div id="wb-lint"></div>
<script>
__ECHARTS__
</script>
<script>
(function () {
  "use strict";
  var REPORT = __NAME__;
  var last = null;

  /* All data reaches the DOM through textContent/createElement — never
     innerHTML of a data value. */
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }

  function button(label, cls, onclick) {
    var b = el("button", "wb-btn" + (cls ? " " + cls : ""), label);
    b.addEventListener("click", onclick);
    return b;
  }

  function copyBtn(label, text) {
    return button(label, null, function () {
      var b = this;
      var done = function () {
        b.textContent = "copied";
        setTimeout(function () { b.textContent = label; }, 1200);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, done);
      } else { done(); }
    });
  }

  function post(path, body) {
    return fetch(path, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    }).then(function () { return refresh(); }, function () {});
  }

  function pinBtn(id, pinned) {
    return button(pinned ? "unpin" : "pin",
                  pinned ? "wb-btn--pinned" : null, function () {
      if (pinned) { post("/__workbench/unpin", {id: id}); return; }
      var note = window.prompt("Pin note (optional):", "") || "";
      post("/__workbench/pin", {id: id, note: note});
    });
  }

  function badge(provenance) {
    var labels = {verified: "verified", derived: "python-derived",
                  unverified: "unverified", error: "unbound"};
    var cls = provenance === "error" ? "wb-badge--error"
                                     : "tb-badge--" + provenance;
    return el("span", "tb-badge wb-badge " + cls,
              labels[provenance] || provenance);
  }

  function smallTable(columns, rows, cap) {
    var wrap = el("div", "wb-table-wrap");
    var t = el("table", "tb-table tb-table--compact");
    var thead = el("thead");
    var tr = el("tr");
    columns.forEach(function (c) { tr.appendChild(el("th", null, c)); });
    thead.appendChild(tr);
    t.appendChild(thead);
    var tbody = el("tbody");
    rows.slice(0, cap || rows.length).forEach(function (r) {
      var tr2 = el("tr");
      columns.forEach(function (c) {
        var v = r[c];
        tr2.appendChild(el("td", typeof v === "number" ? "tb-num" : null,
                           v === null || v === undefined ? "" : v));
      });
      tbody.appendChild(tr2);
    });
    t.appendChild(tbody);
    wrap.appendChild(t);
    return wrap;
  }

  function renderFigures(state) {
    var cov = document.getElementById("wb-coverage");
    cov.textContent = "";
    var c = state.coverage;
    cov.appendChild(el("p", null,
        c.verified + " of " + c.total + " figures model-backed"));
    var bar = el("div", "wb-bar");
    var fill = el("div");
    fill.style.width = (c.total ? Math.round(100 * c.verified / c.total) : 0) + "%";
    bar.appendChild(fill);
    cov.appendChild(bar);

    var host = document.getElementById("wb-figures");
    host.textContent = "";
    state.figures.forEach(function (f) {
      var row = el("div", "wb-row");
      row.appendChild(badge(f.unbound ? "error" : f.provenance));
      row.appendChild(el("code", null, f.id));
      row.appendChild(el("span", "wb-meta",
          f.kind + (f.binding ? " · " + f.binding : "")
                 + (f.note ? " · " + f.note : "")));
      row.appendChild(copyBtn("copy address", REPORT + "#fig:" + f.id));
      row.appendChild(pinBtn(f.id, f.pinned));
      host.appendChild(row);
    });
    if (!state.figures.length) {
      host.appendChild(el("p", "wb-meta", "no figures yet — mark elements "
          + "with data-tb-figure in template.html"));
    }
  }

  function quickChart(binding) {
    var wrap = el("div");
    var xSel = el("select");
    var ySel = el("select");
    binding.columns.forEach(function (c) {
      var ox = el("option", null, c); ox.value = c; xSel.appendChild(ox);
      var oy = el("option", null, c); oy.value = c; ySel.appendChild(oy);
    });
    if (binding.columns.length > 1) ySel.selectedIndex = 1;
    var chartDiv = el("div", "wb-chart");
    chartDiv.style.display = "none";
    var markupPre = el("pre");
    markupPre.style.display = "none";
    var markupCode = el("code");
    markupPre.appendChild(markupCode);
    var actions = el("div");

    var row = el("div", "wb-row");
    row.appendChild(el("span", "wb-meta", "x"));
    row.appendChild(xSel);
    row.appendChild(el("span", "wb-meta", "y"));
    row.appendChild(ySel);
    row.appendChild(button("chart it", null, function () {
      var x = xSel.value, y = ySel.value;
      chartDiv.style.display = "block";
      var chart = window.echarts.init(chartDiv);
      chart.setOption({
        grid: {top: 16, right: 16, bottom: 48, left: 72},
        xAxis: {type: "category",
                data: binding.preview.map(function (r) { return String(r[x]); })},
        yAxis: {type: "value"},
        series: [{type: "bar",
                  data: binding.preview.map(function (r) { return r[y]; })}],
      });
      /* The copy-paste IS the adoption gesture: the markup below is the
         real figure grammar, ready for template.html. */
      var markup = '<div data-tb-figure="chart" data-tb-binding="'
          + binding.name + '" data-tb-type="bar" data-tb-x="' + x
          + '" data-tb-y="' + y + '" id="fig-' + binding.name
          + '" style="height:320px"></div>';
      markupCode.textContent = markup;
      markupPre.style.display = "block";
      actions.textContent = "";
      actions.appendChild(copyBtn("copy markup", markup));
    }));
    wrap.appendChild(row);
    wrap.appendChild(chartDiv);
    wrap.appendChild(markupPre);
    wrap.appendChild(actions);
    return wrap;
  }

  function renderData(state) {
    var host = document.getElementById("wb-data");
    host.textContent = "";
    state.bindings.forEach(function (b) {
      var card = el("div", "wb-card");
      var head = el("div", "wb-row");
      head.appendChild(el("span", "tb-badge wb-badge tb-badge--"
          + (b.source === "python" ? "derived" : "verified"),
          b.source === "python" ? "python" : "query"));
      head.appendChild(el("strong", null, b.name));
      if (b.error === undefined) {
        head.appendChild(el("span", "wb-meta",
            b.rows + " × " + b.columns.length + " · " + b.fingerprint));
      }
      card.appendChild(head);
      if (b.error !== undefined) {
        card.appendChild(el("pre", "wb-error", b.error));
        host.appendChild(card);
        return;
      }
      if (!b.used_by.length) {
        card.appendChild(el("p", "wb-meta wb-warn",
            "unused — no figure references this binding"));
      }
      card.appendChild(el("p", "wb-meta", b.columns.map(function (c) {
        return c + ": " + b.dtypes[c];
      }).join("  ·  ")));
      card.appendChild(smallTable(b.columns, b.preview, 25));
      card.appendChild(quickChart(b));
      host.appendChild(card);
    });
  }

  function renderFeed(state) {
    var host = document.getElementById("wb-feed");
    host.textContent = "";
    if (!state.exhibits.length) {
      host.appendChild(el("p", "wb-meta", "nothing shown yet — call "
          + "tracebi.workbench.show(...) from report.py, or save to see "
          + "binding updates land here"));
      return;
    }
    state.exhibits.forEach(function (ex) {
      var card = el("div", "wb-card");
      var head = el("div", "wb-row");
      head.appendChild(el("span", "wb-meta",
          "#" + ex.seq + (ex.at ? " · " + ex.at : "") + " · " + ex.kind));
      var pid = "exhibit-" + ex.seq;
      head.appendChild(pinBtn(pid, state.pins.some(function (p) {
        return p.id === pid;
      })));
      card.appendChild(head);
      if (ex.kind === "frame") {
        if (ex.name) card.appendChild(el("strong", null, ex.name));
        if (ex.note) card.appendChild(el("p", null, ex.note));
        if (ex.shape) {
          card.appendChild(el("p", "wb-meta",
              ex.shape[0] + " × " + ex.shape[1]
              + (ex.shape[0] > (ex.rows || []).length
                 ? " (first " + (ex.rows || []).length + " shown)" : "")));
        }
        card.appendChild(smallTable(ex.columns || [], ex.rows || [], 10));
      } else if (ex.kind === "binding") {
        card.appendChild(el("p", null, "binding: " + ex.name));
        if (ex.note) card.appendChild(el("p", "wb-meta", ex.note));
      } else if (ex.kind === "auto") {
        card.appendChild(el("p", "wb-meta", ex.text));
      } else {
        var text = ex.text || "";
        if (text.indexOf("\\n") !== -1) {
          card.appendChild(el("pre", null, text));
        } else {
          card.appendChild(el("p", null, text));
        }
        if (ex.note) card.appendChild(el("p", "wb-meta", ex.note));
      }
      host.appendChild(card);
    });
  }

  function renderCode(state) {
    var host = document.getElementById("wb-code");
    host.textContent = "";
    ["report.json", "report.py", "script.js"].forEach(function (label) {
      var text = (state.code || {})[label];
      if (!text) return;
      host.appendChild(el("h3", null, label));
      host.appendChild(el("pre", null, text));
    });
  }

  function renderLint(state) {
    var host = document.getElementById("wb-lint");
    host.textContent = "";
    var ul = el("ul");
    ul.appendChild(el("li", null,
        state.lint.numeric_literals_outside_figures
        + " numeric literal(s) in prose outside figures"));
    ul.appendChild(el("li", null, state.unused_bindings.length
        + " unused binding(s)"
        + (state.unused_bindings.length
           ? ": " + state.unused_bindings.join(", ") : "")));
    var unbound = state.figures.filter(function (f) { return f.unbound; });
    ul.appendChild(el("li", null, unbound.length + " unbound figure(s)"
        + (unbound.length
           ? ": " + unbound.map(function (f) { return f.id; }).join(", ")
           : "")));
    host.appendChild(ul);
    host.appendChild(el("p", "wb-meta",
        "non-blocking — the final build enforces; the workbench points."));
  }

  function render(state) {
    document.getElementById("wb-title").textContent =
        state.name + " — workbench";
    document.title = state.name + " — workbench";
    var err = document.getElementById("wb-error");
    err.textContent = "";
    var problem = state.error || state.render_error;
    if (problem) err.appendChild(el("pre", "wb-error", problem));
    renderFigures(state);
    renderData(state);
    renderFeed(state);
    renderCode(state);
    renderLint(state);
  }

  function refresh() {
    return fetch("/__workbench/state.json")
      .then(function (r) { return r.text(); })
      .then(function (text) {
        if (text === last) return;
        last = text;
        render(JSON.parse(text));
      })
      .catch(function () {});
  }

  refresh();
  setInterval(refresh, 2000);
})();
</script>
</body></html>"""


def _workbench_page(name: str) -> str:
    """The workbench shell, styled by the shipped design system. Static —
    all data arrives via /__workbench/state.json polling."""
    from tracebi.reports.embed import read_lib
    from tracebi.reports.stack import read_asset

    return (_WORKBENCH_PAGE
            .replace("__NAME__", json.dumps(name))
            .replace("__TRACEBI_CSS__", read_asset("tracebi.css"))
            .replace("__ECHARTS__", read_lib("echarts")))


# ── The server ──────────────────────────────────────────────────────────────


def serve_dev(
    target,
    port: int = 8001,
    open_browser: bool = True,
    poll_interval: float = 0.5,
) -> int:
    """Serve *target* with live reload until Ctrl+C. Returns an exit code.

    *target* is an artifact package directory (``reports/<name>/``) or a
    legacy request script file — the form decides the loop.
    """
    target_path = Path(target)
    if target_path.is_dir():
        t: _PackageTarget | _RequestTarget = _PackageTarget(target_path)
    else:
        print("  note: request-script dev is deprecated (requests/ is the "
              "unverified lane, removed in 0.8) — build an artifact under "
              "reports/<name>/ and `tracebi dev <name>` instead.")
        t = _RequestTarget(target_path)
    return _serve(t, port=port, open_browser=open_browser,
                  poll_interval=poll_interval)


def _serve(t, port: int, open_browser: bool, poll_interval: float) -> int:
    from tracebi import workbench as _wb

    # No bytecode for hot-reloaded project files: a .pyc written by this
    # process would be judged "still valid" against a same-second, same-size
    # edit of a model file (mtime compares in whole seconds), and the rebuild
    # would silently exec stale code — the one failure a dev loop must not
    # have.
    sys.dont_write_bytecode = True

    state = {"html": t.render(), "version": 0}
    lock = threading.Lock()
    wb_cache: dict = {}
    wb_page = _workbench_page(t.label) if t.workbench else ""

    def watch():
        last_sig = _scan_signature(t.watch_paths())
        stop = threading.Event()
        while not stop.wait(poll_interval):
            sig = _scan_signature(t.watch_paths())
            if sig != last_sig:
                last_sig = sig
                html = t.render()
                with lock:
                    state["html"] = html
                    state["version"] += 1
                print(f"  Reloaded {t.label} (v{state['version']})")

    def workbench_state() -> dict:
        # Recomputed only when the report version or the feed/pin files
        # moved — a 2s poll must not re-run the bindings' queries.
        with lock:
            version = state["version"]
        key = (version,
               _file_sig(os.path.join(t.wb_dir, _wb.EXHIBITS_FILE)),
               _file_sig(os.path.join(t.wb_dir, _wb.PINS_FILE)))
        if wb_cache.get("key") != key:
            wb_cache["key"] = key
            wb_cache["state"] = t.state()
        return wb_cache["state"]

    class _Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, body: bytes, ctype: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/__status":
                with lock:
                    body = json.dumps({"version": state["version"]}).encode()
                self._send(body, "application/json")
                return
            if t.workbench and self.path == "/__workbench":
                self._send(wb_page.encode(), "text/html; charset=utf-8")
                return
            if t.workbench and self.path == "/__workbench/state.json":
                body = json.dumps(workbench_state(), default=str).encode()
                self._send(body, "application/json")
                return
            with lock:
                body = _inject_refresh(state["html"], state["version"]).encode()
            self._send(body, "text/html; charset=utf-8")

        def do_POST(self):
            if not (t.workbench
                    and self.path in ("/__workbench/pin", "/__workbench/unpin")):
                self._send(b'{"error": "not found"}', "application/json", 404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                payload = {}
            pin_id = payload.get("id")
            if not pin_id:
                self._send(b'{"error": "missing id"}', "application/json", 400)
                return
            with lock:
                pins = [p for p in _wb.read_pins(t.wb_dir)
                        if p.get("id") != pin_id]
                if self.path == "/__workbench/pin":
                    pins.append({"id": pin_id,
                                 "note": payload.get("note") or "",
                                 "at_seq": _wb.last_seq(t.wb_dir)})
                _wb.write_pins(t.wb_dir, pins)
            self._send(json.dumps({"ok": True, "pins": pins}).encode(),
                       "application/json")

        def log_message(self, fmt, *args):  # silence request logs
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()

    url = f"http://127.0.0.1:{port}"
    print(f"\n  TraceBi dev — watching {t.label}")
    print(f"  Preview at {url} (reloads on save)")
    if t.workbench:
        print(f"  Workbench at {url}/__workbench")
    print("  Press Ctrl+C to stop.\n")
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Dev server stopped.")
    finally:
        server.server_close()
    return 0
