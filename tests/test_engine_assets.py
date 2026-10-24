"""The vendored page engine ships, is built from its sources, and is inlined
only where a page has something for it to read.

``tracebi-calc.js`` decodes a page's Parquet blocks (slices and large-detail
bindings) and runs its calc plans (design/live-reports-plan.md).
Like the chart bundles it lives in ``tracebi/reports/assets`` and is
force-included in the wheel.
"""


# ── inlining the engine into an artifact ─────────────────────────────────────


def test_engine_ships_only_when_a_page_has_parquet_or_a_slice():
    """A CSV page with no slice carries no engine; a Parquet binding or a
    slice brings it, once."""
    from tracebi.reports.stack import stack_tail

    csv_block = '<script id="tracebi-data-x" type="application/json">' \
                '{"name": "x", "columns": "[]", "dtypes": "[]", "csv": ""}</script>'
    pq_block = '<script id="tracebi-data-x" type="application/json">' \
               '{"name": "x", "format": "parquet", "parquet_b64": "AAA="}</script>'
    plans = '<script id="tracebi-calc-plans" type="application/json">{}</script>'

    # Assert on the engine's own marker, not the ids: the runtime source
    # names both ids (it looks them up), so a substring check always matches.
    engine = "<!-- tracebi-calc.js"
    assert engine not in stack_tail(libs=(), data_blocks_html=csv_block)
    assert stack_tail(libs=(), data_blocks_html=pq_block).count(engine) == 1
    assert stack_tail(libs=(), data_blocks_html=csv_block + plans).count(engine) == 1


def test_csp_grants_no_eval_no_worker_and_no_network():
    from tracebi.reports.embed import CSP

    # The engine is plain inlined JavaScript: no wasm, no worker, no eval...
    assert "eval" not in CSP and "worker-src" not in CSP and "blob:" not in CSP
    # ...and nothing may phone home.
    assert "connect-src 'none'" in CSP


# ── the page engine bundle (tracebi-calc.js) ─────────────────────────────────


def test_calc_bundle_is_built_from_its_sources():
    """A source edit to ``_calc_src`` that was never rebuilt would ship an
    engine the parity suite never ran. ``build.mjs`` stamps a SHA-256 of the
    sources into the bundle's banner; recompute it here, with no node."""
    import hashlib
    import re
    from pathlib import Path

    assets = Path(__file__).resolve().parents[1] / "tracebi" / "reports" / "assets"
    src = assets / "_calc_src"
    sources = re.findall(r'"([^"]+)"', re.search(
        r"SOURCES = \[(.*?)\]", (src / "build.mjs").read_text()).group(1))
    digest = hashlib.sha256()
    for name in sources:
        digest.update(f"{name}\n".encode())
        digest.update((src / name).read_bytes())
    banner = (assets / "tracebi-calc.js").read_text(encoding="utf-8").split("\n", 1)[0]
    assert f"src-sha256:{digest.hexdigest()}" in banner, (
        "tracebi-calc.js is stale: run `npm ci && node build.mjs` in "
        "tracebi/reports/assets/_calc_src (see CALC_NOTICE.md)")
