"""
Report generator — M0 trust kernel.

Covers the keystone claim: a reviewer with the shipped ``.html`` and its
manifest can confirm offline that the numbers it ships are exactly what the
recorded queries produced, while a number edited in the file is caught.

* the safe embedder neutralises a hostile cell value and round-trips exact bytes
* ``stamp`` fingerprints via the single ``frame_fingerprint`` algorithm
* ``verify_file`` passes an untampered file, fails a tampered one naming the
  binding, and is independent of ``verify_manifest`` (query → model), which is
  unchanged.

Self-contained: a tiny in-memory star model, no warehouse, no project files.
"""

from __future__ import annotations

import json
import os
import re

import pandas as pd
import pytest

from tracebi import DataModel, MemoryConnector, QuerySpec
from tracebi.reports.embed import (
    canonical_triple,
    embed_block,
    embed_json,
    embedded_record,
    fingerprint_triple,
    stamp,
)
from tracebi.reports.report import Report, TableSection
from tracebi.reports.template_package import TemplatePackage
from tracebi.verify import (
    FILE_ALTERED,
    FILE_INTACT,
    FILE_MATCHES,
    FILE_MISSING,
    FILE_TAMPERED,
    FILE_UNBACKED,
    FILE_UNRECORDED,
    REPRODUCES,
    UNVERIFIABLE,
    verify_file,
    verify_manifest,
)


# ── Fixtures: a tiny star model, one hostile issuer name in the data ──────────

@pytest.fixture
def orders_df():
    return pd.DataFrame({
        "order_id":    [1, 2, 3, 4],
        "customer_id": [10, 10, 20, 20],
        "revenue":     [100.5, 200.25, 300.0, 400.75],
    })


@pytest.fixture
def customers_df():
    # An attacker-influencable label (issuer names come from prose) that would
    # break out of a <script> if embedded naively.
    return pd.DataFrame({
        "customer_id": [10, 20],
        "region":      ["</script><img src=x onerror=alert(1)>", "North"],
    })


@pytest.fixture
def model(orders_df, customers_df):
    m = DataModel("kernel_model")
    m.add_connector(MemoryConnector("mem", tables={
        "orders": orders_df, "customers": customers_df,
    }))
    m.add_table("orders", connector="mem", source="orders")
    m.add_table("customers", connector="mem", source="customers")
    m.add_dimension("dim_customer", table_name="customers",
                    key_col="customer_id", attributes=["region"])
    m.add_fact("fact_orders", table_name="orders", measures=["revenue"],
               foreign_keys={"dim_customer": "customer_id"})
    m.add_measure("revenue", column="revenue", agg="sum")
    return m


@pytest.fixture
def spec():
    return QuerySpec(fact="fact_orders", measures=["revenue"],
                     dimensions=["dim_customer.region"])


@pytest.fixture
def artifacts(model, spec):
    """Hand-wire a manifest + matching self-contained .html, as M0 does by hand.

    Returns (html_str, manifest_dict, models_map).
    """
    sd = stamp(model, spec, name="by_region")
    report = Report("kernel").author("t")
    report.add(TableSection(title="By region", dataset=sd.dataset, id="by_region"))
    manifest = report.build_manifest("html", "report.html")
    manifest.embedded_data = [embedded_record(sd)]
    manifest_dict = manifest.to_dict()
    html = (
        "<!doctype html><html><head></head><body>\n"
        f"{embed_block(sd)}\n</body></html>\n"
    )
    return html, manifest_dict, {model.name: model}


# ── The safe embedder (architecture §5) ───────────────────────────────────────

class TestEmbedJson:
    def test_neutralises_injection(self):
        payload = {"cell": "</script><img src=x onerror=alert(1)>"}
        block = embed_json(payload, "x")
        inner = re.match(r'<script id="x" type="application/json">(.*)</script>',
                         block, re.DOTALL).group(1)
        # No raw breakout characters survive into the script body.
        assert "</script>" not in inner
        assert "<" not in inner
        assert ">" not in inner
        assert "&" not in inner
        assert " " not in inner and " " not in inner


# ── The canonical triple is the single fingerprint algorithm ──────────────────

class TestStamp:
    def test_fingerprint_equals_triple_hash(self, model, spec):
        sd = stamp(model, spec, name="by_region")
        assert sd.fingerprint == fingerprint_triple(sd.triple)

    def test_triple_matches_frame_fingerprint(self, model, spec):
        sd = stamp(model, spec, name="by_region")
        # The triple is exactly what frame_fingerprint hashed on the frame.
        assert sd.triple == canonical_triple(sd.dataset.to_pandas())
        assert sd.fingerprint == sd.dataset.fingerprint()


    def test_embedded_bytes_recover_to_fingerprint(self, model, spec):
        """The bytes shipped in the block rehash to the fingerprint — no frame."""
        sd = stamp(model, spec, name="by_region")
        block = embed_block(sd)
        parsed = json.loads(
            re.match(r'<script[^>]*>(.*)</script>', block, re.DOTALL).group(1)
        )
        triple = {k: parsed[k] for k in ("columns", "dtypes", "csv")}
        assert fingerprint_triple(triple) == sd.fingerprint


# ── verify_file: embedded bytes → manifest (architecture §3.2) ────────────────

class TestVerifyFile:
    def test_untampered_passes(self, artifacts):
        html, manifest, _ = artifacts
        result = verify_file(html, manifest)
        assert result["ok"] is True
        assert result["exit_code"] == 0
        assert result["verdict"] == FILE_INTACT
        assert [b["status"] for b in result["bindings"]] == [FILE_MATCHES]
        assert result["bindings"][0]["binding"] == "by_region"

    def test_tampered_number_fails_naming_binding(self, artifacts):
        html, manifest, _ = artifacts
        # Edit a real figure inside the embedded CSV — the $99,999,999 case.
        # 700.75 is an aggregated revenue in the embedded CSV; the csv copy
        # precedes the display 'records' copy, so the first replace hits the
        # fingerprinted bytes.
        assert "700.75" in html
        tampered = html.replace("700.75", "99999999.75", 1)
        assert tampered != html
        result = verify_file(tampered, manifest)
        assert result["ok"] is False
        assert result["exit_code"] == 1
        assert result["verdict"] == FILE_ALTERED
        offenders = [b for b in result["bindings"] if b["status"] == FILE_TAMPERED]
        assert [b["binding"] for b in offenders] == ["by_region"]

    def test_missing_block_in_file_fails(self, artifacts):
        html, manifest, _ = artifacts
        # A file that dropped the data block entirely still must not pass.
        stripped = re.sub(r'<script id="tracebi-data[^>]*>.*?</script>', "",
                          html, flags=re.DOTALL)
        result = verify_file(stripped, manifest)
        assert result["ok"] is False
        assert result["bindings"][0]["status"] == FILE_MISSING

    def test_block_with_no_manifest_binding_fails(self, artifacts):
        html, manifest, _ = artifacts
        manifest_no_rec = dict(manifest)
        manifest_no_rec.pop("embedded_data", None)
        result = verify_file(html, manifest_no_rec)
        assert result["ok"] is False
        assert result["bindings"][0]["status"] == FILE_UNRECORDED

    def test_unbacked_when_no_section_carries_the_fingerprint(self, artifacts):
        # A manifest whose sections were stripped still records the embedded
        # binding — the bytes "match", but nothing in the receipt vouches for
        # them. That must fail, not read as INTACT (it did, before the fix).
        html, manifest, _ = artifacts
        broken = dict(manifest)
        broken["sections"] = [
            {k: v for k, v in s.items() if k != "dataset_fingerprint"}
            for s in manifest["sections"]
        ]
        result = verify_file(html, broken)
        assert result["ok"] is False
        assert result["verdict"] == FILE_ALTERED
        assert result["bindings"][0]["status"] == FILE_UNBACKED


# ── verify_manifest (query → model) is a separate, unaffected check ────────────

class TestChecksAreIndependent:
    def test_tampering_the_file_does_not_affect_manifest_verify(self, artifacts):
        """The whole point: a number edited in the .html leaves the model-
        reproduction check green, and only ``verify_file`` catches it."""
        html, manifest, models = artifacts
        tampered = html.replace("700.75", "99999999.75", 1)
        # File check fails …
        assert verify_file(tampered, manifest)["ok"] is False
        # … while manifest (query → model) reproduces, untouched.
        assert verify_manifest(manifest, models)["ok"] is True


# ── M0: metric receipts in the legacy spec lane (plan §2.2) ───────────────────

class TestMetricReceipts:
    """A metrics section with a ``data`` query embeds its one-row canonical
    triple in the rendered HTML and records it in ``embedded_data``, so
    ``verify --file`` covers the page's biggest numbers (report architecture
    v2 §2.2 — the metric-receipt hole). The KPI cards themselves stay
    server-rendered; the embedded triple is the receipt, not the display.
    """

    def _render(self, tmp_path, model):
        from tracebi.reports.html_renderer import HTMLRenderer
        from tracebi.spec import ReportSpec

        spec = ReportSpec.from_dict({
            "name": "KPIs",
            "sections": [{
                "type": "metrics", "title": "Totals", "id": "kpis",
                "data": {"model": "kernel_model", "query": {
                    "fact": "fact_orders", "measures": ["revenue"]}},
                "metrics": [
                    {"label": "Revenue", "value": "revenue",
                     "format": "currency0"},
                ],
            }],
        })
        report = spec.build({model.name: model})
        out = tmp_path / "kpis.html"
        manifest = HTMLRenderer().render(report, str(out))
        return out.read_text(encoding="utf-8"), manifest


    def test_file_check_passes_then_catches_kpi_tamper(self, tmp_path, model):
        html, manifest = self._render(tmp_path, model)
        man = manifest.to_dict()
        assert verify_file(html, man)["verdict"] == FILE_INTACT

        # Edit the KPI total inside the embedded triple — the $99,999,999 case.
        assert "1001.5" in html
        tampered = html.replace("1001.5", "99999999.5", 1)
        result = verify_file(tampered, man)
        assert result["ok"] is False
        assert result["verdict"] == FILE_ALTERED
        offenders = [b["binding"] for b in result["bindings"]
                     if b["status"] == FILE_TAMPERED]
        assert offenders == ["kpis"]


# ── M1: the template-package renderer (architecture §2 lane B, §8-M1) ─────────

# A template that OMITS every framework placeholder — no {{ head_extra }},
# {{ body_extra }}, no data mount. The renderer must still inject the data by
# string insertion, or the page ships with no numbers (the §8-M1 hole).
_BARE_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{{ title }}</title></head>
<body><main><h1>Bare</h1><table id="mount"><tbody></tbody></table></main></body>
</html>
"""

_STYLE = "body { color: rebeccapurple; } table { border-collapse: collapse; }"

_SCRIPT = (
    'var el = document.getElementById("tracebi-data-by_region");'
    "var data = JSON.parse(el.textContent); void data;"
)


def _write_package(tmp_path, *, template=_BARE_TEMPLATE, style=_STYLE,
                   script=_SCRIPT, data=None, name="Regions",
                   dirname="regions", report_py=None, libs=None,
                   figures=None, title=None):
    """Write a package dir and return its path."""
    if data is None:
        data = {
            "by_region": {
                "model": "kernel_model",
                "query": {
                    "fact": "fact_orders",
                    "measures": ["revenue"],
                    "dimensions": ["dim_customer.region"],
                },
            }
        }
    pkg = tmp_path / dirname
    pkg.mkdir()
    decl = {"name": name, "author": "t", "data": data}
    if title is not None:
        decl["title"] = title
    if libs is not None:
        decl["libs"] = libs
    if figures is not None:
        decl["figures"] = figures
    (pkg / "report.json").write_text(json.dumps(decl), encoding="utf-8")
    (pkg / "template.html").write_text(template, encoding="utf-8")
    if style is not None:
        (pkg / "style.css").write_text(style, encoding="utf-8")
    if script is not None:
        (pkg / "script.js").write_text(script, encoding="utf-8")
    if report_py is not None:
        (pkg / "report.py").write_text(report_py, encoding="utf-8")
    return pkg


class TestProseNumericGate:
    def test_a_hand_typed_number_fails_the_build(self, tmp_path, model):
        template = _BARE_TEMPLATE.replace(
            "<h1>Bare</h1>",
            "<h1>Bare</h1><p>The book is worth 12.</p>",
        )
        pkg = _write_package(tmp_path, template=template, dirname="prose")
        with pytest.raises(Exception, match="numeric literal"):
            TemplatePackage(str(pkg)).render({model.name: model}, str(tmp_path / "out.html"))

    def test_a_number_inside_exploration_is_stripped_before_the_gate(self, tmp_path, model):
        template = _BARE_TEMPLATE.replace(
            "<h1>Bare</h1>",
            '<h1>Bare</h1><div data-tb-stage="exploration"><p>Worth 12.</p></div>',
        )
        pkg = _write_package(tmp_path, template=template, dirname="explore_num")
        TemplatePackage(str(pkg)).render(
            {model.name: model}, str(tmp_path / "out.html"))


class TestTemplatePackageRender:
    def test_self_contained_no_external_refs(self, tmp_path, model):
        pkg = _write_package(tmp_path)
        out = tmp_path / "out.html"
        TemplatePackage(str(pkg)).render({model.name: model}, str(out))
        html = out.read_text(encoding="utf-8")
        # No external CSS/JS/img: nothing that would phone home when opened.
        assert not re.search(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', html)

    def test_strict_csp_on_every_page(self, tmp_path, model):
        # The CSP (architecture §5) ships even on a data-only report: no
        # network, and — since ECharts needs none — no unsafe-eval.
        pkg = _write_package(tmp_path)
        out = tmp_path / "out.html"
        TemplatePackage(str(pkg)).render({model.name: model}, str(out))
        html = out.read_text(encoding="utf-8")
        assert 'http-equiv="Content-Security-Policy"' in html
        assert "connect-src 'none'" in html
        # JS eval is never granted. 'wasm-unsafe-eval' IS (WebAssembly
        # compilation only, for the artifact's worker engine) — and since
        # it CONTAINS "'unsafe-eval'", drop it before checking.
        assert "'unsafe-eval'" not in html.replace("'wasm-unsafe-eval'", "")

    def test_author_text_cannot_suppress_the_csp(self):
        """The strict CSP must not be dropped just because a template mentions
        the phrase 'Content-Security-Policy' (a comment, prose, or a weaker
        policy an injection tried to smuggle) — dedup is on the exact meta."""
        from tracebi.reports.embed import csp_meta
        from tracebi.reports.stack import apply_stack

        page = ("<html><head></head><body>"
                "<!-- notes on Content-Security-Policy -->"
                "<p>our Content-Security-Policy is strict</p></body></html>")
        out = apply_stack(page, libs=(), data_blocks_html="")
        assert csp_meta().strip() in out, "author text must not disable the CSP"

        # But the EXACT framework meta (as html_renderer inserts) is not doubled.
        page2 = f"<html><head>{csp_meta()}</head><body></body></html>"
        out2 = apply_stack(page2, libs=(), data_blocks_html="")
        assert out2.count('http-equiv="Content-Security-Policy"') == 1


def _doc(body: str) -> str:
    """A complete document — the data/style/script injection needs one."""
    return (f"<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>t</title></head><body>{body}</body></html>\n")


class TestChartLibraries:


    _CHART_DATA = {
        "by_region": {
            "model": "kernel_model",
            "query": {
                "fact": "fact_orders",
                "measures": ["revenue"],
                "dimensions": ["dim_customer.region"],
            },
        },
    }
    _CHART_FIGURES = {
        "by_region": {
            "kind": "chart", "binding": "by_region", "chart_type": "bar",
            "x": "dim_customer.region", "y": "revenue",
        },
    }

    def _render_chart(self, tmp_path, model, *, libs=None, template=None,
                      figures=None, dirname="charted"):
        from tracebi.reports.embed import read_lib

        pkg = _write_package(
            tmp_path, dirname=dirname, script=None, libs=libs,
            data=self._CHART_DATA,
            figures=self._CHART_FIGURES if figures is None else figures,
            template=template or _doc('{{ figure("by_region") }}'),
        )
        out = tmp_path / f"{dirname}.html"
        manifest = TemplatePackage(str(pkg)).render(
            {model.name: model}, str(out))
        return out.read_text(encoding="utf-8"), manifest, read_lib("d3")


    def test_verify_file_passes_then_fails_on_tamper(self, tmp_path, model):
        pkg = _write_package(tmp_path)
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(pkg)).render({model.name: model}, str(out))
        man = manifest.to_dict()
        html = out.read_text(encoding="utf-8")

        ok = verify_file(html, man)
        assert ok["ok"] is True
        assert ok["verdict"] == FILE_INTACT
        assert [b["status"] for b in ok["bindings"]] == [FILE_MATCHES]

        # Tamper a real aggregated figure inside the canonical csv bytes.
        assert "700.75" in html
        bad = verify_file(html.replace("700.75", "99999999.75", 1), man)
        assert bad["ok"] is False
        assert bad["verdict"] == FILE_ALTERED
        offenders = [b["binding"] for b in bad["bindings"]
                     if b["status"] == FILE_TAMPERED]
        assert offenders == ["by_region"]


class TestTemplatePackageLoading:


    def test_fragment_template_builds_a_complete_document(self, tmp_path, model):
        # <header> must not be read as <head>. A pure fragment is wrapped,
        # then the runtime is injected into that document.
        pkg = _write_package(
            tmp_path,
            template="<header><section>Regions</section></header>",
            style=None, script=None, title="Book Value",
        )
        out = tmp_path / "out.html"
        TemplatePackage(str(pkg)).render({model.name: model}, str(out))
        html = out.read_text(encoding="utf-8")
        assert html.lower().lstrip().startswith("<!doctype html>")
        assert "<html>" in html.lower()
        assert "</head>" in html.lower()
        assert '<meta charset="utf-8">' in html
        assert "<title>Book Value</title>" in html
        assert "<header><section>Regions</section></header>" in html
        assert "<!-- tracebi.js: the TraceBi runtime -->" in html
        assert "Content-Security-Policy" in html


    def test_malformed_document_without_head_close_still_fails(self, tmp_path, model):
        pkg = _write_package(
            tmp_path,
            template="<html><body>no head</body></html>",
            style=None, script=None,
        )
        out = tmp_path / "out.html"
        with pytest.raises(ValueError, match=r"no </head>"):
            TemplatePackage(str(pkg)).render({model.name: model}, str(out))


# ── M3: the report.py escape hatch + honesty (architecture §4, §8-M3) ─────────

# A template that mounts the report.py OUTPUT block (not an input binding).
_OUTPUT_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{{ title }}</title></head>
<body><main><h1>Derived</h1><table id="mount"><tbody></tbody></table></main></body>
</html>
"""

# report.py: combines the stamped input into a python-derived output carrying a
# running cumulative — a window the declarative query surface cannot express.
_REPORT_PY = """
import pandas as pd


def build(inputs):
    df = inputs["by_region"].copy()
    df = df.sort_values("revenue", ascending=False).reset_index(drop=True)
    df["cumulative"] = df["revenue"].cumsum()
    return {"ranked": df}
"""


def _escape_hatch_package(tmp_path):
    return _write_package(
        tmp_path, template=_OUTPUT_TEMPLATE,
        script='var el=document.getElementById("tracebi-data-ranked");void el;',
        report_py=_REPORT_PY, name="Ranked", dirname="ranked",
    )


class TestEscapeHatchRender:


    def test_manifest_marks_output_unverifiable_input_reproducible(self, tmp_path, model):
        """M0 flip (report-architecture-v2 §2.1, §5 ledger): verifiability is
        per binding, not per package. The manifest records the query binding
        with no ``verifiable: false`` flag (green-eligible) beside the
        report.py output recorded verifiable=false — the escape hatch no
        longer flattens the declared binding to false."""
        pkg = _escape_hatch_package(tmp_path)
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(pkg)).render(
            {model.name: model}, str(out)).to_dict()
        by_name = {r["name"]: r for r in manifest["embedded_data"]}
        assert set(by_name) == {"by_region", "ranked"}
        assert by_name["by_region"].get("verifiable") is None     # query binding
        assert by_name["by_region"]["query_spec"] is not None     # replay-checkable
        assert by_name["by_region"]["model"] == model.name
        assert by_name["ranked"]["verifiable"] is False           # python-derived
        assert by_name["ranked"]["query_spec"] is None
        by_id = {s.get("id"): s for s in manifest["sections"]}
        assert by_id["by_region"].get("verifiable") is None       # reproducible carrier
        assert by_id["by_region"]["dataset_fingerprint"]          # query-stamped
        assert by_id["ranked"]["verifiable"] is False             # python-derived carrier


class TestEscapeHatchHonesty:
    def test_output_classified_unverifiable_input_reproduces(self, tmp_path, model):
        """verify (query -> model): the input query reproduces; the
        python-derived output is UNVERIFIABLE, named as report.py output."""
        pkg = _escape_hatch_package(tmp_path)
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(pkg)).render(
            {model.name: model}, str(out)).to_dict()
        result = verify_manifest(manifest, {model.name: model})
        by_section = {s["section"]: s for s in result["sections"]}
        assert by_section["by_region"]["status"] == REPRODUCES
        assert by_section["ranked"]["status"] == UNVERIFIABLE
        assert by_section["ranked"]["python_derived"] is True
        assert "report.py" in by_section["ranked"]["detail"]

    def test_green_never_reads_as_verified(self, tmp_path, model):
        """Exit 0 (the input reproduced, nothing failed), but the verdict line
        explicitly says the python-derived output was not query-reproducible —
        so a clean exit never reads as 'these numbers were verified'."""
        pkg = _escape_hatch_package(tmp_path)
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(pkg)).render(
            {model.name: model}, str(out)).to_dict()
        result = verify_manifest(manifest, {model.name: model})
        assert result["ok"] is True
        assert result["exit_code"] == 0
        assert result["python_derived"] == 1
        assert "python-derived" in result["verdict_detail"]
        assert "not query-reproducible" in result["verdict_detail"]

    def test_verifiable_false_forces_unverifiable_even_with_a_query_node(
            self, tmp_path, model, spec):
        """Defence in depth: a section flagged verifiable=false is UNVERIFIABLE
        by construction — even if its lineage happens to carry a query node, it
        must not read as reproduced."""
        sd = stamp(model, spec, name="ranked")   # a fully query-stamped dataset
        # Manifest section with a real query in lineage BUT flagged python-derived.
        section = {
            "id": "ranked", "section_type": "table",
            "dataset_fingerprint": sd.fingerprint,
            "dataset_lineage": sd.dataset.lineage_to_dict(),
            "verifiable": False,
        }
        manifest = {"report_name": "x", "schema_version": 1, "sections": [section]}
        result = verify_manifest(manifest, {model.name: model})
        assert result["sections"][0]["status"] == UNVERIFIABLE
        assert result["sections"][0]["python_derived"] is True


class TestPerBindingVerifiability:
    """M0 seam (report-architecture-v2 §2.1 "The per-binding verifiability
    seam", §5 ledger): a report.py beside a report.json no longer poisons the
    declarative bindings — a receipt STRENGTHENING. What was grey (or absent
    from the offline check) becomes green; python-derived outputs stay grey,
    hardcoded, never green."""

    def test_mixed_package_query_binding_reproduces_python_output_stays_grey(
            self, tmp_path, model):
        """The pre-pattern mixed package (one query binding + one report.py
        output): the query binding classifies REPRODUCES under replay, the
        python output stays UNVERIFIABLE, and the offline file check passes
        with BOTH bindings covered."""
        pkg = _escape_hatch_package(tmp_path)
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(pkg)).render(
            {model.name: model}, str(out)).to_dict()

        # Replay check (query -> model): per-binding truth.
        result = verify_manifest(manifest, {model.name: model})
        by_section = {s["section"]: s for s in result["sections"]}
        assert by_section["by_region"]["status"] == REPRODUCES
        assert by_section["ranked"]["status"] == UNVERIFIABLE
        assert by_section["ranked"]["python_derived"] is True

        # Offline check: the query binding's bytes are now embedded and
        # vouched for too — it was not even file-checkable before the seam.
        file_result = verify_file(out.read_text(encoding="utf-8"), manifest)
        assert file_result["verdict"] == FILE_INTACT
        assert file_result["summary"][FILE_MATCHES] == 2
        assert {b["binding"] for b in file_result["bindings"]} == {
            "by_region", "ranked"}

    def test_mixed_verdict_names_both_kinds(self, tmp_path, model):
        """The verdict for a mixed receipt names both kinds honestly: the
        checked-and-matching count AND the python-derived remainder
        (_verdict_fields already supports mixed — this pins it)."""
        pkg = _escape_hatch_package(tmp_path)
        out = tmp_path / "out.html"
        manifest = TemplatePackage(str(pkg)).render(
            {model.name: model}, str(out)).to_dict()
        result = verify_manifest(manifest, {model.name: model})
        assert result["verdict"] == REPRODUCES
        assert result["summary"][REPRODUCES] == 1
        assert result["summary"][UNVERIFIABLE] == 1
        assert "1 of 2 section(s) checked and matching" in result["verdict_detail"]
        assert "python-derived" in result["verdict_detail"]
        assert "not query-reproducible" in result["verdict_detail"]


def test_preview_server_binds_loopback_not_all_interfaces(tmp_path, monkeypatch):
    """The unauthenticated preview server must bind 127.0.0.1, not '' (all
    interfaces) — otherwise a directory of rendered reports is published to
    anyone on the network, while the printed URL says localhost."""
    import http.server

    from tracebi.cli import _serve_file

    captured = {}

    class FakeServer:
        def __init__(self, address, handler):
            captured["address"] = address

        def serve_forever(self):
            raise KeyboardInterrupt   # exit the blocking loop at once

        def server_close(self):
            pass

    monkeypatch.setattr(http.server, "HTTPServer", FakeServer)
    html = tmp_path / "r.html"
    html.write_text("<p>x</p>")
    _serve_file(html, "r", 8099, open_browser=False)
    assert captured["address"][0] == "127.0.0.1"


def test_preview_srcdoc_does_not_double_decode(monkeypatch, tmp_path):
    """A cell escaped to &lt;script&gt; during render must not be decoded back
    into live markup when embedded in an iframe srcdoc: srcdoc is decoded once
    by the browser, so the content's '&' must be escaped too (double-decode
    XSS otherwise)."""
    import sys
    import types

    from tracebi.reports.html_renderer import HTMLRenderer

    captured = {}
    fake = types.ModuleType("IPython.display")
    fake.display = lambda x: captured.__setitem__("shown", x)
    fake.HTML = lambda s: captured.__setitem__("srcdoc", s) or s
    fake.IFrame = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "IPython", types.ModuleType("IPython"))
    monkeypatch.setitem(sys.modules, "IPython.display", fake)

    r = HTMLRenderer()

    def fake_render(report, path, save_manifest=False):
        with open(path, "w", encoding="utf-8") as f:
            f.write("<body>&lt;script&gt;alert(1)&lt;/script&gt;</body>")

    monkeypatch.setattr(r, "render", fake_render)
    r.preview(None)
    s = captured["srcdoc"]
    # The already-escaped entity is DOUBLE-escaped, so one srcdoc-decode leaves
    # it as text (&lt;script&gt;), never a live <script>.
    assert "&amp;lt;script&amp;gt;" in s
    assert 'srcdoc="<body>&lt;script' not in s
