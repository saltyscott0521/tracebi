"""
The page engine (``tracebi-calc.js``) reproduces DuckDB (query semantics).

Python is the source of truth for what a calc plan means; the committed
fixtures in ``tests/fixtures/calc_parity/`` hold DuckDB's answer for each plan
under a selection. This runs every fixture through the VENDORED bundle in node,
the file a page inlines, so an engine source edit that was never rebuilt is
not what gets certified. Each fixture's slice goes in as Parquet, written the
way a build writes a slice block (Snappy, or uncompressed pages), so the reader
is on the path too. Rows are compared in order after the fingerprint's cell
rule, since the order is part of the answer.

The budgets are tests as well: the bundle stays under 50 KB gzipped, every
fixture recomputes within 100 ms, and a 1,000,000-row slice groups and sums
within 100 ms and takes a grouped quantile within 300 ms. Skipped where node
is unavailable.
"""

import gzip
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tracebi.model.dataset import canonical_rows
from tracebi.reports.calc_plan import apply_selection, execute_plan, slice_frame

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "tracebi" / "reports" / "assets" / "tracebi-calc.js"
FIXTURES = ROOT / "tests" / "fixtures" / "calc_parity"
CASES = sorted(p.stem for p in FIXTURES.glob("*.json"))

_NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(_NODE is None, reason="node not available")

# Loads the bundle as a page would (an IIFE that sets tracebiCalc on the
# global), then runs each job: load the slice, run once to warm, time seven
# runs, and hand back the result through the cell rule (in
# the plan's order, and in the fingerprint's total order) and raw.
_RUNNER = r"""
const fs = require('fs');
const vm = require('vm');
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
const jobs = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const now = () => Number(process.hrtime.bigint()) / 1e6;
const out = {};
for (const job of jobs) {
  const t0 = now();
  tracebiCalc.load(job.fact, fs.readFileSync(job.parquet));
  const loadMs = now() - t0;
  if (job.domains) {
    out[job.id] = job.domains.map(d => tracebiCalc.domains(job.fact, d.column, d.selection));
    continue;
  }
  let res = tracebiCalc.run(job.plan, job.selection);
  const times = [];
  for (let k = 0; k < 7; k++) {
    const t = now();
    res = tracebiCalc.run(job.plan, job.selection);
    times.push(now() - t);
  }
  times.sort((a, b) => a - b);
  const canon = tracebiCalc.canonical(res, false);
  out[job.id] = {cols: canon.cols, rows: canon.rows, raw: res.rows.map(r => res.cols.map(c => r[c])),
                 sorted: tracebiCalc.canonical(res).rows, unfiltered_by: res.unfiltered_by,
                 selection: res.selection, ms: times[0], median_ms: times[3],
                 load_ms: loadMs};
}
console.log(JSON.stringify(out));
"""


def _run_node(tmp: Path, jobs: list) -> dict:
    (tmp / "jobs.json").write_text(json.dumps(jobs))
    (tmp / "run.js").write_text(_RUNNER)
    proc = subprocess.run([_NODE, str(tmp / "run.js"), str(BUNDLE), str(tmp / "jobs.json")],
                          capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _fixture(case: str) -> dict:
    return json.loads((FIXTURES / f"{case}.json").read_text())


def _write_slice(fixture: dict, path: Path, compression) -> None:
    frame = slice_frame(fixture["slice"]["columns"], fixture["slice"]["rows"])
    frame.to_parquet(path, engine="pyarrow", compression=compression, index=False)


@pytest.fixture(scope="module")
def engine_results(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("calc_parity")
    jobs = []
    for n, case in enumerate(CASES):
        fx = _fixture(case)
        path = tmp / f"{case}.parquet"
        # Both codecs a slice block may use, alternating across the cases.
        _write_slice(fx, path, "snappy" if n % 2 == 0 else None)
        jobs.append({"id": case, "fact": fx["slice"]["fact"], "parquet": str(path),
                     "plan": fx["plan"], "selection": fx["selection"]})
    return _run_node(tmp, jobs)


@pytest.mark.parametrize("case", CASES)
def test_engine_reproduces_duckdb(engine_results, case):
    fx = _fixture(case)
    got = engine_results[case]
    assert got["cols"] == fx["expected"]["cols"]
    assert got["rows"] == fx["expected"]["rows"], (
        f"{case}: {fx['about']}\nengine: {got['rows']}\nduckdb: {fx['expected']['rows']}")
    assert got["unfiltered_by"] == fx["expected"]["unfiltered_by"]
    # canonical() with its total order is what a trace hashes (algo 3).
    expected = pd.DataFrame(fx["expected"]["rows"], columns=fx["expected"]["cols"], dtype=object)
    assert got["sorted"] == canonical_rows(expected, total_order=True)[1]
    # The applied selection is the composition rule's, field for field.
    assert got["selection"] == apply_selection(fx["plan"], fx["selection"])["selection"]


def test_every_fixture_recomputes_within_100ms(engine_results):
    timings = sorted(((v["ms"], k) for k, v in engine_results.items()), reverse=True)
    print("\ncalc fixtures, slowest warm runs (best of 7, ms): "
          + ", ".join(f"{k} {ms:.2f}" for ms, k in timings[:5]))
    slow = [(k, ms) for ms, k in timings if ms > 100]
    assert not slow, f"over the 100 ms budget: {slow}"


# The fixtures pin the measure kinds; these pin the rest of the closed
# vocabulary the docstring defines (every FILTER op, SQL's null rules against
# having's pandas ones, filtered aggregates, descending nulls) on the "total"
# fixture's slice, which has null sectors and a null spread. The oracle is
# execute_plan: the same plan through DataModel.execute.
_SECTOR = "dim_issuer.sector"
_OPS = {
    "eq": {"column": _SECTOR, "op": "eq", "value": "Energy"},
    "ne": {"column": _SECTOR, "op": "ne", "value": "Energy"},
    "gt": {"column": "par", "op": "gt", "value": 2000000},
    "lt": {"column": "par", "op": "lt", "value": 2000000},
    "lte": {"column": "par", "op": "lte", "value": 2000000},
    "between": {"column": "par", "op": "between", "value": [1500000, 2500000]},
    "in": {"column": _SECTOR, "op": "in", "value": ["Energy", "Software"]},
    "not_in": {"column": _SECTOR, "op": "not_in", "value": ["Energy", "Software"]},
    "is_null": {"column": _SECTOR, "op": "is_null"},
    "not_null": {"column": "spread_bps", "op": "not_null"},
    "contains": {"column": "dim_issuer.issuer", "op": "contains", "value": "r"},
    "or": {"or": [{"column": _SECTOR, "op": "eq", "value": "Energy"},
                  {"column": "spread_bps", "op": "gte", "value": 600}]},
}


def _vocabulary_plans() -> dict:
    base = _fixture("total")["plan"]

    def plan(**over):
        p = json.loads(json.dumps(base))
        p.update(over)
        return p

    by_fund = ["dim_fund.fund"]
    plans = {f"filter_{op}": plan(filters=tree) for op, tree in _OPS.items()}
    big = {"column": "par", "op": "gte", "value": 2000000}
    plans["filtered_aggregates"] = plan(
        group_by=by_fund, order_by=[{"column": "dim_fund.fund", "desc": False}],
        aggregates=[{"name": "low", "func": "min", "source": {"col": "spread_bps"}, "where": big},
                    {"name": "high", "func": "max", "source": {"col": "spread_bps"}, "where": big},
                    {"name": "issuers", "func": "nunique", "source": {"col": "issuer_id"},
                     "where": big},
                    {"name": "spreads", "func": "count", "source": {"col": "spread_bps"},
                     "where": big}],
        columns=by_fund + ["low", "high", "issuers", "spreads"])
    by_sector = [_SECTOR]
    sector_sum = dict(
        group_by=by_sector,
        aggregates=[{"name": "fair_value", "func": "sum", "source": {"col": "fair_value"}}],
        columns=by_sector + ["fair_value"])
    plans["order_desc_nulls_last"] = plan(
        **sector_sum, order_by=[{"column": _SECTOR, "desc": True}])
    for op, value in (("ne", "Energy"), ("not_in", ["Energy"]), ("eq", "Energy")):
        plans[f"having_{op}"] = plan(
            **sector_sum, order_by=[{"column": _SECTOR, "desc": False}],
            having=[{"column": _SECTOR, "op": op, "value": value}])
    return plans


def test_engine_reproduces_the_rest_of_the_vocabulary(tmp_path):
    fx = _fixture("total")
    frame = slice_frame(fx["slice"]["columns"], fx["slice"]["rows"])
    path = tmp_path / "slice.parquet"
    _write_slice(fx, path, "snappy")
    plans = _vocabulary_plans()
    got = _run_node(tmp_path, [{"id": name, "fact": fx["slice"]["fact"], "parquet": str(path),
                                "plan": plan, "selection": {}} for name, plan in plans.items()])
    for name, plan in plans.items():
        want = execute_plan(plan, frame)
        assert got[name]["cols"] == [str(c) for c in want.columns], name
        rows = [[None if pd.isna(v) else v.item() if hasattr(v, "item") else v for v in row]
                for row in want.itertuples(index=False, name=None)]
        # Raw values within 1e-12, not the cell rule: "filter_lt" sums to
        # 15010403.95, and DuckDB's sum lands one ulp above the boundary
        # (15010403.950000001, rounds to 15010404) where the engine's lands
        # one below (15010403.949999999, rounds to 15010403.9). See
        # CALC_NOTICE.md, "Rounding boundaries".
        engine = got[name]["raw"]
        assert len(engine) == len(rows), f"{name}\nengine: {engine}\nduckdb: {rows}"
        for mine, theirs in zip(engine, rows):
            for a, b in zip(mine, theirs):
                if isinstance(a, float) or isinstance(b, float):
                    assert b is not None and abs(a - b) <= 1e-12 * abs(b), (name, mine, theirs)
                else:
                    assert a == b, (name, mine, theirs)


def test_domains_list_present_values_first(tmp_path):
    """A control's options: values present under the rest of the selection,
    then the others; the column's own condition never narrows its options."""
    fx = _fixture("total")
    path = tmp_path / "slice.parquet"
    _write_slice(fx, path, "snappy")
    frame = slice_frame(fx["slice"]["columns"], fx["slice"]["rows"])
    selection = {"dim_fund.fund": ["Fund I"], "dim_issuer.sector": ["Software", "Energy"],
                 "par": {"gte": 1000000, "lt": 3000000}, "not.in_slice": ["x"]}
    columns = ["dim_issuer.sector", "dim_issuer.issuer", "fund_id", "dim_fund.fund"]

    def expected(column):
        keep = pd.Series(True, index=frame.index)
        for field, cond in selection.items():
            if field == column or field not in frame.columns:
                continue
            if isinstance(cond, list):
                keep &= frame[field].isin(cond)
            else:
                keep &= (frame[field] >= cond["gte"]) & (frame[field] < cond["lt"])
        values = sorted(frame[column].dropna().unique().tolist())
        present = set(frame.loc[keep, column].dropna().tolist())
        return {"present": [v for v in values if v in present],
                "rest": [v for v in values if v not in present]}

    got = _run_node(tmp_path, [{
        "id": "d", "fact": fx["slice"]["fact"], "parquet": str(path),
        "domains": [{"column": c, "selection": selection} for c in columns]}])["d"]
    wants = [expected(c) for c in columns]
    # The case must split some column into present and rest to test anything.
    assert any(w["present"] and w["rest"] for w in wants)
    for column, result, want in zip(columns, got, wants):
        assert result == want, column


def test_loads_a_duckdb_written_block(tmp_path):
    """A slice block as DuckDB writes one (L-2 builds slices in DuckDB): every
    slice type, nulls, and naive datetimes in pandas' ISO spelling."""
    duckdb = pytest.importorskip("duckdb")
    path = tmp_path / "slice.parquet"
    con = duckdb.connect()
    con.execute(f"""
        COPY (SELECT * FROM (VALUES
            ('a', 1::BIGINT, 1.5::DOUBLE, true, TIMESTAMP '2026-03-01 00:00:00'),
            (NULL, NULL, NULL, NULL, NULL),
            ('b', -7::BIGINT, 2.25::DOUBLE, false, TIMESTAMP '2026-03-02 04:05:06.250')
        ) t(s, i, f, b, ts)) TO '{path}' (FORMAT parquet, COMPRESSION snappy)""")
    script = tmp_path / "load.js"
    script.write_text(r"""
const fs = require('fs');
require('vm').runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
const t = tracebiCalc.load('f', fs.readFileSync(process.argv[3]));
const plan = {version: 1, model: 'm', fact: 'f', slice_columns: t.columns.map(c => c.name),
  filters: null, group_by: ['s', 'b', 'ts'],
  aggregates: [{name: 'i', func: 'sum', source: {col: 'i'}},
               {name: 'f', func: 'max', source: {col: 'f'}}],
  means: [], ratios: [], shares: [], combines: [], ranks: [], runnings: [], having: [],
  order_by: [{column: 's', desc: false}], limit: null, columns: ['s', 'b', 'ts', 'i', 'f']};
console.log(JSON.stringify({columns: t.columns, rows: t.rows, out: tracebiCalc.run(plan, {}).rows}));
""")
    proc = subprocess.run([_NODE, str(script), str(BUNDLE), str(path)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    got = json.loads(proc.stdout)
    assert got["columns"] == [{"name": "s", "type": "string"}, {"name": "i", "type": "number"},
                              {"name": "f", "type": "number"}, {"name": "b", "type": "boolean"},
                              {"name": "ts", "type": "datetime"}]
    assert got["rows"] == 3
    assert got["out"] == [
        {"s": "a", "b": True, "ts": "2026-03-01T00:00:00", "i": 1, "f": 1.5},
        {"s": "b", "b": False, "ts": "2026-03-02T04:05:06.250000", "i": -7, "f": 2.25},
        {"s": None, "b": None, "ts": None, "i": None, "f": None},
    ]
    assert pd.Timestamp("2026-03-02 04:05:06.250").isoformat() == "2026-03-02T04:05:06.250000"


def test_bundle_fits_its_budget():
    size = len(gzip.compress(BUNDLE.read_bytes(), compresslevel=9))
    print(f"\ntracebi-calc.js: {size / 1024:.1f} KB gzipped")
    assert size <= 50 * 1024


def test_a_million_row_slice_recomputes_within_budget(tmp_path):
    """Three group columns, four measures, 1,000,000 rows: a grouped sum
    within 100 ms and a grouped quantile within 300 ms (warm, in node).

    The budget is held by the best of seven warm runs: the engine's cost,
    not whatever else the machine is doing (the suite shares CI cores). The
    median is printed beside it."""
    rng = np.random.default_rng(20261019)
    n = 1_000_000
    regions = np.array([f"Region {i}" for i in range(8)])
    sectors = np.array([f"Sector {i:02d}" for i in range(12)])
    months = np.array([f"2026-{m:02d}" for m in range(1, 13)]
                      + [f"2027-{m:02d}" for m in range(1, 13)])
    frame = pd.DataFrame({
        "dim_region.region": regions[rng.integers(0, len(regions), n)],
        "dim_issuer.sector": sectors[rng.integers(0, len(sectors), n)],
        "dim_date.month": months[rng.integers(0, len(months), n)],
        "par": rng.uniform(1e3, 5e6, n).round(2),
        "cost": rng.uniform(1e3, 5e6, n).round(2),
        "fair_value": rng.uniform(1e3, 5e6, n).round(2),
        "spread_bps": rng.integers(50, 900, n).astype("float64"),
    })
    path = tmp_path / "big.parquet"
    frame.to_parquet(path, engine="pyarrow", compression="snappy", index=False)
    groups = ["dim_region.region", "dim_issuer.sector", "dim_date.month"]
    measures = ["par", "cost", "fair_value", "spread_bps"]

    def plan(aggregates, group_by):
        return {"version": 1, "model": "m", "fact": "fact_big", "slice_columns": list(frame.columns),
                "filters": None, "group_by": group_by, "aggregates": aggregates, "means": [],
                "ratios": [], "shares": [], "combines": [], "ranks": [], "runnings": [],
                "having": [], "order_by": [{"column": g, "desc": False} for g in group_by],
                "limit": None, "columns": group_by + [a["name"] for a in aggregates]}

    sums = plan([{"name": m, "func": "sum", "source": {"col": m}} for m in measures], groups)
    quantiles = plan([{"name": "p90", "func": "quantile", "q": 0.9,
                       "source": {"col": "fair_value"}}], groups)
    selected = {"dim_issuer.sector": ["Sector 01", "Sector 05", "Sector 09"]}
    res = _run_node(tmp_path, [
        {"id": "sum", "fact": "fact_big", "parquet": str(path), "plan": sums, "selection": {}},
        {"id": "sum_selected", "fact": "fact_big", "parquet": str(path), "plan": sums,
         "selection": selected},
        {"id": "quantile", "fact": "fact_big", "parquet": str(path), "plan": quantiles,
         "selection": {}},
    ])
    print("\n1M-row slice (best / median of 7, ms): decode {:.0f}; grouped sum {:.1f} / {:.1f}; "
          "with a selection {:.1f} / {:.1f}; grouped p90 {:.1f} / {:.1f}".format(
              res["sum"]["load_ms"], res["sum"]["ms"], res["sum"]["median_ms"],
              res["sum_selected"]["ms"], res["sum_selected"]["median_ms"],
              res["quantile"]["ms"], res["quantile"]["median_ms"]))
    # The engine's numbers, not only its speed: pandas over the same frame.
    want = frame.groupby(groups)[measures].sum().reset_index()
    got = pd.DataFrame(res["sum"]["rows"], columns=res["sum"]["cols"])
    assert len(got) == len(want) == 8 * 12 * 24
    assert np.allclose(got[measures].to_numpy(), want[measures].to_numpy(), rtol=1e-8)
    assert res["sum"]["ms"] <= 100
    assert res["sum_selected"]["ms"] <= 100
    assert res["quantile"]["ms"] <= 300
