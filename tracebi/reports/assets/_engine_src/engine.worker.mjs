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
function cellToText(v, dateOnly, isFloat) {
  if (v === null || v === undefined) return '';        /* CSV writes empty */
  const t = typeof v;
  if (t === 'string') return v;
  if (t === 'bigint') {
    /* Never Number(): 2^53+1 would render as a different integer than the
     * fingerprinted bytes. The exact decimal string always round-trips. */
    return v.toString();
  }
  if (t === 'boolean') return v ? 'True' : 'False';    /* pandas CSV spelling */
  if (v instanceof Date) return isoLike(v, dateOnly);
  if (t === 'number') {
    /* Arrow surfaces temporal columns as epoch millis; the caller tags those
     * columns so they are converted before reaching here. */
    if (isFloat) return floatToText(v, isFloat === 'f32');
    return String(v);
  }
  return String(v);
}

/* pandas' to_csv spellings for a float column, which JS String() does not
 * match: an integral float keeps its '.0', the infinities are 'inf'/'-inf'
 * (not 'Infinity'), and negative zero keeps its sign. NaN never reaches here —
 * Arrow stores it as null, which renders '' exactly as pandas writes it. A
 * column the runtime derives no number format for (an id, a year) shows these
 * strings verbatim, so they have to be right. */
function floatToText(v, f32) {
  if (v === Infinity) return 'inf';
  if (v === -Infinity) return '-inf';
  if (Number.isNaN(v)) return '';
  if (Object.is(v, -0)) return '-0.0';
  if (f32) {
    /* Shortest decimal that round-trips through float32 — numpy/pandas print
     * this; a float32 needs at most 9 significant digits. JS holds the value
     * widened to float64, so String() would print the widening
     * ('1.100000023841858' for 1.1f). */
    for (let p = 1; p <= 9; p++) {
      const s = v.toPrecision(p);
      if (Math.fround(parseFloat(s)) === v) return pyRepr(parseFloat(s));
    }
  }
  return pyRepr(v);
}

/* Format finite *v* exactly as Python's repr (hence pandas' to_csv) would.
 * toExponential() with no argument yields the shortest round-trip digits —
 * the same digits Python computes — so only the NOTATION decision remains:
 * fixed while the decimal exponent is in [-4, 16) (with '.0' kept on
 * integral values), else scientific with a two-digit zero-padded exponent
 * ('1e+16', '1e-07'). JS String() differs at every edge: it switches to
 * scientific at 1e21, writes '1e-7', and drops the '.0'. */
function pyRepr(v) {
  const parts = v.toExponential().split('e');
  const exp = parseInt(parts[1], 10);
  if (exp >= 16 || exp < -4) {
    const sign = exp < 0 ? '-' : '+';
    const mag = String(Math.abs(exp)).padStart(2, '0');
    return parts[0] + 'e' + sign + mag;
  }
  /* Fixed notation, rebuilt from the digit string — no float re-rounding. */
  let m = parts[0];
  let neg = '';
  if (m[0] === '-') { neg = '-'; m = m.slice(1); }
  const digits = m.replace('.', '');
  let out;
  if (exp >= 0) {
    if (exp + 1 >= digits.length) {
      out = digits + '0'.repeat(exp + 1 - digits.length) + '.0';
    } else {
      out = digits.slice(0, exp + 1) + '.' + digits.slice(exp + 1);
    }
  } else {
    out = '0.' + '0'.repeat(-exp - 1) + digits;
  }
  return neg + out;
}

/* pandas' to_csv drops the time part for a datetime column only when EVERY
 * value is midnight — a per-COLUMN decision. Deciding per value would render
 * the midnight rows of a mixed column as bare dates while their neighbours keep
 * a time, which the CSV transport never does. *dateOnly* carries the column's
 * verdict. (Only naive datetimes reach here: choose_embed_format keeps
 * tz-aware, timedelta, decimal and friends on the CSV transport, because the
 * engine cannot reproduce their rendering.) */
function isoLike(d, dateOnly) {
  const s = d.toISOString();
  return dateOnly ? s.slice(0, 10) : s.slice(0, 19).replace('T', ' ');
}

function allMidnight(rows, col) {
  for (const r of rows) {
    const v = r[col];
    if (v === null || v === undefined) continue;
    const d = (v instanceof Date) ? v : new Date(typeof v === 'bigint' ? Number(v) : v);
    if (d.getTime() % 86400000 !== 0) return false;
  }
  return true;
}

function floatColumns(schema) {
  const out = {};
  for (const f of (schema && schema.fields) || []) {
    const t = String(f.type || '');
    if (/^Float/i.test(t)) out[f.name] = /32/.test(t) ? 'f32' : 'f64';
  }
  return out;
}

function temporalColumns(schema) {
  const out = {};
  for (const f of (schema && schema.fields) || []) {
    const t = String(f.type || '');
    if (/Date|Timestamp/i.test(t)) out[f.name] = true;
  }
  return out;
}

function toPlain(rows, temporal, floats) {
  /* Decide date-vs-datetime once per column, as pandas does. */
  const dateOnly = {};
  for (const k in (temporal || {})) dateOnly[k] = allMidnight(rows, k);
  return rows.map((r) => {
    const o = {};
    for (const k in r) {
      let v = r[k];
      if (temporal && temporal[k] && v !== null && v !== undefined
          && !(v instanceof Date)) {
        v = new Date(typeof v === 'bigint' ? Number(v) : v);
      }
      o[k] = cellToText(v, dateOnly[k], floats && floats[k]);
    }
    return o;
  });
}

/* A CSV rendering of the decoded rows, so the artifact's download control hands
 * the reader the same values the page is showing. */
function toCsv(cols, rows) {
  const esc = (s) => (/[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s);
  const lines = [cols.map(esc).join(',')];
  for (const r of rows) lines.push(cols.map((c) => esc(r[c] === undefined ? '' : r[c])).join(','));
  return lines.join('\n') + '\n';
}

const tables = {};
const temporals = {};
const floats = {};
let ready = null;

function reply(type, m, dt) {
  const cols = dt ? dt.columnNames() : [];
  const rows = dt ? toPlain(dt.objects(), temporals[m.name], floats[m.name]) : [];
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
      floats[m.name] = floatColumns(at.schema);
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
