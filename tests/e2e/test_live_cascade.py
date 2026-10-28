"""Every shipped live report, worked by every gesture it offers (decision 17
of the live-reports plan): the reference project's reports, the scaffold's
sample dashboard, both ``init --template`` bundles and the demo app's wealth
reports, each built and opened from disk.

For each report the journey shows every tab, and on what it finds there
picks each filter's first present value, narrows each range, clicks each
row-select table's first row and each chart's first selectable mark. After
every step: the address carries the state; the selection bar shows it; every
figure that recomputes holds exactly what ``execute_plan`` over the slice the
file carries gives under that state (less the field a chart highlights,
which the page states); every figure fixed at build keeps its build value
and says so; and the trace's local rows name the selection. Then, once per
report: printed, the bar is one line and the footer says the page was
filtered; "Download what I see" and a binding's own CSV both state the
selection; Escape returns the page to the view as built.

A report that gains a control or a chart is walked by it the day it lands:
the steps are read off the page, never listed here.
"""

from __future__ import annotations

import json
import os
import shutil
from urllib.parse import unquote

import pytest

from tests.e2e.conftest import REFERENCE_PROJECT, release_warehouses, run_cli

DEMO_APP = REFERENCE_PROJECT.parents[1] / "tracebi" / "web" / "demo_app"

# (group, report): the group says how the project is made.
REPORTS = [
    ("reference", "portfolio_model/portfolio_dashboard"),
    ("reference", "portfolio_model/portfolio_book"),
    ("reference", "portfolio_model/portfolio_desk"),
    ("reference", "portfolio_model/portfolio_overview"),
    ("reference", "portfolio_model/portfolio_concentration"),
    ("reference", "portfolio_model/portfolio_showcase"),
    ("reference", "housing_model/affordability"),
    ("reference", "saas_model/mrr_dashboard"),
    ("reference", "saas_model/cohort_brief"),
    ("reference", "wealth_model/aum_by_branch"),
    ("reference", "wealth_model/aum_by_region"),
    ("init", "sample_model/sample_dashboard"),
    ("saas-metrics", "saas_model/mrr_dashboard"),
    ("saas-metrics", "saas_model/cohort_brief"),
    ("sales-pipeline", "sales_pipeline_model/pipeline_dashboard"),
    ("sales-pipeline", "sales_pipeline_model/rep_scorecard"),
    ("demo", "wealth_model/aum_by_region"),
    ("demo", "wealth_model/aum_by_branch"),
]

_TRANSFORMS = {
    "reference": ("holdings_transform", "saas_transform", "affordability_transform",
                  "wealth_transform"),
    "init": ("sample_transform",),
    "saas-metrics": ("saas_transform",),
    "sales-pipeline": ("sales_pipeline_transform",),
    "demo": (),
}


@pytest.fixture(scope="module")
def projects(tmp_path_factory):
    """Builds each group's project once, the first time a report of it is
    walked: ``projects(group) -> its root``."""
    from tracebi import model_registry, pipeline_registry

    roots: dict[str, object] = {}
    saved = (os.getcwd(), model_registry._registry, model_registry._auto_discovered,
             pipeline_registry._registry, pipeline_registry._auto_discovered,
             {k: os.environ.get(k) for k in ("TRACEBI_MODELS_DIR", "TRACEBI_REPORTS_DIR",
                                             "TRACEBI_DEMO_DB_DIR")})

    def make(group):
        if group in roots:
            return roots[group]
        base = tmp_path_factory.mktemp(group)
        model_registry._registry = model_registry.ModelRegistry()
        model_registry._auto_discovered = False
        pipeline_registry._registry = pipeline_registry.PipelineRegistry()
        pipeline_registry._auto_discovered = False
        for key in ("TRACEBI_MODELS_DIR", "TRACEBI_REPORTS_DIR"):
            os.environ.pop(key, None)
        if group == "reference":
            proj = base / "portfolio_project"
            shutil.copytree(REFERENCE_PROJECT, proj, ignore=shutil.ignore_patterns(
                "data", "output", ".tracebi", "explorations", "__pycache__", "*.duckdb"))
        elif group == "demo":
            # The demo app's models read the demo database, which the app
            # seeds when it is first imported (here, into this group's own
            # folder, unless an earlier journey imported it already); its
            # reports are read where they ship.
            proj = base
            os.environ["TRACEBI_MODELS_DIR"] = str(DEMO_APP / "models")
            os.environ["TRACEBI_REPORTS_DIR"] = str(DEMO_APP / "reports")
            os.environ["TRACEBI_DEMO_DB_DIR"] = str(base)
        else:
            proj = base / "proj"
            args = ("init", str(proj)) if group == "init" else (
                "init", str(proj), "--template", group)
            code, out = run_cli(*args)
            assert code == 0, out
        os.chdir(proj)
        for transform in _TRANSFORMS[group]:
            code, out = run_cli("run-transform", transform)
            assert code == 0, f"{group}: {out}"
        for g, name in REPORTS:
            if g == group:
                code, out = run_cli("report", "build", name)
                assert code == 0, f"{group} {name}: {out}"
        roots[group] = proj
        return proj

    try:
        yield make
    finally:
        release_warehouses()
        os.chdir(saved[0])
        (model_registry._registry, model_registry._auto_discovered,
         pipeline_registry._registry, pipeline_registry._auto_discovered) = saved[1:5]
        for key, value in saved[5].items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture(scope="module")
def browser():
    from tests.e2e.test_reference_project import _browser

    pw, chromium = _browser()
    try:
        yield chromium
    finally:
        chromium.close()
        pw.stop()


# ── What the page says ────────────────────────────────────────────────────

def _state(page) -> dict:
    """The selection the address carries ({} when there is none)."""
    for part in page.evaluate("location.hash").lstrip("#").split("&"):
        if part.startswith("sel="):
            return json.loads(unquote(part[4:]))
    return {}


# A field's display name, read off the page by the runtime's rule
# (fieldLabel): a control's data-tb-label or the <label> around it, else a
# table's header for the column, else a chart's x title, else humanise.
_LABEL = """(column) => {
  const controls = document.querySelectorAll('[data-tb-filter][data-tb-column], [data-tb-range][data-tb-column]');
  for (const el of controls) {
    if (el.getAttribute('data-tb-column') !== column) continue;
    if (el.getAttribute('data-tb-label')) return el.getAttribute('data-tb-label');
    const label = el.closest('label');
    if (label) {
      const text = Array.from(label.childNodes).filter(c => c !== el && !(c.nodeType === 1 &&
        (c.contains(el) || /^(SELECT|INPUT)$/.test(c.tagName)))).map(c => c.textContent).join('').trim();
      if (text) return text;
    }
  }
  for (const t of document.querySelectorAll('table[data-tb-figure="table"]')) {
    const own = t.getAttribute('data-tb-columns');
    const rows = window.tracebi.data(t.getAttribute('data-tb-binding'));
    const cols = own ? own.split(',').map(c => c.trim()) : (rows.length ? Object.keys(rows[0]) : []);
    const th = cols.indexOf(column) === -1 ? null : t.querySelectorAll('thead th')[cols.indexOf(column)];
    if (th && th.textContent.trim()) return th.textContent.trim();
  }
  const chart = Array.from(document.querySelectorAll('[data-tb-figure="chart"][data-tb-x-title]'))
    .find(c => c.getAttribute('data-tb-x') === column);
  return chart ? chart.getAttribute('data-tb-x-title') : null;
}"""


def _label(page, column: str) -> str:
    from tracebi.reports.derive import humanise

    return page.evaluate(_LABEL, column) or humanise(column)


def _js_str(v) -> str:
    """A value as JavaScript's String() spells it."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _cell(v) -> str:
    """A value as the page writes it in a chip (liveCell)."""
    if v is True:
        return "True"
    if v is False:
        return "False"
    return _js_str(v)


def _describe(page, sel: dict) -> str:
    """The trace's words for an applied selection (describeSelection)."""
    out = []
    for k, v in sel.items():
        if isinstance(v, list):
            out.append(f"{_label(page, k)} = " + ", ".join(_js_str(x) for x in v))
        else:
            ops = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}
            out.append(_label(page, k) + " " + " and ".join(
                f"{ops[op]} {_js_str(v[op])}" for op in ("gt", "gte", "lt", "lte") if op in v))
    return "; ".join(out)


_FIGURES = """() => Array.from(document.querySelectorAll('[data-tb-figure][data-tb-binding][id]'))
  .filter(el => el.getAttribute('data-tb-figure') !== 'custom').map(el => {
    const kind = el.getAttribute('data-tb-figure');
    return {id: el.id, binding: el.getAttribute('data-tb-binding'), kind,
      x: el.getAttribute('data-tb-x'), color: el.getAttribute('data-tb-color'),
      value: kind === 'value' ? (el.querySelector('.tb-kpi-value') || el).textContent.trim() : null,
      rows: kind === 'table' ? Array.from(el.querySelectorAll('tbody tr')).map(r => r.textContent) : null,
      fixed: el.getAttribute('data-tb-fixed'),
      result: window.tracebi.result(el.id)};
  })"""


def _settle(page):
    page.wait_for_timeout(450)


def _check(page, name, step, plans, frames, built_view):
    """Everything a step must leave true (see the module docstring)."""
    from tracebi.reports.calc_plan import execute_plan, first_mismatch

    where = f"{name} · {step}"
    state = _state(page)
    assert state, f"{where}: the address carries no selection"
    # The bar shows one chip per value (a range is one chip) and names them.
    bar = page.locator(".tb-selection-bar")
    assert bar.count() == 1 and bar.is_visible(), f"{where}: no selection bar"
    chips = bar.locator(".tb-selection-chip").all_text_contents()
    want = sum(len(v) if isinstance(v, list) else 1 for v in state.values())
    assert len(chips) == want, (where, chips, state)
    for k, v in state.items():
        for one in (v if isinstance(v, list) else [None]):
            text = f"{_label(page, k)}: " + ("" if one is None else _cell(one))
            assert any(c.startswith(text) for c in chips), (where, text, chips)
    assert page.locator(".tb-verdict[data-tb-verdict='local']").count() >= 1, where

    checked = traced = 0
    for fig in page.evaluate(_FIGURES):
        plan = plans.get(fig["binding"])
        if plan is None:
            continue
        what = f"{where} · {fig['id']}"
        if "fixed" in plan:
            # Fixed at build: as built, and marked.
            assert fig["fixed"] == plan["fixed"], what
            was = built_view.get(fig["id"])
            if was is not None:
                assert fig["value"] == was["value"] and fig["rows"] == was["rows"], what
            continue
        res = fig["result"]
        assert res and "fixed" not in res, (what, res)
        own = res["highlights"]
        if fig["kind"] == "chart":
            assert set(own) <= {fig["x"], fig["color"]}, (what, own)
        rest = {k: v for k, v in state.items() if k not in own}
        expected = execute_plan(plan, frames[(plan["model"], plan["fact"])], rest)
        assert first_mismatch(res, expected) is None, (
            what, first_mismatch(res, expected), rest)
        applied = {k: v for k, v in rest.items() if k in plan["slice_columns"]}
        assert res["selection"] == applied, (what, res["selection"], applied)
        if fig["kind"] == "table" and fig["rows"]:
            assert len(fig["rows"]) == len(expected), what
        if fig["kind"] == "value" and not res["rows"]:
            assert fig["value"] == "—", what
        checked += 1
        # The trace's local row for the figure states the selection it ran.
        row = page.locator(f'.tb-receipt-row[data-tb-receipt-fig="{fig["id"]}"] .tb-receipt-local')
        if row.count():
            said = row.first.locator("dd").first.text_content()
            assert said == (_describe(page, res["selection"]) or "none applies"), (what, said)
            traced += 1
    assert checked, f"{where}: no figure recomputed"
    if page.locator(".tb-receipt-drawer").count():
        assert traced, f"{where}: no trace row names the selection"


# ── The steps a page offers ───────────────────────────────────────────────

_STEPS = """() => {
  const seen = (el) => !!el.getClientRects().length;
  const out = [];
  document.querySelectorAll('select[data-tb-filter]').forEach((el, i) => {
    if (el.hasAttribute('data-tb-fixed')) return;
    const opt = Array.from(el.options).find(o => !o.disabled && o.value && o.value !== 'All');
    if (opt) out.push({kind: 'filter', index: i, value: opt.value,
                       label: 'filter ' + el.getAttribute('data-tb-column') + ' = ' + opt.value});
  });
  document.querySelectorAll('[data-tb-range]').forEach((el, i) => {
    if (el.hasAttribute('data-tb-fixed') || !el.querySelector('input, select')) return;
    out.push({kind: 'range', index: i, label: 'range ' + el.getAttribute('data-tb-column')});
  });
  document.querySelectorAll('table[data-tb-select-rows]').forEach((el, i) => {
    if (seen(el) && el.querySelector('tbody tr.tb-row-select'))
      out.push({kind: 'row', id: el.id, label: 'row of ' + el.id});
  });
  document.querySelectorAll('[data-tb-figure="chart"].tb-selectable[id]').forEach((el) => {
    if (!seen(el)) return;
    if (el.querySelector('.tb-chart-host svg, .tb-chart-host canvas'))
      out.push({kind: 'mark', id: el.id, label: 'mark of ' + el.id});
    else if (el.querySelector('.tb-legend-item--select'))
      out.push({kind: 'legend', id: el.id, label: 'legend of ' + el.id});
  });
  return out;
}"""


# The page coordinates of a chart's first mark: a slice's middle, a bar's or
# a cell's centre, a point; read from the chart's ECharts instance.
_FIRST_MARK = """(id) => {
  const host = document.querySelector('#' + id + ' .tb-chart-host');
  const c = window.__tbECharts.getInstanceByDom(host), r = host.getBoundingClientRect();
  const s = c.getModel().getSeriesByIndex(0), data = s.getData();
  let x, y;
  if (s.subType === 'pie') {
    const l = data.getItemLayout(0), a = (l.startAngle + l.endAngle) / 2, m = (l.r + l.r0) / 2;
    x = l.cx + m * Math.cos(a); y = l.cy + m * Math.sin(a);
  } else {
    const g = data.getItemGraphicEl(0);
    if (g && g.getBoundingRect && s.subType !== 'line') {
      const b = g.getBoundingRect().clone();
      b.applyTransform(g.getComputedTransform());
      x = b.x + b.width / 2; y = b.y + b.height / 2;
    } else {
      const p = c.convertToPixel({seriesIndex: 0}, [0, data.get(data.mapDimension('y'), 0)]);
      x = p[0]; y = p[1];
    }
  }
  return [r.left + x, r.top + y];
}"""


def _act(page, step):
    kind = step["kind"]
    if kind == "filter":
        page.locator("select[data-tb-filter]").nth(step["index"]).select_option(
            step["value"], force=True)
    elif kind == "range":
        page.evaluate("""(i) => {
          const el = document.querySelectorAll('[data-tb-range]')[i];
          const ins = el.querySelectorAll('input[type=range]');
          if (ins.length) {
            const lo = ins[0];
            lo.value = String((Number(lo.min) + Number(lo.max)) / 2);
            lo.dispatchEvent(new Event('change'));
          } else {
            const from = el.querySelector('select');
            from.selectedIndex = Math.min(1, from.options.length - 1);
            from.dispatchEvent(new Event('change'));
          }
        }""", step["index"])
    elif kind == "row":
        page.locator(f'#{step["id"]} tbody tr.tb-row-select').first.click(force=True)
    elif kind == "mark":
        # A click on the chart's first mark (the first category, slice, cell
        # or point), where ECharts drew it.
        page.locator(f"#{step['id']}").scroll_into_view_if_needed()
        x, y = page.evaluate(_FIRST_MARK, step["id"])
        page.mouse.click(x, y)
    elif kind == "legend":
        page.locator(f"#{step['id']} .tb-legend-item--select").first.click(force=True)


def _tabs(page) -> list:
    return page.locator(".tb-tab-bar button").all_text_contents() or [None]


@pytest.mark.parametrize("group,name", REPORTS, ids=[f"{g}:{n}" for g, n in REPORTS])
def test_every_gesture_recomputes_every_figure(projects, browser, group, name):
    from tests.e2e.test_reference_project import _slices

    root = projects(group)
    manifest = json.loads((root / "output" / f"{name}.html.manifest.json").read_text())
    assert manifest.get("slice"), f"{name} carries no slice"
    frames, plans = _slices(root, name)

    page = browser.new_page(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    url = (root / "output" / f"{name}.html").as_uri()
    try:
        page.goto(url)
        page.wait_for_selector("html[data-tb-ready]")
        _settle(page)
        payload = page.evaluate(
            "JSON.parse(document.getElementById('tracebi-calc-plans').textContent)")
        authored = payload["authored_selection"]
        assert page.locator(".tb-selection-bar:visible").count() == 0, f"{name}: bar as built"
        built_view = {f["id"]: f for f in page.evaluate(_FIGURES)}

        walked = []
        for tab in _tabs(page):
            if tab is not None:
                page.locator(".tb-tab-bar button", has_text=tab).first.click()
                _settle(page)
            # The page's gestures, read as built.
            page.evaluate("(s) => window.tracebi.setSelection(s)", authored)
            _settle(page)
            for step in page.evaluate(_STEPS):
                if step["label"] in walked:
                    continue
                walked.append(step["label"])
                page.evaluate("(s) => window.tracebi.setSelection(s)", authored)
                _settle(page)
                _act(page, step)
                _settle(page)
                assert _state(page) != authored, f"{name} · {step['label']}: changed nothing"
                _check(page, name, (tab or "page") + " · " + step["label"],
                       plans, frames, built_view)
                if name == "portfolio_model/portfolio_desk" and step["label"] == "range spread_bps":
                    # The field is named as its control names it, not as the column.
                    chip = page.locator(".tb-selection-chip").first.text_content()
                    assert chip.startswith("Spread, bps: "), chip
        assert walked, f"{name}: the page offers no gesture"

        # Printed (under the last step's selection), the selection is one
        # line, and the footer says so.
        state = _state(page)
        page.emulate_media(media="print")
        line = page.locator(".tb-selection-print")
        assert line.is_visible(), name
        text = line.text_content()
        assert text.startswith("Filtered to: ") and all(_label(page, k) in text for k in state), text
        assert page.locator(".tb-selection-chip").first.is_hidden(), name
        if page.locator(".tb-footer-line").count():
            assert page.locator(".tb-footer-filtered").first.is_visible(), name
        page.emulate_media(media="screen")

        # Download what I see: one file, the state in its header and name.
        with page.expect_download() as got:
            page.locator(".tb-selection-download").click()
        body = open(got.value.path(), encoding="utf-8").read()
        assert body.splitlines()[0].startswith("# selection: "), body[:200]
        assert all(_label(page, k) in body.splitlines()[0] for k in state), body[:200]
        assert "# figure: " in body
        slug_field = next(iter(state)).split(".")[-1]
        assert slug_field in got.value.suggested_filename, got.value.suggested_filename
        # A binding's own CSV stays the full binding, and says so.
        own = page.locator("[data-tb-download]")
        if own.count():
            with page.expect_download() as full:
                own.first.dispatch_event("click")
            first = open(full.value.path(), encoding="utf-8").read().splitlines()[0]
            assert first == "# selection: none (full binding)", first

        # Escape: back to the view as built.
        page.locator("body").focus()
        page.keyboard.press("Escape")
        _settle(page)
        assert _state(page) == {} or _state(page) == authored
        assert page.locator(".tb-selection-bar:visible").count() == 0
        assert errors == [], errors
    finally:
        page.close()

