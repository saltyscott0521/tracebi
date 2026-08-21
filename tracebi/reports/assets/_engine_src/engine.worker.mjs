import init, { readParquet } from 'parquet-wasm/esm/parquet_wasm.js';
import * as Arrow from 'apache-arrow';
import * as aq from 'arquero';

/* Values leave this worker as the STRINGS the CSV embed would have carried.
 *
 * The runtime downstream was written against the CSV path, where every cell is
 * a string it then parses and formats (toNum / deriveFormat / renderBody). If
 * the Parquet path handed it native JS values instead, the same receipted data
 * would DISPLAY differently either side of the size threshold: Arrow decodes a
 * date to epoch milliseconds ("1705276800000" instead of "2024-01-15"), a NULL
 * to null rather than "" (which the numeric-column detector reads as
 * non-numeric, losing alignment and formatting), and int64 to BigInt (which
 * JSON cannot serialise, and which Number() silently truncates past 2^53).
 * Normalising here keeps ONE rendering for both transports. */
function cellToText(v) {
  if (v === null || v === undefined) return '';        /* CSV writes empty */
  const t = typeof v;
  if (t === 'string') return v;
  if (t === 'bigint') {
    /* Never Number(): 2^53+1 would render as a different integer than the
     * fingerprinted bytes. The exact decimal string always round-trips. */
    return v.toString();
  }
  if (t === 'boolean') return v ? 'True' : 'False';    /* pandas CSV spelling */
  if (v instanceof Date) return isoLike(v);
  if (t === 'number') {
    /* Arrow surfaces temporal columns as epoch millis; the caller tags those
     * columns so they are converted before reaching here. A plain number is a
     * measure: leave its full precision to the runtime's formatter. */
    return String(v);
  }
  return String(v);
}

/* "2024-01-15" for a midnight-UTC instant, else "2024-01-15 10:00:00" — the
 * shapes pandas' to_csv writes, so a date reads as a date on both paths. */
function isoLike(d) {
  const s = d.toISOString();
  return s.endsWith('T00:00:00.000Z') ? s.slice(0, 10)
                                      : s.slice(0, 19).replace('T', ' ');
}

function temporalColumns(schema) {
  const out = {};
  for (const f of (schema && schema.fields) || []) {
    const t = String(f.type || '');
    if (/Date|Timestamp/i.test(t)) out[f.name] = true;
  }
  return out;
}

function toPlain(rows, temporal) {
  return rows.map((r) => {
    const o = {};
    for (const k in r) {
      let v = r[k];
      if (temporal && temporal[k] && v !== null && v !== undefined
          && !(v instanceof Date)) {
        v = new Date(typeof v === 'bigint' ? Number(v) : v);
      }
      o[k] = cellToText(v);
    }
    return o;
  });
}

/* A CSV rendering of the decoded rows, so the artifact's download control hands
 * the reader the same values the page is showing. */
function toCsv(cols, rows) {
  const esc = (s) => (/[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s);
  const lines = [cols.map(esc).join(',')];
  for (const r of rows) lines.push(cols.map((c) => esc(r[c] === undefined ? '' : r[c])).join(','));
  return lines.join('\n') + '\n';
}

const tables = {};
const temporals = {};
let ready = null;

function reply(type, m, dt) {
  const cols = dt ? dt.columnNames() : [];
  const rows = dt ? toPlain(dt.objects(), temporals[m.name]) : [];
  self.postMessage({ type, name: m.name, id: m.id, rows, cols, csv: toCsv(cols, rows) });
}

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
      const at = Arrow.tableFromIPC(wt.intoIPCStream());
      temporals[m.name] = temporalColumns(at.schema);
      tables[m.name] = aq.fromArrow(at);
      self.postMessage({ type: 'loaded', name: m.name, rows: tables[m.name].numRows() });
    } else if (m.type === 'rows') {
      reply('rows', m, tables[m.name]);
    } else if (m.type === 'query') {
      // filter + optional groupby/rollup — the interactive path (§ figure controls)
      const dt = tables[m.name];
      if (!dt) { self.postMessage({ type: 'result', name: m.name, id: m.id, rows: [], cols: [], csv: '' }); return; }
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
      reply('result', m, out);
    }
  } catch (err) {
    self.postMessage({ type: 'error', name: m.name, id: m.id, message: String((err && err.message) || err) });
  }
};
