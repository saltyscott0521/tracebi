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
        # tooltip valueFormat coverage landed — behavior, not bloat.
        assert os.path.getsize(ASSET) < 26 * 1024

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
