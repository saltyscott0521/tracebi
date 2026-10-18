"""Scenarios: the closed formula grammar, the build-time checks, and the
runtime evaluator agreeing with the Python one."""

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest

from tracebi.reports.figures import extract_scenarios
from tracebi.reports.scenario import (
    ScenarioError, evaluate, parse,
)

_JS = Path(__file__).resolve().parent.parent / "tracebi" / "reports" / "assets" / "tracebi.js"

_FORMULAS = [
    ("pmt(rate / 100 / 12, years * 12, price * (1 - down / 100))",
     {"rate": 12.43, "years": 30, "price": 84300, "down": 20}),
    ("pmt(0, 12, 1200)", {}),
    ("-2 ^ 2 + round(2.345, 2) + max(1, 5, 3) - min(4, abs(-7))", {}),
    ("(a + b) * c / 4", {"a": 1, "b": 2, "c": 3}),
    ("2 ^ 3 ^ 2", {}),
]


@pytest.mark.parametrize("formula, message", [
    ("", "empty"),
    ("rate +", "expected"),
    ("fetch(1)", "unknown function"),
    ("pmt(1, 2)", "takes 3"),
    ("rate ; 1", "cannot read"),
    ("(1 + 2", "expected"),
])
def test_bad_formulas_are_refused(formula, message):
    with pytest.raises(ScenarioError, match=message):
        parse(formula)


def _page(body: str) -> str:
    return f"<html><body>{body}</body></html>"


@pytest.mark.parametrize("body, message", [
    ('<div data-tb-figure="value" data-tb-binding="k" data-tb-cell="x">'
     '<div data-tb-scenario="s"><output data-tb-calc="1"></output></div></div>',
     "never a figure"),
    ('<div data-tb-scenario="s"><span data-tb-figure="value" data-tb-binding="k"'
     ' data-tb-cell="x"></span><output data-tb-calc="1"></output></div>',
     "holds a figure"),
    ('<output data-tb-calc="1"></output>', "outside any data-tb-scenario"),
    ('<div data-tb-scenario="s"><div data-tb-scenario="t"></div></div>', "do not nest"),
    ('<div data-tb-scenario="s"><input data-tb-input="a"><input data-tb-input="a">'
     '</div>', "twice"),
    ('<div data-tb-scenario="s"><input data-tb-input="a b"></div>', "identifier"),
    ('<div data-tb-scenario="s"><select data-tb-preset="h"></select></div>',
     "data-tb-key"),
    ('<div data-tb-scenario="s"></div><div data-tb-scenario="s"></div>', "two scenarios"),
])
def test_unsafe_shapes_are_refused(body, message):
    with pytest.raises(ScenarioError, match=message):
        extract_scenarios(_page(body))


def test_the_runtime_evaluates_like_python():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = (
        "global.window = {}; require(process.argv[1]);"
        "const cases = JSON.parse(process.argv[2]);"
        "console.log(JSON.stringify(cases.map(c => window.tracebi.evaluate(c[0], c[1]))));"
    )
    out = subprocess.run(
        [node, "-e", script, str(_JS), json.dumps(_FORMULAS)],
        capture_output=True, text=True, check=True).stdout
    got = json.loads(out)
    for (formula, values), js in zip(_FORMULAS, got):
        assert math.isclose(js, evaluate(formula, values), rel_tol=1e-12), formula
