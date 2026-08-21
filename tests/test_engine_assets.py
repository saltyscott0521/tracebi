"""The vendored artifact worker-engine assets ship and are well-formed.

These are inlined into a large-detail artifact so it decodes + filters its
embedded Parquet offline (docs/large-detail-artifacts.md, increment 3). Like the
ECharts bundle, they live in ``tracebi/reports/assets`` and are force-included in
the wheel; this test guards their presence and shape so a build that drops them
fails in CI rather than shipping an artifact whose engine cannot load.
"""

from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "tracebi" / "reports" / "assets"


def test_engine_worker_bundle_present_and_shaped():
    worker = ASSETS / "tracebi-engine.worker.js"
    assert worker.is_file(), "the worker engine bundle is missing"
    text = worker.read_text(encoding="utf-8", errors="replace")
    assert len(text) > 100_000, "worker bundle is implausibly small"
    # esbuild preserves the protocol's string literals; a bundle missing them
    # is not the engine worker.
    for marker in ("inited", "loaded", '"rows"', '"query"'):
        assert marker in text, f"worker bundle missing protocol marker {marker!r}"


def test_parquet_wasm_is_gzipped_and_substantial():
    wasm_gz = ASSETS / "parquet_wasm_bg.wasm.gz"
    assert wasm_gz.is_file(), "the gzipped parquet-wasm module is missing"
    data = wasm_gz.read_bytes()
    assert data[:2] == b"\x1f\x8b", "not a gzip stream"
    assert len(data) > 500_000, "wasm.gz is implausibly small"


def test_engine_notice_attributes_bundled_libraries():
    notice = ASSETS / "ENGINE_NOTICE.md"
    assert notice.is_file(), "ENGINE_NOTICE.md (attribution) is missing"
    text = notice.read_text(encoding="utf-8")
    for lib in ("parquet-wasm", "arquero", "apache-arrow"):
        assert lib in text, f"NOTICE does not attribute {lib}"
