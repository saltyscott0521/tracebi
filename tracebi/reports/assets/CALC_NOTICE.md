# Page engine — vendored asset & attribution

`tracebi-calc.js` recomputes a live report's figures in the page: it decodes
the embedded slice blocks (Parquet) and runs each binding's calc plan
(`tracebi/reports/calc_plan.py`) under the reader's selection. Plain
JavaScript, no wasm, no worker, nothing fetched; it is inlined like
`tracebi.js`. See `docs/architecture/live-reports-plan.md` (L-3).

| File | What it is |
|---|---|
| `tracebi-calc.js` | `window.tracebiCalc`: `load`, `run`, `domains`, `canonical`, `version`. Built from `_calc_src/` (`index.js`, `engine.js`, `select.js`, `parquet.js`) with the parts of hyparquet a flat Snappy or uncompressed block needs. 42 KB, 13 KB gzipped (budget: 50 KB gzipped, `tests/test_calc_parity.py`). |

## Third-party components (bundled into `tracebi-calc.js`)

- **hyparquet** 1.31.5 — MIT — https://github.com/hyparam/hyparquet
  (metadata, page headers, data pages v1 and v2, dictionary and RLE
  decoding, Snappy). Other codecs (ZSTD, gzip, Brotli) are not bundled; a
  block that uses one fails to load, naming the codec.

## The block it reads

`load(fact, bytes)` takes the raw Parquet bytes of one slice block: the
`parquet_b64` of the carrier `{"format": "parquet", "name", "parquet_b64",
"payload_sha256"}` in `<script type="application/json"
id="tracebi-slice-<fact>">`, base64-decoded (`b64ToBytes` in `tracebi.js`),
and gunzipped first (`gunzip`) when the build gzipped the block whole. Bytes
that still start with the gzip magic are refused with that message. Columns
must be numbers, booleans, strings or naive datetimes, flat.

## Rebuilding

```
cd tracebi/reports/assets/_calc_src
npm ci
npm run build      # writes ../tracebi-calc.js
```

The banner records a SHA-256 of the sources (`SOURCES` in `build.mjs`);
`tests/test_engine_assets.py` recomputes it, so a source edit that was never
rebuilt fails CI. The parity suite (`tests/test_calc_parity.py`) runs the
built bundle, not the sources.

## Exactness, and where it stops

Python is the source of truth: a plan means what `execute_plan` (DuckDB
through `DataModel.execute`) returns. The engine is a port, held to the
fixtures in `tests/fixtures/calc_parity/`, compared after the fingerprint's
cell rule (nine significant digits).

Floats are summed with Neumaier's compensated sum (sums, shares' totals,
runnings), so the engine's sum is the correctly rounded one in practice.
DuckDB sums in its own order and can land an ulp or two away. Two residual
risks follow, and neither is a bug in either engine:

- **Near-ties.** `rank`, `running` and `order_by` compare exact floats. Two
  groups whose sums differ only in the last bits can order differently here
  and on the server, so a rank or a row order can swap.
- **Rounding boundaries.** Nine significant digits absorb a last-bit
  difference except when the exact value sits on the rounding boundary. Money
  in the tens of millions is exactly that case: 15,010,403.95 is
  15010403.949999999 here (rounds to 15010403.9) and 15010403.950000001 in
  DuckDB (rounds to 15010404). A rounded fingerprint of the two results then
  differs although both are right to within an ulp.
