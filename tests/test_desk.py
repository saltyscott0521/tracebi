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
