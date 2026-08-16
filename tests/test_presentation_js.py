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
        assert os.path.getsize(ASSET) < 25 * 1024

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
