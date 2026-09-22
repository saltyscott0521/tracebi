/* selection_eval.js — the worker port of simple aggregations and ratio.
 *
 * Python (tracebi/reports/selection_eval.py) is the source of truth. This
 * file is the port: same filters, same group, same ratio-of-totals. share,
 * rank, running, period_end, and the time-intelligence kinds arrive as
 * plan.offline === false and are refused — the page keeps the authored view.
 * No DOM. ES5. Loaded only into artifacts that embed a selection grain.
 */
var tracebiSelectionEval = function (rows, plan, selectionFilters) {
  if (!plan || plan.offline === false) {
    return { refused: (plan && plan.reason) || "server" };
  }

  function isNull(v) {
    return v === null || v === undefined || v === "";
  }
  function same(a, b) {
    if (isNull(a) || isNull(b)) return false;
    if (a === b) return true;
    var na = Number(a), nb = Number(b);
    if (String(a) !== "" && String(b) !== "" && isFinite(na) && isFinite(nb) && na === nb) {
      return true;
    }
    return String(a) === String(b);
  }
  function cmp(a, b) {
    if (isNull(a)) return 1;
    var na = Number(a), nb = Number(b);
    if (String(a) !== "" && String(b) !== "" && isFinite(na) && isFinite(nb)) {
      return (na > nb) - (na < nb);
    }
    var sa = String(a), sb = String(b);
    return (sa > sb) - (sa < sb);
  }
  function ordered(cell, value, op) {
    if (isNull(cell) || isNull(value)) return false;
    var c = cmp(cell, value);
    if (op === "gt") return c > 0;
    if (op === "gte") return c >= 0;
    if (op === "lt") return c < 0;
    return c <= 0;
  }
  function mask(cell, raw) {
    var i, op, val, keys;
    if (raw && Object.prototype.toString.call(raw) === "[object Array]") {
      for (i = 0; i < raw.length; i++) if (same(cell, raw[i])) return true;
      return false;
    }
    if (raw && Object.prototype.toString.call(raw) === "[object Object]") {
      keys = [];
      for (op in raw) if (raw.hasOwnProperty(op)) keys.push(op);
      if (keys.length !== 1) return false;
      op = keys[0];
      val = raw[op];
      if (op === "eq") return same(cell, val);
      if (op === "ne") return !isNull(cell) && !same(cell, val);
      if (op === "in") return mask(cell, val || []);
      if (op === "not_in") return !isNull(cell) && !mask(cell, val || []);
      if (op === "is_null") return isNull(cell);
      if (op === "not_null") return !isNull(cell);
      if (op === "contains") return !isNull(cell) && String(cell).indexOf(String(val)) !== -1;
      if (op === "between") return cmp(cell, val[0]) >= 0 && cmp(cell, val[1]) <= 0 && !isNull(cell);
      if (op === "gt" || op === "gte" || op === "lt" || op === "lte") return ordered(cell, val, op);
      return false;
    }
    return same(cell, raw);
  }

  var filters = {}, k, base = plan.binding_filters || {}, sel = selectionFilters || {};
  for (k in base) if (base.hasOwnProperty(k)) filters[k] = base[k];
  for (k in sel) if (sel.hasOwnProperty(k)) filters[k] = sel[k];

  var filtered = [], i, row, ok;
  for (i = 0; i < rows.length; i++) {
    row = rows[i];
    ok = true;
    for (k in filters) {
      if (!filters.hasOwnProperty(k)) continue;
      if (!mask(row[k], filters[k])) { ok = false; break; }
    }
    if (ok) filtered.push(row);
  }

  var dims = plan.dimensions || [];
  var aggs = plan.aggs || [];
  var ratios = plan.ratios || [];
  var groups = [], index = {}, gkey, gi, g, a, src, vals, n, s, u, seen, key, out = [];

  function reduce(vals, func) {
    var present = [], nums = [], j, v, n, set = {}, count = 0, sum = 0, mn = null, mx = null;
    for (j = 0; j < vals.length; j++) {
      if (!isNull(vals[j])) present.push(vals[j]);
    }
    if (func === "count") return present.length;
    if (func === "nunique") {
      for (j = 0; j < present.length; j++) {
        key = String(present[j]);
        if (!set[key]) { set[key] = true; count++; }
      }
      return count;
    }
    for (j = 0; j < present.length; j++) {
      n = Number(present[j]);
      if (isFinite(n)) nums.push(n);
    }
    if (!nums.length) return null;
    if (func === "sum" || func === "mean") {
      for (j = 0; j < nums.length; j++) sum += nums[j];
      return func === "mean" ? sum / nums.length : sum;
    }
    if (func === "min" || func === "max") {
      for (j = 0; j < nums.length; j++) {
        if (mn === null || nums[j] < mn) mn = nums[j];
        if (mx === null || nums[j] > mx) mx = nums[j];
      }
      return func === "min" ? mn : mx;
    }
    return null;
  }

  if (!dims.length) {
    g = {};
    for (a = 0; a < aggs.length; a++) {
      vals = [];
      src = aggs[a].source;
      for (i = 0; i < filtered.length; i++) vals.push(filtered[i][src]);
      g[aggs[a].name] = reduce(vals, aggs[a].func);
    }
    out = [g];
  } else {
    for (i = 0; i < filtered.length; i++) {
      row = filtered[i];
      gkey = [];
      for (gi = 0; gi < dims.length; gi++) {
        gkey.push(isNull(row[dims[gi]]) ? "\u0000" : String(row[dims[gi]]));
      }
      key = gkey.join("\u0001");
      if (!index.hasOwnProperty(key)) {
        g = { _rows: [] };
        for (gi = 0; gi < dims.length; gi++) g[dims[gi]] = row[dims[gi]];
        index[key] = g;
        groups.push(g);
      }
      index[key]._rows.push(row);
    }
    groups.sort(function (p, q) {
      var c, d;
      for (d = 0; d < dims.length; d++) {
        c = cmp(p[dims[d]], q[dims[d]]);
        if (c) return c;
      }
      return 0;
    });
    for (gi = 0; gi < groups.length; gi++) {
      g = {};
      for (d = 0; d < dims.length; d++) g[dims[d]] = groups[gi][dims[d]];
      for (a = 0; a < aggs.length; a++) {
        vals = [];
        src = aggs[a].source;
        for (i = 0; i < groups[gi]._rows.length; i++) vals.push(groups[gi]._rows[i][src]);
        g[aggs[a].name] = reduce(vals, aggs[a].func);
      }
      out.push(g);
    }
  }

  for (a = 0; a < ratios.length; a++) {
    for (i = 0; i < out.length; i++) {
      n = out[i][ratios[a].num];
      s = out[i][ratios[a].den];
      out[i][ratios[a].name] = (s === 0 || s === null || isNull(n) || isNull(s)) ? null : n / s;
    }
  }

  var order = (plan.order_by || []).slice();
  var named = {}, c;
  for (i = 0; i < order.length; i++) named[order[i].column] = true;
  var tieCols = dims.slice();
  if (out.length) {
    for (k in out[0]) if (out[0].hasOwnProperty(k) && tieCols.indexOf(k) === -1) tieCols.push(k);
  }
  for (i = 0; i < tieCols.length; i++) {
    if (!named[tieCols[i]]) {
      order.push({ column: tieCols[i], desc: false });
      named[tieCols[i]] = true;
    }
  }
  if (order.length && out.length) {
    out = out.map(function (v, idx) { return { v: v, i: idx }; });
    out.sort(function (p, q) {
      var t, col, desc, c2;
      for (t = 0; t < order.length; t++) {
        col = order[t].column;
        desc = !!order[t].desc;
        if (isNull(p.v[col]) && isNull(q.v[col])) c2 = 0;
        else if (isNull(p.v[col])) c2 = 1;
        else if (isNull(q.v[col])) c2 = -1;
        else c2 = cmp(p.v[col], q.v[col]);
        if (desc) c2 = -c2;
        if (c2) return c2;
      }
      return p.i - q.i;
    });
    out = out.map(function (x) { return x.v; });
  }
  if (plan.limit !== null && plan.limit !== undefined) {
    out = out.slice(0, plan.limit);
  }
  /* Drop the helper if a group object leaked it — groups are copied without _rows. */
  for (i = 0; i < out.length; i++) {
    if (out[i]._rows) delete out[i]._rows;
  }
  return { rows: out };
};
