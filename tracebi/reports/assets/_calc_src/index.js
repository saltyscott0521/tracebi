/* index.js — window.tracebiCalc, the page engine's whole API.
 *
 * Message-free and synchronous: the runtime decodes each embedded slice once
 * (load), then runs a binding's calc plan under the page's selection state
 * whenever the selection changes (run), and asks for a control's options
 * (domains). The engine never sees a model, a DOM or the network; everything
 * it knows arrives in the plan and the slice, which is what lets the trace
 * record exactly what produced a recomputed number.
 */

import { decodeParquet } from "./parquet.js";
import { runPlan, columnDomains, cmpValues } from "./engine.js";
import { applySelection, selectionLeaves } from "./select.js";

/** The calc plan version this engine runs (calc_plan.PLAN_VERSION). */
const PLAN_VERSION = 1;

/* Decoded slices by fact name. */
const tables = {};

/**
 * Decode one slice block and keep it for the plans over its fact.
 *
 * @param {string} name the fact the block is the slice of (plan.fact)
 * @param {Uint8Array|ArrayBuffer} bytes the raw Parquet bytes: base64-decoded
 *   from the carrier's parquet_b64 and gunzipped when the build gzipped them
 * @returns {{columns: Array<{name: string, type: string, integer?: boolean}>, rows: number,
 *   data: Object<string, Float64Array|Int32Array>, dict: Object<string, string[]>}}
 */
function load(name, bytes) {
  const table = decodeParquet(bytes);
  table.kinds = {};
  for (const c of table.columns) table.kinds[c.name] = c.type;
  tables[name] = table;
  return table;
}

/**
 * Decode one Parquet block without keeping it: a binding's stamped block
 * that the build embedded as Parquet (large-detail pages). The runtime reads
 * its rows once and draws them as it draws a CSV block; no plan runs over it.
 *
 * @param {Uint8Array|ArrayBuffer} bytes the raw Parquet bytes
 * @returns the same columnar table load() returns
 */
function decode(bytes) {
  return decodeParquet(bytes);
}

/**
 * Run a binding's calc plan under the page's selection.
 *
 * A fixed plan comes back as ``{fixed: reason}``: the figure keeps its build
 * value. Anything the engine cannot run (an unknown plan version, a step or
 * column it does not know, no slice loaded for the fact) throws, and the
 * caller treats the figure as fixed with that message.
 *
 * @param {object} plan a version-1 calc plan
 * @param {Object<string, Array|Object>} [selection] ``{field: [values]}`` or
 *   ``{field: {gte|gt|lte|lt: v}}``
 * @returns {{cols: string[], rows: Array<Object<string, *>>,
 *   unfiltered_by: string[], selection: Object<string, Array|Object>}|{fixed: string}}
 */
function run(plan, selection) {
  if (plan && "fixed" in plan) return { fixed: plan.fixed };
  if (!plan || plan.version !== PLAN_VERSION) {
    throw new Error(`calc plan version ${plan && plan.version} is not one this engine runs ` +
                    `(${PLAN_VERSION})`);
  }
  const table = tables[plan.fact];
  if (!table) throw new Error(`no slice is loaded for fact '${plan.fact}'`);
  const applied = applySelection(plan.slice_columns, selection);
  const out = runPlan(table, plan, selectionLeaves(applied.selection));
  return { cols: out.cols, rows: out.rows, unfiltered_by: applied.unfiltered_by,
           selection: applied.selection };
}

/**
 * A control's options: the column's distinct non-null values present under
 * the selection, then the rest, each sorted (numbers, false before true,
 * strings by code point). The column's own condition does not narrow its own
 * options, so a multi-select keeps offering its other values as present.
 *
 * @param {string} fact the fact whose slice carries the column
 * @param {string} column a slice column
 * @param {Object<string, Array|Object>} [selection]
 * @returns {{present: Array<*>, rest: Array<*>}}
 */
function domains(fact, column, selection) {
  const table = tables[fact];
  if (!table) throw new Error(`no slice is loaded for fact '${fact}'`);
  const others = {};
  for (const k of Object.keys(selection || {})) if (k !== column) others[k] = selection[k];
  const applied = applySelection(table.columns.map((c) => c.name), others);
  return columnDomains(table, column, selectionLeaves(applied.selection));
}

/* The fingerprint's cell rule (canonical_cell in tracebi/model/dataset.py):
 * nine significant digits, ties away from zero, -0 as 0; nulls and NaN as
 * null; infinities as strings, since JSON has none. */
function cell(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") {
    if (v !== v) return null;
    if (v === Infinity) return "Infinity";
    if (v === -Infinity) return "-Infinity";
    return Number(v.toPrecision(9)) + 0;
  }
  return v;
}

function cellOrder(a, b) {
  if (a === null) return b === null ? 0 : 1;
  if (b === null) return -1;
  return cmpValues(a, b);
}

/**
 * A result as the fingerprint sees it (canonical_rows): every cell through
 * the cell rule, and with *totalOrder* the rows sorted by every column, left
 * to right (numbers, then booleans, then strings, then nulls).
 *
 * @param {{cols: string[], rows: Array<Object<string, *>>}} result from run()
 * @param {boolean} [totalOrder=true]
 * @returns {{cols: string[], rows: Array<Array<*>>}}
 */
function canonical(result, totalOrder) {
  const cols = result.cols.slice();
  const rows = result.rows.map((r) => cols.map((c) => cell(r[c])));
  if (totalOrder !== false) {
    rows.sort((a, b) => {
      for (let j = 0; j < a.length; j++) {
        const c = cellOrder(a[j], b[j]);
        if (c) return c;
      }
      return 0;
    });
  }
  return { cols, rows };
}

const api = { version: "1.1.0", planVersion: PLAN_VERSION, load, decode, run, domains, canonical };

if (typeof window !== "undefined") window.tracebiCalc = api;
if (typeof globalThis !== "undefined") globalThis.tracebiCalc = api;
