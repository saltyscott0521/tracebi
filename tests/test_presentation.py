"""
The presentation stack (architecture v2 §2.4).

The injection order IS the override chain — tracebi.css, then the
project's _theme.css, then the report's style.css, with the author's
script running after the runtime. Badges carry provenance decided at
build time from what was embedded; a config flag can omit them but the
manifest never changes. Presentation must never change a number.
"""

import json

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector
from tracebi.reports.template_package import TemplatePackage


@pytest.fixture()
def stack_model():
    df = pd.DataFrame({"region": ["NE", "SE"], "revenue": [100.0, 250.0]})
    m = DataModel("stack_model")
    m.add_connector(MemoryConnector("st_mem", tables={"t": df}))
    m.add_table("t", connector="st_mem", source="t")
    m.add_dimension("dim_r", table_name="t", key_col="region",
                    attributes=["region"])
    m.add_fact("f", table_name="t", measures=["revenue"], foreign_keys={})
    m.add_measure("total", column="revenue", agg="sum")
    m.connect()
    return m


def _pkg(tmp_path, with_report_py=False):
    pkg = tmp_path / "pkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "report.json").write_text(json.dumps({
        "name": "pkg",
        "data": {
            "kpi": {"model": "stack_model",
                    "query": {"fact": "f", "measures": ["total"]}},
            "by_region": {"model": "stack_model",
                          "query": {"fact": "f",
                                    "measures": {"revenue": "sum"},
                                    "dimensions": ["dim_r.region"]}},
        },
    }))
    (pkg / "template.html").write_text(
        "<html><head><title>x</title></head><body>"
        '<div data-tb-figure="value" data-tb-binding="kpi" '
        'data-tb-cell="total" id="fig-kpi"></div>'
        '<table data-tb-figure="table" data-tb-binding="by_region" '
        'id="fig-tbl"></table>'
        + ('<table data-tb-figure="table" data-tb-binding="ranked" '
           'id="fig-rank"></table>' if with_report_py else "")
        + "</body></html>"
    )
    (pkg / "style.css").write_text(":root { --tb-accent: #ff0000; }")
    if with_report_py:
        (pkg / "report.py").write_text(
            "def build(frames):\n"
            "    return {'ranked': frames['by_region'].head(1)}\n")
    return pkg


class TestStackOrder:
    def test_later_wins_layer_order(self, stack_model, tmp_path, monkeypatch):
        # A project _theme.css between the shipped sheet and the report's own.
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "_theme.css").write_text(
            ":root { --tb-accent: #00ff00; }")
        monkeypatch.chdir(tmp_path)

        out = tmp_path / "out.html"
        TemplatePackage(str(_pkg(tmp_path))).render(
            {"stack_model": stack_model}, str(out))
        html = out.read_text(encoding="utf-8")

        base = html.index("--tb-font")               # shipped tracebi.css
        project = html.index("--tb-accent: #00ff00")  # project layer
        report = html.index("--tb-accent: #ff0000")   # report layer
        assert base < project < report, (
            "the stack must inject shipped → project → report, so later wins"
        )
        # The runtime precedes the data blocks; the author script would come
        # after both (order is the contract that lets authors patch charts).
        assert html.index("window.tracebi") < html.index("tracebi-data-kpi")

    def test_badges_config_carries_provenance(self, stack_model, tmp_path):
        out = tmp_path / "out.html"
        TemplatePackage(str(_pkg(tmp_path, with_report_py=True))).render(
            {"stack_model": stack_model}, str(out))
        html = out.read_text(encoding="utf-8")
        start = html.index('id="tracebi-figures"')
        payload = html[html.index(">", start) + 1:html.index("</script>", start)]
        cfg = json.loads(payload)
        assert cfg["badges"] is True
        prov = {f["id"]: f["provenance"] for f in cfg["figures"]}
        assert prov["fig-kpi"] == "verified"
        assert prov["fig-tbl"] == "verified"
        assert prov["fig-rank"] == "derived"     # report.py output — never green

    def test_no_badges_omits_rendering_but_not_the_manifest(
            self, stack_model, tmp_path):
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(_pkg(tmp_path))).render(
            {"stack_model": stack_model}, str(out), badges=False).to_dict()
        html = out.read_text(encoding="utf-8")
        start = html.index('id="tracebi-figures"')
        payload = html[html.index(">", start) + 1:html.index("</script>", start)]
        assert json.loads(payload)["badges"] is False
        # The receipt is unaffected: the figure claims are all still there.
        assert {f["id"] for f in manifest["figures"]} == {"fig-kpi", "fig-tbl"}

    def test_self_containment_and_csp_hold(self, stack_model, tmp_path):
        out = tmp_path / "out.html"
        TemplatePackage(str(_pkg(tmp_path))).render(
            {"stack_model": stack_model}, str(out))
        html = out.read_text(encoding="utf-8")
        # Exactly one CSP meta: the renderer and the stack both know how to
        # inject it, and the stack yields when one is already present
        # (round-2 review, finding 11 — a duplicated policy is noise).
        assert html.count("Content-Security-Policy") == 1
        assert "http://" not in html.replace("http://www.w3.org", "")
        assert 'src="https://' not in html and "@import" not in html


# ── the receipt block ───────────────────────────────────────────────────────
# The build emits one tracebi-receipt JSON block: the drawer's provenance
# feed. It duplicates facts the manifest records — the MANIFEST remains the
# receipt of record — so every entry is checked against the manifest it
# mirrors.

#: The block's full opening tag. The runtime script also names the bare id
#: string (it reads the block), so tests anchor on the element itself.
RECEIPT_OPEN = '<script id="tracebi-receipt" type="application/json">'


def _receipt(html):
    start = html.index(RECEIPT_OPEN)
    payload = html[start + len(RECEIPT_OPEN):html.index("</script>", start)]
    return json.loads(payload)


class TestReceiptBlock:
    def test_records_manifest_facts_and_figure_fingerprints(
            self, stack_model, tmp_path):
        out = tmp_path / "out.html"
        manifest = TemplatePackage(
            str(_pkg(tmp_path, with_report_py=True))).render(
            {"stack_model": stack_model}, str(out)).to_dict()
        receipt = _receipt(out.read_text(encoding="utf-8"))
        # The header duplicates the manifest, not a second computation.
        assert receipt["report"] == manifest["report_name"]
        assert receipt["rendered_at"] == manifest["rendered_at"]
        assert receipt["git_sha"] == manifest["git_sha"]
        assert receipt["semantic_contract_models"] == ["stack_model"]
        assert receipt["methodology"] is False
        # Every figure's fingerprint equals its binding's embedded_sha256.
        sha = {r["name"]: r["embedded_sha256"]
               for r in manifest["embedded_data"]}
        assert [f["id"] for f in receipt["figures"]] == [
            "fig-kpi", "fig-tbl", "fig-rank"]
        by_id = {f["id"]: f for f in receipt["figures"]}
        assert by_id["fig-kpi"]["fingerprint"] == sha["kpi"]
        assert by_id["fig-tbl"]["fingerprint"] == sha["by_region"]
        assert by_id["fig-rank"]["fingerprint"] == sha["ranked"]
        # Model names come from the bindings' DataRefs; a report.py output
        # has no DataRef, so its figure records no model.
        assert by_id["fig-kpi"]["model"] == "stack_model"
        assert "model" not in by_id["fig-rank"]

    def test_byte_stable_across_renders_modulo_timestamp(
            self, stack_model, tmp_path):
        pkg = TemplatePackage(str(_pkg(tmp_path)))
        receipts = []
        for name in ("a.html", "b.html"):
            out = tmp_path / name
            pkg.render({"stack_model": stack_model}, str(out))
            receipts.append(_receipt(out.read_text(encoding="utf-8")))
        r1, r2 = receipts
        assert r1.pop("rendered_at") and r2.pop("rendered_at")
        # dicts preserve insertion order, so equal dumps means the same
        # bytes in the same order — byte-stable but for the render stamp.
        assert json.dumps(r1) == json.dumps(r2)

    def test_snapshot_carries_no_receipt_block(self, stack_model, tmp_path):
        # A draft page carries no receipt affordance — nothing for the
        # drawer to make look final (it also carries no manifest at all).
        pkg = TemplatePackage(str(_pkg(tmp_path)))
        snap = tmp_path / "snap.html"
        pkg.snapshot({"stack_model": stack_model}, str(snap))
        assert RECEIPT_OPEN not in snap.read_text(encoding="utf-8")
