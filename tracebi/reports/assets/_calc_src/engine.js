/* engine.js — a calc plan run over one decoded slice.
 *
 * The plan's meaning is fixed in Python: the module docstring of
 * tracebi/reports/calc_plan.py is the schema, and execute_plan runs a plan
 * through DataModel.execute (DuckDB). This file is the port, proved by the
 * parity fixtures in tests/fixtures/calc_parity/. It implements exactly the
 * plan vocabulary, in the docstring's order, and refuses anything else by
 * name: a step it guessed at would put a number on the page that no query
 * produced.
 *
 * Floats are summed with Neumaier's compensated sum, so the order the rows
 * arrive in barely moves the last bits. DuckDB sums in its own order, so the
 * two can still differ in the last bit or two; the fingerprint rounds to nine
 * significant digits, which absorbs that. What rounding cannot absorb is a
 * near-tie: rank and order_by compare exact floats, so two groups whose sums
 * differ only in the last bits may order differently here and on the server.
 * CALC_NOTICE.md records that residual risk.
 */

import { cmpStr } from "./parquet.js";

/* ── Values ──────────────────────────────────────────────────────────────── */

/* The total order the plan sorts by: numbers, then booleans (false first),
 * then strings by code point. Nulls are handled by each caller, because
 * where they go depends on the step (always last in a sort key). */
function rankOf(v) {
  return typeof v === "number" ? 0 : typeof v === "boolean" ? 1 : 2;
}

function cmpValues(a, b) {
  const ra = rankOf(a), rb = rankOf(b);
  if (ra !== rb) return ra - rb;
  if (ra === 2) return cmpStr(a, b);
  return a < b ? -1 : a > b ? 1 : 0;
}

/* A sort key comparison with nulls last whichever way the key runs. */
function cmpKey(a, b, desc) {
  if (a === null) return b === null ? 0 : 1;
  if (b === null) return -1;
  const c = cmpValues(a, b);
  return desc ? -c : c;
}

/* A filter value as the column's type sees it. SQL casts a literal to the
 * column it is compared with, so a number column read against "2024" (as a
 * selection carried in a URL would spell it) compares as 2024. */
function coerce(kind, v) {
  if ((kind === "number") && typeof v === "string" && v.trim() !== "" && !isNaN(Number(v))) {
    return Number(v);
  }
  return v;
}

/* Comparable when both sides are the same kind of value; otherwise undefined,
 * and every comparison against it is false. */
function compare(cell, value) {
  if (typeof cell !== typeof value || value === null) return undefined;
  return cmpValues(cell, value);
}

/* One FILTER / having leaf against one cell. *sql* picks the null rules:
 * SQL (filters) drops a null cell under every op but is_null; pandas
 * (having) keeps it under ne and not_in. */
function test(op, cell, value, sql) {
  if (op === "is_null") return cell === null;
  if (op === "not_null") return cell !== null;
  if (cell === null) return !sql && (op === "ne" || op === "not_in");
  let c;
  switch (op) {
    case "eq": return compare(cell, value) === 0;
    case "ne": return compare(cell, value) !== 0;
    case "gt": c = compare(cell, value); return c !== undefined && c > 0;
    case "gte": c = compare(cell, value); return c !== undefined && c >= 0;
    case "lt": c = compare(cell, value); return c !== undefined && c < 0;
    case "lte": c = compare(cell, value); return c !== undefined && c <= 0;
    case "between": {
      const lo = compare(cell, value[0]), hi = compare(cell, value[1]);
      return lo !== undefined && hi !== undefined && lo >= 0 && hi <= 0;
    }
    case "in": {
      for (const v of value) if (compare(cell, v) === 0) return true;
      return false;
    }
    case "not_in": {
      // SQL: x NOT IN (..., NULL) is never true. pandas' ~isin has no such rule.
      for (const v of value) {
        if (v === null) { if (sql) return false; continue; }
        if (compare(cell, v) === 0) return false;
      }
      return true;
    }
    case "contains":
      return typeof cell === "string" && typeof value === "string" && cell.indexOf(value) !== -1;
    default:
      throw new Error(`unknown filter op '${op}'`);
  }
}

/* ── Columns ─────────────────────────────────────────────────────────────── */

function column(table, name) {
  const data = table.data[name];
  if (!data) throw new Error(`the slice does not carry '${name}'`);
  const kind = table.kinds[name];
  return { name, kind, data, dict: table.dict[name] };
}

/* Row i of a column as a plain JS value (null for a null). */
function cellAt(col, i) {
  const v = col.data[i];
  if (col.kind === "number") return v !== v ? null : v;
  if (col.kind === "boolean") return v !== v ? null : v === 1;
  return v < 0 ? null : col.dict[v];
}

/* ── Filters ─────────────────────────────────────────────────────────────── */

/* A FILTER tree as a row predicate, or null for "every row". A string,
 * datetime or boolean leaf is decided once per distinct value (the
 * dictionary) and looked up per row; only a number leaf tests every row. */
function compileFilter(table, tree) {
  if (!tree) return null;
  if (tree.and || tree.or) {
    const parts = (tree.and || tree.or).map((t) => compileFilter(table, t));
    if (tree.and) {
      const live = parts.filter(Boolean);
      return (i) => { for (const p of live) if (!p(i)) return false; return true; };
    }
    if (parts.some((p) => p === null)) return null;
    return (i) => { for (const p of parts) if (p(i)) return true; return false; };
  }
  const { column: name, op } = tree;
  const col = column(table, name);
  let value = tree.value;
  if (op === "in" || op === "not_in" || op === "between") {
    if (!Array.isArray(value)) throw new Error(`filter '${op}' on '${name}' needs a list`);
    value = value.map((v) => coerce(col.kind, v));
  } else {
    value = coerce(col.kind, value);
  }
  if (col.kind === "string" || col.kind === "datetime") {
    const ok = new Uint8Array(col.dict.length + 1);
    ok[0] = test(op, null, value, true) ? 1 : 0;
    for (let c = 0; c < col.dict.length; c++) ok[c + 1] = test(op, col.dict[c], value, true) ? 1 : 0;
    const codes = col.data;
    return (i) => ok[codes[i] + 1] === 1;
  }
  if (col.kind === "boolean") {
    const ok = [test(op, null, value, true), test(op, false, value, true), test(op, true, value, true)];
    const d = col.data;
    return (i) => { const v = d[i]; return ok[v !== v ? 0 : v + 1]; };
  }
  const d = col.data;
  return (i) => { const v = d[i]; return test(op, v !== v ? null : v, value, true); };
}

/* ── Expressions ─────────────────────────────────────────────────────────── */

/* A row EXPR as a function of the row index: a number, or undefined for a
 * null. A null operand gives null; division is IEEE (x / 0 is ±Infinity,
 * 0 / 0 is NaN), exactly the docstring's row rules. */
function compileRowExpr(table, expr) {
  if ("num" in expr) { const n = expr.num; return () => n; }
  if ("col" in expr) {
    const col = column(table, expr.col);
    if (col.kind !== "number" && col.kind !== "boolean") {
      throw new Error(`expression reads '${expr.col}', which is not a number column`);
    }
    const d = col.data;
    return (i) => { const v = d[i]; return v !== v ? undefined : v; };
  }
  if ("ref" in expr) throw new Error(`a row expression cannot read the result column '${expr.ref}'`);
  const args = (expr.args || []).map((a) => compileRowExpr(table, a));
  return arith(expr.op, args, false);
}

/* A combines EXPR over one result row: refs read aggregated columns, and a
 * division by zero is null (the docstring's rule for measure expressions). */
function compileRefExpr(res, expr) {
  if ("num" in expr) { const n = expr.num; return () => n; }
  if ("ref" in expr) {
    const values = res[expr.ref];
    if (!values) throw new Error(`combine reads '${expr.ref}', which is not a result column`);
    return (g) => { const v = values[g]; return v === null || v !== v ? undefined : v; };
  }
  if ("col" in expr) throw new Error(`a measure expression cannot read the row column '${expr.col}'`);
  const args = (expr.args || []).map((a) => compileRefExpr(res, a));
  return arith(expr.op, args, true);
}

function arith(op, args, zeroIsNull) {
  const [f, g] = args;
  switch (op) {
    case "+": return (i) => { const a = f(i); if (a === undefined) return a; const b = g(i); return b === undefined ? b : a + b; };
    case "-": return (i) => { const a = f(i); if (a === undefined) return a; const b = g(i); return b === undefined ? b : a - b; };
    case "*": return (i) => { const a = f(i); if (a === undefined) return a; const b = g(i); return b === undefined ? b : a * b; };
    case "/": return (i) => {
      const a = f(i); if (a === undefined) return a;
      const b = g(i); if (b === undefined) return b;
      return zeroIsNull && b === 0 ? undefined : a / b;
    };
    case "neg": return (i) => { const a = f(i); return a === undefined ? a : -a; };
    default: throw new Error(`unknown expression op '${op}'`);
  }
}

/* ── Grouping ────────────────────────────────────────────────────────────── */

/* Each passing row's group, numbered in first-seen order, and the first row
 * of each group (where the group columns' values are read from). */
function group(table, groupBy, idx) {
  const n = idx.length;
  const gid = new Int32Array(n);
  if (!groupBy.length) return { gid, count: 1, first: new Int32Array([-1]) };
  // Every group column as small integer ids (0 is null), then one key per row.
  const ids = [];
  const cards = [];
  for (const name of groupBy) {
    const col = column(table, name);
    const d = col.data;
    const out = new Int32Array(n);
    if (col.kind === "string" || col.kind === "datetime") {
      for (let k = 0; k < n; k++) out[k] = d[idx[k]] + 1;
      cards.push(col.dict.length + 1);
    } else if (col.kind === "boolean") {
      for (let k = 0; k < n; k++) { const v = d[idx[k]]; out[k] = v !== v ? 0 : v + 1; }
      cards.push(3);
    } else {
      const seen = new Map();
      for (let k = 0; k < n; k++) {
        const v = d[idx[k]];
        if (v !== v) { out[k] = 0; continue; }
        let id = seen.get(v);
        if (id === undefined) { id = seen.size + 1; seen.set(v, id); }
        out[k] = id;
      }
      cards.push(seen.size + 1);
    }
    ids.push(out);
  }
  const space = cards.reduce((a, b) => a * b, 1);
  const firstRows = [];
  if (space <= 1 << 22) {
    // A dense key space: a lookup table beats a hash map by a wide margin.
    // Keys are built a column at a time: tight loops over typed arrays.
    const keys = ids[0];
    for (let j = 1; j < ids.length; j++) {
      const card = cards[j], id = ids[j];
      for (let k = 0; k < n; k++) keys[k] = keys[k] * card + id[k];
    }
    const slot = new Int32Array(space).fill(-1);
    for (let k = 0; k < n; k++) {
      const key = keys[k];
      let g = slot[key];
      if (g < 0) { g = slot[key] = firstRows.length; firstRows.push(idx[k]); }
      gid[k] = g;
    }
  } else {
    const slot = new Map();
    const exact = space <= Number.MAX_SAFE_INTEGER;
    for (let k = 0; k < n; k++) {
      let key = exact ? 0 : "";
      for (let j = 0; j < ids.length; j++) {
        key = exact ? key * cards[j] + ids[j][k] : key + ids[j][k] + ",";
      }
      let g = slot.get(key);
      if (g === undefined) { g = firstRows.length; slot.set(key, g); firstRows.push(idx[k]); }
      gid[k] = g;
    }
  }
  return { gid, count: firstRows.length, first: Int32Array.from(firstRows) };
}

/* ── Aggregates ──────────────────────────────────────────────────────────── */

/* Neumaier's compensated sum, one running total per group. */
function sums(count) {
  return { s: new Float64Array(count), c: new Float64Array(count), n: new Float64Array(count) };
}
function add(acc, g, x) {
  const s = acc.s[g], t = s + x;
  if (Math.abs(s) >= Math.abs(x)) acc.c[g] += (s - t) + x;
  else acc.c[g] += (x - t) + s;
  acc.s[g] = t;
  acc.n[g] += 1;
}
function total(acc, g) {
  const s = acc.s[g];
  // Past an infinity the compensation is NaN and means nothing.
  return Number.isFinite(s) ? s + acc.c[g] : s;
}

function aggregate(table, agg, idx, grouping) {
  const { gid, count } = grouping;
  const func = agg.func;
  const where = compileFilter(table, agg.where || null);
  const src = agg.source || {};
  const col = "col" in src ? column(table, src.col) : null;
  const coded = col && (col.kind === "string" || col.kind === "datetime");
  // One reader per row, giving a number (a code, for a string column), or
  // undefined for a null. NaN reaches only sum and the order statistics,
  // which skip it as null; count counts it, as SQL counts a NaN.
  let read;
  if (col) {
    const d = col.data;
    read = coded ? (i) => { const v = d[i]; return v < 0 ? undefined : v; }
      : (i) => { const v = d[i]; return v !== v ? undefined : v; };
  } else {
    read = compileRowExpr(table, src);
  }
  const n = idx.length;
  const out = new Array(count);
  // A number source's values for the passing rows, NaN for a null or a row
  // the aggregate's own filter drops: one typed array the loops below read.
  const gather = () => {
    const vals = new Float64Array(n);
    if (col && !where) {
      const d = col.data;
      for (let k = 0; k < n; k++) vals[k] = d[idx[k]];
      return vals;
    }
    for (let k = 0; k < n; k++) {
      const i = idx[k];
      const v = where && !where(i) ? undefined : read(i);
      vals[k] = v === undefined ? NaN : v;
    }
    return vals;
  };

  if (func === "sum" || func === "sum_counts") {
    if (coded) throw new Error(`cannot sum the string column '${src.col}'`);
    const acc = sums(count);
    const vals = gather();
    const s = acc.s, c = acc.c, m = acc.n;
    for (let k = 0; k < n; k++) {
      const v = vals[k];
      if (v !== v) continue;
      // add(), inlined: this loop is the engine's hot path.
      const g = gid[k], t0 = s[g], t = t0 + v;
      if (Math.abs(t0) >= Math.abs(v)) c[g] += (t0 - t) + v;
      else c[g] += (v - t) + t0;
      s[g] = t;
      m[g] += 1;
    }
    for (let g = 0; g < count; g++) {
      out[g] = acc.n[g] ? total(acc, g) : func === "sum_counts" ? 0 : null;
    }
    return out;
  }
  if (func === "count") {
    const c = new Float64Array(count);
    for (let k = 0; k < n; k++) {
      const i = idx[k];
      if (where && !where(i)) continue;
      if (read(i) !== undefined) c[gid[k]] += 1;
    }
    for (let g = 0; g < count; g++) out[g] = c[g];
    return out;
  }
  if (func === "min" || func === "max") {
    const best = new Float64Array(count).fill(NaN);
    const isMax = func === "max";
    for (let k = 0; k < n; k++) {
      const i = idx[k];
      if (where && !where(i)) continue;
      const v = read(i);
      if (v === undefined || v !== v) continue;
      const g = gid[k], b = best[g];
      if (b !== b || (isMax ? v > b : v < b)) best[g] = v;
    }
    for (let g = 0; g < count; g++) {
      const b = best[g];
      out[g] = b !== b ? null : coded ? col.dict[b] : col && col.kind === "boolean" ? b === 1 : b;
    }
    return out;
  }
  if (func === "nunique") {
    const sets = new Array(count);
    for (let k = 0; k < n; k++) {
      const i = idx[k];
      if (where && !where(i)) continue;
      const v = read(i);
      if (v === undefined) continue;
      const g = gid[k];
      (sets[g] || (sets[g] = new Set())).add(v);
    }
    for (let g = 0; g < count; g++) out[g] = sets[g] ? sets[g].size : 0;
    return out;
  }
  if (func === "quantile") {
    if (coded) throw new Error(`cannot take a quantile of the string column '${src.col}'`);
    const q = agg.q;
    if (typeof q !== "number" || !(q >= 0 && q <= 1)) {
      throw new Error(`quantile '${agg.name}' needs q in [0, 1]`);
    }
    // Two passes: count each group's values, then lay them out contiguously
    // so each group sorts as one typed subarray (a numeric sort, no boxing).
    const vals = gather();
    const sizes = new Int32Array(count + 1);
    for (let k = 0; k < n; k++) if (vals[k] === vals[k]) sizes[gid[k] + 1] += 1;
    for (let g = 0; g < count; g++) sizes[g + 1] += sizes[g];
    const fill = sizes.slice(0, count);
    const laid = new Float64Array(sizes[count]);
    for (let k = 0; k < n; k++) if (vals[k] === vals[k]) laid[fill[gid[k]]++] = vals[k];
    for (let g = 0; g < count; g++) {
      const xs = laid.subarray(sizes[g], sizes[g + 1]).sort();
      const m = xs.length;
      if (!m) { out[g] = null; continue; }
      const h = (m - 1) * q, lo = Math.floor(h);
      out[g] = h === lo ? xs[lo] : xs[lo] + (h - lo) * (xs[lo + 1] - xs[lo]);
    }
    return out;
  }
  throw new Error(`unknown aggregate func '${func}'`);
}

/* ── Post-aggregate steps ────────────────────────────────────────────────── */

function num(v) { return v === null || v !== v ? null : v; }

/* ranks and runnings share one order: partition_by ascending, then base
 * descending, then every other group column ascending, nulls last in each.
 * The server numbers each partition with a pandas groupby, which leaves out
 * a row whose partition key is null, so such a row gets a null rank or
 * running (and a having on the rank then drops it). */
function windowOrder(res, groupBy, count, spec) {
  const keys = [];
  for (const p of spec.partition_by) keys.push([res[p], false]);
  keys.push([res[spec.base], true]);
  for (const g of groupBy) if (spec.partition_by.indexOf(g) === -1) keys.push([res[g], false]);
  const order = Array.from({ length: count }, (_, g) => g);
  order.sort((a, b) => {
    for (const [values, desc] of keys) {
      const c = cmpKey(values[a], values[b], desc);
      if (c) return c;
    }
    return 0;
  });
  return order;
}

function samePartition(res, parts, a, b) {
  for (const p of parts) {
    const x = res[p][a], y = res[p][b];
    if (x === null || y === null ? x !== y : cmpValues(x, y) !== 0) return false;
  }
  return true;
}

function windowed(res, groupBy, count, spec, running) {
  if (!res[spec.base]) throw new Error(`'${spec.name}' reads '${spec.base}', which is not a result column`);
  for (const p of spec.partition_by) {
    if (!res[p]) throw new Error(`'${spec.name}' partitions by '${p}', which is not a group column`);
  }
  const order = windowOrder(res, groupBy, count, spec);
  const out = new Array(count);
  const base = res[spec.base];
  let pos = 0;
  let acc = sums(1);
  const parts = spec.partition_by.map((p) => res[p]);
  for (let k = 0; k < order.length; k++) {
    const g = order[k];
    if (parts.some((values) => values[g] === null)) { out[g] = null; continue; }
    if (k === 0 || !samePartition(res, spec.partition_by, order[k - 1], g)) { pos = 0; acc = sums(1); }
    pos += 1;
    if (!running) { out[g] = pos; continue; }
    const v = num(base[g]);
    if (v === null) { out[g] = null; continue; }
    add(acc, 0, v);
    out[g] = total(acc, 0);
  }
  return out;
}

/* ── The plan ────────────────────────────────────────────────────────────── */

/**
 * Run one calc plan over its fact's decoded slice, under selection *leaves*
 * already composed by select.js. Returns the result columns and plain row
 * objects keyed by column, in the plan's order; numbers are raw (the runtime
 * formats them, the fingerprint rounds them).
 *
 * @param {object} table a table from decodeParquet, with kinds by column
 * @param {object} plan a version-1 calc plan (see calc_plan.py)
 * @param {Array<object>} leaves FILTER leaves from the applied selection
 * @returns {{cols: string[], rows: Array<Object<string, *>>}}
 */
export function runPlan(table, plan, leaves) {
  // 1. Filter: the binding's own filters AND the applied selection.
  const tree = { and: [plan.filters, ...leaves].filter(Boolean) };
  const keep = compileFilter(table, tree.and.length ? tree : null);
  let idx;
  if (keep) {
    const hits = new Int32Array(table.rows);
    let m = 0;
    for (let i = 0; i < table.rows; i++) if (keep(i)) hits[m++] = i;
    idx = hits.subarray(0, m);
  } else {
    idx = new Int32Array(table.rows);
    for (let i = 0; i < table.rows; i++) idx[i] = i;
  }

  // 2. Group, 3. aggregate.
  const groupBy = plan.group_by || [];
  const grouping = group(table, groupBy, idx);
  const count = grouping.count;
  const res = {};
  for (const name of groupBy) {
    const col = column(table, name);
    res[name] = Array.from(grouping.first, (i) => cellAt(col, i));
  }
  for (const agg of plan.aggregates || []) res[agg.name] = aggregate(table, agg, idx, grouping);

  // 4. means, 5. ratios: a quotient of two aggregated columns, null over zero.
  const quotient = (name, a, b) => {
    const x = res[a], y = res[b];
    if (!x || !y) throw new Error(`'${name}' reads '${x ? b : a}', which is not a result column`);
    res[name] = x.map((v, g) => {
      const p = num(v), q = num(y[g]);
      return p === null || q === null || q === 0 ? null : p / q;
    });
  };
  for (const m of plan.means || []) quotient(m.name, m.sum, m.count);
  for (const r of plan.ratios || []) quotient(r.name, r.num, r.den);

  // 6. shares: each row's base over the base summed across every result row.
  for (const s of plan.shares || []) {
    const base = res[s.base];
    if (!base) throw new Error(`'${s.name}' reads '${s.base}', which is not a result column`);
    const acc = sums(1);
    for (const v of base) if (num(v) !== null) add(acc, 0, v);
    const t = acc.n[0] ? total(acc, 0) : null;
    res[s.name] = base.map((v) => (num(v) === null || t === null || t === 0 ? null : v / t));
  }

  // 7. combines, in order, so a later one may read an earlier one.
  for (const c of plan.combines || []) {
    const f = compileRefExpr(res, c.expr);
    const out = new Array(count);
    for (let g = 0; g < count; g++) { const v = f(g); out[g] = v === undefined || v !== v ? null : v; }
    res[c.name] = out;
  }

  // 8. ranks, then runnings.
  for (const r of plan.ranks || []) res[r.name] = windowed(res, groupBy, count, r, false);
  for (const r of plan.runnings || []) res[r.name] = windowed(res, groupBy, count, r, true);

  // 9. having (pandas' null rules).
  let rows = Array.from({ length: count }, (_, g) => g);
  for (const h of plan.having || []) {
    const values = res[h.column];
    if (!values) throw new Error(`having reads '${h.column}', which is not a result column`);
    rows = rows.filter((g) => test(h.op, values[g] === undefined ? null : values[g], h.value, false));
  }

  // 10. order_by: a stable sort, nulls last in each key.
  const keys = (plan.order_by || []).map((o) => {
    if (!res[o.column]) throw new Error(`order_by reads '${o.column}', which is not a result column`);
    return [res[o.column], !!o.desc];
  });
  if (keys.length) {
    rows.sort((a, b) => {
      for (const [values, desc] of keys) {
        const c = cmpKey(values[a], values[b], desc);
        if (c) return c;
      }
      return 0;
    });
  }

  // 11. limit, 12. columns.
  if (plan.limit !== null && plan.limit !== undefined) rows = rows.slice(0, plan.limit);
  const cols = plan.columns.slice();
  for (const c of cols) if (!res[c]) throw new Error(`the plan lists '${c}', which no step computed`);
  return {
    cols,
    rows: rows.map((g) => {
      const o = {};
      for (const c of cols) o[c] = res[c][g];
      return o;
    }),
  };
}

/**
 * The distinct non-null values of one column among the rows a predicate
 * keeps, and the rest, each in the plan's sort order.
 *
 * @param {object} table a decoded table
 * @param {string} name the column
 * @param {Array<object>} leaves FILTER leaves that decide "present"
 * @returns {{present: Array<*>, rest: Array<*>}}
 */
export function columnDomains(table, name, leaves) {
  const col = column(table, name);
  const keep = compileFilter(table, leaves.length ? { and: leaves } : null);
  const all = new Map();
  const here = new Set();
  for (let i = 0; i < table.rows; i++) {
    const v = cellAt(col, i);
    if (v === null) continue;
    if (!all.has(v)) all.set(v, true);
    if (!keep || keep(i)) here.add(v);
  }
  const values = Array.from(all.keys()).sort(cmpValues);
  return {
    present: values.filter((v) => here.has(v)),
    rest: values.filter((v) => !here.has(v)),
  };
}

export { cmpValues };
