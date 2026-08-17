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
    ACTIVE_FILE,
    collect_discovery_state,
    collect_state,
    discovery_dir,
    heartbeat,
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


class TestShowDiscoveryHeartbeat:
    """The posting rule, exactly: TRACEBI_WORKBENCH_DIR always wins when
    set. Without it, show() posts to the CURRENT working directory's
    _discovery workbench only while its .active heartbeat is fresh — no
    live server (builds, CI) means stale/absent, and show() stays a no-op."""

    def test_fresh_heartbeat_gates_show_into_discovery(
            self, tmp_path, monkeypatch):
        monkeypatch.delenv("TRACEBI_WORKBENCH_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        wb = discovery_dir(str(tmp_path))
        heartbeat(wb)                       # a discovery server is "live"
        show(pd.DataFrame({"a": [1]}), note="probe output")
        exhibits = read_exhibits(wb)
        assert [e["kind"] for e in exhibits] == ["frame"]
        assert exhibits[0]["note"] == "probe output"

    def test_stale_heartbeat_is_a_noop(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TRACEBI_WORKBENCH_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        wb = discovery_dir(str(tmp_path))
        heartbeat(wb)
        marker = os.path.join(wb, ACTIVE_FILE)
        past = os.path.getmtime(marker) - 60        # server long gone
        os.utime(marker, (past, past))
        show(pd.DataFrame({"a": [1]}))
        assert read_exhibits(wb) == []      # the build/CI no-op guarantee

    def test_env_var_wins_over_the_heartbeat(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        wb = discovery_dir(str(tmp_path))
        heartbeat(wb)
        explicit = str(tmp_path / "explicit_wb")
        monkeypatch.setenv("TRACEBI_WORKBENCH_DIR", explicit)
        show("a session note")
        assert [e["kind"] for e in read_exhibits(explicit)] == ["note"]
        assert read_exhibits(wb) == []


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


_DISCOVERY_MODEL = """\
from tracebi import DataModel
from tracebi.connectors.duckdb_connector import DuckDBConnector

# Lazy by design: no connect() at import — discovery must list the model
# even before phase 1 has ever run.
model = DataModel("disc_model")
model.add_connector(DuckDBConnector("wh", database="data/warehouse.duckdb"))
model.add_table("fact_holdings", connector="wh", source="fact_holdings")
model.add_table("dim_issuer", connector="wh", source="dim_issuer")
model.add_relationship("h_to_i", left_table="fact_holdings",
                       right_table="dim_issuer", left_key="issuer_id")
model.add_dimension("dim_issuer", table_name="dim_issuer",
                    key_col="issuer_id", attributes=["issuer"])
model.add_fact("holdings", table_name="fact_holdings",
               measures=["fair_value"],
               foreign_keys={"dim_issuer": "issuer_id"})
model.add_measure("total_fv", column="fair_value", agg="sum")
"""


class TestCollectDiscoveryState:
    """The project-level state builder — phases ① and ② made visible: the
    warehouse (tables + sink-contract summaries), the models' declared star
    schemas, the packages, and the _discovery feed. Per-panel failures are
    captured into the state, never raised."""

    @pytest.fixture()
    def discovery_project(self, tmp_path):
        pytest.importorskip("duckdb")
        from tracebi.connectors.duckdb_connector import DuckDBConnector
        from tracebi.contracts import contract

        (tmp_path / "data").mkdir()
        wh = str(tmp_path / "data" / "warehouse.duckdb")
        sink = DuckDBConnector("wh", database=wh)
        sink.write(pd.DataFrame({"issuer_id": [1, 2, 3],
                                 "fair_value": [10.0, 20.0, 30.0]}),
                   "fact_holdings")
        sink.write(pd.DataFrame({"issuer_id": [1, 2, 3],
                                 "issuer": ["a", "b", "c"]}), "dim_issuer")
        with contract("holdings", warehouse=wh) as c:
            c.rows("fact_holdings", exactly=3)
            c.unique("dim_issuer", ["issuer_id"])

        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "disc_model.py").write_text(_DISCOVERY_MODEL)
        (tmp_path / "models" / "broken_model.py").write_text(
            "import nope_missing\n")
        (tmp_path / "reports" / "empty_pkg").mkdir(parents=True)
        return tmp_path

    def test_collects_warehouse_models_packages(self, discovery_project):
        state = collect_discovery_state(str(discovery_project), {})
        assert state["mode"] == "discovery"
        assert state["name"] == "_discovery"

        wh = state["warehouse"]
        assert wh["exists"] is True
        assert wh["path"].endswith(os.path.join("data", "warehouse.duckdb"))
        tables = {t["name"]: t for t in wh["tables"]}
        assert tables["fact_holdings"]["rows"] == 3
        assert set(tables["fact_holdings"]["columns"]) == {"issuer_id",
                                                           "fair_value"}
        assert tables["dim_issuer"]["rows"] == 3

        # The sink-contract summary — the sink satisfied its contract.
        holdings = wh["contracts"]["holdings"]
        assert holdings["checks"] == "2/2"
        assert holdings["tables"] == ["dim_issuer", "fact_holdings"]
        assert holdings["checked_at"]

        # Model listing via the public info(); the broken FILE is an error
        # entry in the state, not an exception out of it.
        by_name = {m["name"]: m for m in state["models"]}
        good = by_name["disc_model"]
        assert [f["name"] for f in good["facts"]] == ["holdings"]
        assert [d["name"] for d in good["dimensions"]] == ["dim_issuer"]
        assert [m["name"] for m in good["measures"]] == ["total_fv"]
        broken = by_name["broken_model"]
        assert "nope_missing" in broken["error"]

        assert state["packages"] == ["empty_pkg"]
        assert state["exhibits"] == [] and state["pins"] == []

    def test_loaded_models_are_not_reloaded_and_dedupe(self, discovery_project):
        """A model the caller already loaded (keyed by stem AND .name, as
        the loaders do) appears once, and its declared warehouse path
        dedupes against data/warehouse.duckdb."""
        from tracebi.model_registry import ModelRegistry

        reg = ModelRegistry()
        reg.auto_discover(str(discovery_project / "models"))
        m = reg.get("disc_model")
        state = collect_discovery_state(
            str(discovery_project), {"disc_model": m, "alias": m})
        names = [e["name"] for e in state["models"]]
        assert names.count("disc_model") == 1
        assert state["warehouse"]["exists"] is True

    def test_missing_warehouse_is_state_not_crash(self, tmp_path):
        state = collect_discovery_state(str(tmp_path), {})
        wh = state["warehouse"]
        assert wh["exists"] is False
        assert wh["tables"] == [] and wh["contracts"] is None
        assert state["models"] == [] and state["packages"] == []

    def test_state_is_json_serialisable(self, discovery_project):
        json.dumps(collect_discovery_state(str(discovery_project), {}),
                   default=str)
