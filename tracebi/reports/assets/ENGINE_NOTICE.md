# Artifact worker engine — vendored assets & attribution

Two vendored assets power the large-detail artifact's in-browser query engine
(see `docs/large-detail-artifacts.md`). They are inlined into a generated
artifact so it runs **offline, with no network**, decoding and filtering the
embedded Parquet on a background thread.

| File | What it is |
|---|---|
| `tracebi-engine.worker.js` | The bundled Web Worker: a Parquet decoder + a columnar query engine + the artifact's `init`/`load`/`rows`/`query` message protocol. Runs as a blob-URL worker. |
| `parquet_wasm_bg.wasm.gz` | The `parquet-wasm` WebAssembly module, gzip-compressed (6.2 MB → 1.7 MB). Inlined base64 and decompressed in the browser via `DecompressionStream` before instantiation. |

## Third-party components (bundled into `tracebi-engine.worker.js`)

This redistributes the following open-source libraries; their licenses apply:

- **parquet-wasm** 0.7.2 — MIT OR Apache-2.0 — https://github.com/kylebarron/parquet-wasm
- **arquero** 8.0.3 — BSD-3-Clause — https://github.com/uwdata/arquero
- **apache-arrow** (JS) 21.2.0 — Apache-2.0 — https://github.com/apache/arrow

## Rebuilding

Source: `_engine_src/engine.worker.mjs`. With the three libraries installed
(`npm i parquet-wasm@0.7.2 arquero@8.0.3 apache-arrow@21.2.0 esbuild`):

```
esbuild _engine_src/engine.worker.mjs --bundle --format=iife \
  --outfile=tracebi-engine.worker.js
gzip -9 -c node_modules/parquet-wasm/esm/parquet_wasm_bg.wasm \
  > parquet_wasm_bg.wasm.gz
```

The receipt is unaffected by any rebuild: the engine only *reads* the embedded
Parquet; the fingerprint is the frame's content triple, verified in Python.
