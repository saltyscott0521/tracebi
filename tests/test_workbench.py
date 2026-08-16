"""
The workbench — the artifact dev loop's shared state (architecture v2 §2.5).

show() is the notebook-cell-output primitive: a NO-OP outside dev (no
TRACEBI_WORKBENCH_DIR → builds and CI ignore it) and never raising inside
it. collect_state is THE one state builder every workbench surface renders
from — per-binding errors are captured into the state, never raised, and
everything here is dev-state only: no receipts, nothing in builds.
"""

import json
import os

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.workbench import (
    collect_state,
    last_seq,
    read_exhibits,
    read_pins,
    show,
    workbench_dir,
    write_pins,
)


@pytest.fixture()
def wb_model():
    df = pd.DataFrame({"region": ["NE", "SE"], "revenue": [100.0, 250.0]})
    m = DataModel("wb_model")
    m.add_connector(MemoryConnector("wb_mem", tables={"t": df}))
    m.add_table("t", connector="wb_mem", source="t")
    m.add_dimension("dim_r", table_name="t", key_col="region",
                    attributes=["region"])
    m.add_fact("f", table_name="t", measures=["revenue"], foreign_keys={})
    m.add_measure("total", column="revenue", agg="sum")
    m.connect()
    return m


def _pkg(parent, name="wbpkg", broken_binding=True):
    """A working-state package: a spare binding no figure uses, a binding
    naming a model that does not exist, an unverified figure, a report.py
    output, and two prose numbers outside any figure."""
    pkg = parent / name
    pkg.mkdir(parents=True, exist_ok=True)
    data = {
        "kpi": {"model": "wb_model",
                "query": {"fact": "f", "measures": ["total"]}},
        "by_region": {"model": "wb_model",
                      "query": {"fact": "f", "measures": {"revenue": "sum"},
                                "dimensions": ["dim_r.region"]}},
        "spare": {"model": "wb_model",
                  "query": {"fact": "f", "measures": ["total"]}},
    }
    figures = (
        '<div data-tb-figure="value" data-tb-binding="kpi" '
        'data-tb-cell="total" id="fig-kpi"></div>'
        '<table data-tb-figure="table" data-tb-binding="by_region" '
        'id="fig-tbl"></table>'
        '<table data-tb-figure="table" data-tb-binding="ranked" '
        'id="fig-rank"></table>'
        '<div data-tb-figure="value" data-tb-unverified '
        'data-tb-note="estimate" id="fig-est">42</div>'
    )
    if broken_binding:
        data["broken"] = {"model": "ghost_model",
                          "query": {"fact": "f", "measures": ["total"]}}
        figures += ('<div data-tb-figure="chart" data-tb-binding="broken" '
                    'id="fig-broken"></div>')
    (pkg / "report.json").write_text(json.dumps({"name": name, "data": data}))
    (pkg / "template.html").write_text(
        "<html><head><title>x</title></head><body>"
        "<p>Revenue rose 12.5 over 2024.</p>" + figures + "</body></html>"
    )
    (pkg / "report.py").write_text(
        "def build(frames):\n"
        "    return {'ranked': frames['by_region'].head(1)}\n")
    return pkg


class TestShow:
    def test_noop_without_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TRACEBI_WORKBENCH_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        show(pd.DataFrame({"a": [1]}), note="ignored")
        show("also ignored")
        assert list(tmp_path.iterdir()) == []   # a build/CI run leaves no trace

    def test_writes_frame_and_note_jsonl(self, tmp_path, monkeypatch):
        wb = str(tmp_path / "wb")
        monkeypatch.setenv("TRACEBI_WORKBENCH_DIR", wb)
        df = pd.DataFrame({"fund": ["a", "b"], "fv": [1.5, float("nan")]})
        show(df, note="after dropping nulls", name="marks")
        show("## working note")

        lines = [json.loads(line) for line in
                 open(os.path.join(wb, "exhibits.jsonl"), encoding="utf-8")]
        assert [e["seq"] for e in lines] == [1, 2]     # monotonic
        frame, note = lines
        assert frame["kind"] == "frame"
        assert frame["name"] == "marks" and frame["note"] == "after dropping nulls"
        assert frame["columns"] == ["fund", "fv"] and frame["shape"] == [2, 2]
        assert frame["rows"][1]["fv"] is None          # NaN is JSON-safe null
        assert note == {"seq": 2, "at": note["at"], "kind": "note",
                        "text": "## working note"}
        # Newest first, and the pin anchor tracks the newest seq.
        assert [e["seq"] for e in read_exhibits(wb)] == [2, 1]
        assert last_seq(wb) == 2

    def test_show_never_raises(self, tmp_path, monkeypatch, capsys):
        blocker = tmp_path / "blocker"
        blocker.write_text("")                          # a FILE where a dir must go
        monkeypatch.setenv("TRACEBI_WORKBENCH_DIR", str(blocker / "sub"))
        show(pd.DataFrame({"a": [1]}))                  # must not raise
        assert "exhibit dropped" in capsys.readouterr().err


class TestPins:
    def test_pins_round_trip_via_file(self, tmp_path):
        wb = str(tmp_path)
        pins = [{"id": "fig-kpi", "note": "keep this one", "at_seq": 3}]
        write_pins(wb, pins)
        assert read_pins(wb) == pins
        assert read_pins(str(tmp_path / "missing")) == []

    def test_workbench_dir_is_project_scoped(self, tmp_path):
        d = workbench_dir(str(tmp_path), "credit_marks")
        assert d.endswith(os.path.join(".tracebi", "workbench", "credit_marks"))
        assert os.path.isdir(d)


class TestCollectState:
    @pytest.fixture()
    def state(self, wb_model, tmp_path, monkeypatch):
        monkeypatch.setenv("TRACEBI_WORKBENCH_DIR", str(tmp_path / "wb"))
        return collect_state(str(_pkg(tmp_path)), {"wb_model": wb_model})

    def test_figures_carry_provenance_and_unbound_flags(self, state):
        figs = {f["id"]: f for f in state["figures"]}
        assert figs["fig-kpi"]["provenance"] == "verified"
        assert figs["fig-tbl"]["provenance"] == "verified"
        assert figs["fig-rank"]["provenance"] == "derived"   # report.py — never green
        assert figs["fig-est"]["provenance"] == "unverified"
        assert figs["fig-broken"].get("unbound") is True     # its binding failed
        assert all(f["pinned"] is False for f in state["figures"])

    def test_coverage_counts(self, state):
        assert state["coverage"] == {"total": 5, "verified": 2, "derived": 1,
                                     "unverified": 1, "unbound_errors": 1}

    def test_per_binding_error_is_captured_not_raised(self, state):
        broken = next(b for b in state["bindings"] if b["name"] == "broken")
        assert "ghost_model" in broken["error"]
        assert broken["used_by"] == ["fig-broken"]
        # The healthy bindings still resolved fully alongside it.
        kpi = next(b for b in state["bindings"] if b["name"] == "kpi")
        assert kpi["source"] == "query" and kpi["rows"] == 1
        assert len(kpi["fingerprint"]) == 12
        assert kpi["preview"] == [{"total": 350.0}]
        ranked = next(b for b in state["bindings"] if b["name"] == "ranked")
        assert ranked["source"] == "python" and ranked["used_by"] == ["fig-rank"]

    def test_unused_bindings_and_lint(self, state):
        assert state["unused_bindings"] == ["spare"]
        # "12.5" and "2024" sit in prose; the 42 inside fig-est is claimed.
        assert state["lint"]["numeric_literals_outside_figures"] == 2

    def test_code_panel_is_read_back_verbatim(self, state, tmp_path):
        assert '"kpi"' in state["code"]["report.json"]
        assert "def build" in state["code"]["report.py"]

    def test_pins_merge_into_figures(self, wb_model, tmp_path, monkeypatch):
        wb = str(tmp_path / "wb")
        monkeypatch.setenv("TRACEBI_WORKBENCH_DIR", wb)
        write_pins(wb, [{"id": "fig-kpi", "note": "the headline", "at_seq": 0}])
        state = collect_state(str(_pkg(tmp_path)), {"wb_model": wb_model})
        figs = {f["id"]: f for f in state["figures"]}
        assert figs["fig-kpi"]["pinned"] is True
        assert figs["fig-tbl"]["pinned"] is False
        assert state["pins"][0]["note"] == "the headline"

    def test_state_is_json_serialisable(self, state):
        json.dumps(state, default=str)


_MODEL_SOURCE = """\
import pandas as pd
from tracebi import DataModel, MemoryConnector

df = pd.DataFrame({"region": ["NE", "SE"], "revenue": [100.0, %s]})
model = DataModel("wb_model")
model.add_connector(MemoryConnector("wb_mem", tables={"t": df}))
model.add_table("t", connector="wb_mem", source="t")
model.add_dimension("dim_r", table_name="t", key_col="region",
                    attributes=["region"])
model.add_fact("f", table_name="t", measures=["revenue"], foreign_keys={})
model.add_measure("total", column="revenue", agg="sum")
model.connect()
"""


class TestDevServerPackageRender:
    """The dev server's render function, in-process — the working state is
    served from memory (exploration kept, stage meta, data blocks), and the
    feed's auto-entries appear only when a binding's fingerprint CHANGED."""

    def _project(self, tmp_path, monkeypatch):
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "wb_model.py").write_text(_MODEL_SOURCE % "250.0")
        pkg = _pkg(tmp_path / "reports", broken_binding=False)
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("TRACEBI_WORKBENCH_DIR", raising=False)
        # As _serve() sets it: a .pyc written for the model file would read
        # "valid" against a same-second same-size edit and exec stale code.
        import sys
        monkeypatch.setattr(sys, "dont_write_bytecode", True)
        return pkg

    def test_render_serves_exploration_page_from_memory(
            self, tmp_path, monkeypatch):
        from tracebi._dev_server import _PackageTarget
        pkg = self._project(tmp_path, monkeypatch)
        page = _PackageTarget(pkg).render()
        assert 'content="exploration"' in page          # stage meta — never final
        assert "tracebi-data-kpi" in page               # stamped bytes embedded
        assert "tracebi-data-ranked" in page            # report.py output beside them
        # Serving leaked no env var and wrote no build output.
        assert "TRACEBI_WORKBENCH_DIR" not in os.environ
        assert not (tmp_path / "output").exists()

    def test_broken_package_renders_the_error_page(self, tmp_path, monkeypatch):
        from tracebi._dev_server import _PackageTarget
        pkg = self._project(tmp_path, monkeypatch)
        (pkg / "report.py").write_text("def build(frames):\n    return {}\n")
        page = _PackageTarget(pkg).render()
        assert "Report package failed" in page
        assert "non-empty dict" in page                 # the real traceback, escaped

    def test_auto_entry_only_when_fingerprint_changed(
            self, tmp_path, monkeypatch):
        from tracebi._dev_server import _PackageTarget
        pkg = self._project(tmp_path, monkeypatch)
        target = _PackageTarget(pkg)
        target.render()
        assert read_exhibits(target.wb_dir) == []       # first build only primes
        target.render()
        assert read_exhibits(target.wb_dir) == []       # unchanged data — silence
        (tmp_path / "models" / "wb_model.py").write_text(_MODEL_SOURCE % "999.0")
        target.render()
        texts = [e["text"] for e in read_exhibits(target.wb_dir)]
        assert texts and all(t.startswith("binding ") for t in texts)
        assert any("kpi updated" in t for t in texts)
