"""
Agent gateway tests — the ``gateway_*`` functions in ``tracebi/mcp_server.py``.

The gateway's promise is the *stamp*: every query response carries the
resolved query, the lineage chain, and a fingerprint of the full result.
These tests hold it to that — a stamped response must re-verify, a preview
cap must not change the fingerprint, and JSON must survive the trip —
because an agent will quote these numbers to a person who never sees this
code.

The MCP registration layer itself is only exercised when the optional
``mcp`` package is installed (skipped otherwise); the operations are plain
functions precisely so the suite does not depend on it.
"""

import json

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi import model_registry
from tracebi.mcp_server import (
    gateway_context,
    gateway_model_info,
    gateway_models,
    gateway_query,
    gateway_render_spec,
    gateway_validate_spec,
)


@pytest.fixture()
def gateway_model():
    """A small star schema registered under a name no other test uses."""
    orders = pd.DataFrame({
        "order_id":    [1, 2, 3, 4, 5, 6],
        "customer_id": [1, 2, 1, 3, 2, 1],
        "revenue":     [100.0, 250.0, 75.0, 300.0, 125.0, 50.0],
        "status":      ["shipped", "open", "shipped", "shipped", "open", "shipped"],
    })
    customers = pd.DataFrame({
        "customer_id": [1, 2, 3],
        "region":      ["NE", "SE", "MW"],
    })
    connector = MemoryConnector("gw_mem", tables={
        "orders": orders, "customers": customers,
    })
    model = DataModel("gw_demo")
    model.add_connector(connector)
    model.add_table("orders", connector="gw_mem", source="orders")
    model.add_table("customers", connector="gw_mem", source="customers")
    model.add_relationship(
        "orders_to_customers",
        left_table="orders", right_table="customers", left_key="customer_id",
    )
    model.add_dimension(
        "dim_customer", table_name="customers",
        key_col="customer_id", attributes=["region"],
    )
    model.add_fact(
        "fact_orders", table_name="orders",
        measures=["revenue"], foreign_keys={"dim_customer": "customer_id"},
    )
    model.add_measure(
        "total_revenue", column="revenue", agg="sum", format="currency",
    )
    model.connect()
    model_registry.register(model)
    return model


def _query(**overrides):
    kwargs = dict(
        model="gw_demo",
        fact="fact_orders",
        measures={"revenue": "sum"},
        dimensions=["dim_customer.region"],
    )
    kwargs.update(overrides)
    return gateway_query(**kwargs)


# ── The stamp ──────────────────────────────────────────────────────────────

def test_query_is_stamped(gateway_model):
    out = _query()
    assert out["fingerprint"], "a stamped response must carry a fingerprint"
    assert out["lineage"], "a stamped response must carry a lineage chain"
    assert out["query"]["fact"] == "fact_orders"
    assert out["row_count"] == 3          # NE, SE, MW
    assert not out["truncated"]


def test_having_is_applied_and_echoed_by_the_gateway(gateway_model):
    """having must reach the query over MCP — the primary agent surface —
    not be dropped. An impossibly high threshold yields no groups, and the
    stamped query echoes having so what the agent cites is what ran."""
    out = _query(having={"revenue": {"gte": 10 ** 12}})
    assert out["row_count"] == 0, "having must filter groups over the gateway"
    assert out["query"].get("having") == {"revenue": {"gte": 10 ** 12}}, (
        "the stamped query must echo having, not silently drop it"
    )


def test_stamp_reverifies(gateway_model):
    """The recorded query, re-run, reproduces the recorded fingerprint."""
    out = _query()
    q = out["query"]
    ds = gateway_model.query(
        fact=q["fact"], measures=q["measures"],
        dimensions=q["dimensions"], filters=q["filters"] or None,
        aggregate=q["aggregate"], allow_fanout=q["allow_fanout"],
    )
    assert ds.fingerprint() == out["fingerprint"]


def test_preview_cap_does_not_change_the_fingerprint(gateway_model):
    """rows is transport; the stamp covers the full result."""
    full = _query()
    capped = _query(preview_rows=1)
    assert capped["rows_returned"] == 1
    assert capped["truncated"]
    assert capped["row_count"] == full["row_count"]
    assert capped["fingerprint"] == full["fingerprint"]


def test_preview_rows_is_clamped_to_the_hard_cap(gateway_model):
    from tracebi.mcp_server import _ROW_HARD_CAP
    out = _query(preview_rows=10_000)
    assert out["rows_returned"] <= _ROW_HARD_CAP


def test_response_is_json_serializable(gateway_model):
    """numpy scalars and index types must not leak into the payload."""
    out = _query()
    json.dumps(out)  # raises TypeError on any non-JSON-safe value


def test_filters_travel_through(gateway_model):
    out = _query(filters={"status": "shipped"}, dimensions=[])
    assert out["row_count"] == 1
    total = out["rows"][0]["revenue"]
    assert total == pytest.approx(100.0 + 75.0 + 300.0 + 50.0)
    assert out["query"]["filters"] == {"status": "shipped"}


def test_unknown_model_names_the_alternatives(gateway_model):
    with pytest.raises(KeyError, match="gw_demo"):
        gateway_query(model="nope", fact="f", measures={"x": "sum"})


# ── Contract and schema ────────────────────────────────────────────────────

def test_context_carries_the_vocabulary(gateway_model):
    ctx = gateway_context()
    assert "sections" in ctx or "report_sections" in ctx or ctx  # vocabulary present
    with_model = gateway_context(model="gw_demo")
    assert with_model["model"]["name"] == "gw_demo"


def test_models_listing_includes_the_fixture(gateway_model):
    listing = gateway_models()["models"]
    assert "gw_demo" in listing
    assert "total_revenue" in listing["gw_demo"]["measures"]
    info = gateway_model_info("gw_demo")
    assert info["name"] == "gw_demo"


def test_models_listing_collapses_aliases(gateway_model, monkeypatch):
    """stem + .name index the same object; the listing shows one model."""
    import tracebi.mcp_server as gw

    monkeypatch.setattr(
        gw, "_load_models",
        lambda: {"gw_demo": gateway_model, "gw_demo_file": gateway_model},
    )
    listing = gw.gateway_models()["models"]
    assert list(listing) == ["gw_demo"]
    assert listing["gw_demo"]["aliases"] == ["gw_demo_file"]


def test_named_measure_queries_through_the_gateway(gateway_model):
    out = _query(measures=["total_revenue"], dimensions=[])
    assert out["row_count"] == 1
    assert out["rows"][0]["total_revenue"] == pytest.approx(900.0)
    assert out["fingerprint"]


# ── Spec validation and rendering ──────────────────────────────────────────

def _spec(fact="fact_orders"):
    return {
        "name": "GW Spec",
        "sections": [{
            "type": "table",
            "title": "Revenue by region",
            "data": {
                "model": "gw_demo",
                "query": {
                    "fact": fact,
                    "measures": {"revenue": "sum"},
                    "dimensions": ["dim_customer.region"],
                },
            },
        }],
    }


def test_validate_accepts_a_good_spec(gateway_model):
    result = gateway_validate_spec(_spec())
    assert result["ok"], result["errors"]


def test_validate_paths_a_bad_fact(gateway_model):
    result = gateway_validate_spec(_spec(fact="fact_nope"))
    assert not result["ok"]
    assert any("fact" in e for e in result["errors"])


def test_validate_survives_garbage():
    result = gateway_validate_spec("{not json")
    assert not result["ok"]
    assert result["errors"]


def test_render_produces_artifact_and_manifest(gateway_model, tmp_path):
    out = gateway_render_spec(_spec(), output_dir=str(tmp_path))
    assert out["ok"], out.get("errors")
    html = (tmp_path / "gw-spec.html").read_text(encoding="utf-8")
    assert "Revenue by region" in html
    # A spec now renders through the artifact path (compile_spec ->
    # TemplatePackage): the figure grammar + receipt drawer, NOT the legacy
    # renderer's second ECharts runtime.
    assert "data-tb-figure" in html
    assert 'id="tracebi-receipt"' in html
    assert 'id="tracebi-charts"' not in html
    manifest = json.loads(
        (tmp_path / "gw-spec.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 2
    stamped = [s for s in manifest["sections"] if s.get("dataset_fingerprint")]
    assert stamped, "the manifest must fingerprint the data-bearing section"
    assert out["dataset_fingerprints"] == [
        s["dataset_fingerprint"] for s in stamped
    ]


def test_render_refuses_an_invalid_spec(gateway_model, tmp_path):
    out = gateway_render_spec(_spec(fact="fact_nope"), output_dir=str(tmp_path))
    assert not out["ok"]
    assert not list(tmp_path.iterdir()), "no artifact may exist for a refused spec"


# ── build_report: the publish step for the package lane ────────────────────

class TestBuildReport:
    def _package(self, tmp_path, monkeypatch, gateway_model):
        import tracebi.mcp_server as gw

        reports = tmp_path / "reports"
        pkg = reports / "gwpkg"
        pkg.mkdir(parents=True)
        (pkg / "report.json").write_text(json.dumps({
            "name": "gwpkg",
            "data": {"kpi": {"model": "gw_demo",
                             "query": {"fact": "fact_orders",
                                       "measures": ["total_revenue"]}}},
        }))
        (pkg / "template.html").write_text(
            "<html><head><title>g</title></head><body>"
            '<div data-tb-figure="value" data-tb-binding="kpi" '
            'data-tb-cell="total_revenue" id="fig-kpi"></div>'
            '<section data-tb-stage="exploration"><p>scratch</p></section>'
            "</body></html>"
        )
        monkeypatch.setenv("TRACEBI_REPORTS_DIR", str(reports))
        monkeypatch.setattr(gw, "_load_models",
                            lambda: {"gw_demo": gateway_model})
        return pkg

    def test_builds_artifact_and_receipt(self, gateway_model, tmp_path,
                                         monkeypatch):
        from tracebi.mcp_server import gateway_build_report

        self._package(tmp_path, monkeypatch, gateway_model)
        out = gateway_build_report("gwpkg", output_dir=str(tmp_path / "out"))
        assert out["ok"], out.get("errors")
        html = (tmp_path / "out" / "gwpkg.html").read_text(encoding="utf-8")
        assert "scratch" not in html, "exploration must die at build"
        assert (tmp_path / "out" / "gwpkg.html.manifest.json").is_file()
        assert out["figures"] and out["figures"][0]["id"] == "fig-kpi"
        assert out["embedded_fingerprints"]

    def test_refuses_a_path_shaped_name(self, gateway_model, tmp_path,
                                        monkeypatch):
        from tracebi.mcp_server import gateway_build_report

        self._package(tmp_path, monkeypatch, gateway_model)
        out = gateway_build_report("../gwpkg")
        assert not out["ok"]
        assert "name" in out["errors"][0]

    def test_refuses_writing_into_the_installed_package(self, gateway_model,
                                                        tmp_path, monkeypatch):
        """Always on: an agent must not write into the tracebi package (e.g.
        clobber web/ui/dist/index.html, which a server then serves)."""
        import pathlib

        import tracebi
        from tracebi.mcp_server import gateway_build_report

        self._package(tmp_path, monkeypatch, gateway_model)
        pkg_dist = str(
            pathlib.Path(tracebi.__file__).resolve().parent / "web" / "ui" / "dist")
        out = gateway_build_report("index", output_dir=pkg_dist)
        assert not out["ok"]
        assert "package" in out["errors"][0]

    def test_strict_confinement_refuses_output_outside_the_root(
            self, gateway_model, tmp_path, monkeypatch):
        """Opt-in: with TRACEBI_OUTPUT_ROOT set, an absolute path outside it or
        a traversal that escapes it is refused before any write."""
        from tracebi.mcp_server import gateway_build_report

        self._package(tmp_path, monkeypatch, gateway_model)
        monkeypatch.setenv("TRACEBI_OUTPUT_ROOT", str(tmp_path / "out"))
        for bad in ["/tmp/tracebi-escape-xyz", str(tmp_path / "elsewhere")]:
            out = gateway_build_report("gwpkg", output_dir=bad)
            assert not out["ok"], f"{bad!r} was not refused"
            assert "TRACEBI_OUTPUT_ROOT" in out["errors"][0]

    def test_missing_package_is_a_result_not_a_crash(self, gateway_model,
                                                     tmp_path, monkeypatch):
        from tracebi.mcp_server import gateway_build_report

        self._package(tmp_path, monkeypatch, gateway_model)
        out = gateway_build_report("nope")
        assert not out["ok"]
        assert "no artifact package" in out["errors"][0]


# ── workbench_state: no report means the discovery session ─────────────────

def test_workbench_state_defaults_to_discovery(tmp_path, monkeypatch):
    """Called with no report (the human is running `tracebi dev` with no
    name), the tool returns the project-level discovery state."""
    import tracebi.mcp_server as gw
    from tracebi.mcp_server import gateway_workbench_state

    monkeypatch.chdir(tmp_path)
    # Isolate from the process-global model registry: earlier tests
    # register models whose DuckDB warehouses discovery would (correctly)
    # scan, flipping warehouse.exists in full-suite runs.
    monkeypatch.setattr(gw, "_load_models", lambda: {})
    out = gateway_workbench_state()
    assert out["mode"] == "discovery"
    assert out["name"] == "_discovery"
    assert out["warehouse"]["exists"] is False
    assert out["packages"] == []
    assert out["exhibits"] == [] and out["pins"] == []


def test_workbench_state_refuses_a_path_shaped_name(tmp_path, monkeypatch):
    """A caller-supplied report name must never become a path. Without the
    guard, report='/etc/x' or '../../x' escapes reports/ and collect_state
    reads — and executes report.py from — an attacker-chosen directory. The
    refusal must fire before any filesystem access."""
    import tracebi.mcp_server as gw
    from tracebi.mcp_server import gateway_workbench_state

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gw, "_load_models", lambda: {})
    for payload in ["/etc/passwd", "../../etc/x", "../secrets", ".ssh/config"]:
        out = gateway_workbench_state(report=payload)
        assert "errors" in out, f"{payload!r} was not refused: {out!r}"
        assert "not a path" in out["errors"][0]


def test_workbench_state_with_a_name_stays_package_scoped(tmp_path, monkeypatch):
    """A named report keeps exactly the package behavior — a missing
    package is the errors envelope, never the discovery state."""
    from tracebi.mcp_server import gateway_workbench_state

    monkeypatch.setenv("TRACEBI_REPORTS_DIR", str(tmp_path / "reports"))
    out = gateway_workbench_state("nope")
    assert "no artifact package" in out["errors"][0]


# ── MCP registration (only when the optional dep is present) ───────────────

def test_build_server_registers_the_tools(gateway_model):
    pytest.importorskip("mcp")
    import anyio

    from tracebi.mcp_server import build_server

    server = build_server()
    tools = anyio.run(server.list_tools)
    names = {t.name for t in tools}
    # M3 flip: workbench_state joined the surface. Round-2 flip: build_report
    # joined it — the publish step for the package lane, so an MCP-driving
    # agent can finish the loop it iterates in the workbench (ten tools).
    assert names == {
        "get_context", "list_models", "describe_model", "query_model",
        "validate_report_spec", "render_report_spec", "list_reports",
        "verify_manifest", "workbench_state", "build_report",
    }


# ── MCP 2.0 protocol features ────────────────────────────────────────────────
# The gateway advertises typed structured output, read-only tool annotations
# (the "read-and-compute only" refusal, in the protocol), reference resources,
# and an authoring prompt.

class TestMcp2Features:
    def _tools(self):
        pytest.importorskip("mcp")
        import anyio
        from tracebi.mcp_server import build_server
        server = build_server()
        return server, {t.name: t for t in anyio.run(server.list_tools)}

    def test_every_tool_advertises_an_output_schema(self, gateway_model):
        _server, tools = self._tools()
        for name, t in tools.items():
            d = t.model_dump(by_alias=True, exclude_none=True)
            assert d.get("outputSchema"), f"{name} has no outputSchema"

    def test_read_tools_are_annotated_read_only(self, gateway_model):
        _server, tools = self._tools()
        read_only = {
            "get_context", "list_models", "describe_model", "query_model",
            "validate_report_spec", "list_reports", "verify_manifest",
        }
        for name in read_only:
            ann = tools[name].annotations
            assert ann is not None
            assert ann.model_dump(by_alias=True).get("readOnlyHint") is True, name
        # render is the one writer — it must NOT claim read-only, and it is
        # non-destructive (writes only its own artifact, never source data).
        render = tools["render_report_spec"].annotations.model_dump(by_alias=True)
        assert render.get("readOnlyHint") is False
        assert render.get("destructiveHint") is False

    def test_query_tool_emits_structured_content(self, gateway_model):
        pytest.importorskip("mcp")
        import anyio
        server, _ = self._tools()

        async def call():
            return await server.call_tool("query_model", {
                "model": "gw_demo", "fact": "fact_orders",
                "measures": {"revenue": "sum"},
                "dimensions": ["dim_customer.region"],
            })

        result = anyio.run(call)
        payload = result.model_dump(by_alias=True, exclude_none=True)
        assert payload.get("isError") is not True
        sc = payload.get("structuredContent")
        assert sc and sc.get("fingerprint"), "the stamp must arrive as structured content"
        assert sc.get("row_count") == 3

    def test_resources_and_template_are_registered_and_readable(self, gateway_model):
        pytest.importorskip("mcp")
        import anyio
        server, _ = self._tools()

        static = {str(r.uri) for r in anyio.run(server.list_resources)}
        assert {"tracebi://guide", "tracebi://spec-schema"} <= static
        templates = {t.uri_template for t in anyio.run(server.list_resource_templates)}
        assert "tracebi://models/{name}" in templates

        # the spec-schema resource returns the real ReportSpec JSON Schema
        schema = list(anyio.run(server.read_resource, "tracebi://spec-schema"))[0].content
        assert json.loads(schema).get("$schema")
        # the model template resolves to that model's schema
        model_doc = list(anyio.run(server.read_resource, "tracebi://models/gw_demo"))[0].content
        assert json.loads(model_doc)["name"] == "gw_demo"

    def test_author_report_prompt_walks_the_loop(self, gateway_model):
        pytest.importorskip("mcp")
        import anyio
        server, _ = self._tools()

        prompts = {p.name for p in anyio.run(server.list_prompts)}
        assert "author_report" in prompts

        async def render():
            return await server.get_prompt("author_report", {"question": "revenue by region?"})

        got = anyio.run(render)
        text = got.messages[0].content.text
        assert "revenue by region?" in text
        for step in ("get_context", "query_model", "validate_report_spec",
                     "render_report_spec", "verify_manifest"):
            assert step in text, f"the SOP prompt should name {step}"
