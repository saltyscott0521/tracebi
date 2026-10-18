"""
The workbench — the artifact dev loop's shared state (architecture v2 §2.5).

show() is the notebook-cell-output primitive: a NO-OP outside dev (no
TRACEBI_WORKBENCH_DIR → builds and CI ignore it) and never raising inside
it. collect_state is THE one state builder every workbench surface renders
from — per-binding errors are captured into the state, never raised, and
everything here is dev-state only: no receipts, nothing in builds.
"""

import sys

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.workbench import (
    show,
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


class TestNoteMarkdown:
    """Notebook-cell notes: markdown renders in the feed, escaped-first."""


    def test_markdown_cannot_smuggle_markup(self):
        from tracebi.workbench import render_note_markdown
        out = render_note_markdown([
            {"kind": "note", "seq": 1, "text": "<script>alert(1)</script>"},
        ])
        assert "<script>" not in out[0]["html"]
        assert "&lt;script&gt;" in out[0]["html"]


def test_workbench_page_carries_a_csp():
    """The dev workbench does md.innerHTML of md_to_html output. Beyond the
    escaping, the page must carry a CSP as defense-in-depth — relaxed to
    connect-src 'self' for its /__workbench/state.json poll."""
    from tracebi._dev_server import _workbench_page

    page = _workbench_page("demo")
    assert 'http-equiv="Content-Security-Policy"' in page
    assert "default-src 'none'" in page
    assert "connect-src 'self'" in page      # the status poll needs it
    assert "__CSP__" not in page             # placeholder must be filled


class TestSessionExport:
    """export_session — the FULL feed as ONE exploration-record HTML: honest
    by construction (stage meta + banner, no manifest, verify refuses it),
    escaped throughout, uncapped by EXHIBIT_CAP."""

    def _session(self, tmp_path, monkeypatch):
        wb = str(tmp_path / "wb")
        monkeypatch.setenv("TRACEBI_WORKBENCH_DIR", wb)
        monkeypatch.chdir(tmp_path)
        script = tmp_path / "transforms" / "probe.py"
        script.parent.mkdir(exist_ok=True)
        script.write_text("# probe")
        monkeypatch.setattr(sys, "argv", [str(script)])
        show("## Approach\n\nDropped **9** null-mark funds.")
        show(pd.DataFrame({"issuer": ["<script>alert(1)</script>", "b"],
                           "fv": [1.5, 2.5]}), note="hostile & clean")
        show(pd.DataFrame({"sector": ["fin", "tech"], "fv": [10.0, 20.0]}),
             chart="bar", x="sector", y="fv")
        write_pins(wb, [{"id": "fig-x", "note": "keep this cut", "at_seq": 2}])
        return wb

    def _export(self, wb, tmp_path, title=None):
        from tracebi._session_export import export_session
        out = tmp_path / "explorations" / "record.html"
        export_session(wb, str(out), title=title)
        return out, out.read_text(encoding="utf-8")


    def test_carries_a_strict_csp(self, tmp_path, monkeypatch):
        """The offline record interpolates md_to_html output; escaping is the
        real defense, but the file must also carry the strict CSP so a future
        escaping regression can't reach external script or exfil."""
        wb = self._session(tmp_path, monkeypatch)
        _out, html = self._export(wb, tmp_path)
        assert 'http-equiv="Content-Security-Policy"' in html
        assert "default-src 'none'" in html
        assert "connect-src 'none'" in html      # an offline file never polls

    def test_notes_render_markdown_and_frames_escape(
            self, tmp_path, monkeypatch):
        wb = self._session(tmp_path, monkeypatch)
        _out, html = self._export(wb, tmp_path)
        assert "<h3>Approach</h3>" in html               # markdown-converted
        assert "<strong>9</strong>" in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        assert "<script>alert(1)" not in html            # escaped, not live


    def test_no_manifest_and_verify_refuses(self, tmp_path, monkeypatch):
        from tracebi.verify import REFUSED_SNAPSHOT, verify_file
        wb = self._session(tmp_path, monkeypatch)
        out, html = self._export(wb, tmp_path)
        assert list(out.parent.glob("*.manifest.json")) == []
        result = verify_file(html, {})
        assert result["verdict"] == REFUSED_SNAPSHOT
        assert result["ok"] is False and result["exit_code"] == 1


class TestSessionExportMarkdown:
    """The Markdown twin — the git-review format. Raw markdown notes
    verbatim; frames and sketches as pipe tables; same honesty banner."""

    def _session(self, tmp_path, monkeypatch):
        wb = str(tmp_path / "wb")
        monkeypatch.setenv("TRACEBI_WORKBENCH_DIR", wb)
        show("## Approach\n\nDropped **9** null|mark funds.")
        show(pd.DataFrame({"sector": ["fin|tech"], "fv": [1.5]}),
             chart="bar", x="sector", y="fv", note="sketch")
        write_pins(wb, [{"id": "exhibit-2", "note": "keep", "at_seq": 2}])
        return wb

    def test_md_export_is_reviewable(self, tmp_path, monkeypatch):
        from tracebi._session_export import export_session
        wb = self._session(tmp_path, monkeypatch)
        out = tmp_path / "record.md"
        export_session(wb, str(out), title="Probe record")
        md = out.read_text(encoding="utf-8")
        assert md.startswith("# Probe record")
        assert "lab notebook, not a report" in md
        assert "carry no receipts" in md
        # the note is RAW markdown, verbatim — the format's whole point
        assert "## Approach" in md and "**9**" in md
        assert "**chart sketch** — bar · x: sector · y: fv" in md
        assert "| fin\\|tech | 1.5 |" in md    # pipes escaped in cells
        assert "📌 **pinned:** keep" in md
        assert not (tmp_path / "record.md.manifest.json").exists()


def test_dev_server_rejects_dns_rebinding_hosts():
    """The dev server serves the rich /__workbench/state.json; a DNS-rebinding
    page sends its own domain as Host, so only loopback hosts are accepted."""
    from tracebi._dev_server import _host_is_local

    for ok in ["localhost", "localhost:8000", "127.0.0.1", "127.0.0.1:8000",
               "[::1]", "[::1]:8000", ""]:
        assert _host_is_local(ok), f"{ok!r} should be allowed"
    for bad in ["evil.example.com", "evil.example.com:8000", "attacker.test",
                "192.168.1.5:8000", "0.0.0.0:8000"]:
        assert not _host_is_local(bad), f"{bad!r} should be refused"
