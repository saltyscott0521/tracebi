"""Selection through DataModel, then the offline port that has to match it.

The authored selection is the receipt. A reader selection is the same filter
grammar, conjoined, re-run by the model. The fingerprint equals that query.
A report with no selection block still does not recompute. The worker port
of simple aggregations and ratio matches the model; period_end refuses.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector, QuerySpec
from tracebi.model.dataset import frame_fingerprint
from tracebi.reports.selection import (
    conjoin_filters,
    evaluate_selection,
    filters_equal,
    keep_cut,
    query_under_selection,
)
from tracebi.reports.selection_eval import (
    OfflineRefusal,
    aggregate_frame,
    plan_binding,
)
from tracebi.reports.template_package import TemplatePackage

_EVAL_JS = (
    __import__("pathlib").Path(__file__).parent.parent
    / "tracebi" / "reports" / "assets" / "selection_eval.js"
)


def _model():
    orders = pd.DataFrame({
        "customer_id": [10, 10, 20, 20],
        "revenue": [100, 50, 80, 20],
        "cost": [40, 10, 30, 10],
        "order_id": [1, 2, 3, 4],
    })
    customers = pd.DataFrame({
        "customer_id": [10, 20],
        "region": ["East", "West"],
    })
    m = DataModel("selection_model")
    m.add_connector(MemoryConnector("sel_mem", tables={
        "orders": orders, "customers": customers,
    }))
    m.add_table("orders", connector="sel_mem", source="orders")
    m.add_table("customers", connector="sel_mem", source="customers")
    m.add_dimension(
        "dim_customer", table_name="customers", key_col="customer_id",
        attributes=["region"],
    )
    m.add_fact(
        "fact_orders", table_name="orders",
        measures=["revenue", "cost", "order_id"],
        foreign_keys={"dim_customer": "customer_id"},
    )
    m.add_measure("revenue", column="revenue", agg="sum")
    m.add_measure("cost", column="cost", agg="sum")
    m.add_measure("orders", column="order_id", agg="count")
    m.add_measure("margin", ratio=("revenue", "cost"))
    m.add_measure("balance", period_end=("revenue", "dim_customer.region"))
    return m


def _package(tmp_path, *, selection=None, binding_filters=None):
    pkg = tmp_path / "demo"
    pkg.mkdir()
    query = {
        "fact": "fact_orders",
        "measures": ["revenue", "orders", "margin"],
        "dimensions": ["dim_customer.region"],
    }
    if binding_filters:
        query["filters"] = binding_filters
    document = {
        "name": "demo",
        "data": {
            "by_region": {"model": "selection_model", "query": query},
            "totals": {
                "model": "selection_model",
                "query": {
                    "fact": "fact_orders",
                    "measures": ["revenue", "margin"],
                },
            },
        },
    }
    if selection is not None:
        document["selection"] = selection
    (pkg / "report.json").write_text(json.dumps(document), encoding="utf-8")
    (pkg / "template.html").write_text(
        "<html><head><title>demo</title></head><body>"
        '<div class="tb-kpi" data-tb-figure="value" data-tb-binding="totals" '
        'data-tb-cell="revenue" id="fig-total"></div>'
        '<div data-tb-figure="value" data-tb-binding="totals" '
        'data-tb-cell="margin" id="fig-margin"></div>'
        '<table data-tb-figure="table" data-tb-binding="by_region" '
        'id="fig-regions"></table>'
        '<select data-tb-filter data-tb-binding="by_region" '
        'data-tb-column="dim_customer.region"></select>'
        "</body></html>",
        encoding="utf-8",
    )
    return pkg


class TestConjoin:
    def test_selection_wins_on_the_same_target_and_keeps_the_rest(self):
        merged = conjoin_filters(
            {"dim_customer.region": "East", "status": "open"},
            {"dim_customer.region": "West"},
        )
        assert merged == {"dim_customer.region": "West", "status": "open"}

    def test_having_order_and_limit_stay_on_the_binding(self):
        query = QuerySpec(
            fact="fact_orders", measures=["revenue"],
            filters={"status": "open"},
            having={"revenue": {"gte": 10}},
            order_by=("-revenue",), limit=3,
        )
        out = query_under_selection(query, {"dim_customer.region": "East"})
        assert out.having == {"revenue": {"gte": 10}}
        assert out.limit == 3
        assert out.order_by[0]["column"] == "revenue"
        assert out.filters["status"] == "open"
        assert out.filters["dim_customer.region"] == "East"

    def test_empty_selection_does_not_rewrite_an_unfiltered_query(self):
        query = QuerySpec(fact="fact_orders", measures=["revenue"])
        assert query_under_selection(query, {}) is query
        assert filters_equal({}, None)


class TestPackageSelection:
    def test_absent_block_does_not_opt_in(self, tmp_path):
        pkg = TemplatePackage(str(_package(tmp_path)))
        assert pkg.selection is None

    def test_empty_filters_opt_in_without_an_extra_cut(self, tmp_path):
        pkg = TemplatePackage(str(_package(
            tmp_path, selection={"model": "selection_model", "filters": {}},
        )))
        assert pkg.selection == {"model": "selection_model", "filters": {}}

    def test_build_stamps_the_authored_selection(self, tmp_path):
        model = _model()
        pkg = TemplatePackage(str(_package(
            tmp_path,
            selection={"model": "selection_model",
                       "filters": {"dim_customer.region": "East"}},
        )))
        _report, stamped = pkg.build({"selection_model": model})
        by_name = {sd.name: sd for sd in stamped}
        expected = model.query(
            "fact_orders", ["revenue", "margin"],
            filters={"dim_customer.region": "East"},
        )
        assert by_name["totals"].fingerprint == expected.fingerprint()
        assert by_name["totals"].query_spec["filters"] == {
            "dim_customer.region": "East",
        }


class TestEvaluate:
    def test_fingerprint_equals_the_conjoined_query(self, tmp_path):
        model = _model()
        pkg = TemplatePackage(str(_package(
            tmp_path,
            selection={"model": "selection_model", "filters": {}},
            binding_filters={"dim_customer.region": "East"},
        )))
        # The reader moves the region control to West. The binding's East
        # predicate loses, because that target is the control.
        result = evaluate_selection(
            pkg, {"selection_model": model},
            {"dim_customer.region": "West"},
        )
        assert result["authored"] is False
        totals = model.query(
            "fact_orders", ["revenue", "margin"],
            filters={"dim_customer.region": "West"},
        )
        fig = next(f for f in result["figures"] if f["id"] == "fig-total")
        assert fig["fingerprint"] == totals.fingerprint()
        assert fig["value"] == pytest.approx(100.0)
        regions = next(f for f in result["figures"] if f["id"] == "fig-regions")
        assert regions["rows"] == [{
            "dim_customer.region": "West",
            "revenue": 100.0,
            "orders": 2,
            "cost": 40.0,
            "margin": 2.5,
        }]
        control = result["controls"][0]
        assert "West" in control["included"]
        # East still has rows under no other cut, so it is selectable.
        assert "East" in control["included"]
        assert control["excluded"] == []

    def test_a_value_with_no_rows_under_the_rest_is_excluded(self, tmp_path):
        model = _model()
        pkg = TemplatePackage(str(_package(
            tmp_path, selection={"model": "selection_model", "filters": {}},
        )))
        result = evaluate_selection(
            pkg, {"selection_model": model},
            {"dim_customer.region": "East", "revenue": {"gte": 1000}},
        )
        control = result["controls"][0]
        assert control["included"] == []
        assert control["excluded"] == ["East", "West"]

    def test_without_a_block_selection_is_refused(self, tmp_path):
        model = _model()
        pkg = TemplatePackage(str(_package(tmp_path)))
        with pytest.raises(ValueError, match="no selection block"):
            evaluate_selection(pkg, {"selection_model": model}, {})

    def test_page_without_a_block_keeps_connect_src_none(self, tmp_path):
        model = _model()
        pkg = TemplatePackage(str(_package(tmp_path)))
        out = tmp_path / "plain.html"
        pkg.render({"selection_model": model}, str(out), save_manifest=False)
        html = out.read_text(encoding="utf-8")
        assert "connect-src 'none'" in html
        assert 'id="tracebi-selection"' not in html

    def test_opted_in_page_can_reach_the_model(self, tmp_path):
        model = _model()
        pkg = TemplatePackage(str(_package(
            tmp_path, selection={"model": "selection_model", "filters": {}},
        )))
        out = tmp_path / "cut.html"
        pkg.render({"selection_model": model}, str(out), save_manifest=True)
        html = out.read_text(encoding="utf-8")
        assert "connect-src 'self'" in html
        assert 'id="tracebi-selection"' in html
        assert 'id="tracebi-grain"' in html
        from tracebi.verify import verify_file
        manifest = json.loads((tmp_path / "cut.html.manifest.json").read_text())
        checked = verify_file(html, manifest)
        assert checked["ok"], checked["verdict_detail"]


class TestKeep:
    def test_keep_writes_the_cut_and_reproduces(self, tmp_path, monkeypatch):
        model = _model()
        pkg_dir = _package(
            tmp_path, selection={"model": "selection_model", "filters": {}},
        )
        monkeypatch.chdir(tmp_path)
        result = keep_cut(
            str(pkg_dir),
            {"dim_customer.region": "East"},
            {"selection_model": model},
            str(tmp_path / "output" / "demo.html"),
        )
        assert result["verdict"] == "reproduces"
        assert result["ok"] is True
        saved = json.loads((pkg_dir / "report.json").read_text(encoding="utf-8"))
        assert saved["selection"]["filters"] == {"dim_customer.region": "East"}
        manifest = json.loads(
            (tmp_path / "output" / "demo.html.manifest.json").read_text()
        )
        # The authored receipt is the cut that was on screen.
        for section in manifest["sections"]:
            node_specs = []
            for node in section.get("dataset_lineage") or []:
                spec = (node.get("metadata") or {}).get("query_spec")
                if spec:
                    node_specs.append(spec)
            assert node_specs, section
            assert node_specs[-1]["filters"]["dim_customer.region"] == "East"


class TestEndpoint:
    def test_post_selection_returns_the_query_fingerprint(self, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from tracebi import model_registry
        from tracebi.web.api.routers import reports as reports_router
        from tracebi.web.discovery import _register_template_package

        model = _model()
        model_registry.register(model)
        pkg = _package(
            tmp_path, selection={"model": "selection_model", "filters": {}},
        )
        registered = _register_template_package(str(pkg), "sel_demo")
        assert registered["status"] == "registered", registered
        app = FastAPI()
        app.include_router(reports_router.router, prefix="/api")
        client = TestClient(app)
        res = client.post(
            "/api/reports/sel_demo/selection",
            json={"filters": {"dim_customer.region": "East"}},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        fig = next(f for f in body["figures"] if f["id"] == "fig-total")
        expected = model.query(
            "fact_orders", ["revenue", "margin"],
            filters={"dim_customer.region": "East"},
        )
        assert fig["fingerprint"] == expected.fingerprint()
        bare = client.post("/api/reports/sel_demo/selection", json={"filters": {}})
        assert bare.status_code == 200
        # A report that never opted in is not this package; the empty-filters
        # request on an opted-in package is the authored cut.
        assert bare.json()["authored"] is True


class TestOfflinePort:
    def _plan(self, measures, dimensions=(), filters=None, order_by=(), limit=None):
        return plan_binding(_model(), QuerySpec(
            fact="fact_orders", measures=measures, dimensions=tuple(dimensions),
            filters=filters, order_by=order_by, limit=limit,
        ))

    def _grain(self, model, plan):
        sources = []
        for agg in plan["aggs"]:
            if agg["source"] not in sources:
                sources.append(agg["source"])
        spec = QuerySpec(
            fact=plan["fact"],
            measures={src: "sum" for src in sources},
            dimensions=tuple(plan["dimensions"]),
            aggregate=False,
        )
        return model.execute(spec).to_pandas()

    def _js(self, rows, plan, filters):
        node = shutil.which("node")
        if node is None:
            pytest.skip("node not available")
        script = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const payload = JSON.parse(process.argv[2]);
eval(src);
const result = tracebiSelectionEval(payload.rows, payload.plan, payload.filters);
process.stdout.write(JSON.stringify(result));
"""
        proc = subprocess.run(
            [node, "-e", script, str(_EVAL_JS), json.dumps({
                "rows": rows, "plan": plan, "filters": filters,
            })],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    def _as_frame(self, js_rows, plan, grain):
        from tracebi.reports.selection_eval import _cast_agg, _empty_result
        dims = plan["dimensions"]
        aggs = plan["aggs"]
        ratios = plan["ratios"]
        if not js_rows:
            return _empty_result(grain, dims, aggs, ratios)
        df = pd.DataFrame(js_rows)
        cols = dims + [a["name"] for a in aggs] + [r["name"] for r in ratios]
        df = df[cols]
        for agg in aggs:
            df[agg["name"]] = _cast_agg(df[agg["name"]], agg["func"], grain[agg["source"]])
        for dim in dims:
            df[dim] = df[dim].astype(grain[dim].dtype)
        for ratio in ratios:
            df[ratio["name"]] = df[ratio["name"]].astype("float64")
        return df.reset_index(drop=True)

    def test_simple_and_ratio_match_the_model(self):
        model = _model()
        plan = self._plan(
            ["revenue", "orders", "margin"], ["dim_customer.region"],
        )
        assert plan["offline"] is True
        grain = self._grain(model, plan)
        port = aggregate_frame(grain, plan, {})
        expected = model.query(
            "fact_orders", ["revenue", "orders", "margin"],
            ["dim_customer.region"],
        ).to_pandas()
        assert frame_fingerprint(port) == frame_fingerprint(expected)
        js = self._js(
            json.loads(grain.to_json(orient="records")), plan, {},
        )
        assert js.get("refused") in (None, False) or "rows" in js
        js_frame = self._as_frame(js["rows"], plan, grain)
        assert frame_fingerprint(js_frame) == frame_fingerprint(expected)

    def test_a_one_row_drift_changes_the_fingerprint(self):
        model = _model()
        plan = self._plan(["revenue", "margin"])
        grain = self._grain(model, plan)
        expected = model.query(
            "fact_orders", ["revenue", "margin"],
        ).fingerprint()
        js = self._js(json.loads(grain.to_json(orient="records")), plan, {})
        assert frame_fingerprint(self._as_frame(js["rows"], plan, grain)) == expected
        drifted = json.loads(grain.to_json(orient="records"))
        drifted[0]["revenue"] = drifted[0]["revenue"] + 1
        js_drift = self._js(drifted, plan, {})
        assert frame_fingerprint(
            self._as_frame(js_drift["rows"], plan, grain)
        ) != expected

    def test_selection_filter_matches_the_model(self):
        model = _model()
        plan = self._plan(["revenue", "margin"], ["dim_customer.region"])
        grain = self._grain(model, plan)
        filters = {"dim_customer.region": "East"}
        port = aggregate_frame(grain, plan, filters)
        expected = model.query(
            "fact_orders", ["revenue", "margin"],
            ["dim_customer.region"], filters=filters,
        ).to_pandas()
        assert frame_fingerprint(port) == frame_fingerprint(expected)

    def test_period_end_refuses_offline(self):
        plan = self._plan(["balance"])
        assert plan["offline"] is False
        assert plan["reason"] == "period_end"
        with pytest.raises(OfflineRefusal):
            aggregate_frame(pd.DataFrame({"revenue": [1]}), plan, {})
        js = self._js([], plan, {})
        assert js["refused"] == "period_end"

    def test_top_n_stays_inside_the_selection(self):
        model = _model()
        plan = self._plan(
            ["revenue"], ["dim_customer.region"],
            order_by=("-revenue",), limit=1,
        )
        grain = self._grain(model, plan)
        filters = {"dim_customer.region": ["East", "West"]}
        port = aggregate_frame(grain, plan, filters)
        expected = model.query(
            "fact_orders", ["revenue"], ["dim_customer.region"],
            filters=filters, order_by=["-revenue"], limit=1,
        ).to_pandas()
        assert frame_fingerprint(port) == frame_fingerprint(expected)
        assert len(port) == 1
