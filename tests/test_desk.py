"""Desk lists what needs a person, and opens a receipt that reproduces."""

from __future__ import annotations

import json

import duckdb

from tracebi.desk import review


def test_review_lists_pins_drafts_failures_and_sinks(tmp_path):
    pin_dir = tmp_path / ".tracebi" / "workbench" / "demo"
    pin_dir.mkdir(parents=True)
    (pin_dir / "pins.json").write_text(json.dumps([
        {"id": "fig-1", "note": "look here", "at_seq": 3},
    ]), encoding="utf-8")
    discovery = tmp_path / ".tracebi" / "workbench" / "_discovery"
    discovery.mkdir(parents=True)
    (discovery / "pins.json").write_text(json.dumps([
        {"id": "table", "note": "warehouse", "at_seq": 1},
    ]), encoding="utf-8")

    draft = tmp_path / "reports" / "scratch"
    draft.mkdir(parents=True)
    (draft / "template.html").write_text(
        '<section data-tb-stage="exploration">probe</section>',
        encoding="utf-8",
    )
    clean = tmp_path / "reports" / "published"
    clean.mkdir(parents=True)
    (clean / "template.html").write_text("<p>done</p>", encoding="utf-8")

    output = tmp_path / "output"
    output.mkdir()
    (output / "waiting.html.manifest.json").write_text(json.dumps({
        "report_name": "waiting",
        "sections": [{"title": "note"}],
    }), encoding="utf-8")
    (output / "broken.html.manifest.json").write_text("{", encoding="utf-8")

    warehouse = tmp_path / "data" / "warehouse.duckdb"
    warehouse.parent.mkdir()
    con = duckdb.connect(str(warehouse))
    con.execute("CREATE TABLE certified (id INTEGER)")
    con.execute("INSERT INTO certified VALUES (1)")
    con.execute("CREATE TABLE loose (id INTEGER)")
    con.execute("INSERT INTO loose VALUES (1)")
    con.close()
    (tmp_path / "data" / "warehouse.contracts.json").write_text(json.dumps({
        "transforms": {
            "demo": {"tables": {"certified": "not-the-fingerprint"}, "checks": []},
        },
    }), encoding="utf-8")

    body = review(str(tmp_path), models={})
    notes = {pin["note"] for pin in body["pins"]}
    assert notes == {"look here", "warehouse"}
    assert [d["report"] for d in body["drafts"]] == ["scratch"]
    verdicts = {row["report"]: row["verdict"] for row in body["verdicts"]}
    assert verdicts["waiting"] == "nothing_to_verify"
    assert verdicts["broken"] == "error"
    statuses = {row["table"]: row["status"] for row in body["sinks"]}
    assert statuses["certified"] == "stale"
    assert statuses["loose"] == "no_contract"
    assert body["warehouse"] is True
    assert body["open"] is None


def test_desk_endpoint_reads_the_project(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from tracebi.web.api.routers import desk as desk_router

    monkeypatch.chdir(tmp_path)
    out = tmp_path / "output"
    out.mkdir()
    (out / "note.html.manifest.json").write_text(json.dumps({
        "report_name": "note",
        "sections": [],
    }), encoding="utf-8")
    app = FastAPI()
    app.include_router(desk_router.router, prefix="/api")
    client = TestClient(app)
    res = client.get("/api/desk")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["verdicts"][0]["verdict"] == "nothing_to_verify"
    assert body["pins"] == []


def test_a_kept_verdicts_key_moves_with_its_inputs_and_only_them(tmp_path, monkeypatch):
    """Catches a kept verdict served after one of its inputs changed (the
    receipt, the warehouse, its contracts certificate, the model's file), one
    thrown away when nothing it reads changed, and one kept for a source that
    cannot say when it changed."""
    import os
    import time

    from tracebi import model_registry
    from tracebi.connectors.duckdb_connector import DuckDBConnector
    from tracebi.connectors.memory_connector import MemoryConnector
    from tracebi.desk import verdict_key
    from tracebi.model.data_model import DataModel

    warehouse = tmp_path / "data" / "warehouse.duckdb"
    warehouse.parent.mkdir()
    con = duckdb.connect(str(warehouse))
    con.execute("CREATE TABLE fact_x AS SELECT 1 AS v")
    con.close()
    model_file = tmp_path / "models" / "m.yaml"
    model_file.parent.mkdir()
    model_file.write_text("name: m\n", encoding="utf-8")
    other_file = tmp_path / "models" / "other.yaml"
    other_file.write_text("name: other\n", encoding="utf-8")
    files = {"m": str(model_file), "other": str(other_file)}
    monkeypatch.setattr(model_registry, "model_path", files.get)

    m = DataModel("m").add_connector(DuckDBConnector("wh", database=str(warehouse)))
    other = DataModel("other").add_connector(DuckDBConnector("wh", database=str(warehouse)))
    models = {"m": m, "other": other}
    receipt = tmp_path / "output" / "r.html.manifest.json"
    receipt.parent.mkdir()
    receipt.write_text(json.dumps({"sections": [{
        "dataset_fingerprint": "f",
        "dataset_lineage": [{"metadata": {"model": "m", "query_spec": {}}}],
    }]}), encoding="utf-8")

    def key(models=models):
        return verdict_key(str(receipt), os.stat(receipt),
                           json.loads(receipt.read_text(encoding="utf-8")), models)

    def later(path, text):
        # Step past the clock's resolution, so a rewrite always moves mtime.
        time.sleep(0.01)
        path.write_text(text, encoding="utf-8")

    base = key()
    assert base is not None and key() == base

    # Not inputs: a model the receipt does not name, a file beside the warehouse.
    later(other_file, "name: other\n# edited\n")
    later(tmp_path / "data" / "notes.txt", "x")
    assert key() == base

    later(receipt, receipt.read_text(encoding="utf-8").replace('"f"', '"g"'))
    assert key() != base
    base = key()

    time.sleep(0.01)
    con = duckdb.connect(str(warehouse))
    con.execute("CREATE OR REPLACE TABLE fact_x AS SELECT 2 AS v")
    con.close()
    assert key() != base
    base = key()

    later(tmp_path / "data" / "warehouse.contracts.json", "{}")
    assert key() != base
    base = key()

    later(model_file, "name: m\n# edited\n")
    assert key() != base

    # A source that cannot say when it changed is never kept.
    memory = DataModel("m").add_connector(MemoryConnector("mem", {}))
    assert key({"m": memory, "other": other}) is None


def test_a_kept_verdicts_key_names_a_model_file_one_way(tmp_path, monkeypatch):
    """Catches the key that changed when live discovery's rescan recorded the
    model's file relative to the working directory instead of absolute: every
    verdict then re-ran on the next read, seconds per library load."""
    import os

    from tracebi import model_registry
    from tracebi.connectors.duckdb_connector import DuckDBConnector
    from tracebi.desk import verdict_key
    from tracebi.model.data_model import DataModel

    monkeypatch.chdir(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "m.yaml").write_text("name: m\n", encoding="utf-8")
    warehouse = tmp_path / "w.duckdb"
    duckdb.connect(str(warehouse)).close()
    models = {"m": DataModel("m").add_connector(DuckDBConnector("wh", database=str(warehouse)))}
    receipt = tmp_path / "r.html.manifest.json"
    receipt.write_text(json.dumps({"sections": [{
        "dataset_lineage": [{"metadata": {"model": "m"}}]}]}), encoding="utf-8")
    manifest = json.loads(receipt.read_text(encoding="utf-8"))

    def key(path):
        monkeypatch.setattr(model_registry, "model_path", lambda name: path)
        return verdict_key(str(receipt), os.stat(receipt), manifest, models)

    assert key("models/m.yaml") == key(str(tmp_path / "models" / "m.yaml"))


def test_a_new_process_paints_the_last_verdicts_and_never_a_green_it_did_not_compute(
        tmp_path, monkeypatch):
    """The state store keeps each build's last verdict with a digest of its
    inputs (tracebi_verdicts). Catches a process that has computed nothing yet
    making the library wait for every re-run; a stored verdict whose inputs
    moved served as if current; and a quick read that re-runs anything or
    offers a receipt it has not checked as the one to open."""
    import time

    from tracebi import desk, verify

    out = tmp_path / "output"
    out.mkdir()
    receipt = out / "r.html.manifest.json"
    receipt.write_text(json.dumps({"report_name": "r", "sections": []}), encoding="utf-8")
    (out / "r.html").write_text("<p>r</p>", encoding="utf-8")
    runs = []

    def checked(manifest, models):
        runs.append(1)
        return {"verdict": "reproduces", "summary": {}}

    monkeypatch.setattr(verify, "verify_manifest", checked)

    # Nothing recorded yet: a quick read re-runs nothing and claims nothing.
    desk.invalidate()
    quick = desk.review(str(tmp_path), quick=True)
    assert runs == [] and quick["open"] is None and quick["verdicts"] == []
    assert quick["builds"][0]["pending"] is True and quick["builds"][0]["verdict"] is None

    first = desk.review(str(tmp_path))["builds"][0]
    assert (runs, first["verdict"], first["cached"]) == ([1], "reproduces", False)

    # A new process (nothing kept in memory): the stored verdict, as computed.
    desk.invalidate()
    painted = desk.review(str(tmp_path), quick=True)
    row = painted["builds"][0]
    assert runs == [1] and "pending" not in row
    assert (row["verdict"], row["computed_at"], row["cached"]) == ("reproduces", first["computed_at"], True)
    assert painted["open"]["report"] == "r"

    # Its inputs move: the stored verdict is only what the last re-check said.
    time.sleep(0.01)
    receipt.write_text(json.dumps({"report_name": "r", "sections": [], "x": 1}), encoding="utf-8")
    desk.invalidate()
    painted = desk.review(str(tmp_path), quick=True)
    row = painted["builds"][0]
    assert runs == [1] and row["pending"] is True and painted["open"] is None
    assert (row["verdict"], row["computed_at"]) == ("reproduces", first["computed_at"])
    again = desk.review(str(tmp_path))["builds"][0]
    assert runs == [1, 1] and "pending" not in again and again["cached"] is False
