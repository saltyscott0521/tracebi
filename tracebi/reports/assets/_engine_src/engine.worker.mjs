import init, { readParquet } from 'parquet-wasm/esm/parquet_wasm.js';
import * as Arrow from 'apache-arrow';
import * as aq from 'arquero';


function toPlain(rows) {
  // parquet-wasm/Arrow decode int64 to BigInt; coerce to Number for rendering
  // and JSON. (BI quantities/counts fit in a double; true ids belong in strings.)
  return rows.map((r) => {
    const o = {};
    for (const k in r) { const v = r[k]; o[k] = (typeof v === 'bigint') ? Number(v) : v; }
    return o;
  });
}

const tables = {};
let ready = null;

self.onmessage = async (e) => {
  const m = e.data || {};
  try {
    if (m.type === 'init') {
      ready = init(m.wasm);           // wasm bytes passed from the main thread
      await ready;
      self.postMessage({ type: 'inited' });
    } else if (m.type === 'load') {
      await ready;
      const wt = readParquet(new Uint8Array(m.parquet));
      tables[m.name] = aq.fromArrow(Arrow.tableFromIPC(wt.intoIPCStream()));
      self.postMessage({ type: 'loaded', name: m.name, rows: tables[m.name].numRows() });
    } else if (m.type === 'rows') {
      const dt = tables[m.name];
      self.postMessage({ type: 'rows', name: m.name, id: m.id, rows: dt ? toPlain(dt.objects()) : [] });
    } else if (m.type === 'query') {
      // filter + optional groupby/rollup — the interactive path (§ figure controls)
      const dt = tables[m.name];
      if (!dt) { self.postMessage({ type: 'result', name: m.name, id: m.id, rows: [] }); return; }
      let f = dt;
      if (m.where) for (const [col, val] of Object.entries(m.where)) {
        f = f.params({ _c: col, _v: val }).filter((d, $) => d[$._c] === $._v);
      }
      let out = f;
      if (m.groupby) {
        const rollup = {};
        for (const [alias, spec] of Object.entries(m.agg || {})) {
          rollup[alias] = aq.escape(spec.op === 'sum'
            ? (d) => aq.op.sum(d[spec.col])
            : (d) => aq.op.count());
        }
        out = f.groupby(...m.groupby).rollup(rollup);
      }
      self.postMessage({ type: 'result', name: m.name, id: m.id, rows: toPlain(out.objects()) });
    }
  } catch (err) {
    self.postMessage({ type: 'error', name: m.name, id: m.id, message: String((err && err.message) || err) });
  }
};
