/* select.js — the page's selection state composed onto a calc plan.
 *
 * A port of apply_selection in tracebi/reports/calc_plan.py, which is the
 * source of truth: one rule for every figure on the page (decision 4 of the
 * live-reports plan). A field applies when the plan's slice carries that
 * column, and it ANDs with the binding's own filters, so a selection can
 * narrow a figure and never widen one. A field the slice does not carry
 * leaves the figure untouched and is listed in unfiltered_by, so the page can
 * say so instead of showing a number that only looks filtered.
 */

/** The selection's range bounds, in the order a folded query lists them. */
export const RANGE_OPS = ["gt", "gte", "lt", "lte"];

/* A selection condition, checked; null when it selects nothing. A malformed
 * condition throws rather than being ignored: a figure that silently dropped
 * part of the reader's selection would show a number for a question nobody
 * asked. */
function condition(field, raw) {
  if (Array.isArray(raw)) return raw.length ? raw.slice() : null;
  if (raw && typeof raw === "object") {
    const keys = Object.keys(raw);
    if (keys.length && keys.every((k) => RANGE_OPS.indexOf(k) !== -1)) {
      const out = {};
      for (const op of RANGE_OPS) if (op in raw) out[op] = raw[op];
      return out;
    }
  }
  throw new Error(
    `selection '${field}' must be a list of values or a range ` +
    `{'gte'|'gt': v, 'lte'|'lt': v}, got ${JSON.stringify(raw)}`);
}

/* Python's sorted() over str keys: code point order, which differs from
 * JavaScript's UTF-16 sort only past the BMP. */
function byCodePoint(a, b) {
  const x = Array.from(a), y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const d = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (d) return d;
  }
  return x.length - y.length;
}

/**
 * The applied part of *selection* for a plan over *sliceColumns*.
 *
 * @param {string[]} sliceColumns every column of the fact's slice
 * @param {Object<string, Array|Object>|null} selection the page's state
 * @returns {{selection: Object<string, Array|Object>, unfiltered_by: string[]}}
 */
export function applySelection(sliceColumns, selection) {
  const applied = {};
  const unfiltered = [];
  const have = new Set(sliceColumns);
  const fields = Object.keys(selection || {}).sort(byCodePoint);
  for (const field of fields) {
    const cond = condition(field, selection[field]);
    if (cond === null) continue;
    if (have.has(field)) applied[field] = cond;
    else unfiltered.push(field);
  }
  return { selection: applied, unfiltered_by: unfiltered };
}

/**
 * An applied selection as FILTER leaves, one per value list or bound, the
 * same groups selection_filters builds on the server.
 *
 * @param {Object<string, Array|Object>} applied
 * @returns {Array<{column: string, op: string, value: *}>}
 */
export function selectionLeaves(applied) {
  const leaves = [];
  for (const field of Object.keys(applied)) {
    const cond = applied[field];
    if (Array.isArray(cond)) {
      leaves.push({ column: field, op: "in", value: cond });
    } else {
      for (const op of RANGE_OPS) {
        if (op in cond) leaves.push({ column: field, op, value: cond[op] });
      }
    }
  }
  return leaves;
}
