"""
The presentation runtime asset — tracebi/reports/assets/tracebi.js (M2).

The runtime ships inside self-contained HTML under the strict CSP, so the
asset must be dependency-free, eval-free, and must never build markup from
data. Its number formatter is a JS port of ``ChartSpec._fmt`` — the one
implementation of "550.7B" — so when node is available the two are compared
byte-for-byte on the values where the port could plausibly drift (unit
boundaries, mantissa rollover, negatives, trailing-zero trimming).
"""

import json
import os
import shutil
import subprocess

import pytest

import tracebi.reports
from tracebi.reports.chart import ChartSpec

ASSET = os.path.join(
    os.path.dirname(tracebi.reports.__file__), "assets", "tracebi.js"
)

#: (value, compact) pairs covering the honesty rules: rounded-value unit
#: boundaries (999999.99 → "1M", never "1000K"), K→M→B→T mantissa rollover,
#: integer thousands separators, and trailing-zero trimming.
COMPACT_VALUES = [
    0,
    123,
    999.999,
    1234.5,
    999999,
    999999.99,
    2400240.38,
    550696024575,
    -1500000,
    1e12 * 1.5,
]


class TestAssetHygiene:
    def test_asset_exists_and_under_size_budget(self):
        assert os.path.isfile(ASSET), f"runtime asset missing at {ASSET}"
        # 25 KiB → 26 KiB when the badge anchor (tables) and the scatter /
        # tooltip valueFormat coverage landed; → 44 KiB when the control
        # grammar (filters/search), scrollable tables, the verbatim CSV
        # download, tabs, and the receipt drawer landed — behavior, not bloat.
        assert os.path.getsize(ASSET) < 44 * 1024

    def test_no_eval(self):
        with open(ASSET, encoding="utf-8") as f:
            src = f.read()
        assert "eval(" not in src

    def test_no_innerhtml(self):
        # Data reaches the DOM only via textContent / ECharts — never markup.
        with open(ASSET, encoding="utf-8") as f:
            src = f.read()
        assert src.count("innerHTML") == 0

    def test_public_api_defined(self):
        with open(ASSET, encoding="utf-8") as f:
            src = f.read()
        # The one global, with the three public entry points.
        assert "root.tracebi" in src
        for member in ("data: data", "fmt: fmt", "configureChart: configureChart"):
            assert member in src, f"public API member missing: {member}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestFmtParity:
    """tracebi.fmt must agree byte-for-byte with ChartSpec._fmt."""

    def _js_fmt(self, cases):
        """Run tracebi.fmt in node for [(value, mode), ...] → list of strings."""
        script = (
            "require(process.argv[1]);"
            "var cases = JSON.parse(process.argv[2]);"
            "var out = cases.map(function (c) {"
            "  return globalThis.tracebi.fmt(c[0], c[1] || undefined);"
            "});"
            "process.stdout.write(JSON.stringify(out));"
        )
        result = subprocess.run(
            ["node", "-e", script, ASSET, json.dumps(cases)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def test_compact_parity(self):
        expected = [ChartSpec._fmt(v, compact=True) for v in COMPACT_VALUES]
        actual = self._js_fmt([[v, "compact"] for v in COMPACT_VALUES])
        assert actual == expected

    def test_non_compact_parity(self):
        assert self._js_fmt([[1234.5, None]]) == ["1,234.5"]
        assert ChartSpec._fmt(1234.5) == "1,234.5"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestSsrValueFormatParity:
    """The SSR fill formats value figures in Python; the runtime hydrates the
    same figure with applyNamedFormat. They MUST be byte-identical or a no-JS
    number and the hydrated one disagree — a visible flicker / a changed number.
    This pins _ssr_format against applyNamedFormat over a corpus that stresses
    half-to-even ties, negative zero, and large/small magnitudes.
    """

    NAMES = ["currency", "currency0", "comma", "decimal", "percent"]
    EDGES = [0, 1, -1, 0.5, -0.5, 1.5, 2.5, 3.5, -2.5, 1234.5, -1234.5,
             0.005, -0.005, 0.125, -0.125, 0.069, -0.3, -0.001, -0.00005,
             999.995, 1000000, 12345.678, -0.0]

    def _js(self, cases):
        script = (
            "var fs=require('fs');var src=fs.readFileSync(process.argv[1],'utf8');"
            "var p=src.replace('root.tracebi = {',"
            " 'root.tracebi = { applyNamedFormat: applyNamedFormat, toNum: toNum,');"
            "if(p===src) throw new Error('export line not found');"
            "new Function(p)();"
            "var cs=JSON.parse(process.argv[2]);"
            "process.stdout.write(JSON.stringify(cs.map(function(c){"
            "  return globalThis.tracebi.applyNamedFormat("
            "    globalThis.tracebi.toNum(c[0]), c[1]); })));"
        )
        r = subprocess.run(["node", "-e", script, ASSET, json.dumps(cases)],
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    def test_ssr_format_matches_the_runtime(self):
        from tracebi.reports.template_package import _ssr_format
        cases = [[v, n] for v in self.EDGES for n in self.NAMES]
        js = self._js(cases)
        for (v, n), expected in zip(cases, js):
            got = _ssr_format(v, n)
            assert got == expected, f"{v} {n}: python {got!r} != js {expected!r}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestChartValueFormat:
    """optionFor honors data-tb-value-format on every chart type and mode."""

    PIE_ROWS = [
        {"region": "US", "mv": "550696024575"},
        {"region": "EU", "mv": "1234.5"},
    ]

    def _probe(self, plan, rows, expr):
        """Build optionFor(plan, rows) under node; JSON-print `expr` over opt.

        optionFor is internal to the runtime's IIFE (the public global stays
        data/fmt/configureChart), so the harness exposes it by rewriting the
        export line of the source before executing it — the asset on disk is
        untouched, and a failed rewrite fails loudly below.
        """
        script = (
            "var fs = require('fs');"
            "var src = fs.readFileSync(process.argv[1], 'utf8');"
            "var patched = src.replace('root.tracebi = {',"
            " 'root.tracebi = { optionFor: optionFor,');"
            "if (patched === src) throw new Error('export line not found');"
            "new Function(patched)();"
            "var opt = globalThis.tracebi.optionFor("
            "JSON.parse(process.argv[2]), JSON.parse(process.argv[3]));"
            "process.stdout.write(JSON.stringify(" + expr + "));"
        )
        result = subprocess.run(
            ["node", "-e", script, ASSET, json.dumps(plan), json.dumps(rows)],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    def _pie_plan(self, value_format=None):
        plan = {"type": "pie", "x": "region", "y": ["mv"], "palette": []}
        if value_format is not None:
            plan["valueFormat"] = value_format
        return plan

    def test_pie_without_value_format_has_no_formatter(self):
        out = self._probe(
            self._pie_plan(), self.PIE_ROWS,
            "[typeof opt.series[0].label.formatter,"
            " typeof opt.tooltip.valueFormatter,"
            " opt.series[0].label.show]",
        )
        assert out == ["undefined", "undefined", True]

    def test_pie_label_and_tooltip_use_fmt(self):
        expected = ChartSpec._fmt(550696024575, compact=True)
        out = self._probe(
            self._pie_plan("compact"), self.PIE_ROWS,
            "[opt.series[0].label.formatter(opt.series[0].data[0]),"
            " opt.tooltip.valueFormatter(opt.series[0].data[0].value),"
            " opt.series[0].label.show]",
        )
        assert out == [f"US: {expected}", expected, True]

    def test_categorical_honors_non_compact_mode(self):
        plan = {"type": "bar", "x": "region", "y": ["mv"],
                "valueFormat": "currency", "palette": []}
        out = self._probe(
            plan, self.PIE_ROWS,
            "[opt.yAxis.axisLabel.formatter(1234.5),"
            " opt.series[0].label.formatter({value: 1234.5})]",
        )
        assert out == ["$1,234.50", "$1,234.50"]

    def test_unknown_mode_returns_raw_value(self):
        # The guard: an unknown mode never blanks a number.
        plan = {"type": "bar", "x": "region", "y": ["mv"],
                "valueFormat": "bogus", "palette": []}
        out = self._probe(
            plan, self.PIE_ROWS,
            "[opt.yAxis.axisLabel.formatter(1234.5),"
            " opt.series[0].label.formatter({value: 1234.5})]",
        )
        assert out == [1234.5, 1234.5]

    def test_cartesian_tooltip_uses_value_format(self):
        plan = {"type": "bar", "x": "region", "y": ["mv"],
                "valueFormat": "currency", "palette": []}
        out = self._probe(
            plan, self.PIE_ROWS, "[opt.tooltip.valueFormatter(1234.5)]")
        assert out == ["$1,234.50"]

    def test_cartesian_without_value_format_has_no_tooltip_formatter(self):
        plan = {"type": "bar", "x": "region", "y": ["mv"], "palette": []}
        out = self._probe(
            plan, self.PIE_ROWS, "[typeof opt.tooltip.valueFormatter]")
        assert out == ["undefined"]

    def test_scatter_axes_and_tooltip_use_value_format(self):
        plan = {"type": "scatter", "x": "mv", "y": ["mv"],
                "valueFormat": "compact", "palette": []}
        expected = ChartSpec._fmt(550696024575, compact=True)
        out = self._probe(
            plan, self.PIE_ROWS,
            "[opt.xAxis.axisLabel.formatter(550696024575),"
            " opt.yAxis.axisLabel.formatter(550696024575),"
            " opt.tooltip.valueFormatter(550696024575)]",
        )
        assert out == [expected, expected, expected]

    def test_scatter_without_value_format_unchanged(self):
        plan = {"type": "scatter", "x": "mv", "y": ["mv"], "palette": []}
        out = self._probe(
            plan, self.PIE_ROWS,
            "[typeof opt.xAxis.axisLabel, typeof opt.yAxis.axisLabel,"
            " typeof opt.tooltip.valueFormatter]",
        )
        assert out == ["undefined", "undefined", "undefined"]


# ── The control-grammar harness ──────────────────────────────────────────
# A DOM stub covering exactly the element surface the interactive runtime
# touches: compound + descendant selectors, attributes, events, Blob/URL,
# and an echarts stub that records every setOption/resize. The fixture is
# built BEFORE the runtime loads, so the load-time hydration pass exercises
# the real wiring; internals (filteredRows) are exposed by the same
# export-line rewrite _probe uses — the asset on disk is untouched.

_DOM_STUB = """
var fs = require('fs');

function El(tag) {
  this.tagName = String(tag).toUpperCase();
  this.attributes = {};
  this.children = [];
  this.parentNode = null;
  this.className = '';
  this.id = '';
  this.title = '';
  this.value = '';
  this.textContent = '';
  this.style = {};
  this._h = {};
}
El.prototype.getAttribute = function (n) {
  if (n === 'class') return this.className || null;
  if (n === 'id') return this.id || null;
  return Object.prototype.hasOwnProperty.call(this.attributes, n)
    ? this.attributes[n] : null;
};
El.prototype.setAttribute = function (n, v) {
  if (n === 'class') this.className = String(v);
  else if (n === 'id') this.id = String(v);
  else this.attributes[n] = String(v);
};
El.prototype.removeChild = function (c) {
  var i = this.children.indexOf(c);
  if (i !== -1) this.children.splice(i, 1);
  c.parentNode = null;
  return c;
};
El.prototype.appendChild = function (c) {
  if (c.parentNode) c.parentNode.removeChild(c);
  c.parentNode = this;
  this.children.push(c);
  return c;
};
El.prototype.insertBefore = function (c, ref) {
  if (c.parentNode) c.parentNode.removeChild(c);
  var i = ref ? this.children.indexOf(ref) : -1;
  if (i === -1) this.children.push(c); else this.children.splice(i, 0, c);
  c.parentNode = this;
  return c;
};
Object.defineProperty(El.prototype, 'firstChild', {
  get: function () { return this.children[0] || null; }
});
El.prototype.addEventListener = function (type, fn) {
  (this._h[type] = this._h[type] || []).push(fn);
};
El.prototype._fire = function (type) {
  var self = this;
  (this._h[type] || []).slice().forEach(function (fn) { fn({ target: self }); });
};
El.prototype.click = function () {
  (globalThis.__clicks = globalThis.__clicks || []).push(this);
  this._fire('click');
};

function parseCompound(src) {
  var out = { tag: null, classes: [], attrs: [] };
  var re = /([a-zA-Z][\\w-]*)|\\.([\\w-]+)|\\[([\\w-]+)(?:="([^"]*)")?\\]/g, m;
  while ((m = re.exec(src)) !== null) {
    if (m[1]) out.tag = m[1].toUpperCase();
    else if (m[2]) out.classes.push(m[2]);
    else out.attrs.push([m[3], m[4] === undefined ? null : m[4]]);
  }
  return out;
}
function matchesCompound(el, c) {
  if (c.tag && el.tagName !== c.tag) return false;
  var i, v;
  for (i = 0; i < c.classes.length; i++) {
    if ((' ' + el.className + ' ').indexOf(' ' + c.classes[i] + ' ') === -1) {
      return false;
    }
  }
  for (i = 0; i < c.attrs.length; i++) {
    v = el.getAttribute(c.attrs[i][0]);
    if (v === null) return false;
    if (c.attrs[i][1] !== null && v !== c.attrs[i][1]) return false;
  }
  return true;
}
function matchesSelector(el, parts) {
  if (!matchesCompound(el, parts[parts.length - 1])) return false;
  var i = parts.length - 2, node = el.parentNode;
  while (i >= 0 && node) {
    if (matchesCompound(node, parts[i])) i--;
    node = node.parentNode;
  }
  return i < 0;
}
function queryAll(rootEl, sel) {
  var parts = sel.split(/\\s+/).filter(Boolean).map(parseCompound);
  var out = [];
  (function walk(el) {
    el.children.forEach(function (c) {
      if (matchesSelector(c, parts)) out.push(c);
      walk(c);
    });
  })(rootEl);
  return out;
}
El.prototype.querySelectorAll = function (sel) { return queryAll(this, sel); };
El.prototype.querySelector = function (sel) {
  return queryAll(this, sel)[0] || null;
};

var ROOT = new El('html');
var BODY = new El('body');
ROOT.appendChild(BODY);
globalThis.document = {
  readyState: 'complete',
  body: BODY,
  createElement: function (t) { return new El(t); },
  querySelectorAll: function (sel) { return queryAll(ROOT, sel); },
  querySelector: function (sel) { return queryAll(ROOT, sel)[0] || null; },
  getElementById: function (id) {
    var found = null;
    (function walk(el) {
      if (found) return;
      if (el.id === id) { found = el; return; }
      for (var i = 0; i < el.children.length && !found; i++) walk(el.children[i]);
    })(ROOT);
    return found;
  },
  addEventListener: function () {}
};
globalThis.addEventListener = function () {};

globalThis.Blob = function (parts, opts) {
  this.parts = parts;
  this.opts = opts || {};
};
globalThis.URL = {
  createObjectURL: function (b) { globalThis.__lastBlob = b; return 'blob:tb'; },
  revokeObjectURL: function () {}
};
globalThis.__charts = [];
globalThis.echarts = {
  init: function (target) {
    var c = { el: target, options: [], resized: 0 };
    c.setOption = function (o) { c.options.push(o); };
    c.resize = function () { c.resized++; };
    globalThis.__charts.push(c);
    return c;
  }
};

function el(tag, attrs, parent) {
  var e = new El(tag);
  for (var k in (attrs || {})) e.setAttribute(k, attrs[k]);
  (parent || BODY).appendChild(e);
  return e;
}
function dataBlock(name, csv) {
  var s = el('script', { id: 'tracebi-data-' + name, type: 'application/json' });
  s.textContent = JSON.stringify({ name: name, csv: csv });
  return s;
}
function loadRuntime() {
  var src = fs.readFileSync(process.argv[1], 'utf8');
  var patched = src.replace('root.tracebi = {',
    'root.tracebi = { _filteredRows: filteredRows,');
  if (patched === src) throw new Error('export line not found');
  new Function(patched)();
}
function hasClass(e, cls) {
  return (' ' + e.className + ' ').indexOf(' ' + cls + ' ') !== -1;
}
function allText(e) {
  var t = e.textContent || '';
  e.children.forEach(function (c) { t += ' ' + allText(c); });
  return t;
}
"""


def _run_dom(fixture: str):
    """Execute _DOM_STUB + *fixture* under node; the fixture prints JSON."""
    result = subprocess.run(
        ["node", "-e", _DOM_STUB + fixture, ASSET],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestViewLayer:
    """Controls subset WHICH STAMPED ROWS figures display — never compute.

    Filters AND-combine per binding; search ANDs in on top; table and chart
    figures re-render through filteredRows; value figures never react (a
    filtered KPI would be client-side aggregation — forbidden).
    """

    _SCRIPT = """
var CSV = 'region,category,mv\\n' +
  'US,Bond,100\\nUS,Equity,200\\nEU,Equity,300\\nEU,Bond,150\\nAPAC,Equity,50\\n';
dataBlock('b', CSV);
var kpi = el('div', { 'data-tb-figure': 'value', 'data-tb-binding': 'b',
                      'data-tb-cell': 'mv' });
var tbl = el('table', { 'data-tb-figure': 'table', 'data-tb-binding': 'b' });
var cht = el('div', { 'data-tb-figure': 'chart', 'data-tb-binding': 'b',
                      'data-tb-x': 'region', 'data-tb-y': 'mv' });
var fRegion = el('select', { 'data-tb-filter': '', 'data-tb-binding': 'b',
                             'data-tb-column': 'region' });
var fCat = el('select', { 'data-tb-filter': '', 'data-tb-binding': 'b',
                          'data-tb-column': 'category' });
var search = el('input', { 'data-tb-search': '', 'data-tb-binding': 'b' });
var badSel = el('select', { 'data-tb-filter': '', 'data-tb-binding': 'nope',
                            'data-tb-column': 'x' });
loadRuntime();
var tb = globalThis.tracebi;
var tbody = tbl.querySelector('tbody');
var out = {
  kpi_initial: kpi.textContent,
  initial_rows: tbody.children.length,
  region_options: fRegion.children.map(function (o) { return o.textContent; }),
  chart_opts_initial: __charts[0].options.length,
  bad_title: badSel.title,
  bad_options: badSel.children.length,
  no_receipt_btn: BODY.querySelector('.tb-receipt-btn') === null
};

fRegion.value = 'US';
fRegion._fire('change');
out.rows_after_region = tbody.children.length;
out.chart_cats_after = __charts[0].options[1].xAxis.data;
out.kpi_after_filter = kpi.textContent;

fCat.value = 'Equity';
fCat._fire('change');
out.and_mv = tb._filteredRows('b').map(function (r) { return r.mv; });

search.value = 'BOND';
search._fire('input');
out.and_search_count = tb._filteredRows('b').length;
out.tbody_after_search = tbody.children.length;
out.tbody_after_search_text = tbody.children.length ? tbody.children[0].children[0].textContent : null;

fCat.value = 'All';
fCat._fire('change');
out.search_and_region_mv = tb._filteredRows('b')
  .map(function (r) { return r.mv; });
out.kpi_final = kpi.textContent;
process.stdout.write(JSON.stringify(out));
"""

    def test_filters_and_combine_with_search_and_value_figures_exempt(self):
        out = _run_dom(self._SCRIPT)
        # Load-time hydration: full stamped rows everywhere.
        assert out["kpi_initial"] == "100"
        assert out["initial_rows"] == 5
        # "All" plus the sorted distinct stamped values.
        assert out["region_options"] == ["All", "APAC", "EU", "US"]
        assert out["chart_opts_initial"] == 1
        # One filter: the table tbody and the chart re-render, subset only.
        assert out["rows_after_region"] == 2
        assert out["chart_cats_after"] == ["US"]
        # Two filters on one binding AND-combine: US ∧ Equity → the 200 row.
        assert out["and_mv"] == ["200"]
        # Search ANDs in (case-insensitive): US ∧ Equity ∧ "bond" → nothing.
        assert out["and_search_count"] == 0
        # A filter/search matching nothing shows a "no data" row, not a void.
        assert out["tbody_after_search"] == 1
        assert out["tbody_after_search_text"] == "no data"
        # Releasing one filter re-widens: US ∧ "bond" → the 100 row.
        assert out["search_and_region_mv"] == ["100"]
        # Value figures never react to controls — a filtered KPI needs its
        # own binding. The KPI text survives every control change above.
        assert out["kpi_after_filter"] == "100"
        assert out["kpi_final"] == "100"
        # Unknown binding: loudly-silent — a title note, nothing populated.
        assert "unknown binding" in out["bad_title"]
        assert out["bad_options"] == 0
        # No receipt block on this page → no drawer chrome.
        assert out["no_receipt_btn"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestScrollWrap:
    """Post-hydration scroll wrap: >N rows wraps, <=N and "all" do not."""

    _SCRIPT = """
function csvRows(n) {
  var s = 'k,v\\n';
  for (var i = 0; i < n; i++) s += 'k' + i + ',' + i + '\\n';
  return s;
}
dataBlock('big', csvRows(12));
dataBlock('small', csvRows(10));
dataBlock('optout', csvRows(12));
dataBlock('five', csvRows(6));
var big = el('table', { 'data-tb-figure': 'table', 'data-tb-binding': 'big' });
var small = el('table', { 'data-tb-figure': 'table',
                          'data-tb-binding': 'small' });
var optout = el('table', { 'data-tb-figure': 'table',
                           'data-tb-binding': 'optout',
                           'data-tb-rows': 'all' });
var five = el('table', { 'data-tb-figure': 'table', 'data-tb-binding': 'five',
                         'data-tb-rows': '5' });
loadRuntime();
process.stdout.write(JSON.stringify({
  big_parent_class: big.parentNode.className,
  big_max_height: big.parentNode.style.maxHeight || null,
  small_unwrapped: small.parentNode === BODY,
  optout_unwrapped: optout.parentNode === BODY,
  five_parent_class: five.parentNode.className,
  big_rows: big.querySelector('tbody').children.length
}));
"""

    def test_wrap_thresholds(self):
        out = _run_dom(self._SCRIPT)
        # 12 rows > the default 10 → wrapped, sized in em from the count.
        assert out["big_parent_class"] == "tb-scroll"
        assert out["big_max_height"] and out["big_max_height"].endswith("em")
        # Presentation only: every stamped row is still in the table.
        assert out["big_rows"] == 12
        # 10 rows <= the default 10 → untouched.
        assert out["small_unwrapped"] is True
        # data-tb-rows="all" opts out even at 12 rows.
        assert out["optout_unwrapped"] is True
        # An explicit data-tb-rows="5" wraps at 6 rows.
        assert out["five_parent_class"] == "tb-scroll"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestDownload:
    """The download button ships the embedded csv string byte-verbatim."""

    # Quoted commas and a trailing newline: any re-serialisation would
    # change these bytes and break the receipt.
    CSV = 'a,b\n"x,1",2\n'

    _SCRIPT = """
var CSV = %s;
dataBlock('dl', CSV);
var btn = el('button', { 'data-tb-download': '', 'data-tb-binding': 'dl' });
var lbl = el('button', { 'data-tb-download': '', 'data-tb-binding': 'dl',
                         'data-tb-label': 'Export' });
var bad = el('button', { 'data-tb-download': '', 'data-tb-binding': 'zzz' });
var fSel = el('select', { 'data-tb-filter': '', 'data-tb-binding': 'dl',
                          'data-tb-column': 'a' });
loadRuntime();
fSel.value = 'x,1';  /* activate a filter first: the download must ignore it */
fSel._fire('change');
btn._fire('click');
process.stdout.write(JSON.stringify({
  text_default: btn.textContent,
  text_label: lbl.textContent,
  blob_parts: globalThis.__lastBlob.parts,
  blob_type: globalThis.__lastBlob.opts.type,
  anchor_download: globalThis.__clicks[0].download,
  anchor_href: globalThis.__clicks[0].href,
  bad_title: bad.title,
  bad_handlers: (bad._h.click || []).length
}));
"""

    def test_verbatim_csv_blob(self):
        out = _run_dom(self._SCRIPT % json.dumps(self.CSV))
        assert out["text_default"] == "CSV"
        assert out["text_label"] == "Export"
        # Byte-verbatim: the embedded triple's csv string, even while a
        # filter is active — the receipt-preserving export, never the view.
        assert out["blob_parts"] == [self.CSV]
        assert out["blob_type"] == "text/csv"
        assert out["anchor_download"] == "dl.csv"
        assert out["anchor_href"] == "blob:tb"
        # Unknown binding: a title note, and no click handler wired.
        assert "unknown binding" in out["bad_title"]
        assert out["bad_handlers"] == 0


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestTabs:
    """The runtime builds the bar from labels; one section shows at a time."""

    _SCRIPT = """
var group = el('div', { 'class': 'tb-tabs' });
var s1 = el('section', { 'data-tb-tab': 'One' }, group);
var s2 = el('section', { 'data-tb-tab': 'Two' }, group);
dataBlock('t', 'x,y\\nA,1\\n');
el('div', { 'data-tb-figure': 'chart', 'data-tb-binding': 't',
            'data-tb-x': 'x', 'data-tb-y': 'y' }, s2);
loadRuntime();
var bar = group.children[0];
var out = {
  bar_class: bar.className,
  labels: bar.children.map(function (b) { return b.textContent; }),
  btn0_active: hasClass(bar.children[0], 'tb-tab-active'),
  s1_active: hasClass(s1, 'tb-tab-active'),
  s2_active: hasClass(s2, 'tb-tab-active'),
  resized_before: __charts[0].resized
};
bar.children[1]._fire('click');
out.btn1_active_after = hasClass(bar.children[1], 'tb-tab-active');
out.btn0_active_after = hasClass(bar.children[0], 'tb-tab-active');
out.s2_active_after = hasClass(s2, 'tb-tab-active');
out.s1_active_after = hasClass(s1, 'tb-tab-active');
out.resized_after = __charts[0].resized;
process.stdout.write(JSON.stringify(out));
"""

    def test_tab_bar_built_and_switches(self):
        out = _run_dom(self._SCRIPT)
        # The bar is inserted first, one button per labelled section.
        assert out["bar_class"] == "tb-tab-bar"
        assert out["labels"] == ["One", "Two"]
        # First tab active on load: button and section both marked.
        assert out["btn0_active"] is True
        assert out["s1_active"] is True
        assert out["s2_active"] is False
        # Switching moves the class pair and remeasures charts (a chart
        # hidden at init has no size until its section shows).
        assert out["btn1_active_after"] is True
        assert out["btn0_active_after"] is False
        assert out["s2_active_after"] is True
        assert out["s1_active_after"] is False
        assert out["resized_after"] > out["resized_before"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestReceiptDrawer:
    """The drawer renders ONLY what #tracebi-receipt records — display,
    never re-judged, in the locked language."""

    _SCRIPT = """
var FP = new Array(65).join('f');
var rc = el('script', { id: 'tracebi-receipt', type: 'application/json' });
rc.textContent = JSON.stringify({
  report: 'portfolio_book',
  rendered_at: '2026-08-17 09:00',
  git_sha: 'abc123d',
  figures: [
    { id: 'fig-a', kind: 'table', binding: 'holdings', fingerprint: FP },
    { id: 'fig-b', kind: 'chart', unverified: true }
  ],
  transform_contracts: {
    fact_holdings: { status: 'satisfied' },
    dim_sector: { status: 'stale' },
    dim_misc: { status: 'no_contract' }
  },
  semantic_contract_models: ['portfolio_model'],
  methodology: true
});
loadRuntime();
var btn = BODY.querySelector('.tb-receipt-btn');
var drawer = BODY.querySelector('.tb-receipt-drawer');
var rows = drawer.querySelectorAll('.tb-receipt-row');
var out = {
  btn_text: btn.textContent,
  closed_on_load: !hasClass(drawer, 'tb-receipt-open'),
  head_text: drawer.querySelector('.tb-receipt-head').textContent,
  a_text: allText(rows[0]),
  a_fp_text: rows[0].querySelector('.tb-receipt-fp').textContent,
  a_fp_title: rows[0].querySelector('.tb-receipt-fp').title,
  b_badge_class: rows[1].querySelector('.tb-badge')
    ? rows[1].querySelector('.tb-badge').className : null,
  b_badge_text: rows[1].querySelector('.tb-badge')
    ? rows[1].querySelector('.tb-badge').textContent : null,
  drawer_text: allText(drawer)
};
btn._fire('click');
out.open_after_click = hasClass(drawer, 'tb-receipt-open');
btn._fire('click');
out.closed_after_second = !hasClass(drawer, 'tb-receipt-open');
process.stdout.write(JSON.stringify(out));
"""

    def test_drawer_rows_from_sample_block(self):
        out = _run_dom(self._SCRIPT)
        assert out["btn_text"] == "Receipt"
        assert out["closed_on_load"] is True
        assert out["head_text"] == "portfolio_book"
        # Figure row: id · kind · binding, fingerprint 12 chars + full title.
        for piece in ("fig-a", "table", "holdings"):
            assert piece in out["a_text"]
        assert out["a_fp_text"] == "f" * 12
        assert out["a_fp_title"] == "f" * 64
        # The unverified row carries the existing badge tone, untouched.
        assert out["b_badge_class"] == "tb-badge tb-badge--unverified"
        assert out["b_badge_text"] == "unverified"
        text = out["drawer_text"]
        assert "rendered 2026-08-17 09:00" in text
        assert "git abc123d" in text
        # The locked language, per recorded status — never re-colored, and
        # never "the transform was verified".
        assert "fact_holdings: the sink satisfied its contract" in text
        assert "dim_sector: contract stale" in text
        assert "dim_misc: no contract" in text
        assert "the transform was verified" not in text
        assert "semantic contract: portfolio_model" in text
        assert "stated methodology aboard" in text
        # The button toggles the drawer open and closed again.
        assert out["open_after_click"] is True
        assert out["closed_after_second"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
class TestBadgeAnchoring:
    """hydrateBadges pins a table's badge to the table, not the page.

    A <table> is not a reliable containing block for the absolute .tb-badge
    (tracebi.css positions it top/right against the nearest positioned
    ancestor — with a static table that is the page corner), so the runtime
    wraps the table in a positioned .tb-badge-anchor div and badges that.
    There was no DOM stub in this harness before; the stub below covers
    exactly the element surface hydrateBadges touches, nothing more.
    """

    # hydrateBadges is internal to the IIFE; exposed by the same
    # export-line rewrite _probe uses. The stub document must exist before
    # the runtime loads (it schedules hydration at load); the fixture is
    # registered after, so the load-time pass sees an empty page.
    _SCRIPT = """
var fs = require('fs');

function El(tag) {
  this.tagName = String(tag).toUpperCase();
  this.children = [];
  this.parentNode = null;
  this.className = '';
  this.textContent = '';
}
El.prototype.removeChild = function (c) {
  var i = this.children.indexOf(c);
  if (i !== -1) this.children.splice(i, 1);
  c.parentNode = null;
  return c;
};
El.prototype.appendChild = function (c) {
  if (c.parentNode) c.parentNode.removeChild(c);
  c.parentNode = this;
  this.children.push(c);
  return c;
};
El.prototype.insertBefore = function (c, ref) {
  if (c.parentNode) c.parentNode.removeChild(c);
  var i = ref ? this.children.indexOf(ref) : -1;
  if (i === -1) this.children.push(c); else this.children.splice(i, 0, c);
  c.parentNode = this;
  return c;
};
El.prototype.querySelector = function (sel) {  // class selectors only
  var cls = sel.slice(1);
  var stack = this.children.slice();
  while (stack.length) {
    var el = stack.shift();
    if ((' ' + el.className + ' ').indexOf(' ' + cls + ' ') !== -1) return el;
    stack = stack.concat(el.children);
  }
  return null;
};
Object.defineProperty(El.prototype, 'firstChild', {
  get: function () { return this.children[0] || null; }
});

var byId = {};
globalThis.document = {
  readyState: 'complete',
  querySelectorAll: function () { return []; },
  getElementById: function (id) { return byId[id] || null; },
  createElement: function (t) { return new El(t); },
  addEventListener: function () {}
};

var src = fs.readFileSync(process.argv[1], 'utf8');
var patched = src.replace('root.tracebi = {',
  'root.tracebi = { _badges: hydrateBadges,');
if (patched === src) throw new Error('export line not found');
new Function(patched)();

var page = new El('div');
var kpi = new El('div');
kpi.className = 'tb-kpi';
page.appendChild(kpi);
var section = new El('div');
page.appendChild(section);
var table = new El('table');
section.appendChild(table);
var cfg = new El('script');
cfg.textContent = JSON.stringify({
  badges: true,
  figures: [{ id: 'k1', provenance: 'verified' },
            { id: 't1', provenance: 'unverified', note: 'stale' }]
});
byId['tracebi-figures'] = cfg;
byId['k1'] = kpi;
byId['t1'] = table;

globalThis.tracebi._badges();
globalThis.tracebi._badges();  // second pass must not double-badge or re-wrap

var wrap = table.parentNode;
process.stdout.write(JSON.stringify({
  kpi_children: kpi.children.map(function (c) { return c.className; }),
  kpi_not_wrapped: kpi.parentNode === page,
  wrap_class: wrap ? wrap.className : null,
  wrap_in_section: wrap !== null && wrap.parentNode === section,
  section_children: section.children.length,
  wrap_children: wrap ? wrap.children.map(function (c) { return c.tagName; }) : null,
  table_badge_class: wrap && wrap.children[0] ? wrap.children[0].className : null,
  table_badge_title: wrap && wrap.children[0] ? wrap.children[0].title : null
}));
"""

    def test_table_badge_anchors_to_wrapper_kpi_badges_in_place(self):
        result = subprocess.run(
            ["node", "-e", self._SCRIPT, ASSET],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr
        out = json.loads(result.stdout)
        # The KPI is its own anchor (position:relative in css): badged in
        # place, never wrapped — and exactly once across two passes.
        assert out["kpi_children"] == ["tb-badge tb-badge--verified"]
        assert out["kpi_not_wrapped"] is True
        # The table is wrapped in the positioned anchor div, which holds
        # the badge and then the table — badge pinned to the table corner.
        assert out["wrap_class"] == "tb-badge-anchor"
        assert out["wrap_in_section"] is True
        assert out["section_children"] == 1        # wrapper replaced the table
        assert out["wrap_children"] == ["SPAN", "TABLE"]
        assert out["table_badge_class"] == "tb-badge tb-badge--unverified"
        assert out["table_badge_title"] == "stale"
