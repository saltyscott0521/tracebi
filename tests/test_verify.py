"""
The verify loop — input fingerprints at load, manifest schema_version, and
``tracebi verify`` / the ``verify_manifest`` gateway tool.

The trust thesis rests on receipts someone can check. These tests close the
loop end to end: a rendered manifest re-verifies (REPRODUCES), a mutated
source table is diagnosed (SOURCE DRIFT via input fingerprints), a tampered
result fingerprint with unmoved inputs is the alarming case (UNEXPLAINED),
and python-authored ad hoc data is honestly UNVERIFIABLE — with the CLI
exit codes distinguishing the three outcomes.
"""

import json

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector, model_registry
from tracebi.cli import main as cli_main
from tracebi.mcp_server import gateway_render_spec, gateway_verify_manifest
from tracebi.model.dataset import DataSet, LineageNode, frame_fingerprint
from tracebi.reports.report import Report, TableSection
from tracebi.verify import (
    MISMATCH_UNKNOWN,
    REPRODUCES,
    SOURCE_DRIFT,
    UNEXPLAINED,
    UNVERIFIABLE,
    load_models,
    verify_manifest,
)


ORDERS = pd.DataFrame({
    "order_id":    [1, 2, 3, 4, 5, 6],
    "customer_id": [1, 2, 1, 3, 2, 1],
    "revenue":     [100.0, 250.0, 75.0, 300.0, 125.0, 50.0],
    "status":      ["shipped", "open", "shipped", "shipped", "open", "shipped"],
})
CUSTOMERS = pd.DataFrame({
    "customer_id": [1, 2, 3],
    "region":      ["NE", "SE", "MW"],
})


@pytest.fixture()
def vf_model():
    """A fresh star schema per test, registered under a name only this
    module uses. Fresh per test so one test's source mutation cannot leak
    into another."""
    connector = MemoryConnector("vf_mem", tables={
        "orders": ORDERS.copy(), "customers": CUSTOMERS.copy(),
    })
    model = DataModel("vf_demo")
    model.add_connector(connector)
    model.add_table("orders", connector="vf_mem", source="orders")
    model.add_table("customers", connector="vf_mem", source="customers")
    model.add_dimension(
        "dim_customer", table_name="customers",
        key_col="customer_id", attributes=["region"],
    )
    model.add_fact(
        "fact_orders", table_name="orders",
        measures=["revenue"], foreign_keys={"dim_customer": "customer_id"},
    )
    model.connect()
    model_registry.register(model)
    return model


@pytest.fixture()
def empty_models_dir(tmp_path):
    """A models dir with no files, so verify sees only registry models and
    never auto-discovers the repository's own models/ as a side effect."""
    d = tmp_path / "no_models"
    d.mkdir()
    return d


def _spec():
    return {
        "name": "VF Spec",
        "sections": [{
            "type": "table",
            "title": "Revenue by region",
            "data": {
                "model": "vf_demo",
                "query": {
                    "fact": "fact_orders",
                    "measures": {"revenue": "sum"},
                    "dimensions": ["dim_customer.region"],
                },
            },
        }],
    }


def _render(tmp_path):
    out = gateway_render_spec(_spec(), output_dir=str(tmp_path))
    assert out["ok"], out.get("errors")
    return tmp_path / "vf-spec.manifest.json"


def _connector_of(model):
    return model.connectors()[0]


# ── (a) Input fingerprints at query time ───────────────────────────────────

def test_query_lineage_records_input_fingerprints(vf_model):
    ds = vf_model.query(
        fact="fact_orders", measures={"revenue": "sum"},
        dimensions=["dim_customer.region"],
    )
    inputs = {
        n.metadata["input"]["table"]: n.metadata["input"]
        for n in ds.lineage if n.operation == "load"
    }
    assert set(inputs) == {"orders", "customers"}
    assert inputs["orders"]["fingerprint"] == frame_fingerprint(ORDERS)
    assert inputs["orders"]["rows"] == len(ORDERS)
    assert inputs["customers"]["fingerprint"] == frame_fingerprint(CUSTOMERS)


def test_rendered_manifest_carries_input_fingerprints(vf_model, tmp_path):
    manifest = json.loads(_render(tmp_path).read_text(encoding="utf-8"))
    section = next(
        s for s in manifest["sections"] if s.get("dataset_fingerprint")
    )
    recorded = [
        n["metadata"]["input"]
        for n in section["dataset_lineage"]
        if n.get("metadata", {}).get("input")
    ]
    assert {i["table"] for i in recorded} == {"orders", "customers"}
    assert all(i["fingerprint"] and i["rows"] for i in recorded)


# ── (b) Manifest schema version ────────────────────────────────────────────

def test_manifest_declares_schema_version(vf_model, tmp_path):
    manifest = json.loads(_render(tmp_path).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1


# ── Render → verify round trip ─────────────────────────────────────────────

def test_render_verify_reproduces(vf_model, tmp_path, empty_models_dir, capsys):
    manifest_path = _render(tmp_path)
    rc = cli_main([
        "verify", str(manifest_path), "--models-dir", str(empty_models_dir),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "REPRODUCES" in out
    assert "Revenue by region" in out


def test_mutated_source_is_diagnosed_as_source_drift(
    vf_model, tmp_path, empty_models_dir, capsys,
):
    manifest_path = _render(tmp_path)
    drifted = ORDERS.copy()
    drifted.loc[0, "revenue"] = 999.0
    _connector_of(vf_model).write(drifted, "orders")

    rc = cli_main([
        "verify", str(manifest_path), "--models-dir", str(empty_models_dir),
    ])
    assert rc == 2, "diagnosed drift is exit 2, not the alarming exit 1"
    err = capsys.readouterr().err
    assert "SOURCE DRIFT" in err
    assert "orders" in err, "the drifted table must be named"

    result = verify_manifest(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        load_models(empty_models_dir),
    )
    (section,) = result["sections"]
    assert section["status"] == SOURCE_DRIFT
    orders_input = next(
        i for i in section["inputs"] if i["table"] == "orders"
    )
    assert not orders_input["match"], "the input fingerprint diff is the diagnosis"
    customers_input = next(
        i for i in section["inputs"] if i["table"] == "customers"
    )
    assert customers_input["match"]


def test_tampered_fingerprint_is_unexplained(
    vf_model, tmp_path, empty_models_dir, capsys,
):
    manifest_path = _render(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    section = next(
        s for s in manifest["sections"] if s.get("dataset_fingerprint")
    )
    section["dataset_fingerprint"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    rc = cli_main([
        "verify", str(manifest_path), "--models-dir", str(empty_models_dir),
    ])
    assert rc == 1
    assert "UNEXPLAINED" in capsys.readouterr().err

    result = verify_manifest(manifest, load_models(empty_models_dir))
    (checked,) = result["sections"]
    assert checked["status"] == UNEXPLAINED
    assert all(i["match"] for i in checked["inputs"])


def test_python_authored_section_is_unverifiable(
    vf_model, tmp_path, empty_models_dir, capsys,
):
    """Ad hoc data has no recorded query — honest UNVERIFIABLE, exit 0."""
    adhoc = DataSet(
        df=pd.DataFrame({"metric": ["a"], "value": [1.0]}),
        name="adhoc",
        lineage=[LineageNode(operation="load", description="hand-built frame")],
    )
    report = Report("VF Python Report").add(
        TableSection(title="Ad hoc", dataset=adhoc)
    )
    manifest_path = tmp_path / "vf-python.manifest.json"
    report.build_manifest("html", "(in-memory)").save(str(manifest_path))

    rc = cli_main([
        "verify", str(manifest_path), "--models-dir", str(empty_models_dir),
    ])
    assert rc == 0, "unverifiable alone is not a failure"
    out = capsys.readouterr().out
    assert "UNVERIFIABLE" in out
    assert "no recorded query" in out


def test_post_query_transform_is_unverifiable(vf_model, empty_models_dir):
    """A dataset transformed after the query cannot be reproduced by the
    query alone — claiming drift or unexplained would be a guess."""
    ds = vf_model.query(
        fact="fact_orders", measures={"revenue": "sum"},
        dimensions=["dim_customer.region"],
    ).sort("revenue", ascending=False)
    report = Report("VF Transformed").add(
        TableSection(title="Sorted", dataset=ds)
    )
    manifest = report.build_manifest("html", "(in-memory)").to_dict()

    result = verify_manifest(manifest, load_models(empty_models_dir))
    (section,) = result["sections"]
    assert section["status"] == UNVERIFIABLE
    assert "transformed after the recorded query" in section["detail"]
    assert result["exit_code"] == 0


def test_pre_input_fingerprint_manifest_is_honestly_unknown(
    vf_model, tmp_path, empty_models_dir,
):
    """A mismatch in a manifest rendered before input fingerprints existed
    cannot be split into drift vs unexplained — say so, and stay loud."""
    manifest = json.loads(_render(tmp_path).read_text(encoding="utf-8"))
    section = next(
        s for s in manifest["sections"] if s.get("dataset_fingerprint")
    )
    for node in section["dataset_lineage"]:
        node.get("metadata", {}).pop("input", None)
    section["dataset_fingerprint"] = "0" * 64

    result = verify_manifest(manifest, load_models(empty_models_dir))
    (checked,) = result["sections"]
    assert checked["status"] == MISMATCH_UNKNOWN
    assert "no input fingerprints recorded" in checked["detail"]
    assert result["exit_code"] == 1, "an undiagnosable mismatch must stay loud"


# ── CLI edges ──────────────────────────────────────────────────────────────

def test_cli_verify_missing_manifest_fails_loudly(tmp_path, capsys):
    rc = cli_main(["verify", str(tmp_path / "nope.manifest.json")])
    assert rc == 1
    assert "not found" in capsys.readouterr().err


def test_cli_verify_rejects_invalid_json(tmp_path, capsys):
    bad = tmp_path / "bad.manifest.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = cli_main(["verify", str(bad)])
    assert rc == 1
    assert "not valid JSON" in capsys.readouterr().err


# ── The gateway tool ───────────────────────────────────────────────────────

def test_gateway_verify_manifest_dict_and_path(vf_model, tmp_path):
    manifest_path = _render(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for arg in (manifest, str(manifest_path)):
        result = gateway_verify_manifest(arg)
        assert result["ok"], result
        assert result["report_name"] == "VF Spec"
        assert result["schema_version"] == 1
        assert result["summary"][REPRODUCES] == 1
        (section,) = result["sections"]
        assert section["status"] == REPRODUCES
        assert section["expected_fingerprint"] == section["actual_fingerprint"]
        assert section["model"] == "vf_demo"
        assert section["query_spec"]["fact"] == "fact_orders"
        json.dumps(result)  # the payload must survive the wire


def test_gateway_verify_detects_drift_structurally(vf_model, tmp_path):
    manifest_path = _render(tmp_path)
    drifted = ORDERS.copy()
    drifted.loc[0, "revenue"] = 999.0
    _connector_of(vf_model).write(drifted, "orders")

    result = gateway_verify_manifest(str(manifest_path))
    assert not result["ok"]
    assert result["exit_code"] == 2
    assert result["summary"][SOURCE_DRIFT] == 1
    (section,) = result["sections"]
    assert section["status"] == SOURCE_DRIFT


def test_gateway_verify_manifest_bad_inputs():
    missing = gateway_verify_manifest("/no/such/manifest.json")
    assert not missing["ok"]
    assert any("not found" in e for e in missing["errors"])

    not_a_manifest = gateway_verify_manifest(42)
    assert not not_a_manifest["ok"]
    assert not_a_manifest["errors"]


# ─────────────────────────────────────────────
# Review-pass fixes (adversarial findings)
# ─────────────────────────────────────────────

def test_model_repointing_is_model_changed_not_source_drift(
    vf_model, tmp_path, empty_models_dir
):
    """A table remapped to a different source is a governance event (exit 1),
    never a benign data refresh (exit 2) — the review's major finding."""
    from tracebi.verify import MODEL_CHANGED, load_models, verify_manifest

    import json as _json
    manifest = _json.loads(_render(tmp_path).read_text(encoding="utf-8"))

    # Repoint: same model name, same fingerprint-different data, but the
    # table now loads from a *different source table* on the connector.
    other = ORDERS.copy()
    other.loc[0, "revenue"] = 99999.0
    connector = MemoryConnector("vf_mem2", tables={
        "orders_v2": other, "customers": CUSTOMERS.copy(),
    })
    model = DataModel("vf_demo")
    model.add_connector(connector)
    model.add_table("orders", connector="vf_mem2", source="orders_v2")
    model.add_table("customers", connector="vf_mem2", source="customers")
    model.add_dimension("dim_customer", table_name="customers",
                        key_col="customer_id", attributes=["region"])
    model.add_fact("fact_orders", table_name="orders",
                   measures=["revenue"], foreign_keys={"dim_customer": "customer_id"})
    model.connect()
    model_registry.register(model)

    result = verify_manifest(manifest, load_models(empty_models_dir))
    statuses = [s["status"] for s in result["sections"]]
    assert MODEL_CHANGED in statuses
    assert result["exit_code"] == 1
    section = next(s for s in result["sections"] if s["status"] == MODEL_CHANGED)
    assert "orders" in section["detail"]


def test_malformed_lineage_nodes_do_not_crash_verification(vf_model, empty_models_dir):
    """Corrupt receipts are exactly what verify gets pointed at."""
    from tracebi.verify import UNVERIFIABLE, load_models, verify_manifest

    manifest = {
        "report_name": "corrupt", "schema_version": 1,
        "sections": [{
            "section_type": "table", "title": "t",
            "dataset_fingerprint": "x",
            "dataset_lineage": ["bogus", 42, {"metadata": "not-a-dict"}],
        }],
    }
    result = verify_manifest(manifest, load_models(empty_models_dir))
    assert result["sections"][0]["status"] == UNVERIFIABLE


def test_gateway_verify_survives_corrupt_manifest():
    from tracebi.mcp_server import gateway_verify_manifest

    out = gateway_verify_manifest({"sections": "not-a-list"})
    assert isinstance(out, dict)
    assert "ok" in out


def test_newer_schema_version_refuses_to_guess(vf_model, empty_models_dir):
    from tracebi.verify import load_models, verify_manifest

    result = verify_manifest(
        {"report_name": "future", "schema_version": 99, "sections": []},
        load_models(empty_models_dir),
    )
    assert not result["ok"]
    assert result["exit_code"] == 1
    assert "schema_version 99" in result["error"]
