"""The vendored artifact worker-engine assets ship and are well-formed.

These are inlined into a large-detail artifact so it decodes + filters its
embedded Parquet offline (docs/architecture/large-detail-artifacts.md, increment 3). Like the
ECharts bundle, they live in ``tracebi/reports/assets`` and are force-included in
the wheel; this test guards their presence and shape so a build that drops them
fails in CI rather than shipping an artifact whose engine cannot load.
"""



# ── inlining the engine into an artifact ─────────────────────────────────────


def test_engine_ships_only_when_a_binding_is_parquet():
    """A CSV artifact must not pay megabytes for an engine it never starts."""
    from tracebi.reports.stack import stack_tail

    csv_block = '<script id="tracebi-data-x" type="application/json">' \
                '{"name": "x", "columns": "[]", "dtypes": "[]", "csv": ""}</script>'
    pq_block = '<script id="tracebi-data-x" type="application/json">' \
               '{"name": "x", "format": "parquet", "parquet_b64": "AAA="}</script>'

    csv_tail = stack_tail(libs=(), data_blocks_html=csv_block)
    pq_tail = stack_tail(libs=(), data_blocks_html=pq_block)

    # Assert on the engine BLOCKS, not the bare ids: the runtime source itself
    # names both ids (it looks them up), so a substring check always matches.
    worker_block = 'id="tracebi-engine-worker"'
    wasm_block = 'id="tracebi-engine-wasm"'
    assert worker_block not in csv_tail
    assert worker_block in pq_tail
    assert wasm_block in pq_tail
    # The engine is megabytes; a CSV artifact must not carry it.
    assert len(pq_tail) - len(csv_tail) > 1_000_000


def test_csp_grants_wasm_and_blob_worker_but_never_js_eval():
    from tracebi.reports.embed import CSP

    # The worker engine needs a blob worker + WebAssembly compilation...
    assert "worker-src blob:" in CSP
    assert "'wasm-unsafe-eval'" in CSP
    assert "blob:" in CSP.split("script-src", 1)[1].split(";", 1)[0]
    # ...but JS eval is still never granted, and nothing may phone home.
    assert "'unsafe-eval'" not in CSP.replace("'wasm-unsafe-eval'", "")
    assert "connect-src 'none'" in CSP
