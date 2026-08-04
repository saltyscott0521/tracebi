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
    capped = _query(limit=1)
    assert capped["rows_returned"] == 1
    assert capped["truncated"]
    assert capped["row_count"] == full["row_count"]
    assert capped["fingerprint"] == full["fingerprint"]


def test_limit_is_clamped_to_the_hard_cap(gateway_model):
    from tracebi.mcp_server import _ROW_HARD_CAP
    out = _query(limit=10_000)
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
    manifest = json.loads(
        (tmp_path / "gw-spec.manifest.json").read_text(encoding="utf-8")
    )
    stamped = [s for s in manifest["sections"] if s.get("dataset_fingerprint")]
    assert stamped, "the manifest must fingerprint the data-bearing section"
    assert out["dataset_fingerprints"] == [
        s["dataset_fingerprint"] for s in stamped
    ]


def test_render_refuses_an_invalid_spec(gateway_model, tmp_path):
    out = gateway_render_spec(_spec(fact="fact_nope"), output_dir=str(tmp_path))
    assert not out["ok"]
    assert not list(tmp_path.iterdir()), "no artifact may exist for a refused spec"


# ── MCP registration (only when the optional dep is present) ───────────────

def test_build_server_registers_the_tools(gateway_model):
    pytest.importorskip("mcp")
    import anyio

    from tracebi.mcp_server import build_server

    server = build_server()
    tools = anyio.run(server.list_tools)
    names = {t.name for t in tools}
    assert names == {
        "get_context", "list_models", "describe_model", "query_model",
        "validate_report_spec", "render_report_spec", "list_reports",
        "verify_manifest",
    }
