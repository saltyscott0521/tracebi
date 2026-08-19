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

**No target at all** (``tracebi dev`` with no name) is DISCOVERY MODE: no
report is anchored, and the workbench IS the site — the live surface for
phase ① (interrogating source data) and phase ② (designing the model). It
renders the warehouse's tables and sink-contract summaries, every model's
declared star schema, and the report packages that exist; the server
heartbeats ``.tracebi/workbench/_discovery/.active`` each watcher tick so
ANY script run in the project can post to the exhibit feed via
``tracebi.workbench.show`` with zero configuration (see the heartbeat rule
in ``tracebi/workbench.py``).

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


def _host_is_local(host_header: str) -> bool:
    """Whether a ``Host`` header names a loopback address — the DNS-rebinding
    guard. A browser pointed at a malicious domain that resolves to 127.0.0.1
    sends that domain as ``Host``; only localhost / 127.0.0.1 / [::1] (and an
    absent header) are legitimate for this local dev server.
    """
    if host_header.startswith("["):              # IPv6 literal, e.g. [::1]:port
        bare = host_header.split("]", 1)[0].lstrip("[")
    else:
        bare = host_header.rsplit(":", 1)[0]
    return bare in ("localhost", "127.0.0.1", "::1", "")


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
    discovery = False

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.label = self.path.name

    def render(self) -> str:
        # Same dev-only CSP relaxation as the package form: the reload poll
        # needs connect-src 'self'; only served pages are touched.
        return render_request(self.path).replace(
            "connect-src 'none'", "connect-src 'self'", 1)

    def watch_paths(self) -> list[Path]:
        return [self.path]


class _PackageTarget:
    """An artifact package — the in-memory exploration render + workbench."""

    workbench = True
    discovery = False

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
        # Dev-only CSP relaxation: the shipped page's connect-src 'none'
        # would block the /__status reload poll, silently killing the live
        # loop. Served pages may talk to THIS server and nothing else; the
        # built artifact keeps the strict policy untouched.
        return page.replace("connect-src 'none'", "connect-src 'self'", 1)

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


class _DiscoveryTarget:
    """Discovery mode — no report anchored; the workbench IS the site."""

    workbench = True
    discovery = True

    def __init__(self) -> None:
        from tracebi.workbench import DISCOVERY_NAME, discovery_dir

        self.name = DISCOVERY_NAME
        self.label = "discovery"
        self.wb_dir = discovery_dir(os.getcwd())

    def render(self) -> str:
        # In discovery there is no report to preview — the root just points
        # at the workbench.
        return ('<!DOCTYPE html>\n<html><head><meta charset="UTF-8">'
                '<meta http-equiv="refresh" content="0; url=/__workbench">'
                '<title>tracebi dev — discovery</title></head>'
                '<body><p><a href="/__workbench">workbench</a></p>'
                '</body></html>')

    def watch_paths(self) -> list[Path]:
        # data/ is watched so a sink landing bumps the version and the
        # workbench page refreshes with the new tables.
        return [
            Path(os.environ.get("TRACEBI_TRANSFORMS_DIR", "transforms")),
            Path(os.environ.get("TRACEBI_MODELS_DIR", "models")),
            Path(os.environ.get("TRACEBI_REPORTS_DIR", "reports")),
            Path("data"),
        ]

    def state(self) -> dict:
        """collect_discovery_state, degraded to an error state rather than
        a 500 when even collecting fails (mirrors _PackageTarget.state)."""
        from tracebi.workbench import collect_discovery_state

        try:
            return collect_discovery_state(os.getcwd(), _project_models())
        except Exception as exc:  # noqa: BLE001 — the panel must show the break
            return {
                "mode": "discovery",
                "name": self.name,
                "error": f"{type(exc).__name__}: {exc}",
                "warehouse": {"path": "", "exists": False, "tables": [],
                              "contracts": None},
                "models": [], "packages": [], "exhibits": [], "pins": [],
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
__CSP__
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
manifests, and no receipts are minted here.
<a id="wb-preview-link" href="/">← report preview</a></p>
<div id="wb-error"></div>
<section id="wb-sec-figures">
<h2>Figures</h2>
<div id="wb-coverage"></div>
<div id="wb-figures"></div>
</section>
<section id="wb-sec-data">
<h2>Data</h2>
<div id="wb-data"></div>
</section>
<section id="wb-sec-warehouse" hidden>
<h2>Warehouse</h2>
<div id="wb-warehouse"></div>
</section>
<section id="wb-sec-models" hidden>
<h2>Models</h2>
<div id="wb-models"></div>
</section>
<section id="wb-sec-packages" hidden>
<h2>Packages</h2>
<div id="wb-packages"></div>
</section>
<section id="wb-sec-feed">
<h2>Feed</h2>
<div id="wb-feed"></div>
</section>
<section id="wb-sec-code">
<h2>Code</h2>
<div id="wb-code"></div>
</section>
<section id="wb-sec-lint">
<h2>Lint</h2>
<div id="wb-lint"></div>
</section>
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

  function smallTable(columns, rows, cap, sortable) {
    var wrap = el("div", "wb-table-wrap");
    var t = el("table", "tb-table tb-table--compact");
    var thead = el("thead");
    var tr = el("tr");
    var tbody = el("tbody");
    var shown = rows.slice(0, cap || rows.length);
    var sortCol = null;
    var sortAsc = true;

    function fill(list) {
      tbody.textContent = "";
      list.forEach(function (r) {
        var tr2 = el("tr");
        columns.forEach(function (c) {
          var v = r[c];
          tr2.appendChild(el("td", typeof v === "number" ? "tb-num" : null,
                             v === null || v === undefined ? "" : v));
        });
        tbody.appendChild(tr2);
      });
    }

    function isNum(v) {
      return v !== null && v !== undefined && v !== "" && !isNaN(Number(v));
    }

    columns.forEach(function (c) {
      var th = el("th", null, c);
      if (sortable) {
        /* Sorting is presentation of the excerpt only — it reorders the
           rows already on screen, never the data they came from. */
        th.style.cursor = "pointer";
        th.addEventListener("click", function () {
          sortAsc = sortCol === c ? !sortAsc : true;
          sortCol = c;
          var sorted = shown.slice().sort(function (ra, rb) {
            var a = ra[c], b = rb[c];
            var d;
            if (isNum(a) && isNum(b)) d = Number(a) - Number(b);
            else d = String(a) < String(b) ? -1
                                           : (String(a) > String(b) ? 1 : 0);
            return sortAsc ? d : -d;
          });
          fill(sorted);
        });
      }
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    t.appendChild(thead);
    fill(shown);
    t.appendChild(tbody);
    wrap.appendChild(t);
    return wrap;
  }

  function profileToggle(profile, note) {
    /* The per-column stats card, collapsed behind a button. A null profile
       (capped or failed upstream) shows only its note. */
    if (!profile) {
      return note ? el("p", "wb-meta", note) : null;
    }
    var wrap = el("div");
    var cols = ["column", "dtype", "nulls", "distinct",
                "min", "max", "mean", "top"];
    var rows = Object.keys(profile).map(function (c) {
      var p = profile[c] || {};
      return {column: c, dtype: p.dtype, nulls: p.nulls,
              distinct: p.distinct, min: p.min, max: p.max, mean: p.mean,
              top: (p.top || []).join(", ")};
    });
    var body = smallTable(cols, rows);
    body.style.display = "none";
    var btn = button("profile", null, function () {
      var open = body.style.display !== "none";
      body.style.display = open ? "none" : "block";
      btn.textContent = open ? "profile" : "hide profile";
    });
    wrap.appendChild(btn);
    wrap.appendChild(body);
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

  /* One ECharts option builder for every workbench chart surface — the
     quick-chart picker and chart exhibits share it, so a sketch's recipe
     has exactly one rendering. kind is the runtime's vocabulary
     (bar/barh/line/area/pie/scatter); ys is a list of y columns. */
  function chartOption(kind, x, ys, rows) {
    if (kind === "pie") {
      return {series: [{type: "pie", radius: "70%",
                        data: rows.map(function (r) {
                          return {name: String(r[x]), value: r[ys[0]]};
                        })}]};
    }
    var grid = {top: 16, right: 16, bottom: 48, left: 72};
    if (kind === "scatter") {
      return {grid: grid,
              xAxis: {type: "value"}, yAxis: {type: "value"},
              series: ys.map(function (y) {
                return {type: "scatter",
                        data: rows.map(function (r) { return [r[x], r[y]]; })};
              })};
    }
    var catAxis = {type: "category",
                   data: rows.map(function (r) { return String(r[x]); })};
    var valAxis = {type: "value"};
    return {grid: grid,
            xAxis: kind === "barh" ? valAxis : catAxis,
            yAxis: kind === "barh" ? catAxis : valAxis,
            series: ys.map(function (y) {
              var s = {type: kind === "line" || kind === "area" ? "line" : "bar",
                       data: rows.map(function (r) { return r[y]; })};
              if (kind === "area") s.areaStyle = {};
              return s;
            })};
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
      chart.setOption(chartOption("bar", x, [y], binding.preview));
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

  function exhibitFrame(card, ex) {
    if (ex.name) card.appendChild(el("strong", null, ex.name));
    if (ex.note) card.appendChild(el("p", null, ex.note));
    if (ex.shape) {
      card.appendChild(el("p", "wb-meta",
          ex.shape[0] + " × " + ex.shape[1]
          + (ex.shape[0] > (ex.rows || []).length
             ? " (first " + (ex.rows || []).length + " shown)" : "")));
    }
    card.appendChild(smallTable(ex.columns || [], ex.rows || [], 10, true));
    var prof = profileToggle(ex.profile);
    if (prof) card.appendChild(prof);
  }

  function exhibitChart(card, ex) {
    var recipe = ex.recipe || {};
    var ys = recipe.y || [];
    if (!window.echarts || !window.echarts.init || !recipe.chart) {
      /* No ECharts (or a torn entry) — degrade to the frame-table
         rendering, never a blank card. */
      exhibitFrame(card, ex);
      return;
    }
    if (ex.name) card.appendChild(el("strong", null, ex.name));
    var chartDiv = el("div", "wb-chart");
    card.appendChild(chartDiv);
    var option = chartOption(recipe.chart, recipe.x, ys, ex.rows || []);
    if (ex.note) option.title = {text: ex.note, textStyle: {fontSize: 13}};
    /* init after the card lands in the DOM, or ECharts sees width 0. */
    setTimeout(function () {
      window.echarts.init(chartDiv).setOption(option);
    }, 0);
    card.appendChild(el("p", "wb-meta",
        recipe.chart + " · x: " + recipe.x + " · y: " + ys.join(", ")
        + " — the sketch's recipe; promotion = re-expressing it as a "
        + "binding + figure"));
    var prof = profileToggle(ex.profile);
    if (prof) card.appendChild(prof);
  }

  /* Feed order: a log reads newest-first; a notebook reads top-down. The
     toggle is presentation only — seq order is the truth either way. */
  var feedChronological = false;

  function renderFeed(state) {
    var host = document.getElementById("wb-feed");
    host.textContent = "";
    if (!state.exhibits.length) {
      host.appendChild(el("p", "wb-meta", "nothing shown yet — call "
          + "tracebi.workbench.show(...) from report.py, or save to see "
          + "binding updates land here"));
      return;
    }
    host.appendChild(button(
      feedChronological ? "newest first" : "read as document", null,
      function () { feedChronological = !feedChronological; renderFeed(state); }
    ));
    var exhibits = state.exhibits.slice();
    if (feedChronological) exhibits.reverse();
    exhibits.forEach(function (ex) {
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
        exhibitFrame(card, ex);
      } else if (ex.kind === "chart") {
        exhibitChart(card, ex);
      } else if (ex.kind === "binding") {
        card.appendChild(el("p", null, "binding: " + ex.name));
        if (ex.note) card.appendChild(el("p", "wb-meta", ex.note));
      } else if (ex.kind === "auto") {
        card.appendChild(el("p", "wb-meta", ex.text));
      } else {
        if (ex.html) {
          /* The ONE innerHTML exception on this page: ex.html is produced
             server-side by the escaped-first markdown subset
             (render_note_markdown), so a note reads like a notebook cell
             while content can never smuggle live markup. */
          var md = el("div", "wb-md");
          md.innerHTML = ex.html;
          card.appendChild(md);
        } else {
          var text = ex.text || "";
          if (text.indexOf("\\n") !== -1) {
            card.appendChild(el("pre", null, text));
          } else {
            card.appendChild(el("p", null, text));
          }
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

  /* ── Discovery mode: no report anchored — phases ① and ② live here. ── */

  function renderWarehouse(state) {
    var host = document.getElementById("wb-warehouse");
    host.textContent = "";
    var wh = state.warehouse || {};
    if (wh.error) host.appendChild(el("pre", "wb-error", wh.error));
    if (!wh.exists) {
      host.appendChild(el("p", "wb-meta",
          "no warehouse yet — run a transform"));
      return;
    }
    host.appendChild(el("p", "wb-meta", wh.path));
    var tables = wh.tables || [];
    tables.forEach(function (tb) {
      var card = el("div", "wb-card");
      var head = el("div", "wb-row");
      head.appendChild(el("strong", null, tb.name));
      head.appendChild(el("span", "wb-meta", tb.rows + " rows"));
      /* Same pin mechanism as figures — a warehouse table pins by the
         stable id "table-<name>". */
      var pid = "table-" + tb.name;
      head.appendChild(pinBtn(pid, state.pins.some(function (p) {
        return p.id === pid;
      })));
      card.appendChild(head);
      if (tb.error) card.appendChild(el("pre", "wb-error", tb.error));
      var cols = tb.columns || {};
      card.appendChild(el("p", "wb-meta",
          Object.keys(cols).map(function (c) {
            return c + ": " + cols[c];
          }).join("  ·  ")));
      var prof = profileToggle(tb.profile, tb.note);
      if (prof) card.appendChild(prof);
      host.appendChild(card);
    });
    if (!tables.length) {
      host.appendChild(el("p", "wb-meta", "the warehouse has no tables"));
    }
    var contracts = wh.contracts || {};
    Object.keys(contracts).forEach(function (t) {
      var c = contracts[t];
      /* Locked language: the SINK satisfied its contract — this line
         certifies the landed tables, never the transform's pandas. */
      host.appendChild(el("p", "wb-meta",
          "sink contract " + t + " · " + c.checks + " checks passed"
          + (c.checked_at ? " · " + c.checked_at : "")
          + " · tables: " + (c.tables || []).join(", ")));
    });
  }

  function renderModels(state) {
    var host = document.getElementById("wb-models");
    host.textContent = "";
    var models = state.models || [];
    if (!models.length) {
      host.appendChild(el("p", "wb-meta",
          "no models yet — tracebi new-model"));
      return;
    }
    function names(list) {
      return (list || []).map(function (x) { return x.name; }).join(", ");
    }
    models.forEach(function (m) {
      var card = el("div", "wb-card");
      var head = el("div", "wb-row");
      head.appendChild(el("strong", null, m.name));
      card.appendChild(head);
      if (m.error !== undefined) {
        card.appendChild(el("pre", "wb-error", m.error));
        host.appendChild(card);
        return;
      }
      card.appendChild(el("p", "wb-meta", "facts: " + (names(m.facts) || "—")));
      card.appendChild(el("p", "wb-meta",
          "dimensions: " + (names(m.dimensions) || "—")));
      card.appendChild(el("p", "wb-meta",
          "measures: " + (names(m.measures) || "—")));
      host.appendChild(card);
    });
  }

  function renderPackages(state) {
    var host = document.getElementById("wb-packages");
    host.textContent = "";
    var packages = state.packages || [];
    if (!packages.length) {
      host.appendChild(el("p", "wb-meta",
          "no packages yet — tracebi new-report \\"My Report\\""));
      return;
    }
    packages.forEach(function (name) {
      var row = el("div", "wb-row");
      row.appendChild(el("strong", null, name));
      row.appendChild(el("span", "wb-meta", "tracebi dev " + name));
      host.appendChild(row);
    });
  }

  function setMode(discovery) {
    ["figures", "data", "code", "lint"].forEach(function (id) {
      document.getElementById("wb-sec-" + id).hidden = discovery;
    });
    ["warehouse", "models", "packages"].forEach(function (id) {
      document.getElementById("wb-sec-" + id).hidden = !discovery;
    });
    document.getElementById("wb-preview-link").hidden = discovery;
  }

  function render(state) {
    var discovery = state.mode === "discovery";
    setMode(discovery);
    var title = discovery ? "discovery workbench"
                          : state.name + " — workbench";
    document.getElementById("wb-title").textContent = title;
    document.title = title;
    var err = document.getElementById("wb-error");
    err.textContent = "";
    var problem = state.error || state.render_error;
    if (problem) err.appendChild(el("pre", "wb-error", problem));
    if (discovery) {
      renderWarehouse(state);
      renderModels(state);
      renderPackages(state);
      renderFeed(state);
      return;
    }
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
    from tracebi.reports.embed import CSP, read_lib
    from tracebi.reports.stack import read_asset

    # Defense-in-depth for the ONE innerHTML on this page (md_to_html output):
    # the escaping in _inline is the real protection, but unlike the built
    # artifact this page carried no CSP. Add one, relaxing connect-src to 'self'
    # for the /__workbench/state.json poll (as the served exploration page does).
    csp = CSP.replace("connect-src 'none'", "connect-src 'self'")
    csp_meta = f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
    return (_WORKBENCH_PAGE
            .replace("__CSP__", csp_meta)
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

    *target* is an artifact package directory (``reports/<name>/``), a
    legacy request script file, or ``None`` — discovery mode: no report
    anchored, the project-level workbench served for phases ① and ②.
    """
    if target is None:
        return _serve(_DiscoveryTarget(), port=port,
                      open_browser=open_browser, poll_interval=poll_interval)
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
        # Discovery liveness: the heartbeat is what lets a script's show()
        # post with no env var — touched every tick, stale within seconds
        # of Ctrl+C (the rule in tracebi/workbench.py).
        if t.discovery:
            _wb.heartbeat(t.wb_dir)
        last_sig = _scan_signature(t.watch_paths())
        stop = threading.Event()
        while not stop.wait(poll_interval):
            if t.discovery:
                _wb.heartbeat(t.wb_dir)
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

        def _host_ok(self) -> bool:
            # Block DNS rebinding: a malicious domain resolving to 127.0.0.1
            # could otherwise read the rich /__workbench/state.json.
            return _host_is_local(self.headers.get("Host", ""))

        def do_GET(self):
            if not self._host_ok():
                self._send(b'{"error": "host not allowed"}',
                           "application/json", 403)
                return
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
            if not self._host_ok():
                self._send(b'{"error": "host not allowed"}',
                           "application/json", 403)
                return
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
    if t.discovery:
        print("\n  TraceBi dev — discovery mode (no report anchored)")
        print(f"  Workbench at {url}/__workbench")
        print("  Exhibits: any script you run can call "
              "tracebi.workbench.show(df, note=...) while this server is "
              "up — no env var needed (or set TRACEBI_WORKBENCH_DIR=<dir> "
              "explicitly).")
    else:
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
