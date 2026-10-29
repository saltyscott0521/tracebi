/* tracebi.js — the dependency-free presentation runtime (architecture v2 §2.4).
 *
 * Stack position: after any charting library, before the data blocks and the
 * author's script.js; hydration runs at DOM-ready so a later inline script
 * can still register chart patches first. The one law: presentation NEVER
 * changes a number — figures draw only from the embedded fingerprinted bytes
 * ("tracebi-data-<name>" blocks), and values reach the DOM only through
 * textContent or ECharts. Strict CSP: no eval, no fetches, ES5 throughout.
 *
 * Public API (the only global): window.tracebi
 *   .data(name)                → row objects from the embedded block
 *   .fmt(value, mode)          → the ChartSpec._fmt port; mode "compact"
 *   .configureChart(id, patch) → deep-merge patch for that chart's option;
 *                                series data re-sourced from the stamped
 *                                bytes after merging (restyle, never re-source)
 *
 * Controls (data-tb-filter / data-tb-search / data-tb-download, tabs) obey
 * the same law: a figure's number is only ever a query result. A page built
 * with a slice (#tracebi-calc-plans, the default) is live: its filters, and
 * every other gesture (a chart mark, a table row, a range, the selection
 * bar; The interaction grammar, below), write
 * one selection state and tracebi-calc.js runs each binding's own query plan
 * over the embedded data under it, so every figure the selection reaches is
 * recomputed as a query result (The live page, below). A page built without
 * one ("embed": "none") has no data to recompute from: its filters subset
 * which stamped rows tables and charts display, and value figures keep their
 * stamped numbers (the view layer below). Search only ever narrows the rows
 * shown.
 *
 * Every hydration step is defensive: a missing block, empty rows, or absent
 * echarts skips that figure silently — the author's content still shows.
 */
(function (root) {
  "use strict";

  /* ── CSV parsing (the RFC-4180 parser: the artifact runtime parses the
   *    embedded triple, never a hardcoded copy) ───────────────────────── */

  function parseCsv(text) {
    var rows = [], row = [], field = "", inQ = false, i = 0, c;
    while (i < text.length) {
      c = text[i];
      if (inQ) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; } else { inQ = false; }
        } else { field += c; }
      } else if (c === '"') {
        inQ = true;
      } else if (c === ',') {
        row.push(field); field = "";
      } else if (c === '\n') {
        row.push(field); rows.push(row); row = []; field = "";
      } else if (c !== '\r') {
        field += c;
      }
      i++;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    var head = rows.shift() || [];
    var out = rows
      .filter(function (r) { return r.length === head.length; })
      .map(function (r) {
        var o = {};
        head.forEach(function (h, j) { o[h] = r[j]; });
        return o;
      });
    return { cols: head, rows: out };
  }

  function trim(s) { return String(s).replace(/^\s+|\s+$/g, ""); }

  function addClass(el, cls) {
    if ((" " + el.className + " ").indexOf(" " + cls + " ") === -1) {
      el.className = trim(el.className + " " + cls);
    }
  }

  function removeClass(el, cls) {
    el.className = trim((" " + el.className + " ").replace(" " + cls + " ", " "));
  }

  /* "a, b ,c" -> ["a", "b", "c"] for the comma-separated attributes. */
  function splitList(s) { return s.split(",").map(trim); }

  /* Parsed blocks by binding name; only successful parses are cached. */
  var _blocks = {};

  function readBlock(name) {
    if (_blocks[name]) return _blocks[name];
    if (typeof document === "undefined") return null;
    var el = document.getElementById("tracebi-data-" + name);
    if (!el) return null;
    var payload;
    try { payload = JSON.parse(el.textContent); } catch (e) { return null; }
    if (!payload || typeof payload.csv !== "string") return null;
    var parsed = parseCsv(payload.csv);
    parsed.csv = payload.csv; /* the raw string, kept for verbatim download */
    _blocks[name] = parsed;
    return parsed;
  }

  /* ── Data readiness ───────────────────────────────────────────────────────
   * On a CSV artifact every block is parseable the moment the page exists, so
   * an author's script.js can call tracebi.data() inline. A Parquet artifact
   * decodes its blocks at DOM-ready, and script.js runs BEFORE that — so a
   * bare data() call would see an empty table on one transport and full data on
   * the other. tracebi.ready(fn) runs fn once the data is loaded either way
   * (immediately, if it already is), so author code is written once and behaves
   * the same on both. */
  var _dataReady = false;
  var _readyQueue = [];

  function runReady() {
    var q = _readyQueue;
    _readyQueue = [];
    for (var i = 0; i < q.length; i++) {
      try { q[i](); } catch (e) { /* an author callback must not stop the rest */ }
    }
  }

  function ready(fn) {
    if (typeof fn !== "function") return;
    if (_dataReady) { try { fn(); } catch (e) {} return; }
    _readyQueue.push(fn);
  }

  /* Public accessor: returns COPIES of the cached rows, so author code
   * cannot mutate what hydration draws from. */
  function data(name) {
    var block = readBlock(name);
    if (!block) return [];
    return block.rows.map(function (r) {
      var o = {}, k;
      for (k in r) if (r.hasOwnProperty(k)) o[k] = r[k];
      return o;
    });
  }

  /* ── Number formatting — the JS port of ChartSpec._fmt ─────────────────
   * One implementation of "550.7B": byte-for-byte agreement with the Python
   * original (chart.py), so screen and print show the same string. Python's
   * f-string rounding is half-to-even on the exact double; toFixed rounds
   * ties away from zero, so exact ties are detected and rounded to even. */

  /* True only when v is EXACTLY half-way at <digits> decimals. A double's
   * fractional expansion terminates (odd/2^s has exactly s decimal digits,
   * the last a 5), so a genuine tie shows digit digits+1 == 5 then zeros —
   * while a value merely *near* a tie shows its true digits and is left to
   * toFixed, which rounds by the true value exactly as Python does. */
  function isTie(v, digits) {
    var a = Math.abs(v);
    if (a >= 1e15) return false;
    var s = a.toFixed(digits + 15);
    var frac = s.slice(s.indexOf(".") + 1);
    if (frac.charAt(digits) !== "5") return false;
    return /^0*$/.test(frac.slice(digits + 1));
  }

  /* Python-compatible fixed-point string: f"{v:.<digits>f}". toFixed rounds
   * exact ties away from zero; Python rounds them half-to-even. */
  function pyFixed(v, digits) {
    if (isTie(v, digits)) {
      var pow = Math.pow(10, digits);
      var t = v * pow; /* exact: the tie's scaled value is representable */
      if (Math.abs(t) < 4503599627370496) { /* 2^52 — .5 still representable */
        var fl = Math.floor(t);
        var r = (fl % 2 === 0) ? fl : fl + 1; /* half to even */
        return (r / pow).toFixed(digits);
      }
    }
    return v.toFixed(digits);
  }

  /* "1234567" → "1,234,567" (digits only, no sign, no decimals). */
  function groupDigits(s) {
    var out = "", n = 0, i;
    for (i = s.length - 1; i >= 0; i--) {
      out = s.charAt(i) + out;
      n++;
      if (n % 3 === 0 && i > 0) out = "," + out;
    }
    return out;
  }

  /* f"{v:,.<digits>f}" — fixed-point with thousands separators. */
  function fixedGrouped(v, digits) {
    var s = pyFixed(v, digits);
    if (s.indexOf("e") !== -1 || s.indexOf("E") !== -1) return s;
    var neg = s.charAt(0) === "-";
    if (neg) s = s.slice(1);
    var dot = s.indexOf(".");
    var ip = dot === -1 ? s : s.slice(0, dot);
    var fp = dot === -1 ? "" : s.slice(dot);
    return (neg ? "-" : "") + groupDigits(ip) + fp;
  }

  /* Python str.rstrip("0").rstrip(".") — only meaningful on dotted strings. */
  function trimZeros(s) {
    if (s.indexOf(".") === -1) return s;
    return s.replace(/0+$/, "").replace(/\.$/, "");
  }

  function fmt(v, mode) {
    if (v === null || v === undefined || v === "") return "";
    var n = (typeof v === "number") ? v : Number(v);
    if (typeof n !== "number" || !isFinite(n)) return String(v);
    if (mode === "compact") {
      /* Threshold and mantissa both use *rounded* values so unit boundaries
       * stay honest: 999,999.99 is "1M", never "1000K"; 999.999 is "1K". */
      var a2 = Math.abs(parseFloat(pyFixed(Math.abs(n), 2)));
      if (a2 >= 1000) {
        var steps = [[1e12, "T"], [1e9, "B"], [1e6, "M"], [1e3, "K"]];
        var up = { K: "M", M: "B", B: "T" };
        for (var i = 0; i < steps.length; i++) {
          var div = steps[i][0], unit = steps[i][1];
          if (a2 >= div) {
            var mant = pyFixed(n / div, 1);
            if (Math.abs(parseFloat(mant)) >= 1000 && unit !== "T") {
              div = div * 1000;
              unit = up[unit];
              mant = pyFixed(n / div, 1);
            }
            return trimZeros(mant) + unit;
          }
        }
      }
    }
    if (n % 1 === 0 && Math.abs(n) < 1e15) return fixedGrouped(n, 0);
    return trimZeros(fixedGrouped(n, 2));
  }

  /* Named formats — mirrors NAMED_NUMBER_FORMATS (report.py). Explicit author
   * intent only; "percent" multiplies by 100 and is never inferred here. */
  function applyNamedFormat(n, name) {
    if (name === "compact") return fmt(n, "compact");
    if (name === "comma") return fixedGrouped(n, 0);
    if (name === "decimal") return fixedGrouped(n, 2);
    /* The sign leads the symbol: -$1,234, never $-1,234. */
    if (name === "currency") return (n < 0 ? "-$" : "$") + fixedGrouped(Math.abs(n), 2);
    if (name === "currency0") return (n < 0 ? "-$" : "$") + fixedGrouped(Math.abs(n), 0);
    if (name === "currency_compact") return (n < 0 ? "-$" : "$") + fmt(Math.abs(n), "compact");
    if (name === "percent") return pyFixed(n * 100, 1) + "%";
    return null; /* unknown name — caller falls back to the raw value */
  }

  /* ── Derived table labels + formats — the derive.py port ─────────────── */

  /* "dim_branch.region" → "Region"; "market_value" → "Market value". */
  /* Business acronyms a label spells in capitals — derive.py _ACRONYMS. */
  var ACRONYMS = ["aov","api","arpu","arr","cac","cogs","cpa","cpc","cpm","ctr","ebitda","eur","fte","gbp","gmv","kpi","ltv","mau","mom","mrr","mtd","nps","qoq","qtd","roas","roi","sku","sla","usd","wau","dau","wow","yoy","ytd"];
  function humanise(column) {
    var name = String(column).split(".").pop();
    name = name.replace(/^(dim|fact)_/, "");
    name = trim(name.replace(/_/g, " "));
    if (!name) return String(column);
    name = name.split(" ").map(function (w) {
      return ACRONYMS.indexOf(w.toLowerCase()) !== -1 ? w.toUpperCase() : w;
    }).join(" ");
    return name.charAt(0).toUpperCase() + name.slice(1);
  }

  /* id/key/year columns address a row rather than measure one — no format. */
  function isIdentity(column) {
    /* the last dotted part: dim_date.year is a year, like derive.py */
    var name = String(column).toLowerCase().split(".").pop();
    if (name === "id" || name === "key" || name === "year") return true;
    return /(_id|_key|_year)$/.test(name);
  }

  var _SUFFIX_HINTS = ["_pct", "_percent", "_rate", "_ratio"]; /* → percent */

  /* The _FRACTION_BOUND guard, ported exactly: the percent hint stands only
   * when every non-null value is fraction-shaped (|v| <= 1.5). A presentation
   * default must never change the number it presents. */
  var _FRACTION_BOUND = 1.5;

  function toNum(v) {
    if (v === null || v === undefined || v === "") return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
  }

  /* Non-empty values of a column. null counts as empty alongside undefined and
   * "": the CSV path writes a NULL as "", so treating null differently would
   * make the SAME data read as non-numeric — losing alignment and number
   * formatting — on one transport but not the other. */
  function columnValues(rows, col) {
    var out = [], v;
    for (var i = 0; i < rows.length; i++) {
      v = rows[i][col];
      if (v !== undefined && v !== null && v !== "") out.push(v);
    }
    return out;
  }

  /* CSV carries strings, so numeric-ness is decided by shape: every non-null
   * value parses as a finite number, and at least one exists. */
  function isNumericColumn(rows, col) {
    var vals = columnValues(rows, col);
    if (!vals.length) return false;
    for (var i = 0; i < vals.length; i++) {
      if (toNum(vals[i]) === null) return false;
    }
    return true;
  }

  function isFractionShaped(rows, col) {
    var vals = columnValues(rows, col), i, n;
    for (i = 0; i < vals.length; i++) {
      n = toNum(vals[i]);
      if (n !== null && Math.abs(n) > _FRACTION_BOUND) return false;
    }
    return true; /* empty/all-null is vacuously fraction-shaped */
  }

  /* derive.py precedence, minus the layers that need the model (explicit
   * author formats and declared measure formats are resolved server-side):
   * suffix hint (percent, guarded) → identity (none) → whole numbers get
   * separators, fractional get two decimals. */
  function deriveFormat(rows, col) {
    var lower = String(col).toLowerCase(), i;
    for (i = 0; i < _SUFFIX_HINTS.length; i++) {
      if (lower.length >= _SUFFIX_HINTS[i].length &&
          lower.indexOf(_SUFFIX_HINTS[i], lower.length - _SUFFIX_HINTS[i].length) !== -1) {
        if (isFractionShaped(rows, col)) return "percent";
        break; /* hint refused by the guard — fall through to shape */
      }
    }
    if (isIdentity(col)) return null;
    var vals = columnValues(rows, col), allWhole = vals.length > 0;
    for (i = 0; i < vals.length; i++) {
      var n = toNum(vals[i]);
      if (n === null || n % 1 !== 0) { allWhole = false; break; }
    }
    return allWhole ? "comma" : "decimal";
  }

  /* ── The view layer — the control grammar's one law ─────────────────────
   * A figure's number is only ever a query result. On a live page the engine
   * reruns each binding's plan (The live page, below); everywhere else a
   * control only subsets WHICH STAMPED ROWS tables and charts display, and
   * value figures never react: summing the rows shown here would be a number
   * no query produced. */

  /* binding → { filters: {column: value}, search: "lowercased term" } */
  var _views = {};

  function viewOf(binding) {
    if (!_views[binding]) _views[binding] = { filters: {}, search: "" };
    return _views[binding];
  }

  function rowMatches(row, cols, view) {
    var col, i, cell, hit;
    for (col in view.filters) {
      if (!view.filters.hasOwnProperty(col)) continue;
      if (String(row[col]) !== view.filters[col]) return false;
    }
    if (view.search) {
      hit = false;
      for (i = 0; i < cols.length; i++) {
        cell = row[cols[i]];
        if (cell !== undefined &&
            String(cell).toLowerCase().indexOf(view.search) !== -1) {
          hit = true;
          break;
        }
      }
      if (!hit) return false;
    }
    return true;
  }

  /* binding → rows the page engine recomputed under the selection. Absent
   * on a page with no slice, so filteredRows stays the stamped-row subset. */
  var _liveRows = {};
  var _lastSelection = null;

  /* The one gate reactive figures re-render through: the stamped rows,
   * subset by the binding's filters and search, or on a live page the
   * engine's rows, subset by search. */
  function filteredRows(binding) {
    var block = readBlock(binding);
    /* A live page (tracebi-calc-plans): the engine already applied the
     * selection, so its rows replace the stamped ones; search, and a filter
     * on a column no slice carries, still subset what is shown. */
    if (_calc) {
      var current = _liveRows[binding] || (block ? block.rows : []);
      var subset = _views[binding];
      if (!subset || !block) return current;
      return current.filter(function (r) { return rowMatches(r, block.cols, subset); });
    }
    if (!block) return [];
    var plain = _views[binding];
    if (!plain) return block.rows;
    return block.rows.filter(function (r) {
      return rowMatches(r, block.cols, plain);
    });
  }

  function selectionConfig() {
    if (typeof document === "undefined") return null;
    var el = document.getElementById("tracebi-selection");
    if (!el) return null;
    try {
      var cfg = JSON.parse(el.textContent);
      return (cfg && typeof cfg === "object") ? cfg : null;
    } catch (e) { return null; }
  }

  /* Hydrated figures, registered so a control change can re-render them. */
  var _tables = []; /* { el, binding, cols, numeric, formats, rowCount } */
  var _charts = []; /* { el, binding, plan, chart } */

  /* Re-render the binding's table and chart figures from its current rows.
   * Value figures are exempt BY CODE: a live page paints them from the
   * engine's result (paintLiveValues), and summing the rows shown would be a
   * number no query produced. */
  function refreshBinding(binding) {
    var rows = filteredRows(binding), i, entry;
    for (i = 0; i < _tables.length; i++) {
      if (_tables[i].binding === binding) {
        try { renderBody(_tables[i], entryRows(_tables[i], rows)); } catch (e) { /* defensive */ }
      }
    }
    for (i = 0; i < _charts.length; i++) {
      entry = _charts[i];
      if (entry.binding === binding) {
        try { drawChart(entry, entryRows(entry, rows), true); } catch (e) { /* defensive */ }
      }
    }
    for (i = 0; i < _drawers.length; i++) {
      if (_drawers[i].binding === binding && _drawers[i].surface) drawEntry(_drawers[i]);
    }
  }

  function resizeCharts() {
    for (var i = 0; i < _charts.length; i++) {
      var c = _charts[i];
      try {
        /* A chart first shown (a tab) is drawn now; one whose box changed
         * width is drawn at the new width (small multiples lay out by it). */
        if (!c.chart || c.surface.clientWidth !== c.width) drawChart(c, c.rows, false);
        else c.chart.resize();
      } catch (e) { /* defensive */ }
    }
    redrawResized();
  }

  /* ── configureChart — the raw-ECharts escape valve ─────────────────────
   * Patches register before hydration (author script.js runs inline,
   * hydration at DOM-ready). After deep-merging a patch into the built
   * option, every series' data is overwritten from the stamped bytes and
   * dataset-style side channels are dropped: restyle, never re-source. */

  var _patches = {};

  function configureChart(figureId, patch) {
    if (!figureId || !patch || typeof patch !== "object") return;
    _patches[figureId] = _patches[figureId]
      ? deepMerge(_patches[figureId], patch) : patch;
  }

  function isPlainObject(v) {
    return !!v && Object.prototype.toString.call(v) === "[object Object]";
  }

  function deepMerge(base, patch) {
    var out = {}, k;
    for (k in base) if (base.hasOwnProperty(k)) out[k] = base[k];
    for (k in patch) {
      if (!patch.hasOwnProperty(k)) continue;
      if (isPlainObject(out[k]) && isPlainObject(patch[k])) {
        out[k] = deepMerge(out[k], patch[k]);
      } else {
        out[k] = patch[k];
      }
    }
    return out;
  }

  /* ── Hydration ─────────────────────────────────────────────────────── */

  function attr(el, name) {
    var v = el.getAttribute(name);
    return (v === null || v === "") ? null : v;
  }

  function figureEls(kind) {
    var sel = '[data-tb-figure="' + kind + '"][data-tb-binding]';
    return Array.prototype.slice.call(document.querySelectorAll(sel));
  }

  /* The elements one hydrator has not seen yet. A page drawn by a React app
   * mounts figures after load (a view switch, a drawer); refresh() runs the
   * hydrators again and each touches only what is new, once. */
  function fresh(els, phase) {
    return els.filter(function (el) {
      var seen = el.__tbHydrated || (el.__tbHydrated = {});
      if (seen[phase]) return false;
      seen[phase] = 1;
      return true;
    });
  }

  /* A value figure's format takes a table column's precedence: the author's
   * data-tb-format, then one the model declares on the measure, then the
   * shape guess — so an unformatted KPI reads 4,846.10, never 4846.1. */
  function valueFormat(el, rows, cell) {
    var name = attr(el, "data-tb-format");
    if (name || !isNumericColumn(rows, cell)) return name;
    /* "label": a time-grain period, written as it is (no "2,026"). */
    return (declaredFormats()[attr(el, "data-tb-binding")] || {})[cell] ||
           deriveFormat(rows, cell);
  }

  /* data-tb-direction="up-good" | "down-good": mark a change figure with its
   * direction (tb-up / tb-down / tb-flat, drawn as an arrow) and whether that
   * direction is good or bad for the reader. Read from the stamped value's
   * sign — the text itself is never altered. */
  function markDirection(el, target, raw) {
    var want = attr(el, "data-tb-direction");
    if (want !== "up-good" && want !== "down-good") return;
    var n = toNum(raw);
    if (n === null) return;
    ["tb-up", "tb-down", "tb-flat", "tb-good", "tb-bad"].forEach(function (c) {
      removeClass(target, c);
    });
    addClass(target, n > 0 ? "tb-up" : (n < 0 ? "tb-down" : "tb-flat"));
    if (n !== 0) {
      addClass(target, (n > 0) === (want === "up-good") ? "tb-good" : "tb-bad");
    }
  }

  function hydrateValues() {
    fresh(figureEls("value"), "value").forEach(function (el) {
      try {
        var block = readBlock(attr(el, "data-tb-binding"));
        if (!block || !block.rows.length) return;
        var row = block.rows[0];
        var cell = attr(el, "data-tb-cell");
        if (!cell) {
          if (block.cols.length !== 1) return;
          cell = block.cols[0];
        }
        var raw = row[cell];
        if (raw === undefined || raw === "") return;
        var text = raw;
        var name = valueFormat(el, block.rows, cell);
        if (name) {
          var n = toNum(raw);
          if (n !== null) {
            var formatted = applyNamedFormat(n, name);
            if (formatted !== null) text = formatted;
          }
        }
        var target = el.querySelector(".tb-kpi-value") || el;
        target.textContent = text;
        markDirection(el, target, raw);
      } catch (e) { /* defensive: leave the author's content */ }
    });
  }

  /* Rebuild a hydrated table's body from *rows*. Labels and formats were
   * derived ONCE from the full stamped rows, so a filtered subset can never
   * flip a column's presentation between control states. */
  /* data-tb-totals names a one-row binding the model computed (the table's
   * query with no dimensions): its values fill a <tfoot> row. Nothing is
   * summed here — a ratio's total is the model's ratio of totals. */
  function totalsRow(el, cols, numeric, formats, bars) {
    var name = attr(el, "data-tb-totals");
    if (!name) return null;
    var old = el.querySelector("tfoot");
    if (old) el.removeChild(old);           /* the server-rendered copy */
    var block = currentBlock(name);  /* recomputed with the table on a live page */
    if (!block || block.rows.length !== 1) return null;
    var row = block.rows[0];
    if (!el.querySelector("tbody")) el.appendChild(document.createElement("tbody"));
    var tfoot = document.createElement("tfoot");
    var tr = document.createElement("tr");
    tr.className = "tb-total";
    cols.forEach(function (col, i) {
      var td = document.createElement("td");
      if (bars[col]) td.className = "tb-bar-cell";
      if (block.cols.indexOf(col) !== -1) {
        addClass(td, "tb-num");
        var n = toNum(row[col]), text = row[col] === undefined ? "" : row[col];
        var fmt = formats[col] || deriveFormat(block.rows, col);
        if (n !== null && fmt) {
          var formatted = applyNamedFormat(n, fmt);
          if (formatted !== null) text = formatted;
        }
        td.textContent = text;
      } else if (i === 0 && !numeric[col]) {
        td.textContent = "Total";
      }
      tr.appendChild(td);
    });
    tfoot.appendChild(tr);
    el.appendChild(tfoot);
    return tfoot;
  }

  /* data-tb-sort: the reader reorders the rows a table DISPLAYS by clicking a
   * header — ascending, descending, then back to the query's own order.
   * Reordering computes nothing: every cell is the stamped value, and the
   * totals row still describes all of them. Ties keep the query order. */
  function sortedRows(entry, rows) {
    var s = entry.sort;
    if (!s || !s.dir) return rows;
    var col = s.col, num = entry.numeric[col], sign = s.dir === "asc" ? 1 : -1;
    return rows.map(function (r, i) { return { r: r, i: i }; })
      .sort(function (a, b) {
        var x = a.r[col], y = b.r[col], c;
        var xe = x === undefined || x === null || x === "";
        var ye = y === undefined || y === null || y === "";
        if (xe || ye) c = xe === ye ? 0 : (xe ? 1 : -1); /* blanks last, both ways */
        else if (num) c = sign * (toNum(x) - toNum(y));
        else c = sign * String(x).localeCompare(String(y));
        return c || a.i - b.i;
      })
      .map(function (w) { return w.r; });
  }

  function hydrateSort(entry) {
    var el = entry.el;
    if (el.getAttribute("data-tb-sort") === null) return;
    var ths = el.querySelectorAll("thead th");
    entry.cols.forEach(function (col, i) {
      var th = ths[i];
      if (!th) return;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tb-sort";
      while (th.firstChild) btn.appendChild(th.firstChild);
      th.appendChild(btn);
      th.setAttribute("aria-sort", "none");
      btn.addEventListener("click", function () {
        var cur = entry.sort && entry.sort.col === col ? entry.sort.dir : null;
        var next = cur === null ? "asc" : (cur === "asc" ? "desc" : null);
        entry.sort = next ? { col: col, dir: next } : null;
        Array.prototype.forEach.call(ths, function (h) {
          h.setAttribute("aria-sort", "none");
        });
        if (next) th.setAttribute("aria-sort", next === "asc" ? "ascending" : "descending");
        renderBody(entry, entryRows(entry));
      });
    });
  }

  /* data-tb-bars: a thin bar after each cell of the named numeric columns,
   * proportional to the stamped value. Zero is the left edge; a column with
   * negatives gets its zero in the middle so neither side is exaggerated.
   * The scale comes from ALL rows of the current result (the stamped block,
   * or the selection's full row set), never from a filter subset and never
   * from the painted window — a bar must not change length as you scroll. */
  function barScales(el, rows, cols, numeric) {
    var want = attr(el, "data-tb-bars"), out = {};
    if (!want) return out;
    splitList(want).forEach(function (col) {
      if (cols.indexOf(col) === -1 || !numeric[col]) return;
      var max = 0, neg = false;
      columnValues(rows, col).forEach(function (v) {
        var n = toNum(v);
        if (n === null) return;
        if (Math.abs(n) > max) max = Math.abs(n);
        if (n < 0) neg = true;
      });
      if (max > 0) out[col] = { max: max, neg: neg };
    });
    return out;
  }

  function paintBar(td, n, scale) {
    var bar = document.createElement("span");
    bar.className = "tb-bar" + (n < 0 ? " tb-bar--neg" : "");
    bar.setAttribute("aria-hidden", "true");
    var span = (scale.neg ? 50 : 100) * Math.abs(n) / scale.max;
    var zero = scale.neg ? 50 : 0;
    bar.style.left = (n < 0 ? zero - span : zero) + "%";
    bar.style.width = span + "%";
    /* The bar's percentages are of a fixed-width lane after the number. */
    var track = document.createElement("span");
    track.className = "tb-bar-track";
    track.setAttribute("aria-hidden", "true");
    track.appendChild(bar);
    addClass(td, "tb-bar-cell");
    td.appendChild(track);
  }

  /* Above this many rows the scroll box paints only the visible window.
   * At or below it, renderBody is the previous full-tbody path. */
  var WINDOW_THRESHOLD = 500;
  var WINDOW_OVERSCAN = 8;
  var _printing = false;

  function scrollCap(el) {
    var want = attr(el, "data-tb-rows");
    if (want === "all") return null; /* author opted out of the scroll box */
    var n = want === null ? 10 : parseInt(want, 10);
    if (!isFinite(n) || n < 1) n = 10;
    return n;
  }

  function scrollBox(el) {
    var p = el.parentNode;
    while (p) {
      if (p.className && (" " + p.className + " ").indexOf(" tb-scroll ") !== -1) {
        return p;
      }
      p = p.parentNode;
    }
    return null;
  }

  /* Print always paints the full set. data-tb-rows="all" opts out of the
   * scroll box, so windowing there would hide rows for good. */
  function wantsWindow(entry, total) {
    if (_printing) return false;
    if (total <= WINDOW_THRESHOLD) return false;
    return scrollCap(entry.el) !== null;
  }

  /* hydrateScroll runs after badges. Before that, a window paints into the
   * bare table; once this is set, a large result grows its own scroll box
   * if the authored row count never needed one (a selection can). */
  var _scrollReady = false;

  function ensureScroll(entry) {
    if (scrollBox(entry.el)) return;
    var el = entry.el, parent = el.parentNode, cap = scrollCap(el);
    if (!parent || cap === null) return;
    var wrap = document.createElement("div");
    wrap.className = "tb-scroll";
    wrap.style.maxHeight = ((cap + 1) * 2.6) + "em";
    parent.insertBefore(wrap, el);
    wrap.appendChild(el);
    if (!wrap._tbWin) {
      wrap._tbWin = true;
      wrap.addEventListener("scroll", function () {
        if (entry._rendering) return;
        try { renderBody(entry, entry.modelRows); } catch (e) {}
      });
    }
  }

  function measureRow(tr) {
    var h = 0;
    if (tr.getBoundingClientRect) {
      var box = tr.getBoundingClientRect();
      if (box && box.height) h = box.height;
    }
    if (!h && tr.offsetHeight) h = tr.offsetHeight;
    return h || 0;
  }

  function viewHeight(entry, rh) {
    var box = scrollBox(entry.el), h = 0, thead, th;
    if (box) {
      if (box.clientHeight) h = box.clientHeight;
      else if (box.getBoundingClientRect) {
        var b = box.getBoundingClientRect();
        if (b && b.height) h = b.height;
      }
    }
    if (h) {
      thead = entry.el.querySelector("thead");
      th = 0;
      if (thead && thead.getBoundingClientRect) {
        th = thead.getBoundingClientRect().height || 0;
      }
      h = h - th;
      if (h < rh) h = rh;
      return h;
    }
    return (scrollCap(entry.el) || 10) * rh;
  }

  function spacerRow(cols, px) {
    var tr = document.createElement("tr");
    var td = document.createElement("td");
    tr.className = "tb-window-pad";
    tr.setAttribute("aria-hidden", "true");
    tr.style.height = px + "px";
    td.colSpan = cols;
    td.setAttribute("colspan", String(cols));
    td.style.height = px + "px";
    td.style.padding = "0";
    td.style.border = "0";
    td.style.lineHeight = "0";
    tr.appendChild(td);
    return tr;
  }

  function dataRow(entry, r, fixedPx, index) {
    var tr = document.createElement("tr");
    var bars = entry._paintBars || entry.bars;
    if (fixedPx) tr.style.height = fixedPx + "px";
    if (index >= 0 && index % 2 === 1) tr.className = "tb-stripe";
    entry.cols.forEach(function (col) {
      var td = document.createElement("td");
      var raw = r[col], text = (raw === undefined) ? "" : raw;
      var n = null;
      if (bars && bars[col]) td.className = "tb-bar-cell";
      if (entry.numeric[col]) {
        addClass(td, "tb-num");
        n = toNum(raw);
        if (n !== null && entry.formats[col]) {
          var formatted = applyNamedFormat(n, entry.formats[col]);
          if (formatted !== null) text = formatted;
        }
      }
      if (fixedPx) {
        td.style.height = fixedPx + "px";
        td.style.boxSizing = "border-box";
      }
      td.textContent = text;
      if (n !== null && bars && bars[col]) paintBar(td, n, bars[col]);
      tr.appendChild(td);
    });
    if (entry.selectCols && _calc) selectableRow(entry, tr, r);
    return tr;
  }

  function displayRows(entry) {
    var rows = entry.modelRows || [];
    var sig = entry.sort ? entry.sort.col + "\n" + entry.sort.dir : "";
    if (entry._sig === sig && entry._src === rows && entry._disp) return entry._disp;
    entry._sig = sig;
    entry._src = rows;
    entry._disp = sortedRows(entry, rows);
    return entry._disp;
  }

  /* The one row model. Sort, filter, search, selection, totals and the
   * window all read `rows` here — the full current set, already subset by
   * filteredRows. The window is only which of those become <tr>s. */
  function renderBody(entry, rows) {
    if (entry._rendering) return;
    entry._rendering = true;
    try {
      rows = rows || [];
      if (entry._count !== undefined && entry._count !== rows.length) {
        var reset = scrollBox(entry.el);
        if (reset) reset.scrollTop = 0;
      }
      entry._count = rows.length;
      entry.modelRows = rows;
      if (entry._genRows !== rows) {
        entry._genRows = rows;
        entry._gen = (entry._gen || 0) + 1;
      }
      /* A grand total under a filtered view would not add up to the rows
       * shown, so the totals row steps aside while a filter or search is on. */
      if (entry.tfoot) entry.tfoot.hidden = rows.length !== entry.rowCount;
      /* Rows stand out only when some do not: a sector filter that leaves
       * one sector picks every row, and then none is marked. */
      entry._pickAll = !!(entry.selectCols && _calc && rows.length && rows.every(function (r) {
        return rowPicked(entry, r) === true;
      }));
      paintRows(entry, displayRows(entry));
    } finally {
      entry._rendering = false;
    }
  }

  function paintRows(entry, rows) {
    var el = entry.el, tbody = el.querySelector("tbody"), total = rows.length;
    var windowed, live, block, all, rh, box, scrollTop, viewH, maxScroll;
    var start, end, key, saved, topPx, botPx, i;
    if (!tbody) {
      tbody = document.createElement("tbody");
      el.appendChild(tbody);
    }
    windowed = wantsWindow(entry, total);
    entry.windowed = windowed;
    entry._paintBars = entry.bars;
    if (windowed && _scrollReady) ensureScroll(entry);
    if (windowed) {
      /* Full result, not the rows argument: a filter/search subset must not
       * rescale, and neither must the visible slice. */
      live = _liveRows[entry.binding];
      block = readBlock(entry.binding);
      all = live || (block ? block.rows : rows);
      entry._paintBars = barScales(el, all, entry.cols, entry.numeric);
      addClass(el, "tb-window");
    } else {
      removeClass(el, "tb-window");
      entry._winKey = null;
    }
    if (!windowed) {
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
      if (!total) {
        /* An empty result (or a filter that matches nothing) says so, rather
         * than leaving a header over a void — mirrors the server-rendered
         * empty row and the chart's "no data". */
        var etr = document.createElement("tr");
        var etd = document.createElement("td");
        etd.className = "tb-empty";
        etd.colSpan = entry.cols.length;
        etd.textContent = "no data";
        etr.appendChild(etd);
        tbody.appendChild(etr);
        return;
      }
      for (i = 0; i < total; i++) tbody.appendChild(dataRow(entry, rows[i], 0, -1));
      return;
    }
    if (!entry.rowPx) {
      while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
      var probe = dataRow(entry, rows[0], 0, 0);
      /* A lone row is :last-child, and that rule drops the bottom border, so
       * the probe would measure a pixel short of every row that follows it.
       * A thousand rows later the window would show the wrong slice. */
      var hold = document.createElement("tr");
      hold.appendChild(document.createElement("td"));
      tbody.appendChild(probe);
      tbody.appendChild(hold);
      var measured = measureRow(probe) || 36;
      probe.style.height = measured + "px";
      var pc = probe.children, pi;
      for (pi = 0; pi < pc.length; pi++) {
        pc[pi].style.height = measured + "px";
        pc[pi].style.boxSizing = "border-box";
      }
      /* Table-cell height is a minimum; lock the stride to the border box
       * the row actually occupies, which is what scroll math divides by. */
      entry.rowPx = measureRow(probe) || measured;
      tbody.removeChild(probe);
      tbody.removeChild(hold);
    }
    rh = entry.rowPx;
    box = scrollBox(el);
    scrollTop = box ? (box.scrollTop || 0) : 0;
    viewH = viewHeight(entry, rh);
    maxScroll = Math.max(0, total * rh - viewH);
    if (scrollTop > maxScroll) scrollTop = maxScroll;
    if (scrollTop < 0) scrollTop = 0;
    start = Math.floor(scrollTop / rh) - WINDOW_OVERSCAN;
    if (start < 0) start = 0;
    end = Math.ceil((scrollTop + viewH) / rh) + WINDOW_OVERSCAN;
    if (scrollTop + viewH + rh >= total * rh) end = total;
    if (end > total) end = total;
    if (start > end) start = end;
    key = start + ":" + end + ":" + total + ":" + (entry._sig || "") + ":" + entry._gen;
    if (entry._winKey === key && tbody.firstChild) return;
    entry._winKey = key;
    saved = box ? box.scrollTop : 0;
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    topPx = start * rh;
    if (topPx > 0) tbody.appendChild(spacerRow(entry.cols.length, topPx));
    for (i = start; i < end; i++) tbody.appendChild(dataRow(entry, rows[i], rh, i));
    botPx = (total - end) * rh;
    if (botPx > 0) tbody.appendChild(spacerRow(entry.cols.length, botPx));
    if (box && saved && box.scrollTop !== saved) box.scrollTop = saved;
  }

  function bindPrintMode() {
    if (bindPrintMode.done) return;
    bindPrintMode.done = true;
    var opened = [];
    var apply = function (on) {
      on = !!on;
      if (_printing === on) return;
      _printing = on;
      /* The receipt prints as an appendix with every disclosure open. */
      var boxes = document.querySelectorAll(".tb-receipt-drawer details"), k;
      if (on) {
        for (k = 0; k < boxes.length; k++) {
          if (!boxes[k].open) { boxes[k].open = true; opened.push(boxes[k]); }
        }
      } else {
        while (opened.length) opened.pop().open = false;
      }
      for (var i = 0; i < _tables.length; i++) {
        try { renderBody(_tables[i], _tables[i].modelRows); } catch (e) {}
      }
      printCharts(on);
    };
    if (root.addEventListener) {
      root.addEventListener("beforeprint", function () { apply(true); });
      root.addEventListener("afterprint", function () { apply(false); });
    }
    if (root.matchMedia) {
      var mq = root.matchMedia("print");
      var onMq = function () { apply(mq.matches); };
      if (mq.addEventListener) mq.addEventListener("change", onMq);
      else if (mq.addListener) mq.addListener(onMq);
      if (mq.matches) _printing = true;
    }
  }

  function attachWindow(entry) {
    if (!entry.windowed) return;
    var box = scrollBox(entry.el);
    if (box && !box._tbWin) {
      box._tbWin = true;
      box.addEventListener("scroll", function () {
        if (entry._rendering) return;
        try { renderBody(entry, entry.modelRows); } catch (e) {}
      });
    }
    try { renderBody(entry, entry.modelRows); } catch (e) {}
  }

  /* "col=Value; col2=Value" → {col: "Value", col2: "Value"}. Pairs split on
   * ";" so a label may hold a comma; the build has already validated them. */
  function columnMap(value) {
    var out = {};
    if (!value) return out;
    String(value).split(";").forEach(function (pair) {
      var i = pair.indexOf("=");
      if (i < 1) return;
      out[trim(pair.slice(0, i))] = trim(pair.slice(i + 1));
    });
    return out;
  }

  /* {binding: {column: format}} for measures the model declares a format
   * on — a presentation block, not part of the fingerprinted data. */
  var _declaredFormats = null;
  function declaredFormats() {
    if (_declaredFormats) return _declaredFormats;
    _declaredFormats = {};
    try {
      var el = document.getElementById("tracebi-formats");
      if (el) _declaredFormats = JSON.parse(el.textContent) || {};
    } catch (e) { /* defensive */ }
    return _declaredFormats;
  }

  function hydrateTables() {
    fresh(figureEls("table"), "table").forEach(function (el) {
      try {
        if (el.tagName !== "TABLE") return;
        /* An author-rendered table is left alone (and never reactive). A
         * build-filled one (SSR) carries <tbody data-tb-hydrate>: fall through
         * so it re-registers and stays reactive — renderBody clears the tbody
         * before rebuilding, so hydrating over the server rows never doubles
         * them. */
        if (el.querySelector("tbody tr") &&
            !el.querySelector("tbody[data-tb-hydrate]")) return;
        var binding = attr(el, "data-tb-binding");
        var block = readBlock(binding);
        if (!block || !block.rows.length) return;
        var rows = block.rows;

        var cols = block.cols;
        var allow = attr(el, "data-tb-columns");
        if (allow) {
          cols = splitList(allow).filter(function (c) {
            return block.cols.indexOf(c) !== -1;
          });
        }
        if (!cols.length) return;

        /* data-tb-labels / data-tb-formats: author overrides for the named
         * columns ("col=Value; col2=Value"). They win over the derived label
         * and format; a format applies only to a numeric column. */
        var labels = columnMap(attr(el, "data-tb-labels"));
        var ownFormats = columnMap(attr(el, "data-tb-formats"));
        /* Then a format the model declares on the measure (tracebi-formats,
         * written at build), then the shape guess. */
        var declared = declaredFormats()[binding] || {};
        var numeric = {}, formats = {};
        cols.forEach(function (col) {
          /* A time-grain label ("2026") is text, however numeric it looks. */
          numeric[col] = declared[col] !== "label" && isNumericColumn(rows, col);
          formats[col] = numeric[col]
            ? (ownFormats[col] || declared[col] || deriveFormat(rows, col)) : null;
        });

        /* Build via createElement/textContent only — data never becomes
         * markup. An existing author thead is honoured. */
        if (!el.querySelector("thead")) {
          var thead = document.createElement("thead");
          var htr = document.createElement("tr");
          cols.forEach(function (col) {
            var th = document.createElement("th");
            th.textContent = labels[col] || humanise(col);
            if (numeric[col]) th.className = "tb-num";
            htr.appendChild(th);
          });
          thead.appendChild(htr);
          el.appendChild(thead);
        }
        var entry = { el: el, binding: binding, cols: cols,
                      numeric: numeric, formats: formats,
                      rowCount: rows.length, sort: null,
                      bars: barScales(el, rows, cols, numeric) };
        /* A bar column's header keeps its lane empty, so it sits over the
         * numbers (an author's or the server's thead as well). */
        var heads = el.querySelectorAll("thead th");
        cols.forEach(function (col, i) {
          if (entry.bars[col] && heads[i]) addClass(heads[i], "tb-bar-cell");
        });
        entry.tfoot = totalsRow(el, cols, numeric, formats, entry.bars);
        /* data-tb-select-rows: a row click selects the row's values of the
         * dimension columns the table shows, on a live page; a value
         * ("dim_issuer.issuer") names the columns it writes instead, so a
         * table can show a sector without selecting by it. */
        var picks = el.getAttribute("data-tb-select-rows");
        if (picks !== null && _calc) {
          var named = trim(picks) ? splitList(picks) : null;
          entry.selectCols = el.__tbSelectCols = (named || cols).filter(function (c) {
            return c.indexOf(".") !== -1 && selectableField(c)
              && (!named || block.cols.indexOf(c) !== -1);
          });
        }
        hydrateSort(entry);
        _tables.push(entry);
        renderBody(entry, entryRows(entry));
      } catch (e) { /* defensive */ }
    });
  }

  /* ── The chart engine — Apache ECharts ─────────────────────────────────
   * Every chart on a page draws here: a template's {{ figure() }} chart, a
   * hand-written data-tb-figure="chart", and the kit's <Chart>, <Spark> and
   * <EChart binding x y> (the kit renders the element, this draws it), from
   * the same plan (data-tb-type, -x, -y, -color, -value-format, -unit,
   * -stack, -mark, -annotate, -facet, -x-title, -y-title, -palette,
   * -renderer) and the same rows the rest of the page reads, through ONE
   * option builder (optionFor) and one ECharts theme built from the page's
   * tokens (chartTheme). The ECharts build is echarts-kit.min.js
   * (root.__tbECharts), SVG by default; canvas per figure
   * (data-tb-renderer="canvas", <Chart renderer>) or per report
   * (report.json "charts": {"renderer": "canvas"}) for thousands of marks.
   *
   * What it never does: compute a number. Every bar, point and slice is one
   * row's own value; there are no totals, shares or averages drawn. Colours
   * are assigned from the UNFILTERED rows, so a filter that removes a series
   * never repaints the ones that stay. A click on a mark writes the page's
   * one selection (markAction), never a side channel.
   * ──────────────────────────────────────────────────────────────────── */

  /* Charts whose first motion has not settled: the page reports ready
   * (data-tb-ready, what a printer waits for) once they have. */
  var _introPending = 0;

  function echartsLib() {
    var lib = root.__tbECharts;
    return lib && typeof lib.init === "function" ? lib : null;
  }

  function groupOf(v) {
    return (v === null || v === undefined || v === "") ? "(none)" : String(v);
  }

  /* Category values in first-seen order over *rows*. */
  function categories(plan, rows) {
    var cats = [], seen = {};
    rows.forEach(function (r) {
      var c = String(r[plan.x]);
      if (!seen.hasOwnProperty(c)) { seen[c] = 1; cats.push(c); }
    });
    return cats;
  }

  function cssPalette(el) {
    var out = [];
    if (typeof getComputedStyle === "undefined") return out;
    var cs = getComputedStyle(el || document.documentElement);
    for (var i = 1; i <= 8; i++) {
      var v = cs.getPropertyValue("--tb-chart-" + i);
      if (v && trim(v)) out.push(trim(v));
    }
    return out;
  }

  function cssVar(cs, name) {
    var v = cs.getPropertyValue(name);
    return (v && trim(v)) ? trim(v) : null;
  }

  /* ── Colours, from the page's tokens ── */

  var _colorCtx = null;
  /* A token as a colour ECharts can parse. A theme may write oklch() or
   * color-mix(), which a canvas keeps in its own space: then the pixel it
   * paints, as rgb() / rgba(). Unparseable (no canvas): the token as written. */
  function plainColor(v) {
    if (!v) return v;
    try {
      if (!_colorCtx) {
        var c = document.createElement("canvas");
        if (!c || !c.getContext) return v;
        c.width = 1;
        c.height = 1;
        _colorCtx = c.getContext("2d", { willReadFrequently: true });
        if (!_colorCtx) return v;
      }
      _colorCtx.fillStyle = "#000";
      _colorCtx.fillStyle = v;
      var s = _colorCtx.fillStyle;
      if (/^(#|rgb)/.test(s)) return s;
      _colorCtx.clearRect(0, 0, 1, 1);
      _colorCtx.fillRect(0, 0, 1, 1);
      var d = _colorCtx.getImageData(0, 0, 1, 1).data;
      return d[3] === 255 ? "rgb(" + d[0] + "," + d[1] + "," + d[2] + ")"
        : "rgba(" + d[0] + "," + d[1] + "," + d[2] + "," + (+(d[3] / 255).toFixed(3)) + ")";
    } catch (e) { return v; }
  }

  /* [r, g, b, a] of a #rgb / #rrggbb / rgb() / rgba() colour, or null. */
  function rgbaOf(c) {
    var s = trim(String(c || "")), m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(s);
    if (m) {
      var h = m[1].length === 3 ? m[1].replace(/(.)/g, "$1$1") : m[1];
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16), 1];
    }
    m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:\s*[,\/]\s*([\d.]+))?/i.exec(s);
    return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null;
  }

  function withAlpha(c, a) {
    var v = rgbaOf(c);
    return v ? "rgba(" + v[0] + "," + v[1] + "," + v[2] + "," + a + ")" : c;
  }

  function contrast(a, b) {
    var lum = function (c) {
      var v = rgbaOf(c);
      if (!v) return null;
      var lin = function (x) { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
      return 0.2126 * lin(v[0]) + 0.7152 * lin(v[1]) + 0.0722 * lin(v[2]);
    };
    var la = lum(a), lb = lum(b);
    if (la === null || lb === null) return 0;
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }

  /* The text colour that reads on a fill: the page's ink or its card. */
  function labelOn(fill, k) {
    return contrast(k.ink, fill) >= contrast(k.card, fill) ? k.ink : k.card;
  }

  function motionOk() {
    if (_printing) return false;
    try {
      if (root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return false;
      }
    } catch (e) {}
    return true;
  }

  /* The house chart tokens (tracebi.css, docs/reference/chart-style.md), read
   * from the figure at every draw: the page's, the house theme's, the
   * brand's, and any the figure's own container restates (a lead KPI tile
   * draws its sparkline in the tile's ink). */
  function chartTokens(el) {
    var cs = null;
    try { cs = getComputedStyle(el || document.documentElement); } catch (e) {}
    var raw = function (n) {
      var v = cs ? cs.getPropertyValue("--tb-" + n) : "";
      return v ? trim(v) : "";
    };
    var col = function (n, d) { var v = raw(n); return v ? plainColor(v) : d; };
    var num = function (n, d) { var v = parseFloat(raw(n)); return isNaN(v) ? d : v; };
    var motion = raw("chart-motion") || "450ms", ms = parseFloat(motion);
    if (!/ms\s*$/.test(motion)) ms *= 1000;
    var palette = [], i, c;
    for (i = 1; i <= 8; i++) { c = col("chart-" + i); if (c) palette.push(c); }
    var dash = raw("chart-grid-dash").split(/[\s,]+/).map(Number).filter(function (n) { return n > 0; });
    var ink = col("ink", "#111111"), muted = col("muted", "#666666");
    var font = raw("chart-font") || raw("font") || undefined;
    return {
      ink: ink, muted: muted, card: col("bg", "#ffffff"), accent: col("accent"),
      onAccent: col("on-accent"),
      font: font, num: raw("chart-num-font") || font,
      grid: col("chart-grid", "rgba(17,17,17,0.11)"), gridDash: dash.length ? dash : "dashed",
      axis: col("chart-axis", "#e5e5e5"), label: col("chart-label") || muted,
      value: col("chart-value") || ink,
      tipBg: col("chart-tooltip-bg") || col("bg", "#ffffff"),
      tipBorder: col("chart-tooltip-border") || col("rule", "#e5e5e5"),
      tipShadow: raw("chart-tooltip-shadow"), tipRadius: raw("chart-tooltip-radius") || "8px",
      tipInk: col("chart-tooltip-ink") || muted, glow: num("chart-glow", 0),
      radius: num("chart-radius", 2), bar: num("chart-bar", 55), line: num("chart-line", 2),
      area: num("chart-area", 0.12), dim: num("chart-dim", 0.28),
      motion: motionOk() ? (isNaN(ms) ? 450 : ms) : 0,
      palette: palette
    };
  }

  /* The TraceBi theme for ECharts, from the chart tokens: the house look
   * (chart-style.md) as ECharts' defaults, so an option an author adds
   * (configureChart, <EChart option>) and an option-only <EChart> (a sankey
   * the page computes) take it too. */
  function chartTheme(k) {
    k = k || chartTokens();
    var font = k.font;
    var text = function (color, size, weight) {
      return { color: color, fontSize: size, fontWeight: weight, fontFamily: font };
    };
    var axis = {
      axisLine: { show: false, lineStyle: { color: k.axis } },
      axisTick: { show: false },
      axisLabel: { color: k.label, fontSize: 11, fontFamily: k.num, margin: 10, lineHeight: 15 },
      splitLine: { show: true, lineStyle: { color: k.grid, type: k.gridDash, width: 1 } },
      splitArea: { show: false },
      nameTextStyle: text(k.label, 11, 600)
    };
    /* The category axis is the one solid rule: the baseline, at zero. Its
     * names at 12px, the value ticks at 11. */
    var categoryAxis = extend(extend({}, axis), {
      axisLine: { show: true, lineStyle: { color: k.axis } },
      axisLabel: { color: k.label, fontSize: 12, fontFamily: font, margin: 10, lineHeight: 15 },
      splitLine: { show: false }
    });
    var cells = { itemStyle: { borderColor: k.card, borderWidth: 2, gapWidth: 2 },
                  label: text(k.ink, 12, 500) };
    return {
      color: k.palette.length ? k.palette : undefined,
      backgroundColor: "transparent",
      textStyle: { color: k.ink, fontFamily: font },
      animation: k.motion > 0, animationDuration: k.motion, animationEasing: "cubicOut",
      animationDurationUpdate: k.motion, animationEasingUpdate: "cubicOut",
      title: { textStyle: text(k.ink, 14, 600), subtextStyle: text(k.label, 12), itemGap: 4 },
      legend: { icon: "circle", itemWidth: 8, itemHeight: 8, itemGap: 16,
                textStyle: text(k.ink, 12), pageTextStyle: text(k.label, 11),
                pageIconColor: k.ink, pageIconInactiveColor: k.grid, inactiveColor: k.grid },
      tooltip: tooltipBase(k),
      categoryAxis: categoryAxis, valueAxis: axis, logAxis: axis, timeAxis: axis,
      line: { lineStyle: { width: k.line, cap: "round", join: "round" }, symbol: "circle",
              symbolSize: 7, showSymbol: false, smooth: false },
      bar: { barCategoryGap: (100 - k.bar) + "%", barMaxWidth: 36,
             itemStyle: { borderRadius: [k.radius, k.radius, 0, 0] } },
      scatter: { symbolSize: 10, itemStyle: { opacity: 0.85, borderColor: k.card, borderWidth: 2 } },
      pie: { radius: ["54%", "90%"], padAngle: 0.7, label: { show: false }, labelLine: { show: false },
             itemStyle: { borderColor: k.card, borderWidth: 2, borderRadius: 3 } },
      treemap: extend(extend({}, cells), { breadcrumb: { show: false } }),
      sunburst: cells,
      sankey: { itemStyle: { borderWidth: 0 }, label: text(k.ink, 12), lineStyle: { opacity: 0.3 } },
      radar: { axisName: { color: k.label }, axisLine: { lineStyle: { color: k.grid } },
               splitLine: { lineStyle: { color: k.grid } }, splitArea: { show: false } },
      visualMap: { textStyle: text(k.label, 11) },
      dataZoom: { textStyle: text(k.label, 11), borderColor: k.grid },
      toolbox: { iconStyle: { borderColor: k.label } },
      markLine: { label: text(k.label, 11), lineStyle: { color: k.label, type: k.gridDash } },
      label: { color: k.ink, fontFamily: font }
    };
  }

  /* The readout as a card (.tb-echart-tip), drawn by ECharts' HTML tooltip. */
  function tooltipBase(k) {
    return {
      className: "tb-echart-tip", backgroundColor: k.tipBg, borderColor: k.tipBorder,
      borderWidth: 1, padding: [8, 10],
      // The readout holds "Trace →": it must hold still and wait for the
      // pointer to reach it. ECharts' default follows the cursor, glides for
      // 0.4s and hides 0.1s after the pointer leaves the mark, so the link
      // runs away from a person reaching for it. Pin it where it opened for
      // this mark or category; it moves only when another one is hovered.
      transitionDuration: 0, hideDelay: 400, position: pinnedTip,
      textStyle: { color: k.tipInk, fontFamily: k.font, fontSize: 13 },
      extraCssText: "border-radius:" + k.tipRadius + ";box-shadow:" + (k.tipShadow || "none") +
        ";min-width:140px;max-width:280px;white-space:normal;",
      axisPointer: { lineStyle: { color: k.label, type: [3, 3], width: 1 },
                     shadowStyle: { color: withAlpha(k.ink, 0.05) } }
    };
  }

  function pinnedTip(point, params, dom, rect, size) {
    var p = isArray(params) ? params[0] : params;
    var key = p ? [p.seriesIndex, p.dataIndex, p.axisValue].join("|") : "";
    if (dom._tbTipKey === key && dom._tbTipAt) return dom._tbTipAt;
    var view = size.viewSize, box = size.contentSize, gap = 14;
    var x = point[0] + gap, y = point[1] + gap;
    if (x + box[0] > view[0]) x = Math.max(0, point[0] - gap - box[0]);
    if (y + box[1] > view[1]) y = Math.max(0, point[1] - gap - box[1]);
    dom._tbTipKey = key;
    dom._tbTipAt = [x, y];
    return dom._tbTipAt;
  }

  function extend(a, b) {
    for (var key in b) if (b.hasOwnProperty(key)) a[key] = b[key];
    return a;
  }

  function escHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* The readout's content: the category, then a row per series of its
   * swatch, its value as the page formats it and its name; the measures'
   * own descriptions; and, when the trace holds this figure, the way to it. */
  function tipHtml(title, rows, about, trace) {
    var out = '<div class="tb-chart-tip-title">' + escHtml(title) + "</div>";
    rows.forEach(function (r) {
      out += '<div class="tb-chart-tip-row"><span class="tb-chart-tip-key" style="background:' +
        escHtml(r.colour || "") + '"></span><strong>' + escHtml(r.value) + "</strong><span>" +
        escHtml(r.name) + "</span></div>";
    });
    (about || []).forEach(function (text) {
      out += '<div class="tb-chart-tip-about">' + escHtml(text) + "</div>";
    });
    if (trace) {
      out += '<button type="button" class="tb-chart-tip-receipt" data-tb-receipt-for="' +
        escHtml(trace) + '">Trace →</button>';
    }
    return out;
  }

  /* The format a value is shown in: the author's value format, then the
   * model's declared format for the column, then the shape default — the
   * table's precedence, so a tooltip agrees with the table beside it. An
   * unknown format writes the value as it is: an attribute may format or do
   * nothing, never blank out a number. data-tb-unit is a suffix only. */
  function chartFormatter(plan, rows, col) {
    var mode = plan.valueFormat ||
      (declaredFormats()[plan.binding] || {})[col] || deriveFormat(rows, col);
    var unit = plan.unit || "";
    return function (v) {
      var n = toNum(v);
      if (n === null) return v === null || v === undefined ? "" : String(v);
      var out = mode ? applyNamedFormat(n, mode) : null;
      return (out === null ? String(v) : out) + unit;
    };
  }

  /* Axis ticks are short: compact digits, keeping a currency sign or a
   * percent, so "$20M" rather than "$20,000,000". Marks and the readout keep
   * the full format. */
  function tickFormatter(plan) {
    var mode = plan.valueFormat, unit = plan.unit || "";
    return function (v) {
      var n = Number(v), out;
      if (mode === "percent") out = applyNamedFormat(n, "percent");
      else if (mode === "currency" || mode === "currency0" || mode === "currency_compact") {
        out = (n < 0 ? "-$" : "$") + applyNamedFormat(Math.abs(n), "compact");
      } else out = applyNamedFormat(n, "compact");
      return (out === null ? String(v) : out) + unit;
    };
  }

  var _measureCtx = null;
  /* How wide *text* sets at *size* px: room for labels the option reserves. */
  function textWidth(text, size, font) {
    try {
      if (!_measureCtx) {
        var c = document.createElement("canvas");
        _measureCtx = c && c.getContext ? c.getContext("2d") : null;
      }
      if (_measureCtx) {
        _measureCtx.font = (size || 12) + "px " + (font || "sans-serif");
        return _measureCtx.measureText(String(text)).width;
      }
    } catch (e) {}
    return String(text).length * (size || 12) * 0.56;
  }

  /* The plan a chart element declares. */
  var KIT_TYPES = { bar: 1, barh: 1, line: 1, area: 1, pie: 1, scatter: 1 };
  var AXIS_TYPES = { bar: 1, barh: 1, line: 1, area: 1, effectScatter: 1, pictorialBar: 1 };
  /* Shares of a whole that the legend names (a treemap or sunburst labels its cells). */
  var LEGEND_TYPES = { pie: 1, funnel: 1 };

  function chartPlan(el) {
    var own = attr(el, "data-tb-palette");
    var type = attr(el, "data-tb-echart-type") || attr(el, "data-tb-type") || "bar";
    if (KIT_TYPES.hasOwnProperty(String(type).toLowerCase())) type = String(type).toLowerCase();
    return {
      binding: attr(el, "data-tb-binding"),
      type: type,
      x: attr(el, "data-tb-x"),
      y: splitList(attr(el, "data-tb-y") || ""),
      color: attr(el, "data-tb-color"),
      valueFormat: attr(el, "data-tb-value-format"),
      palette: own ? splitList(own) : null,
      xTitle: attr(el, "data-tb-x-title"),
      yTitle: attr(el, "data-tb-y-title"),
      stack: el.getAttribute("data-tb-stack") !== null,
      mark: attr(el, "data-tb-mark"),
      annotate: attr(el, "data-tb-annotate"),
      facet: attr(el, "data-tb-facet"),
      unit: attr(el, "data-tb-unit"),
      renderer: attr(el, "data-tb-renderer"),
      spark: (" " + (el.className || "") + " ").indexOf(" tb-spark ") !== -1
    };
  }

  /* axis (bar, barh, line, area, …), scatter, or item (pie, funnel, treemap,
   * sunburst: any ECharts series that takes name/value items). */
  function chartKind(plan) {
    var t = plan.type || "bar";
    return t === "scatter" ? "scatter" : AXIS_TYPES.hasOwnProperty(t) ? "axis" : "item";
  }

  /* Series keys in first-seen order over ALL stamped rows: the colour map.
   * A key keeps its slot whatever the selection leaves on screen. */
  function seriesKeys(plan, rows) {
    if (chartKind(plan) === "item") return categories(plan, rows);
    if (plan.color) {
      var keys = [], seen = {};
      rows.forEach(function (r) {
        var g = groupOf(r[plan.color]);
        if (!seen.hasOwnProperty(g)) { seen[g] = 1; keys.push(g); }
      });
      return keys;
    }
    return plan.y.slice();
  }

  function colourOf(plan, ctx, key) {
    var pal = plan.palette && plan.palette.length ? plan.palette : ctx.k.palette;
    if (!pal || !pal.length) return undefined;
    var i = ctx.keys.indexOf(key);
    return pal[(i < 0 ? 0 : i) % pal.length];
  }

  /* "2020=Pandemic; 2022=Rates rise" → [{at: "2020", text: "Pandemic"}, …] */
  function annotations(plan) {
    if (!plan.annotate) return [];
    return String(plan.annotate).split(";").map(function (part) {
      var i = part.indexOf("=");
      return i < 0 ? null : { at: trim(part.slice(0, i)), text: trim(part.slice(i + 1)) };
    }).filter(function (a) { return a && a.at; });
  }

  function marksWanted(plan) {
    return plan.mark ? splitList(String(plan.mark)).map(function (m) {
      return m.toLowerCase();
    }) : [];
  }

  /* A line or area over whole numbers (years owned, a year) spaces them as
   * numbers: the missing steps between them become empty slots, so a gap in
   * the data reads as a gap, not as neighbours. */
  function evenSteps(plan, cats) {
    var t = plan.type;
    if ((t !== "line" && t !== "area") || cats.length < 2) return cats;
    var ns = [], i, step = Infinity;
    for (i = 0; i < cats.length; i++) {
      if (!/^-?\d+$/.test(cats[i])) return cats;
      ns.push(Number(cats[i]));
      if (i && ns[i] <= ns[i - 1]) return cats;
      if (i) step = Math.min(step, ns[i] - ns[i - 1]);
    }
    var span = (ns[ns.length - 1] - ns[0]) / step;
    if (span === cats.length - 1 || span > 400) return cats;
    for (i = 1; i < ns.length; i++) if ((ns[i] - ns[0]) % step) return cats;
    var out = [];
    for (i = 0; i <= span; i++) out.push(String(ns[0] + i * step));
    out.filled = true;
    return out;
  }

  /* Bounds a shared value axis rounds out to (small multiples): drawing
   * only, the extent of the rows' own values. */
  function niceExtent(lo, hi) {
    if (lo === hi) hi = lo + 1;
    var step = Math.pow(10, Math.floor(Math.log(hi - lo) / Math.LN10));
    var err = (hi - lo) / 5 / step;
    step *= err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
    return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
  }

  /* An option for a figure: what a plan and its rows draw, in the house look.
   * ctx: {k: tokens, stamped: the binding's stamped rows (the colour map),
   * hidden: legend keys switched off, xSet / sSet: picked values of the x and
   * series columns (they dim the rest), width, height, zoom, zoomX, trace:
   * the figure id when the trace holds it, out: receives the keyboard stops
   * and, for small multiples, the height they take}. */
  function optionFor(plan, rows, ctx) {
    ctx = ctx || {};
    ctx.k = ctx.k || chartTokens();
    ctx.hidden = ctx.hidden || {};
    ctx.keys = ctx.keys || seriesKeys(plan, ctx.stamped || rows);
    ctx.out = ctx.out || {};
    ctx.width = ctx.width || 600;
    ctx.height = ctx.height || 320;
    var kind = chartKind(plan), opt;
    if (kind === "item") opt = itemOption(plan, rows, ctx);
    else if (kind === "scatter") opt = scatterOption(plan, rows, ctx);
    else opt = axisOption(plan, rows, ctx);
    opt.color = plan.palette && plan.palette.length ? plan.palette : ctx.k.palette;
    opt.animation = ctx.k.motion > 0;
    return opt;
  }

  function seriesDim(s, k) {
    s.itemStyle = extend(s.itemStyle || {}, { opacity: k.dim });
    s.lineStyle = extend(s.lineStyle || {}, { opacity: k.dim });
    if (s.areaStyle) s.areaStyle = extend(s.areaStyle, { opacity: (s.areaStyle.opacity || 0.12) * k.dim });
    if (s.label) s.label = extend(s.label, { opacity: k.dim });
    if (s.endLabel) s.endLabel = extend(s.endLabel, { opacity: k.dim });
  }

  function axisOption(plan, rows, ctx) {
    var k = ctx.k, out = ctx.out;
    var horizontal = plan.type === "barh";
    var type = horizontal ? "bar" : plan.type === "area" ? "line" : plan.type;
    var isBar = type === "bar" || type === "pictorialBar";
    var stacked = !!plan.stack && plan.type !== "line";
    var marks = marksWanted(plan);
    var tick = tickFormatter(plan);
    var trace = ctx.trace || null;
    var panels = [];
    var allCats = evenSteps(plan, categories(plan, rows));
    if (plan.facet) {
      var order = [], byFacet = {};
      (ctx.stamped || rows).forEach(function (r) {
        var f = groupOf(r[plan.facet]);
        if (order.indexOf(f) === -1) order.push(f);
      });
      rows.forEach(function (r) {
        var f = groupOf(r[plan.facet]);
        (byFacet[f] = byFacet[f] || []).push(r);
      });
      order.forEach(function (f) { if (byFacet[f]) panels.push({ title: f, rows: byFacet[f] }); });
    } else {
      panels.push({ title: null, rows: rows });
    }
    var cats = allCats;
    if (ctx.zoom && !plan.facet) {
      cats = allCats.slice(ctx.zoom[0], ctx.zoom[1] + 1);
      if (cats.length < 2) cats = allCats;
    }
    var index = {};
    cats.forEach(function (c, i) { index[c] = i; });

    /* Each panel's series: one per visible key the rows hold. */
    panels.forEach(function (p) {
      p.series = [];
      ctx.keys.forEach(function (key) {
        if (ctx.hidden[key]) return;
        var col = plan.color ? plan.y[0] : key, data = [], any = false, i;
        for (i = 0; i < cats.length; i++) data.push(null);
        p.rows.forEach(function (r) {
          if (plan.color && groupOf(r[plan.color]) !== key) return;
          var c = String(r[plan.x]);
          if (!index.hasOwnProperty(c)) return;
          data[index[c]] = toNum(r[col]);
          any = true;
        });
        if (!any) return;
        p.series.push({ key: key, col: col, name: plan.color ? key : humanise(key), data: data,
                        colour: colourOf(plan, ctx, key), fmt: chartFormatter(plan, rows, col) });
      });
    });

    /* A pick none of this chart's marks carries (a year it does not draw)
     * dims nothing: a chart all faint says nothing. */
    var xSet = ctx.xSet, sSet = ctx.sSet;
    var drawn = function (set, test) {
      if (!set) return null;
      for (var key in set) if (set.hasOwnProperty(key) && test(key)) return set;
      return null;
    };
    xSet = drawn(xSet, function (c) {
      return index.hasOwnProperty(c) && panels.some(function (p) {
        return p.series.some(function (s) { return s.data[index[c]] !== null; });
      });
    });
    sSet = drawn(sSet, function (key) {
      return panels.some(function (p) {
        return p.series.some(function (s) { return s.key === key; });
      });
    });

    var nSeries = panels.length ? Math.max.apply(null, panels.map(function (p) { return p.series.length; })) : 0;
    var labelled = isBar && !stacked && !plan.facet && !plan.spark && !marks.length &&
      nSeries > 0 && nSeries <= 3 && cats.length * nSeries <= (horizontal ? 24 : 12);
    var ends = !isBar && !plan.spark && !plan.facet && marks.indexOf("last") === -1 && nSeries <= 4;
    var r = stacked ? 0 : k.radius;
    /* The text that reads on a bar's fill: the accent's own text or the
     * ink, at 4.5:1; null when neither does. */
    var insideInk = function (fill) {
      var c = [k.onAccent, k.ink].filter(function (x) { return x && contrast(x, fill) >= 4.5; });
      return c.length ? c[0] : null;
    };
    /* Whether every bar's label fits inside its free end, 12px to spare,
     * on the axis the values will be drawn against. */
    var inside = false;
    if (labelled) {
      var lo0 = 0, hi0 = 0, widestLabel = 0;
      panels.forEach(function (p) {
        p.series.forEach(function (s) {
          s.data.forEach(function (v) {
            if (v === null) return;
            lo0 = Math.min(lo0, v);
            hi0 = Math.max(hi0, v);
            widestLabel = Math.max(widestLabel, textWidth(s.fmt(v), 11, k.num));
          });
        });
      });
      var ext = niceExtent(lo0, hi0), span0 = (ext[1] - ext[0]) || 1;
      var catW0 = 0;
      cats.forEach(function (c) { catW0 = Math.max(catW0, textWidth(c, 12, k.font)); });
      var plot = horizontal ? ctx.width - Math.min(catW0, ctx.width * 0.4) - 60 : ctx.height - 60;
      var across = (horizontal ? ctx.height - 40 : ctx.width - 60) / Math.max(1, cats.length) *
        (k.bar / 100) / Math.max(1, nSeries);
      across = Math.min(36, across);
      inside = across >= (horizontal ? 15 : widestLabel + 4);
      panels.forEach(function (p) {
        p.series.forEach(function (s) {
          s.data.forEach(function (v) {
            if (v === null) return;
            var len = Math.abs(v) / span0 * plot;
            if (len < (horizontal ? textWidth(s.fmt(v), 11, k.num) : 11) + 12) inside = false;
          });
        });
      });
    }

    /* Room the labels at the free ends need. */
    var endRoom = 0;
    if (labelled || ends) {
      panels.forEach(function (p) {
        p.series.forEach(function (s) {
          var vals = ends ? s.data.filter(function (v) { return v !== null; }).slice(-1) : s.data;
          vals.forEach(function (v) {
            if (v !== null) endRoom = Math.max(endRoom, textWidth(s.fmt(v), 11, k.num));
          });
        });
      });
    }

    /* Category names: every name on a short axis, wrapped rather than
     * skipped; a long run of numbers (years, months) shows every k-th. */
    var W = ctx.width, H = ctx.height, cols = 1, rowsN = 1;
    if (plan.facet && panels.length) {
      cols = Math.max(1, Math.min(panels.length, Math.floor(W / 260)));
      rowsN = Math.ceil(panels.length / cols);
    }
    var widest = 0;
    cats.forEach(function (c) { widest = Math.max(widest, textWidth(c, 12, k.font)); });
    var catLabel = {};
    var valueTitle = horizontal ? plan.xTitle : plan.yTitle;
    var catTitle = horizontal ? plan.yTitle : plan.xTitle;
    if (horizontal) {
      catLabel = { width: Math.round(Math.min(widest + 2, W * 0.4)), overflow: "break" };
    } else {
      var band = (W / cols - (plan.facet ? 2 * 8 + 8 : 0) - 60) / Math.max(1, cats.length);
      var run = cats.length > 1 && cats.every(function (c) { return /^[\d\s.,:\/-]+$/.test(String(c)); });
      /* A name wraps only between words: a single word wider than its band
       * would be cut mid-word, so the names turn instead. */
      var oneWord = cats.some(function (c) {
        return String(c).split(/\s+/).some(function (w) { return textWidth(w, 12, k.font) + 6 > band; });
      });
      if (widest + 6 <= band) catLabel = { interval: 0 };
      else if (cats.length > 16 || run) catLabel = { interval: "auto", hideOverlap: true };
      else if (band >= 48 && !oneWord) catLabel = { interval: 0, width: Math.floor(band - 6), overflow: "break" };
      /* Set smaller (to 9px) when that fits; turned 30° when not. */
      else if (Math.floor(12 * (band - 6) / widest) >= 9) {
        catLabel = { interval: 0, fontSize: Math.min(11, Math.floor(12 * (band - 6) / widest)) };
      } else catLabel = { interval: 0, rotate: 30 };
    }

    var series = [], xAxis = [], yAxis = [], grid = [], titles = [], stops = [], meta = {};
    var ph = rowsN > 1 ? Math.max(160, Math.floor((H + (rowsN - 1) * 40) / rowsN)) : H;
    var domain = null;
    if (plan.facet) {
      var lo = 0, hi = 0;
      panels.forEach(function (p) {
        var up = {}, down = {};
        p.series.forEach(function (s) {
          s.data.forEach(function (v, i) {
            if (v === null) return;
            if (stacked) {
              if (v >= 0) { up[i] = (up[i] || 0) + v; hi = Math.max(hi, up[i]); }
              else { down[i] = (down[i] || 0) + v; lo = Math.min(lo, down[i]); }
            } else { lo = Math.min(lo, v); hi = Math.max(hi, v); }
          });
        });
      });
      domain = niceExtent(lo, hi);
    }
    var gap = 8;
    panels.forEach(function (p, pi) {
      var col = pi % cols, row = Math.floor(pi / cols);
      var bare = !!plan.facet && !horizontal && pi + cols < panels.length;
      var g = { id: "g" + pi, containLabel: true };
      if (plan.spark) extend(g, { left: 3, right: 3, top: 3, bottom: 3, containLabel: false });
      else if (plan.facet) {
        var pw = W / cols;
        extend(g, { left: col * pw + gap, width: pw - 2 * gap - 8,
                    top: row * ph + 26, height: ph - 26 - (bare ? 12 : 40) });
        titles.push({ id: "t" + pi, text: p.title, left: col * pw + gap, top: row * ph + 2,
                      textStyle: { fontSize: 12, fontWeight: 600, color: k.ink, fontFamily: k.font } });
      } else {
        extend(g, { left: 8 + (valueTitle && !horizontal ? 18 : 0) + (catTitle && horizontal ? 18 : 0),
                    right: (ends ? Math.ceil(endRoom) + 14 : 16) + (labelled && horizontal && !inside ? Math.ceil(endRoom) + 8 : 0) +
                           (marks.length && horizontal ? 56 : 0),
                    top: (labelled && !horizontal && !inside ? 24 : 12) + (marks.length && !horizontal ? 16 : 0),
                    bottom: 8 + (catTitle && !horizontal ? 22 : 0) + (valueTitle && horizontal ? 22 : 0) });
      }
      grid.push(g);
      var catAxis = { id: "c" + pi, gridIndex: pi, type: "category", data: cats, inverse: horizontal,
                      boundaryGap: isBar || !plan.spark,
                      axisLabel: extend({ show: !plan.spark && !bare }, catLabel),
                      axisLine: { show: !plan.spark }, show: !plan.spark };
      var valAxis = { id: "v" + pi, gridIndex: pi, type: "value", show: !plan.spark,
                      axisLabel: { formatter: tick, hideOverlap: true },
                      /* Value ticks thin to what fits: about one per 80px
                       * across the plot, one per 50px up. */
                      splitNumber: horizontal
                        ? Math.max(2, Math.min(6, Math.floor((W / cols - Math.min(widest, W * 0.4) -
                            (labelled ? endRoom : 0) - 40) / 80)))
                        : Math.max(2, Math.min(5, Math.floor((ph - 40) / 50))) };
      if (plan.spark) valAxis.splitLine = { show: false };
      if (domain) { valAxis.min = domain[0]; valAxis.max = domain[1]; }
      if (!plan.facet && catTitle) {
        extend(catAxis, { name: catTitle, nameLocation: "middle",
                          nameGap: horizontal ? Math.round(Math.min(widest, W * 0.4)) + 14 : 30 });
      }
      if (!plan.facet && valueTitle) {
        extend(valAxis, { name: valueTitle, nameLocation: "middle", nameGap: horizontal ? 28 : 44 });
      }
      if (horizontal) { xAxis.push(valAxis); yAxis.push(catAxis); }
      else { xAxis.push(catAxis); yAxis.push(valAxis); }

      p.series.forEach(function (s, si) {
        var id = pi + "|" + s.key;
        var dimS = sSet && !sSet[s.key];
        var on = labelled ? insideInk(s.colour) : null;
        var e = { id: id, type: type, name: s.name, xAxisIndex: pi, yAxisIndex: pi,
                  itemStyle: { color: s.colour }, emphasis: { disabled: true } };
        if (stacked) {
          e.stack = "total" + pi;
          if (isBar) extend(e.itemStyle, { borderColor: k.card, borderWidth: 1 });
        }
        if (type === "line") {
          e.showSymbol = false;
          e.symbolSize = 7;
          e.connectNulls = false;
          if (plan.type === "area") e.areaStyle = { opacity: k.area };
          if (plan.spark) e.symbol = "none";
          e.lineStyle = { width: k.line };
          /* --tb-chart-glow: a faint light under the line, in its own colour. */
          if (k.glow > 0 && !plan.spark && s.colour) {
            extend(e.lineStyle, { shadowBlur: k.glow, shadowColor: withAlpha(s.colour, 0.55) });
          }
          if (ends) {
            e.endLabel = { show: true, distance: 6, color: k.value, fontSize: 11, fontWeight: 600,
                           fontFamily: k.num, formatter: function (q) { return s.fmt(lastOf(q.value)); } };
            e.labelLayout = { moveOverlap: "shiftY" };
          }
        }
        var dimItem = function (v, c) {
          var d = { value: v };
          if (xSet && !xSet[c]) {
            d.itemStyle = { opacity: k.dim };
            d.label = { color: k.label };
          }
          return d;
        };
        e.data = s.data.map(function (v, i) {
          var c = cats[i];
          if (v === null) return null;
          if (isBar) {
            var item = (xSet && !xSet[c]) || v < 0 ? dimItem(v, c) : v;
            /* A bar below zero rounds its own far end, and its label sits past it. */
            if (v < 0) {
              item.itemStyle = extend(item.itemStyle || {},
                { borderRadius: horizontal ? [r, 0, 0, r] : [0, 0, r, r] });
              if (labelled) item.label = extend(item.label || {}, { position: inside && on
                ? (horizontal ? "insideLeft" : "insideBottom") : (horizontal ? "left" : "bottom") });
            }
            return item;
          }
          return v;
        });
        if (isBar) {
          e.itemStyle.borderRadius = horizontal ? [0, r, r, 0] : [r, r, 0, 0];
          if (labelled) {
            /* Inside the free end when every label fits there and reads on
             * the bar's colour; just past it otherwise. */

            e.label = { show: true, distance: 5, fontSize: 11, fontWeight: 600, fontFamily: k.num,
                        position: horizontal ? (inside && on ? "insideRight" : "right")
                          : (inside && on ? "insideTop" : "top"),
                        color: inside && on ? on : k.value,
                        formatter: function (q) { return s.fmt(lastOf(q.value)); } };
            e.labelLayout = { hideOverlap: true };
          }
        }
        /* Points: the author's marks (the series' own high, low, first or
         * last row, labelled with that row's value), a picked category's
         * dot on a line, and the line's last point. */
        var points = [];
        var at = function (i, v) { return horizontal ? [v, i] : [i, v]; };
        var defined = [];
        s.data.forEach(function (v, i) { if (v !== null) defined.push(i); });
        if (marks.length && defined.length) {
          var pick = {};
          marks.forEach(function (mk) {
            var i = null;
            if (mk === "max" || mk === "high" || mk === "min" || mk === "low") {
              defined.forEach(function (j) {
                var better = mk === "max" || mk === "high" ? s.data[j] > s.data[i] : s.data[j] < s.data[i];
                if (i === null || better) i = j;
              });
            } else if (mk === "first") i = defined[0];
            else if (mk === "last") i = defined[defined.length - 1];
            if (i === null) return;
            var word = mk === "max" || mk === "high" ? "High" : mk === "min" || mk === "low" ? "Low" : "";
            if (pick[i]) { if (word && !pick[i].word) pick[i].word = word; return; }
            pick[i] = { i: i, word: word, low: mk === "min" || mk === "low" };
          });
          Object.keys(pick).forEach(function (key) {
            var m = pick[key], v = s.data[m.i], text = (m.word ? m.word + " " : "") + s.fmt(v);
            points.push({ coord: at(m.i, v), value: v, symbol: "circle", symbolSize: isBar ? 0 : 10,
                          itemStyle: { color: k.card, borderColor: s.colour, borderWidth: 2.5 },
                          label: { show: true, color: k.ink, fontSize: 11, fontWeight: 600, fontFamily: k.num,
                                   position: horizontal ? "right" : m.low ? "bottom" : "top",
                                   formatter: (function (t) { return function () { return t; }; })(text) } });
          });
        }
        if (type === "line" && !plan.spark) {
          defined.forEach(function (i) {
            var picked = xSet && xSet[cats[i]];
            var last = i === defined[defined.length - 1] && !(marks.indexOf("last") !== -1);
            if (!picked && !last) return;
            points.push({ coord: at(i, s.data[i]), symbol: "circle", symbolSize: picked ? 8 : 6,
                          itemStyle: { color: s.colour, borderColor: k.card, borderWidth: 1.5 },
                          label: { show: false } });
          });
        }
        if (points.length) {
          e.markPoint = { silent: true, animation: false, data: points };
        }
        /* Annotations: the author's notes at a category, a dashed rule and a word. */
        if (si === 0 && !plan.spark) {
          var notes = annotations(plan).filter(function (a) { return index.hasOwnProperty(a.at); });
          if (notes.length) {
            e.markLine = { silent: true, animation: false, symbol: ["none", "none"],
              lineStyle: { color: k.muted, type: [4, 3], opacity: 0.8, width: 1 },
              data: notes.map(function (a) {
                var d = horizontal ? { yAxis: a.at } : { xAxis: a.at };
                d.label = { formatter: (function (t) { return function () { return t; }; })(a.text),
                            position: "insideEndTop", color: k.muted, fontSize: 11,
                            fontStyle: "italic", fontFamily: k.font };
                return d;
              }) };
          }
        }
        if (dimS) seriesDim(e, k);
        meta[id] = { s: s, panel: p.title };
        series.push(e);
      });

      /* One keyboard stop per category, in reading order. */
      cats.forEach(function (c, i) {
        var rowsOut = [], about = [], first = -1;
        p.series.forEach(function (s) {
          var v = s.data[i];
          if (v === null) return;
          if (first < 0) first = series.length - p.series.length + p.series.indexOf(s);
          rowsOut.push({ colour: s.colour, name: s.name, value: s.fmt(v) });
          var said = measureAbout(s.col);
          if (said && about.indexOf(said) === -1) about.push(said);
        });
        stops.push({ si: first < 0 ? series.length - p.series.length : first, di: i,
                     title: (p.title ? p.title + " · " : "") + c, rows: rowsOut, about: about,
                     pick: allCats.filled && first < 0 ? null : c, empty: first < 0 });
      });
    });
    out.stops = stops;
    out.cats = cats;
    out.allCats = allCats;
    out.height = plan.facet ? rowsN * ph : null;

    var tip = extend(tooltipBase(k), {
      trigger: "axis", enterable: !!trace, confine: true,
      axisPointer: extend(tooltipBase(k).axisPointer, { type: isBar ? "shadow" : "line" }),
      formatter: function (params) {
        var list = isArray(params) ? params : [params];
        if (!list.length) return "";
        var title = list[0].axisValueLabel !== undefined ? list[0].axisValueLabel : list[0].name;
        var rowsOut = [], about = [], panel = null;
        list.forEach(function (q) {
          var m = meta[q.seriesId];
          if (!m) return;
          panel = m.panel;
          var v = m.s.data[q.dataIndex];
          if (v === null || v === undefined) return;
          rowsOut.push({ colour: m.s.colour, name: m.s.name, value: m.s.fmt(v) });
          var said = measureAbout(m.s.col);
          if (said && about.indexOf(said) === -1) about.push(said);
        });
        return tipHtml((panel ? panel + " · " : "") + title, rowsOut, about, trace);
      }
    });
    if (plan.spark) tip.axisPointer = { type: "none" };
    return { tooltip: tip, grid: grid, xAxis: xAxis, yAxis: yAxis, series: series, title: titles };
  }

  function lastOf(v) {
    return v && typeof v === "object" && v.length !== undefined ? v[v.length - 1] : v;
  }

  function scatterOption(plan, rows, ctx) {
    var k = ctx.k, trace = ctx.trace || null, tick = tickFormatter(plan);
    var fx = chartFormatter(plan, rows, plan.x);
    var block = readBlock(plan.binding), labelCol = null;
    /* A point is named by its row's first text column (an issuer, a
     * customer), when the binding has one beside the plotted columns. */
    (block ? block.cols : []).forEach(function (c) {
      if (labelCol || c === plan.x || c === plan.color || plan.y.indexOf(c) !== -1) return;
      if (!isNumericColumn(rows, c)) labelCol = c;
    });
    var sSet = ctx.sSet, series = [], stops = [], meta = {};
    var groups = [];
    ctx.keys.forEach(function (key) {
      if (ctx.hidden[key]) return;
      var col = plan.color ? plan.y[0] : key, pts = [];
      rows.forEach(function (r) {
        if (plan.color && groupOf(r[plan.color]) !== key) return;
        var x = toNum(r[plan.x]), y = toNum(r[col]);
        if (x === null || y === null) return;
        if (ctx.zoomX && (x < ctx.zoomX[0] || x > ctx.zoomX[1])) return;
        pts.push({ x: x, y: y, label: labelCol && r[labelCol] !== undefined ? String(r[labelCol]) : null });
      });
      if (pts.length) groups.push({ key: key, col: col, pts: pts });
    });
    if (sSet && !groups.some(function (g) { return sSet[g.key]; })) sSet = null;
    groups.forEach(function (g) {
      var name = plan.color ? g.key : humanise(g.key), colour = colourOf(plan, ctx, g.key);
      var fy = chartFormatter(plan, rows, g.col), id = "s|" + g.key, si = series.length;
      var e = { id: id, type: "scatter", name: name, itemStyle: { color: colour },
                emphasis: { scale: 1.4 },
                data: g.pts.map(function (p) { return { value: [p.x, p.y], name: p.label || name }; }) };
      if (sSet && !sSet[g.key]) seriesDim(e, k);
      meta[id] = { g: g, name: name, colour: colour, fy: fy };
      series.push(e);
      g.pts.forEach(function (p, di) {
        var title = p.label !== null ? p.label + (plan.color ? " · " + name : "") : name;
        stops.push({ si: si, di: di, title: title,
                     rows: [{ colour: colour, name: humanise(plan.x), value: fx(p.x) },
                            { colour: colour, name: humanise(g.col), value: fy(p.y) }],
                     about: [measureAbout(plan.x), measureAbout(g.col)].filter(Boolean),
                     pick: plan.color ? g.key : null });
      });
    });
    ctx.out.stops = stops;
    var ticksW = 0;
    groups.forEach(function (g) {
      g.pts.forEach(function (p) { ticksW = Math.max(ticksW, textWidth(tick(p.y), 11, k.num)); });
    });
    var axisTitle = { color: k.ink, fontSize: 12, fontWeight: 600, fontFamily: k.font };
    return {
      tooltip: extend(tooltipBase(k), {
        trigger: "item", enterable: !!trace, confine: true,
        formatter: function (q) {
          var m = meta[q.seriesId];
          if (!m) return "";
          var stop = null;
          for (var i = 0; i < stops.length && !stop; i++) {
            if (stops[i].si === q.seriesIndex && stops[i].di === q.dataIndex) stop = stops[i];
          }
          return stop ? tipHtml(stop.title, stop.rows, stop.about, trace) : "";
        }
      }),
      /* Both axes are measures, so each is titled: nothing else says which is which. */
      grid: { left: 8 + 22, right: 16, top: 12, bottom: 8 + 22, containLabel: true },
      xAxis: { type: "value", scale: true, axisLabel: { formatter: tick },
               name: plan.xTitle || humanise(plan.x), nameLocation: "middle", nameGap: 30,
               nameTextStyle: axisTitle, splitLine: { show: false } },
      yAxis: { type: "value", scale: true, axisLabel: { formatter: tick },
               name: plan.yTitle || humanise(plan.y[0]), nameLocation: "middle",
               nameGap: Math.ceil(ticksW) + 16, nameTextStyle: axisTitle },
      series: series
    };
  }

  function itemOption(plan, rows, ctx) {
    var k = ctx.k, t = plan.type, y0 = plan.y[0], trace = ctx.trace || null;
    var fmtV = chartFormatter(plan, rows, y0);
    var cells = t === "treemap" || t === "sunburst";
    var stops = [];
    var data = rows.filter(function (r) { return !ctx.hidden[String(r[plan.x])]; }).map(function (r) {
      var name = String(r[plan.x]), raw = toNum(r[y0]), fill = colourOf(plan, ctx, name);
      /* |value|: a negative slice has no geometry; the readout shows the row's own value. */
      var o = { name: name, value: t === "pie" ? Math.abs(raw || 0) : raw, raw: raw,
                itemStyle: { color: fill } };
      /* Each cell's label in whichever of ink and card reads on its fill. */
      if (cells && fill) o.label = { color: labelOn(fill, k) };
      stops.push({ si: 0, di: stops.length, title: name,
                   rows: [{ colour: fill, name: humanise(y0), value: fmtV(raw) }],
                   about: [measureAbout(y0)].filter(Boolean), pick: name });
      return o;
    });
    /* What the selection did not pick recedes; a pick none of the items
     * carries dims nothing. A cell keeps its label at full strength in the
     * muted text colour, never white on a pale cell. */
    var xSet = ctx.xSet;
    if (xSet && !data.some(function (d) { return xSet[d.name]; })) xSet = null;
    if (xSet) {
      data.forEach(function (d) {
        if (xSet[d.name]) return;
        if (cells && d.itemStyle.color) {
          d.itemStyle.color = withAlpha(d.itemStyle.color, k.dim);
          d.label = { color: k.label };
        } else d.itemStyle.opacity = k.dim;
      });
    }
    var s = { id: "items", type: t, name: humanise(y0), data: data };
    if (t === "pie") {
      /* A donut: the inner radius 60% of the outer. The centre stays empty:
       * no total is drawn, because a chart never computes a number. */
      var R = Math.max(20, Math.min(ctx.width, ctx.height) / 2 - 8);
      extend(s, { radius: [Math.round(R * 0.6), Math.round(R)], center: ["50%", "50%"],
                  avoidLabelOverlap: true, emphasis: { scaleSize: 6 } });
    }
    if (t === "treemap") {
      extend(s, { nodeClick: false, roam: false, left: 0, top: 0, width: "100%", height: "100%",
        label: { position: "insideTopLeft", padding: [8, 10],
                 formatter: function (q) { return "{n|" + q.name + "}\n{v|" + fmtV(q.data && q.data.raw) + "}"; },
                 rich: { n: { fontSize: 12, fontWeight: 600, lineHeight: 17 },
                         v: { fontSize: 11, lineHeight: 15 } } } });
    }
    if (t === "sunburst") s.nodeClick = false;
    ctx.out.stops = stops;
    return {
      tooltip: extend(tooltipBase(k), {
        trigger: "item", enterable: !!trace, confine: true,
        formatter: function (q) {
          var st = stops[q.dataIndex];
          return st ? tipHtml(st.title, st.rows, st.about, trace) : "";
        }
      }),
      series: [s]
    };
  }

  /* `over` deep-merged onto `base`: objects key by key, arrays of objects item
   * by item (series[0] onto series[0]), anything else replaced. */
  function mergeOption(base, over) {
    if (over === undefined) return base;
    if (isArray(over)) {
      if (!isArray(base) || !over.some(isPlainObject)) return over;
      var n = Math.max(base.length, over.length), out = [], i;
      for (i = 0; i < n; i++) out.push(i < over.length ? mergeOption(base[i], over[i]) : base[i]);
      return out;
    }
    if (!isPlainObject(over)) return over;
    var o = isPlainObject(base) ? extend({}, base) : {};
    for (var key in over) if (over.hasOwnProperty(key)) o[key] = mergeOption(o[key], over[key]);
    return o;
  }

  /* An override with its data taken out: on a receipted chart the numbers
   * are the binding's, so a patch styles them and cannot replace them (series
   * data, a dataset, category labels). */
  function withoutData(over) {
    if (!isPlainObject(over)) return over;
    var o = extend({}, over);
    delete o.dataset;
    var strip = function (v, key) {
      if (isArray(v)) return v.map(function (x) { return strip(x, key); });
      if (isPlainObject(v)) { var c = extend({}, v); delete c[key]; return c; }
      return v;
    };
    if (o.series !== undefined) o.series = strip(o.series, "data");
    if (o.xAxis !== undefined) o.xAxis = strip(o.xAxis, "data");
    if (o.yAxis !== undefined) o.yAxis = strip(o.yAxis, "data");
    return o;
  }

  /* Restyle, never re-source: a patch (configureChart, the kit's option)
   * merged onto the built option, every series keeping the data built from
   * the rows. A patch series past the built ones (which could only carry
   * the author's data) is not drawn. */
  function restyle(option, patch) {
    if (!isPlainObject(patch)) return option;
    var built = option.series || [];
    var merged = mergeOption(option, withoutData(patch));
    delete merged.dataset;
    var series = isArray(merged.series) ? merged.series : [merged.series];
    merged.series = built.map(function (s, i) {
      var o = isPlainObject(series[i]) ? series[i] : s;
      o.data = s.data;
      return o;
    });
    return merged;
  }

  /* An author's option (an option-only <EChart>, numbers the page computed)
   * with the values its field did not pick receding to the house dim; a pick
   * none of its marks carries dims nothing. A mark with its own colour (a
   * treemap cell) fades that colour and its label takes the muted text
   * colour; any other mark fades as a whole. */
  function dimOption(opt, set, k) {
    k = k || chartTokens();
    if (!set || !isPlainObject(opt) || !opt.series) return opt;
    var axisCats = function (a) {
      var ax = isArray(a) ? a[0] : a;
      return ax && isArray(ax.data) ? ax.data.map(function (d) {
        return String(isPlainObject(d) ? d.value : d);
      }) : null;
    };
    var cats = axisCats(opt.xAxis) || axisCats(opt.yAxis), hit = false;
    var walk = function (data, byIndex) {
      return data.map(function (d, i) {
        var item = d;
        if (isPlainObject(d) && isArray(d.children)) {
          item = extend(extend({}, d), { children: walk(d.children, false) });
        }
        var name = isPlainObject(d) && d.name !== null && d.name !== undefined ? String(d.name)
          : byIndex && cats ? cats[i] : null;
        if (name === null || name === undefined) return item;
        if (set[name]) { hit = true; return item; }
        var o = isPlainObject(item) ? extend({}, item) : { value: item };
        var own = isPlainObject(o.itemStyle) && typeof o.itemStyle.color === "string";
        o.itemStyle = own
          ? extend(extend({}, o.itemStyle), { color: withAlpha(plainColor(o.itemStyle.color), k.dim) })
          : extend(extend({}, o.itemStyle || {}), { opacity: k.dim });
        if (own) o.label = extend(extend({}, o.label || {}), { color: k.label });
        return o;
      });
    };
    var list = isArray(opt.series) ? opt.series : [opt.series];
    var series = list.map(function (s) {
      return isPlainObject(s) && isArray(s.data) ? extend(extend({}, s), { data: walk(s.data, true) }) : s;
    });
    return hit ? extend(extend({}, opt), { series: series }) : opt;
  }

  /* ── Drawing ── */

  /* The renderer: the figure's own (data-tb-renderer, <Chart renderer>),
   * then the report's (report.json "charts"), then SVG. */
  var _chartsConfig = null;
  function chartsConfig() {
    if (_chartsConfig) return _chartsConfig;
    _chartsConfig = {};
    try {
      var el = document.getElementById("tracebi-charts");
      if (el) _chartsConfig = JSON.parse(el.textContent) || {};
    } catch (e) { /* defensive */ }
    return _chartsConfig;
  }

  function chartOpts(entry) { return entry.el.__tbChart || {}; }

  function rendererOf(entry) {
    var r = entry.plan.renderer || chartOpts(entry).renderer || chartsConfig().renderer;
    return r === "canvas" ? "canvas" : "svg";
  }

  function chartLabel(entry) {
    var o = chartOpts(entry), plan = entry.plan;
    if (o.ariaLabel) return o.ariaLabel;
    var kind = plan.type === "barh" ? "bar" : plan.type;
    return kind + " chart of " + plan.y.map(humanise).join(", ") + " by " +
      humanise(plan.x) + ". Use the arrow keys to read each value.";
  }

  function themeFor(entry, k) {
    var own = chartOpts(entry).theme;
    return own && own !== "auto" ? own : chartTheme(k);
  }

  /* What a click on a mark picks: the kit's onSelect(params) may name the
   * value itself (or null for none). */
  function chooseValue(entry, value, params, event) {
    if (!entry.act) return;
    var o = chartOpts(entry);
    if (typeof o.onSelect === "function") {
      try { value = o.onSelect(params || { name: value }); } catch (e) { return; }
    }
    if (value === null || value === undefined || value === "") return;
    entry.act(String(value), event);
  }

  function initChart(entry, k) {
    var lib = echartsLib();
    entry.renderer = rendererOf(entry);
    if (_printing && entry.renderer === "canvas") entry.renderer = "svg";
    var chart = lib.init(entry.host, themeFor(entry, k), { renderer: entry.renderer });
    entry.chart = chart;
    entry.themeSig = null;
    var zr = chart.getZr ? chart.getZr() : null;
    var kind = chartKind(entry.plan);
    if (zr && kind !== "item") bindPointer(entry, chart, zr, kind);
    if (chart.on) {
      chart.on("click", function (p) {
        if (kind !== "item" || !p || p.componentType !== "series") return;
        chooseValue(entry, p.name, p, p.event && p.event.event);
      });
      /* The first draw's motion: the page reports ready once it settles. */
      if (k.motion > 0) {
        _introPending++;
        var done = false, settle = function () {
          if (done) return;
          done = true;
          _introPending = Math.max(0, _introPending - 1);
        };
        chart.on("finished", settle);
        setTimeout(settle, k.motion + 400);
      }
      var o = chartOpts(entry);
      Object.keys(o.onEvents || {}).forEach(function (name) {
        chart.on(name, function (p) {
          var h = (chartOpts(entry).onEvents || {})[name];
          if (typeof h === "function") h(p, chart);
        });
      });
    }
    bindKeyboard(entry);
  }

  /* A click on a category (its full band, not the 2px of a line) picks it;
   * a drag across a long line or area, or a scatter, zooms to that range and
   * a double-click returns. On a scatter the nearest point within 40px is
   * the one meant. */
  function bindPointer(entry, chart, zr, kind) {
    var press = null;
    var zoomable = function () {
      return kind === "scatter" || (!entry.plan.facet && !entry.plan.spark &&
        (entry.plan.type === "line" || entry.plan.type === "area") && entry.allCats &&
        entry.allCats.length >= 8);
    };
    var inGrid = function (pt) {
      var n = (chart.getOption().grid || []).length || 1;
      for (var i = 0; i < n; i++) {
        try { if (chart.containPixel({ gridIndex: i }, pt)) return i; } catch (e) {}
      }
      return -1;
    };
    var catAt = function (pt, gi) {
      var v = chart.convertFromPixel({ gridIndex: gi }, pt);
      var i = entry.plan.type === "barh" ? v[1] : v[0];
      return Math.max(0, Math.min((entry.cats || []).length - 1, Math.round(i)));
    };
    var nearest = function (pt) {
      var best = null, bd = 40 * 40;
      (entry.stops || []).forEach(function (s) {
        var opt = chart.getOption().series[s.si];
        var d = opt && opt.data[s.di];
        if (!d) return;
        var px = chart.convertToPixel({ seriesIndex: s.si }, d.value);
        var dx = px[0] - pt[0], dy = px[1] - pt[1];
        if (dx * dx + dy * dy < bd) { bd = dx * dx + dy * dy; best = s; }
      });
      return best;
    };
    var box = null;
    var brush = function (x0, x1) {
      if (!box) {
        box = document.createElement("div");
        box.className = "tb-chart-brush";
        entry.host.appendChild(box);
      }
      box.style.left = Math.min(x0, x1) + "px";
      box.style.width = Math.abs(x1 - x0) + "px";
    };
    var unbrush = function () { if (box && box.parentNode) box.parentNode.removeChild(box); box = null; };
    zr.on("mousedown", function (e) {
      var pt = [e.offsetX, e.offsetY];
      press = inGrid(pt) >= 0 ? { x: e.offsetX, y: e.offsetY } : null;
    });
    zr.on("mousemove", function (e) {
      var pt = [e.offsetX, e.offsetY];
      if (press && zoomable() && Math.abs(e.offsetX - press.x) > 4) brush(press.x, e.offsetX);
      if (zr.setCursorStyle && inGrid(pt) >= 0) {
        zr.setCursorStyle(zoomable() ? "crosshair" : entry.act ? "pointer" : "default");
      }
    });
    zr.on("mouseup", function (e) {
      var start = press;
      press = null;
      unbrush();
      if (!start) return;
      var pt = [e.offsetX, e.offsetY], gi = inGrid([start.x, start.y]);
      if (Math.abs(e.offsetX - start.x) > 6 && zoomable() && gi >= 0) {
        if (kind === "scatter") {
          var a = chart.convertFromPixel({ gridIndex: gi }, [Math.min(start.x, e.offsetX), start.y])[0];
          var b = chart.convertFromPixel({ gridIndex: gi }, [Math.max(start.x, e.offsetX), start.y])[0];
          var inside = (entry.stops || []).filter(function (s) {
            var d = chart.getOption().series[s.si].data[s.di];
            return d && d.value[0] >= a && d.value[0] <= b;
          });
          if (inside.length >= 2) { entry.zoomX = [a, b]; drawChart(entry, null, true); }
          return;
        }
        var c0 = catAt([Math.min(start.x, e.offsetX), start.y], gi);
        var c1 = catAt([Math.max(start.x, e.offsetX), start.y], gi);
        if (c1 - c0 < 1) return;
        var base = entry.zoom ? entry.zoom[0] : 0;
        entry.zoom = [base + c0, base + c1];
        drawChart(entry, null, true);
        return;
      }
      var ev = e.event;
      if (kind === "scatter") {
        var hit = nearest(pt);
        if (hit && hit.pick !== null) {
          chooseValue(entry, hit.pick, { name: hit.pick, seriesIndex: hit.si, dataIndex: hit.di,
                                         event: { event: ev } }, ev);
        }
        return;
      }
      gi = inGrid(pt);
      if (gi < 0 || !entry.act) return;
      var i = catAt(pt, gi), cats = entry.cats || [];
      var stop = (entry.stops || [])[gi * cats.length + i];
      /* An empty step (evenSteps) has no value to pick. */
      if (stop && stop.pick === null) return;
      chooseValue(entry, cats[i], { name: cats[i], dataIndex: i, seriesIndex: stop ? stop.si : 0,
                                    event: { event: ev } }, ev);
    });
    zr.on("dblclick", function () {
      if (!entry.zoom && !entry.zoomX) return;
      entry.zoom = null;
      entry.zoomX = null;
      drawChart(entry, null, true);
    });
  }

  /* Arrow keys walk the marks, the readout follows and the value is
   * announced; Enter selects the one focused, Escape hides the readout. */
  function bindKeyboard(entry) {
    var host = entry.host;
    var show = function () {
      var s = (entry.stops || [])[entry.focus];
      if (!s) return;
      try { entry.chart.dispatchAction({ type: "showTip", seriesIndex: s.si, dataIndex: s.di }); } catch (e) {}
      entry.live.textContent = s.title + ": " + s.rows.map(function (r) {
        return r.name + " " + r.value;
      }).join(", ");
    };
    var hide = function () {
      try { entry.chart.dispatchAction({ type: "hideTip" }); } catch (e) {}
    };
    host.addEventListener("keydown", function (e) {
      var n = (entry.stops || []).length, key = e.key;
      if (!n) return;
      if (key === "ArrowRight" || key === "ArrowDown") entry.focus = (entry.focus + 1) % n;
      else if (key === "ArrowLeft" || key === "ArrowUp") entry.focus = (entry.focus - 1 + n) % n;
      else if (key === "Home") entry.focus = 0;
      else if (key === "End") entry.focus = n - 1;
      else if (key === "Enter" || key === " ") {
        var s = entry.stops[entry.focus];
        if (s && s.pick !== null) chooseValue(entry, s.pick, { name: s.pick, seriesIndex: s.si, dataIndex: s.di }, e);
      } else if (key === "Escape") { hide(); return; }
      else return;
      e.preventDefault();
      show();
    });
    host.addEventListener("focus", function () {
      entry.focus = Math.min(entry.focus || 0, Math.max(0, (entry.stops || []).length - 1));
      show();
    });
    host.addEventListener("blur", function (e) {
      if (!(e.relatedTarget && host.contains(e.relatedTarget))) hide();
    });
    /* The readout's Trace link opens the trace at this figure. */
    host.addEventListener("click", function (e) {
      var t = e.target, btn = t && t.closest ? t.closest(".tb-chart-tip-receipt") : null;
      if (!btn) return;
      hide();
      openReceipt(btn.getAttribute("data-tb-receipt-for"));
    });
  }

  /* The legend: small round chips over the chart. On a live page a chip
   * naming a value the selection can name (a pie's category, a chart's
   * series) selects it, as a mark does; otherwise it shows or hides its
   * series (never the last one). */
  function legendFor(entry, k) {
    var host = entry.legend, plan = entry.plan, kind = chartKind(plan);
    while (host.firstChild) host.removeChild(host.firstChild);
    var zoomed = !!(entry.zoom || entry.zoomX);
    var named = kind === "item" ? LEGEND_TYPES.hasOwnProperty(plan.type) : entry.keys.length > 1;
    var own = chartOpts(entry).option;
    if (isPlainObject(own) && own.legend) named = false;
    host.hidden = !(named || zoomed) || plan.spark;
    if (zoomed) {
      var reset = document.createElement("button");
      reset.type = "button";
      reset.className = "tb-legend-item tb-legend-reset";
      reset.textContent = "Reset zoom";
      reset.addEventListener("click", function () {
        entry.zoom = null;
        entry.zoomX = null;
        drawChart(entry, null, true);
      });
      host.appendChild(reset);
    }
    if (!named) return;
    var keyColumn = kind === "item" ? plan.x : plan.color;
    var on = !highlightOff(entry.el);
    var select = keyColumn && on && selectableField(keyColumn) ? markAction(keyColumn) : null;
    var picked = keyColumn ? pickedSet(keyColumn) : null;
    var swatch = plan.type === "line" || plan.type === "area" ? "line"
      : plan.type === "scatter" ? "dot" : "box";
    entry.keys.forEach(function (key) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tb-legend-item";
      if (select) {
        var is = !!(picked && picked[key]);
        btn.className += " tb-legend-item--select";
        btn.__tbKey = key;
        btn.setAttribute("aria-pressed", is ? "true" : "false");
        btn.setAttribute("aria-label", (is ? "clear " : "select ") + key);
        if (picked && !is) addClass(btn, "tb-dimmed");
        btn.addEventListener("click", function (event) { select(key, event); });
      } else {
        btn.setAttribute("aria-pressed", entry.hidden[key] ? "false" : "true");
        btn.addEventListener("click", function () {
          var visible = entry.keys.filter(function (x) { return !entry.hidden[x]; });
          if (!entry.hidden[key] && visible.length === 1) return; /* keep one */
          entry.hidden[key] = !entry.hidden[key];
          drawChart(entry, null, true);
        });
      }
      var sw = document.createElement("span");
      sw.className = "tb-legend-swatch tb-legend-swatch--" + swatch;
      sw.style.background = colourOf(plan, { k: k, keys: entry.keys }, key) || "";
      var label = document.createElement("span");
      label.textContent = kind === "item" || plan.color ? key : humanise(key);
      btn.appendChild(sw);
      btn.appendChild(label);
      host.appendChild(btn);
    });
  }

  /* Draw (or redraw) one chart from *rows* (default: what it draws now). */
  function drawChart(entry, rows, animate) {
    if (!echartsLib()) return;
    if (!rows) rows = entryRows(entry);
    entry.rows = rows;
    var W = entry.surface.clientWidth;
    entry.width = W;
    if (!W) return; /* a hidden tab: drawn when shown */
    var plan = entry.plan, o = chartOpts(entry);
    var k = chartTokens(entry.el);
    if (o.theme && o.theme !== "auto") k.palette = [];
    legendFor(entry, k);
    var H = o.height ? Number(o.height)
      : plan.spark ? entry.height : Math.max(200, entry.height - entry.legend.offsetHeight - 8);
    var on = !highlightOff(entry.el);
    var kind = chartKind(plan);
    var trace = entry.el.id && receiptRowFor(entry.el.id) ? entry.el.id : null;
    var ctx = { k: k, stamped: (readBlock(entry.binding) || { rows: rows }).rows, hidden: entry.hidden,
                keys: entry.keys, width: W, height: H, zoom: entry.zoom, zoomX: entry.zoomX,
                trace: plan.spark ? null : trace,
                xSet: on && kind !== "scatter" ? pickedSet(plan.x) : null,
                sSet: on && plan.color ? pickedSet(plan.color) : null, out: {} };
    var option = optionFor(plan, rows, ctx);
    if (ctx.out.height) H = ctx.out.height;
    entry.stops = ctx.out.stops || [];
    entry.cats = ctx.out.cats;
    entry.allCats = ctx.out.allCats;
    if (entry.focus === undefined || entry.focus >= entry.stops.length) entry.focus = 0;
    /* The kit's option (an object, or a function of the rows) and then the
     * page's configureChart patch: restyle, never re-source. */
    var own = typeof o.option === "function" ? o.option(copyRows(rows)) : o.option;
    if (own) option = restyle(option, own);
    var patch = entry.el.id ? _patches[entry.el.id] : null;
    if (patch) option = restyle(option, patch);
    option.aria = { enabled: true, decal: { show: false },
                    label: { description: chartLabel(entry) } };
    option.animation = !!animate && k.motion > 0;
    entry.host.style.height = H + "px";
    var sig = tokenSig(k);
    if (!entry.chart) initChart(entry, k);
    else {
      if (sig !== entry.themeSig && entry.chart.setTheme && !(o.theme && o.theme !== "auto")) {
        entry.chart.setTheme(chartTheme(k));
      }
      if (entry.chart.getWidth && (entry.chart.getWidth() !== W || entry.chart.getHeight() !== H)) {
        entry.chart.resize();
      }
    }
    entry.themeSig = sig;
    /* The same series as before move to their new values (the motion of an
     * update); a different set is drawn afresh, so no series index is left
     * pointing at one that has gone. */
    var ids = (option.series || []).map(function (s) { return s.id; }).join("\n") + "|" +
      (option.grid || []).length;
    entry.chart.setOption(option, ids === entry.ids
      ? { replaceMerge: ["series", "xAxis", "yAxis", "grid", "title"] } : { notMerge: true });
    entry.ids = ids;
    entry.act = (kind === "axis" && !plan.spark) || kind === "item" ? markAction(plan.x)
      : kind === "scatter" && plan.color ? markAction(plan.color) : null;
    if (entry.act) addClass(entry.el, "tb-selectable"); else removeClass(entry.el, "tb-selectable");
    entry.host.setAttribute("aria-label", chartLabel(entry));
    /* The SVG states its own drawing box, so printed it scales to the page
     * as vectors instead of overflowing it. */
    var svg = entry.renderer === "svg" ? entry.host.querySelector("svg") : null;
    if (svg) svg.setAttribute("viewBox", "0 0 " + W + " " + H);
  }

  function tokenSig(k) {
    return JSON.stringify([k.palette, k.ink, k.card, k.grid, k.label, k.value, k.font, k.num,
                           k.tipBg, k.tipInk, k.axis, k.glow, k.radius, k.bar, k.dim]);
  }

  function copyRows(rows) {
    return rows.map(function (r) {
      var o = {}, key;
      for (key in r) if (r.hasOwnProperty(key)) o[key] = r[key];
      return o;
    });
  }

  function startChart(el, plan, block) {
    var fb = el.querySelector(".tb-chart-fallback");
    if (fb) el.removeChild(fb);
    /* The figure's own height (CSS, else the 320px minimum), read once:
     * reading it after drawing would measure the chart itself. */
    var height = plan.spark ? (el.clientHeight || 44) : Math.max(320, el.clientHeight || 0);
    var surface = document.createElement("div");
    surface.className = "tb-chart";
    var legend = document.createElement("div");
    legend.className = "tb-legend-row";
    legend.hidden = true;
    var host = document.createElement("div");
    host.className = "tb-chart-host";
    host.setAttribute("role", "img");
    host.setAttribute("aria-roledescription", "chart");
    host.setAttribute("tabindex", "0");
    var live = document.createElement("div");
    live.className = "tb-sr-only";
    live.setAttribute("aria-live", "polite");
    surface.appendChild(legend);
    surface.appendChild(host);
    surface.appendChild(live);
    el.appendChild(surface);
    var entry = { el: el, binding: plan.binding, plan: plan, surface: surface, legend: legend,
                  host: host, live: live, hidden: {}, height: height, focus: 0,
                  keys: seriesKeys(plan, block.rows) };
    _charts.push(entry);
    el.__tbRedraw = function () { drawChart(entry, null, false); };
    drawChart(entry, entryRows(entry), true);
    watchCharts();
    return entry;
  }

  function disposeChart(entry) {
    try { if (entry.chart) entry.chart.dispose(); } catch (e) {}
    entry.chart = null;
  }

  /* A redraw when the page's ground changes (data-tb-mode, the reader's
   * system preference) and a resize when a chart's box does. */
  var _chartWatch = false;
  function watchCharts() {
    if (_chartWatch || typeof document === "undefined") return;
    _chartWatch = true;
    var pending = false;
    var redrawAll = function () {
      if (pending) return;
      pending = true;
      setTimeout(function () {
        pending = false;
        for (var i = 0; i < _charts.length; i++) {
          try {
            if (tokenSig(chartTokens(_charts[i].el)) !== _charts[i].themeSig) {
              drawChart(_charts[i], _charts[i].rows, false);
            }
          } catch (e) { /* defensive */ }
        }
      }, 0);
    };
    try {
      if (typeof MutationObserver !== "undefined") {
        new MutationObserver(redrawAll).observe(document.documentElement,
          { attributes: true, attributeFilter: ["data-tb-mode", "class"] });
      }
      var mq = root.matchMedia ? root.matchMedia("(prefers-color-scheme: dark)") : null;
      if (mq && mq.addEventListener) mq.addEventListener("change", redrawAll);
      else if (mq && mq.addListener) mq.addListener(redrawAll);
    } catch (e) {}
    if (root.addEventListener) {
      var later = false;
      root.addEventListener("resize", function () {
        if (later) return;
        later = true;
        setTimeout(function () { later = false; resizeCharts(); }, 120);
      });
    }
    if (typeof ResizeObserver !== "undefined") {
      _chartResize = new ResizeObserver(function () {
        if (_resizeLater) return;
        _resizeLater = true;
        setTimeout(function () { _resizeLater = false; resizeCharts(); }, 60);
      });
    }
  }
  var _chartResize = null, _resizeLater = false;

  /* Printed, every chart is drawn at its printed width with no motion, and
   * a canvas chart prints as vectors: it is drawn by the SVG renderer while
   * the page prints, and by canvas again after. */
  function printCharts(on) {
    for (var i = 0; i < _charts.length; i++) {
      var entry = _charts[i];
      try {
        if (entry.chart && entry.renderer === "canvas" && on) disposeChart(entry);
        else if (entry.chart && !on && entry.renderer !== rendererOf(entry)) disposeChart(entry);
        drawChart(entry, entry.rows, false);
      } catch (e) { /* defensive */ }
    }
  }

  function hydrateCharts() {
    fresh(figureEls("chart"), "chart").forEach(function (el) {
      try {
        if (!echartsLib()) return; /* no chart library: the no-JS picture stays */
        var block = readBlock(attr(el, "data-tb-binding"));
        if (!block || !block.rows.length) return;
        var plan = chartPlan(el);
        if (!plan.x || !plan.y.length) return;
        var entry = startChart(el, plan, block);
        if (_chartResize) _chartResize.observe(entry.surface);
      } catch (e) { /* defensive */ }
    });
  }

  /* The page's filter controls for *column*: a click on a mark sets them. */
  function filterControlsFor(column) {
    if (typeof document === "undefined") return [];
    return controlEls("data-tb-filter").filter(function (el) {
      return attr(el, "data-tb-column") === column;
    });
  }

  function filterTo(column, value) {
    var controls = filterControlsFor(column);
    if (!controls.length) return false;
    var next = controls[0].value === String(value) ? "All" : String(value);
    controls.forEach(function (el) {
      var has = false;
      for (var i = 0; i < el.options.length; i++) {
        if (el.options[i].value === next && !el.options[i].disabled) has = true;
      }
      if (!has) return;
      el.value = next;
      var ev;
      try { ev = new Event("change"); }
      catch (e) { ev = document.createEvent("Event"); ev.initEvent("change", true, true); }
      el.dispatchEvent(ev);
    });
    return true;
  }

  /* What a click on a mark of *column* does: on a live page whose slice
   * carries the column, it writes the selection state itself (no control
   * needed; shift adds a value, the same value again removes it); on a page
   * with no slice, it sets the page's filter control for the column, as it
   * always has. null: the mark selects nothing. */
  function markAction(column) {
    if (selectableField(column)) {
      return function (value, event) { toggleValue(column, String(value), !!(event && event.shiftKey)); };
    }
    if (filterControlsFor(column).length) return function (value) { filterTo(column, value); };
    return null;
  }

  /* The measures' own descriptions, from the semantic contract the build
   * embedded (the manifest's measure definitions): read once. */
  var _measureAbout = null;
  function pageContracts() {
    var blocks = typeof document === "undefined" ? []
      : document.querySelectorAll('script[id^="tb-semantic-contract-"]');
    var out = [];
    for (var i = 0; i < blocks.length; i++) {
      try { out.push(JSON.parse(blocks[i].textContent)); } catch (e) {}
    }
    return out;
  }
  function measureIndex(contracts) {
    var out = {};
    (contracts || []).forEach(function (c) {
      ((c && c.measures) || []).forEach(function (m) {
        if (m && m.name && m.description && !out.hasOwnProperty(m.name)) {
          out[m.name] = String(m.description);
        }
      });
    });
    return out;
  }
  function measureAbout(col) {
    if (_measureAbout === null) _measureAbout = measureIndex(pageContracts());
    return _measureAbout.hasOwnProperty(col) ? _measureAbout[col] : null;
  }

  function receiptRowFor(id) {
    if (typeof document === "undefined") return null;
    var rows = document.querySelectorAll(".tb-receipt-row[data-tb-receipt-fig]");
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].getAttribute("data-tb-receipt-fig") === id) return rows[i];
    }
    return null;
  }

  /* Open the receipt drawer at one figure's record. */
  function openReceipt(id) {
    var row = receiptRowFor(String(id));
    var drawer = receiptDrawer();
    if (!row || !drawer) return false;
    setReceiptOpen(true);
    var scroll = drawer.querySelector(".tb-receipt-scroll") || drawer;
    scroll.scrollTop = Math.max(0, row.offsetTop - 8);
    addClass(row, "tb-receipt-row--here");
    setTimeout(function () { removeClass(row, "tb-receipt-row--here"); }, 1600);
    return true;
  }

  /* ── Code-drawn figures — tracebi.draw ─────────────────────────────────
   * A custom figure (data-tb-figure="custom") is drawn by the author's
   * script.js, typically with the inlined d3 (report.json "libs": ["d3"]).
   * draw(figureId, fn) calls fn(surface, rows, theme): surface is an empty
   * <div> inside the figure (cleared before every call, so the receipt badge
   * the runtime pins to the figure survives), rows are the figure binding's
   * rows as the page's filters and search currently leave them, and theme is
   * tracebi.theme(). fn runs again whenever those rows change or the figure
   * is resized, so a hand-drawn figure follows the theme and the page's
   * filters with no wiring of its own. The rows are copies of the same
   * stamped rows every other figure reads: drawing cannot add a number. */
  var _drawers = []; /* { el, binding, fn, surface, width } */
  var _drawReady = false;

  /* The page's design tokens, resolved: what a hand-drawn figure colours
   * itself with so it matches the declared figures around it. */
  function theme() {
    var out = { palette: cssPalette() }, cs, names, i;
    if (typeof getComputedStyle === "undefined") return out;
    cs = getComputedStyle(document.documentElement);
    names = ["ink", "muted", "rule", "bg", "surface", "accent", "good", "bad",
             "font", "mono"];
    for (i = 0; i < names.length; i++) out[names[i]] = cssVar(cs, "--tb-" + names[i]);
    return out;
  }

  /* A figure inside a hidden tab measures 0 wide: it is drawn when it is
   * shown (the tab switch remeasures through resizeCharts). */
  function drawEntry(entry) {
    var surface = entry.surface;
    entry.width = surface.clientWidth;
    if (!entry.width) return;
    while (surface.firstChild) surface.removeChild(surface.firstChild);
    try { entry.fn(surface, filteredRows(entry.binding).map(function (r) {
      var o = {}, k;
      for (k in r) if (r.hasOwnProperty(k)) o[k] = r[k];
      return o;
    }), theme()); } catch (e) { /* an author's drawing must not stop the rest */ }
  }

  function startDrawer(entry) {
    var el = document.getElementById(entry.id);
    if (!el) return;
    entry.el = el;
    entry.binding = attr(el, "data-tb-binding");
    var surface = document.createElement("div");
    surface.className = "tb-draw";
    el.appendChild(surface);
    entry.surface = surface;
    drawEntry(entry);
  }

  function draw(figureId, fn) {
    if (typeof fn !== "function" || typeof document === "undefined") return;
    var entry = { id: String(figureId), fn: fn };
    _drawers.push(entry);
    if (_drawReady) startDrawer(entry);
  }

  function redrawResized() {
    for (var i = 0; i < _drawers.length; i++) {
      var d = _drawers[i];
      if (d.surface && d.surface.clientWidth !== d.width) drawEntry(d);
    }
  }

  function hydrateDrawn() {
    _drawReady = true;
    for (var i = 0; i < _drawers.length; i++) startDrawer(_drawers[i]);
    if (_drawers.length && root.addEventListener) {
      var pending = false;
      root.addEventListener("resize", function () {
        if (pending) return;
        pending = true;
        var later = typeof requestAnimationFrame === "function"
          ? requestAnimationFrame : function (f) { setTimeout(f, 16); };
        later(function () { pending = false; redrawResized(); });
      });
    }
  }

  /* ── Receipt badges — provenance from the manifest-derived config only.
   *    Author CSS can restyle a badge; the runtime never lets a grey one
   *    become green, because the class is chosen from provenance here. ──── */

  /* The badge word is what a non-technical reviewer reads, so it must state
   * the actual guarantee, not imply "correct/audited". A figure a re-runnable
   * query backs carries the verdict chip (.tb-verdict) with this file's own
   * state: "Draft" on a working preview, "Not checked" on a built file. It is
   * never green here: only a host that re-ran the queries may say Reproduces.
   * Grey is computed in python (not query-reproducible); amber is an honest
   * unbacked figure. The provenance KEY stays as-is. */
  var _BADGES = {
    verified:   { cls: "tb-verdict", verdict: true },
    derived:    { cls: "tb-badge--derived",    text: "python-derived" },
    unverified: { cls: "tb-badge--unverified", text: "unverified" }
  };

  /* A <table> is not a reliable containing block for the absolute badge —
   * it would escape to the nearest positioned ancestor, often the page.
   * Wrap it in a positioned div (.tb-badge-anchor, tracebi.css) so the
   * badge pins to the table's own corner. Idempotent: an existing wrapper
   * is reused. */
  function badgeHost(host) {
    if (host.tagName !== "TABLE") return host;
    var parent = host.parentNode;
    if (!parent) return host;
    if ((" " + parent.className + " ").indexOf(" tb-badge-anchor ") !== -1) {
      return parent;
    }
    var wrap = document.createElement("div");
    wrap.className = "tb-badge-anchor";
    parent.insertBefore(wrap, host);
    wrap.appendChild(host);
    return wrap;
  }

  function hydrateBadges() {
    var el = document.getElementById("tracebi-figures");
    if (!el) return; /* no config block → no badges, no errors */
    var cfg;
    try { cfg = JSON.parse(el.textContent); } catch (e) { return; }
    if (!cfg || cfg.badges !== true || !cfg.figures || !cfg.figures.length) return;
    cfg.figures.forEach(function (fig) {
      try {
        if (!fig || !fig.id) return;
        var spec = _BADGES[fig.provenance];
        if (!spec) return; /* unknown provenance never guesses a colour */
        var host = document.getElementById(fig.id);
        if (!host) return;
        var anchor = badgeHost(host);
        if (anchor.querySelector(".tb-badge")) return;
        var badge = document.createElement("span");
        badge.className = "tb-badge " + spec.cls;
        if (spec.verdict) {
          badge.__tbFig = host;
          var state = verdictState();
          badge.setAttribute("data-tb-verdict", state);
          badge.textContent = _VERDICTS[state].text;
          badge.title = _VERDICTS[state].tip;
        } else {
          badge.textContent = spec.text;
        }
        if (fig.note) badge.title = fig.note;
        anchor.insertBefore(badge, anchor.firstChild);
      } catch (e) { /* defensive */ }
    });
  }

  /* ── Controls — filters and search (the control grammar) ───────────────
   * Controls hydrate AFTER figures so the registries they refresh exist.
   * Unknown bindings do nothing loudly-silently: no console under the
   * CSP'd page — a title note on the control, and nothing else touched. */

  function controlEls(kind) {
    var sel = "[" + kind + "][data-tb-binding]";
    return Array.prototype.slice.call(document.querySelectorAll(sel));
  }

  function noteUnknown(el, what) {
    try { el.title = what; } catch (e) { /* defensive */ }
  }

  function paintValues(binding, rows) {
    var row = rows && rows.length ? rows[0] : null;
    figureEls("value").forEach(function (el) {
      try {
        if (attr(el, "data-tb-binding") !== binding) return;
        if (!row) return;
        var cell = attr(el, "data-tb-cell");
        if (!cell) {
          var keys = [], k;
          for (k in row) if (row.hasOwnProperty(k)) keys.push(k);
          if (keys.length !== 1) return;
          cell = keys[0];
        }
        var raw = row[cell];
        if (raw === undefined || raw === null || raw === "") return;
        var text = raw;
        var name = valueFormat(el, rows, cell);
        if (name) {
          var n = toNum(raw);
          if (n !== null) {
            var formatted = applyNamedFormat(n, name);
            if (formatted !== null) text = formatted;
          }
        }
        var target = el.querySelector(".tb-kpi-value") || el;
        target.textContent = text;
        markDirection(el, target, raw);
      } catch (e) { /* defensive */ }
    });
  }

  /* The host bridge's post, once a window embeds this page (hostBridge). */
  var _hostPost = null;

  /* Set the page's selection, as its filters would ({field: value or
   * [values]}; {} is every row). Only a live page has one: a page with no
   * slice has nothing to recompute from, and ignores it. */
  function setSelection(filters) {
    if (!_calc) return;
    _calc.state = offered(_calc, normalSelection(filters)) || {};
    _calc.sources = {};
    selectionChanged();
  }

  function selectionSlug(filters) {
    var parts = [], k, s, v;
    for (k in filters) {
      if (!filters.hasOwnProperty(k)) continue;
      v = filters[k];
      parts.push(String(k).split(".").pop() + "=" + (isArray(v) ? v.map(liveCell).join("+")
        : (v && typeof v === "object") ? fieldText(k, v) : v));
    }
    s = parts.join("_") || "authored";
    return s.replace(/[^A-Za-z0-9._=-]+/g, "_").slice(0, 80);
  }

  function selectionCsv(rows) {
    if (!rows || !rows.length) return "";
    var cols = [], k, i, lines, r;
    for (k in rows[0]) if (rows[0].hasOwnProperty(k)) cols.push(k);
    function cell(v) {
      if (v === null || v === undefined) return "";
      var s = String(v);
      if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
      return s;
    }
    lines = [cols.join(",")];
    for (i = 0; i < rows.length; i++) {
      r = rows[i];
      lines.push(cols.map(function (c) { return cell(r[c]); }).join(","));
    }
    return lines.join("\n");
  }

  function downloadSelection() {
    var filters, groups = {}, k, name, header, body, blob, url, a;
    if (_lastSelection && _lastSelection.figures) {
      filters = _lastSelection.filters || {};
      _lastSelection.figures.forEach(function (fig) {
        if (fig.binding && fig.rows) groups[fig.binding] = fig.rows;
      });
    } else {
      var cfg = selectionConfig() || {};
      filters = cfg.filters || {};
      controlEls("data-tb-download").forEach(function (el) {
        var binding = attr(el, "data-tb-binding");
        var block = binding && readBlock(binding);
        if (block) groups[binding] = block.rows;
      });
      if (!Object.keys) {
        /* ES5: collect bindings from figures instead. */
      }
      figureEls("table").concat(figureEls("chart")).concat(figureEls("value"))
        .forEach(function (el) {
          var binding = attr(el, "data-tb-binding");
          var block = binding && readBlock(binding);
          if (binding && block && !groups[binding]) groups[binding] = block.rows;
        });
    }
    header = "# selection: " + (describeSelection(normalSelection(filters)) || "authored");
    for (name in groups) {
      if (!groups.hasOwnProperty(name)) continue;
      body = header + "\n" + selectionCsv(groups[name]);
      blob = new Blob([body], { type: "text/csv" });
      url = URL.createObjectURL(blob);
      a = document.createElement("a");
      a.href = url;
      a.download = name + "--" + selectionSlug(filters) + ".csv";
      a.click();
      URL.revokeObjectURL(url);
    }
  }

  function paintSelectionReceipt(payload) {
    var line = document.getElementById("tb-selection-status");
    if (!line || !payload) return;
    var filters = payload.filters || {}, parts = [], k, text;
    for (k in filters) if (filters.hasOwnProperty(k)) parts.push(k + " = " + filters[k]);
    text = "selection: " + (parts.length ? parts.join(", ") : "no extra cut");
    text += payload.local ? " · local" : " · authored";
    line.textContent = text;
  }

  /* Every binding the page embeds, by name. */
  function allBindings() {
    var els = document.querySelectorAll('script[type="application/json"][id^="tracebi-data-"]');
    var out = [];
    for (var i = 0; i < els.length; i++) out.push(els[i].id.slice(13));
    return out;
  }

  /* data-tb-binding="*" on a page with no slice: one filter for the whole
   * page. It subsets the rows of every binding that has the column — each
   * binding's tables and charts redraw — and never touches a value figure:
   * a KPI stays the stamped total. (On a live page every filter is a page
   * filter and recomputes the KPI too: hydrateCalcControls.) */
  function pageFilter(el, column) {
    var targets = allBindings().filter(function (b) {
      var blk = readBlock(b);
      return blk && blk.cols.indexOf(column) !== -1;
    });
    if (!column || !targets.length) { noteUnknown(el, "no binding has column: " + column); return; }
    var values = [];
    targets.forEach(function (b) {
      readBlock(b).rows.forEach(function (r) {
        var v = r[column];
        if (v === undefined) return;
        v = String(v);
        if (values.indexOf(v) === -1) values.push(v);
      });
    });
    values.sort();
    ["All"].concat(values).forEach(function (v) {
      var o = document.createElement("option");
      o.value = v;
      o.textContent = v;
      el.appendChild(o);
    });
    el.addEventListener("change", function () {
      targets.forEach(function (b) {
        var view = viewOf(b);
        if (el.value === "All") delete view.filters[column];
        else view.filters[column] = el.value;
        refreshBinding(b);
      });
    });
  }

  /* A filter that subsets one binding's stamped rows (or, with
   * data-tb-binding="*", every binding that has the column). */
  function plainFilter(el) {
    try {
      var binding = attr(el, "data-tb-binding");
      var column = attr(el, "data-tb-column");
      if (binding === "*") { pageFilter(el, column); return; }
      var block = readBlock(binding);
      if (!block) { noteUnknown(el, "unknown binding: " + binding); return; }
      if (!column || block.cols.indexOf(column) === -1) {
        noteUnknown(el, "unknown column: " + column);
        return;
      }
      /* Sorted distinct values from the stamped rows, plus "All". */
      var values = [];
      block.rows.forEach(function (r) {
        var v = r[column];
        if (v === undefined) return;
        v = String(v);
        if (values.indexOf(v) === -1) values.push(v);
      });
      values.sort();
      var all = document.createElement("option");
      all.value = "All";
      all.textContent = "All";
      el.appendChild(all);
      values.forEach(function (v) {
        var o = document.createElement("option");
        o.value = v;
        o.textContent = v;
        el.appendChild(o);
      });
      el.addEventListener("change", function () {
        var view = viewOf(binding);
        if (el.value === "All") delete view.filters[column];
        else view.filters[column] = el.value;
        refreshBinding(binding);
      });
    } catch (e) { /* defensive */ }
  }

  function hydrateControls() {
    if (_calc) {
      try { hydrateCalcControls(); } catch (e) { /* defensive */ }
      try { hydrateRanges(); } catch (e) { /* defensive */ }
    } else fresh(controlEls("data-tb-filter"), "filter").forEach(plainFilter);
    fresh(controlEls("data-tb-search"), "search").forEach(function (el) {
      try {
        var binding = attr(el, "data-tb-binding");
        if (!readBlock(binding)) {
          noteUnknown(el, "unknown binding: " + binding);
          return;
        }
        el.addEventListener("input", function () {
          viewOf(binding).search = trim(el.value || "").toLowerCase();
          refreshBinding(binding);
        });
      } catch (e) { /* defensive */ }
    });
  }

  /* ── The live page — a selection recomputes every figure it can ────────
   * A page built with a slice (report.json "embed"; tracebi/reports/slice.py)
   * carries #tracebi-calc-plans, every binding's calc plan or why it is
   * fixed, and one Parquet block per fact. tracebi-calc.js
   * (window.tracebiCalc) runs a binding's plan over its fact's slice under
   * the page's selection state: the binding's own query, answered here
   * under the reader's filters, so its result is a query result and is
   * painted through the same path as a stamped row. What the engine cannot
   * run keeps its build value and says so (data-tb-fixed); a figure the
   * selection cannot reach says that too (data-tb-unfiltered-by). The state
   * lives in the URL hash (#sel=), so a link carries the view. While the
   * state is the authored one the page is exactly as built: the stamped
   * rows and the file's own chip. Nothing persists. */

  var _calc = null;
  var _liveBlocks = {}; /* binding → {cols, rows, csv}, as readBlock gives */
  var RANGE_KEYS = ["gt", "gte", "lt", "lte"];

  function isArray(v) { return Object.prototype.toString.call(v) === "[object Array]"; }
  function errorText(e) { return e && e.message ? e.message : String(e); }

  /* A selection as the engine reads it: {field: [values]} or a range
   * {field: {gte|gt|lte|lt: v}}. The authored selection block spells a
   * single value as a scalar and may use {"in": [...]} or {"eq": v}; an
   * empty list selects nothing and is dropped. */
  function normalSelection(raw) {
    var out = {}, k, v, keys, i, range;
    if (!raw || typeof raw !== "object") return out;
    for (k in raw) {
      if (!raw.hasOwnProperty(k)) continue;
      v = raw[k];
      if (v === null || v === undefined) continue;
      if (isArray(v)) {
        if (v.length) out[k] = v.slice();
      } else if (typeof v === "object") {
        if (isArray(v["in"])) { if (v["in"].length) out[k] = v["in"].slice(); continue; }
        if (v.hasOwnProperty("eq")) { out[k] = [v.eq]; continue; }
        keys = Object.keys(v);
        range = {};
        for (i = 0; i < keys.length; i++) {
          if (RANGE_KEYS.indexOf(keys[i]) === -1) { range = null; break; }
          range[keys[i]] = v[keys[i]];
        }
        if (range && keys.length) out[k] = range;
      } else {
        out[k] = [v];
      }
    }
    return out;
  }

  /* Two selections are the same view when they select the same values,
   * whatever order a control listed them in. */
  function selectionKey(sel) {
    return JSON.stringify(Object.keys(sel || {}).sort().map(function (k) {
      var v = sel[k];
      return [k, isArray(v) ? v.map(String).sort() : v];
    }));
  }

  /* The hash holds key=value pairs joined by "&", as the kit's useUrlState
   * writes them (#view=Holdings&sel=...), so the selection and an app's own
   * state share the address without either erasing the other. */
  function hashParts() {
    var out = [], hash = "";
    try { hash = String(root.location.hash || "").replace(/^#/, ""); } catch (e) { return out; }
    hash.split("&").forEach(function (part) {
      if (!part) return;
      var i = part.indexOf("=");
      out.push([i < 0 ? part : part.slice(0, i), i < 0 ? "" : part.slice(i + 1)]);
    });
    return out;
  }

  function hashSelection() {
    var parts = hashParts(), i;
    for (i = 0; i < parts.length; i++) {
      if (parts[i][0] !== "sel") continue;
      try { return normalSelection(JSON.parse(decodeURIComponent(parts[i][1]))); }
      catch (e) { return null; }
    }
    return null;
  }

  /* The state in the address, so a reload or a shared link opens the same
   * view; the authored state leaves no sel= at all. */
  function writeHash() {
    try {
      if (!root.history || !root.history.replaceState) return;
      /* A page an app shows in a srcdoc frame has no address anyone sees or
       * shares, and a browser may hand a re-created frame the hash of the one
       * it replaced, so a rebuilt report would come up still filtered. */
      if (String(root.location.href || "").indexOf("about:srcdoc") === 0) return;
      var parts = hashParts().filter(function (p) { return p[0] !== "sel"; });
      if (_calc.local) parts.push(["sel", encodeURIComponent(JSON.stringify(_calc.state))]);
      var hash = parts.map(function (p) { return p[0] + "=" + p[1]; }).join("&");
      root.history.replaceState(root.history.state, "", hash ? "#" + hash
        : String(root.location.pathname || "") + String(root.location.search || ""));
    } catch (e) { /* a sandboxed frame may refuse; the view still applies */ }
  }

  /* A link carries only a view the page offers: the fields its controls,
   * its authored selection and its slices' grain name (what a control, a
   * mark or a row can select). A field the page offers no way to pick is
   * dropped, so an edited address cannot recut a page by a field its author
   * never made cuttable. */
  function offered(calc, sel) {
    if (!sel) return null;
    var out = {}, k, asked = 0, kept = 0;
    for (k in sel) {
      if (!sel.hasOwnProperty(k)) continue;
      asked++;
      if (calc.fields[k]) { out[k] = sel[k]; kept++; }
    }
    return (kept || !asked) ? out : null;
  }

  function bootCalc() {
    if (typeof document === "undefined" || !root.tracebiCalc) return;
    var el = document.getElementById("tracebi-calc-plans");
    if (!el) return;
    var payload;
    try { payload = JSON.parse(el.textContent); } catch (e) { return; }
    if (!payload || typeof payload !== "object" || !payload.bindings) return;
    var calc = { plans: payload.bindings, facts: payload.facts || {}, columns: {},
                 types: {}, grain: {}, hashes: {}, error: null, results: {},
                 variants: {}, sources: {}, local: false,
                 authored: normalSelection(payload.authored_selection) };
    var key, fact, block, carrier;
    for (key in calc.facts) {
      if (!calc.facts.hasOwnProperty(key)) continue;
      fact = calc.facts[key];
      (fact.columns || []).forEach(function (c) {
        if (!calc.columns.hasOwnProperty(c.name)) {
          calc.columns[c.name] = fact.fact;
          calc.types[c.name] = c.type;
        }
      });
      (fact.grain || []).forEach(function (g) { calc.grain[g] = true; });
      if (calc.error) continue;
      /* One failure is said once, in the trace, and leaves every figure as
       * built: a page that half-loaded its data must not half-recompute. */
      try {
        block = document.getElementById(fact.block);
        if (!block) throw new Error("its block " + fact.block + " is missing");
        carrier = JSON.parse(block.textContent);
        root.tracebiCalc.load(fact.fact, b64ToBytes(carrier.parquet_b64));
        calc.hashes[fact.fact] = carrier.payload_sha256 || null;
      } catch (e) {
        calc.error = "the embedded data for " + fact.fact + " could not be read: " + errorText(e);
      }
    }
    /* A control the reader can turn: one whose column a slice carries. */
    calc.fields = {};
    calc.pickable = {};
    (payload.controls || []).forEach(function (c) {
      if (!calc.columns.hasOwnProperty(c.column)) return;
      calc.fields[c.column] = true;
      if (c.kind !== "range") calc.pickable[c.column] = true;
    });
    calc.controls = Object.keys(calc.fields).length > 0;
    for (key in calc.authored) if (calc.authored.hasOwnProperty(key)) calc.fields[key] = true;
    /* A mark or a table row selects by any column the slice is grouped by
     * (decision 12), so a link may carry those too: the build put each one
     * in the slice because a figure or a control on this page names it. */
    for (key in calc.grain) {
      if (calc.grain.hasOwnProperty(key)) calc.fields[key] = calc.pickable[key] = true;
    }
    calc.state = offered(calc, hashSelection()) || normalSelection(payload.authored_selection);
    _calc = calc;
  }

  /* An engine value as the stamped CSV spells it, so every figure reads a
   * live row exactly as it reads a stamped one. */
  function liveCell(v) {
    if (v === null || v === undefined) return "";
    if (v === true) return "True";
    if (v === false) return "False";
    return String(v);
  }

  function liveBlock(res) {
    var rows = res.rows.map(function (r) {
      var o = {};
      res.cols.forEach(function (c) { o[c] = liveCell(r[c]); });
      return o;
    });
    return { cols: res.cols.slice(), rows: rows,
             csv: rows.length ? selectionCsv(rows) : res.cols.join(",") };
  }

  function isFixed(res) { return !!res && res.fixed !== undefined; }

  /* local: recomputed under the selection; unfiltered: recomputable, but no
   * selected field reaches it, so it is the unfiltered answer; fixed: the
   * build value. */
  function figureState(res) {
    if (isFixed(res)) return "fixed";
    var applied = Object.keys(res.selection || {}).length;
    return (!applied && res.unfiltered_by && res.unfiltered_by.length) ? "unfiltered" : "local";
  }

  /* The slowest single plan run of the last recompute, in milliseconds, as
   * data-tb-calc-ms on <html>: what the audit's budget (100 ms per binding)
   * reads. A measurement of the page, never shown and never a figure. */
  function now() {
    return root.performance && root.performance.now ? root.performance.now() : Date.now();
  }

  function computeLocal() {
    var calc = _calc, name, plan, res, t0, slowest = 0;
    calc.local = selectionKey(calc.state) !== selectionKey(calc.authored);
    calc.results = {};
    calc.variants = {};
    for (name in calc.plans) {
      if (!calc.plans.hasOwnProperty(name)) continue;
      plan = calc.plans[name];
      if (plan && plan.fixed !== undefined) res = { fixed: String(plan.fixed) };
      else if (calc.error) res = { fixed: calc.error };
      else {
        t0 = now();
        try { res = root.tracebiCalc.run(plan, calc.state); }
        catch (e) { res = { fixed: "the page engine could not run its plan: " + errorText(e) }; }
        slowest = Math.max(slowest, now() - t0);
      }
      calc.results[name] = res;
      if (calc.local && !isFixed(res)) {
        _liveBlocks[name] = liveBlock(res);
        _liveRows[name] = _liveBlocks[name].rows;
      } else {
        delete _liveBlocks[name];
        delete _liveRows[name];
      }
    }
    try {
      document.documentElement.setAttribute("data-tb-calc-ms", slowest.toFixed(1));
    } catch (e) { /* defensive */ }
  }

  function currentBlock(name) { return _liveBlocks[name] || readBlock(name); }

  /* Value figures from the binding's current rows. A recomputed result can
   * hold no row (a grouped query nothing matched) or a null (a sum over no
   * rows): the figure shows "—" rather than keeping a number the selection
   * no longer supports. */
  function paintLiveValues(binding, block) {
    var rows = block ? block.rows : [];
    var els = figureEls("value").filter(function (el) {
      if (attr(el, "data-tb-binding") !== binding) return false;
      /* What the build left, so the authored view can be put back. */
      if (el.__tbBuilt === undefined) el.__tbBuilt = (el.querySelector(".tb-kpi-value") || el).textContent;
      return true;
    });
    paintValues(binding, rows);
    els.forEach(function (el) {
      try {
        var target = el.querySelector(".tb-kpi-value") || el;
        var cell = attr(el, "data-tb-cell") || (block && block.cols.length === 1 ? block.cols[0] : null);
        var raw = rows.length && cell ? rows[0][cell] : undefined;
        var missing = raw === undefined || raw === null || raw === "";
        el.__tbEmpty = _calc.local && missing;
        if (el.__tbEmpty) target.textContent = "—";
        else if (missing) target.textContent = el.__tbBuilt;
      } catch (e) { /* defensive */ }
    });
  }

  function paintLocal() {
    var calc = _calc, name, i, entry, block;
    for (name in calc.results) {
      if (calc.results.hasOwnProperty(name) && !isFixed(calc.results[name])) {
        paintLiveValues(name, currentBlock(name));
      }
    }
    /* A table's row count, bars and totals follow its current result: the
     * totals row is its own binding (data-tb-totals), recomputed above. */
    for (i = 0; i < _tables.length; i++) {
      entry = _tables[i];
      try {
        block = ownBlock(entry) || currentBlock(entry.binding);
        if (!block) continue;
        entry.rowCount = block.rows.length;
        entry.bars = barScales(entry.el, block.rows, entry.cols, entry.numeric);
        if (attr(entry.el, "data-tb-totals")) {
          entry.tfoot = totalsRow(entry.el, entry.cols, entry.numeric, entry.formats, entry.bars);
        }
      } catch (e) { /* defensive */ }
    }
    for (name in calc.results) {
      if (calc.results.hasOwnProperty(name) && !isFixed(calc.results[name])) refreshBinding(name);
    }
    paintLiveMarks();
    try { stampFigures(); } catch (e) { /* the runtime wrote these: they are the new baseline */ }
  }

  /* "Fixed at build · period_end": the kind of reason, in a word or two;
   * the note's title and the trace carry the whole of it. */
  function shortReason(reason) {
    var r = String(reason), m = /^(period_end|offset\/growth|to_date) measure/.exec(r);
    if (m) return m[1];
    if (r === "report.py") return "report.py";
    if (/^sql binding/.test(r) || /^a SQL binding/.test(r)) return "SQL";
    if (/^the embedded data/.test(r)) return "the embedded data could not be read";
    return r.length > 48 ? r.slice(0, 47) + "…" : r;
  }

  function fieldNames(fields) {
    return fields.map(fieldLabel).join(", ");
  }

  /* A field's one name on the page, wherever the page names it (chips, the
   * print line, the download header, the notes, the trace): the label of a
   * control for the column (data-tb-label, else the <label> around it; the
   * kit's label prop renders one of those), else the header a table or the
   * axis title a chart gives the column, else humanise(column). Read from
   * the page each time, since an app mounts its controls later. */
  function controlText(el) {
    var own = attr(el, "data-tb-label");
    if (own) return own;
    for (var n = el.parentNode; n && n.tagName; n = n.parentNode) {
      if (n.tagName !== "LABEL") continue;
      var text = "";
      Array.prototype.forEach.call(n.childNodes, function (c) {
        if (c === el || (c.nodeType === 1 && c.contains(el))) return;
        if (c.nodeType === 3 || (c.nodeType === 1 && !/^(SELECT|INPUT)$/.test(c.tagName))) {
          text += c.textContent;
        }
      });
      return trim(text) || null;
    }
    return null;
  }

  function fieldLabel(column) {
    if (typeof document === "undefined") return humanise(column);
    var els = document.querySelectorAll("[data-tb-filter][data-tb-column], [data-tb-range][data-tb-column]");
    var i, text;
    for (i = 0; i < els.length; i++) {
      if (els[i].getAttribute("data-tb-column") !== column) continue;
      text = controlText(els[i]);
      if (text) return text;
    }
    for (i = 0; i < _tables.length; i++) {
      var at = _tables[i].cols.indexOf(column);
      var th = at === -1 ? null : _tables[i].el.querySelectorAll("thead th")[at];
      if (th && trim(th.textContent)) return trim(th.textContent);
    }
    for (i = 0; i < _charts.length; i++) {
      if (_charts[i].plan.x === column && _charts[i].plan.xTitle) return _charts[i].plan.xTitle;
    }
    return humanise(column);
  }

  /* The figure's note: after a table's scroll box and badge row, inside a
   * KPI card, after anything else. An inline value (a number in a sentence)
   * gets no words dropped into the prose: it is underlined, dotted, and the
   * note is its title. Chrome: Build mode and the stamped-text watcher both
   * look past it. */
  function setLiveNote(el, text, title) {
    var card = el.querySelector(".tb-kpi-value");
    if (!card && el.tagName === "SPAN") {
      if (text) {
        if (el.__tbTitle === undefined) el.__tbTitle = el.getAttribute("title");
        el.title = title || text;
        addClass(el, "tb-live-marked");
      } else if (el.__tbTitle !== undefined) {
        if (el.__tbTitle === null) el.removeAttribute("title"); else el.title = el.__tbTitle;
        delete el.__tbTitle;
        removeClass(el, "tb-live-marked");
      }
      el.__tbLiveNote = null;
      return;
    }
    var note = el.__tbLiveNote;
    if (!text) {
      if (note && note.parentNode) note.parentNode.removeChild(note);
      el.__tbLiveNote = null;
      return;
    }
    if (!note || !note.parentNode) {
      note = document.createElement("div");
      note.className = "tb-live-note";
      note.setAttribute("data-tb-chrome", "");
      if (card) {
        el.appendChild(note);
      } else {
        var host = el;
        while (host.parentNode && host.parentNode.className !== undefined &&
               /(^| )(tb-scroll|tb-badge-anchor)( |$)/.test(host.parentNode.className)) {
          host = host.parentNode;
        }
        if (!host.parentNode) return;
        host.parentNode.insertBefore(note, host.nextSibling);
      }
      el.__tbLiveNote = note;
    }
    note.textContent = text;
    note.title = title || text;
  }

  function paintLiveMarks() {
    var calc = _calc;
    var els = document.querySelectorAll("[data-tb-figure][data-tb-binding]");
    Array.prototype.forEach.call(els, function (el) {
      try {
        var res = figureResult(el);
        if (!res) return;
        var notes = [], title = null;
        if (isFixed(res)) {
          el.setAttribute("data-tb-fixed", res.fixed);
          el.removeAttribute("data-tb-unfiltered-by");
          if (calc.local) {
            notes.push("Fixed at build · " + shortReason(res.fixed));
            title = "Fixed at build: " + res.fixed;
          }
        } else {
          el.removeAttribute("data-tb-fixed");
          if (calc.local && res.unfiltered_by && res.unfiltered_by.length) {
            el.setAttribute("data-tb-unfiltered-by", res.unfiltered_by.join(","));
            notes.push("Not filtered by " + fieldNames(res.unfiltered_by));
          } else {
            el.removeAttribute("data-tb-unfiltered-by");
          }
          if (el.__tbEmpty) notes.push("No rows under this selection");
        }
        setLiveNote(el, notes.join(" · "), title);
      } catch (e) { /* defensive */ }
    });
  }

  /* The trace, while the page is Local: per figure the binding's plan, the
   * selection it applied, what it could not apply and the hash of the slice
   * block it read; above them, how many figures are local, fixed and
   * unchanged. As built, the trace is the build's alone. */
  function paintLocalTrace() {
    var calc = _calc;
    var mount = document.querySelector(".tb-receipt-drawer .tb-receipt");
    if (!mount) return;
    var old = mount.querySelectorAll(".tb-receipt-local, .tb-receipt-local-summary"), i;
    for (i = 0; i < old.length; i++) old[i].parentNode.removeChild(old[i]);
    var shown = calc.local || calc.error;
    var counts = { local: 0, fixed: 0, unfiltered: 0 };
    var rows = mount.querySelectorAll(".tb-receipt-row[data-tb-receipt-fig]");
    Array.prototype.forEach.call(rows, function (row) {
      var page = document.getElementById(row.getAttribute("data-tb-receipt-fig"));
      var binding = page ? attr(page, "data-tb-binding") : null;
      var res = binding ? figureResult(page) : null;
      if (!res) return;
      var state = figureState(res);
      counts[state]++;
      /* The row shows what the page shows now. */
      var value = row.querySelector(".tb-receipt-value");
      if (value && attr(page, "data-tb-figure") === "value") {
        value.textContent = trim((page.querySelector(".tb-kpi-value") || page).textContent || "");
      }
      if (!shown) return;
      var box = document.createElement("div");
      box.className = "tb-receipt-local";
      var title = row.querySelector(".tb-receipt-title");
      row.insertBefore(box, title ? title.nextSibling : row.firstChild);
      if (state === "fixed") {
        receiptEl(box, "div", "tb-receipt-local-line", "Fixed at build: " + res.fixed);
        return;
      }
      var kind = attr(page, "data-tb-figure");
      var line = "Recomputed on this page";
      if (kind !== "value") line += ", " + res.rows.length + (res.rows.length === 1 ? " row" : " rows");
      receiptEl(box, "div", "tb-receipt-local-line",
                line + "; the query and fingerprint below are the build's.");
      var facts = receiptEl(box, "dl", "tb-receipt-facts");
      receiptEl(facts, "dt", null, "Selection");
      receiptEl(facts, "dd", null, describeSelection(res.selection) || "none applies");
      if (res.highlights && res.highlights.length) {
        /* A chart or row-select table keeps its own field's other values,
         * drawn back: its rows answer the rest of the selection. */
        receiptEl(facts, "dt", null, "Highlights");
        receiptEl(facts, "dd", null, describeSelection(pickFields(calc.state, res.highlights)));
      }
      if (res.unfiltered_by && res.unfiltered_by.length) {
        receiptEl(facts, "dt", null, "Not filtered by");
        receiptEl(facts, "dd", null, res.unfiltered_by.join(", "));
      }
      var plan = calc.plans[binding];
      var hash = calc.hashes[plan.fact];
      if (hash) {
        receiptEl(facts, "dt", null, "Slice");
        var dd = receiptEl(facts, "dd");
        var code = receiptEl(dd, "code", "tb-receipt-fp-short", String(hash).slice(0, 8));
        code.title = "payload_sha256 " + hash;
      }
      var details = receiptEl(box, "details", "tb-receipt-details");
      receiptEl(details, "summary", null, "Plan");
      var pre = receiptEl(details, "pre", "tb-receipt-json");
      try { pre.textContent = JSON.stringify(plan, null, 2); } catch (e) { /* defensive */ }
    });
    if (!shown) return;
    var section = mount.querySelector(".tb-receipt-figures");
    if (!section) return;
    var summary = document.createElement("p");
    summary.className = "tb-receipt-local-summary";
    summary.textContent = calc.error
      ? "As built: " + calc.error + "."
      : counts.local + " recomputed on this page · " + counts.fixed
        + " fixed at build · " + counts.unfiltered + " unchanged";
    var label = section.querySelector(".tb-receipt-label");
    section.insertBefore(summary, label ? label.nextSibling : section.firstChild);
  }

  function describeSelection(sel) {
    return Object.keys(sel || {}).map(function (k) {
      var v = sel[k];
      if (isArray(v)) return fieldLabel(k) + " = " + v.map(String).join(", ");
      return fieldLabel(k) + " " + RANGE_KEYS.filter(function (op) { return v.hasOwnProperty(op); })
        .map(function (op) { return { gt: ">", gte: "≥", lt: "<", lte: "≤" }[op] + " " + v[op]; })
        .join(" and ");
    }).join("; ");
  }

  /* ── The interaction grammar — every gesture writes the one state ──────
   * A mark (a bar, a slice, a point, a legend entry), a table row
   * (data-tb-select-rows), a range (data-tb-range), a chip in the selection
   * bar and Escape all write _calc.state, exactly as a filter control does;
   * every figure then re-runs from it (decision 11). Nothing here computes
   * a number: a gesture only says which values the reader picked. */

  /* A field a click may pick values of: one a slice carries and groups by,
   * or a filter control's column. A range's own column (a holding's fair
   * value) is ranged, never picked value by value. */
  function selectableField(column) {
    return !!(_calc && column && _calc.columns.hasOwnProperty(column) && _calc.pickable[column]);
  }

  /* A mark's or a row's text back to the slice's own value: a chart reads
   * "2026" or "True" where the slice holds 2026 or true. */
  function typedValue(column, text) {
    var dom, all, i;
    try { dom = root.tracebiCalc.domains(_calc.columns[column], column, {}); }
    catch (e) { return text; }
    all = dom.present.concat(dom.rest);
    for (i = 0; i < all.length; i++) if (liveCell(all[i]) === text) return all[i];
    return text;
  }

  function pickedIndex(list, text) {
    for (var i = 0; i < list.length; i++) if (liveCell(list[i]) === text) return i;
    return -1;
  }

  /* Which table's row click wrote a field ({field: "table:<id>"}). Only
   * that table keeps the field's other rows (it highlights them); every
   * other gesture that writes the field takes it back, and the address
   * carries the plain state, so a link opens with no field owned. */
  function ownSource(el) { return "table:" + (el.id || attr(el, "data-tb-binding")); }

  function disown(column) {
    if (_calc && _calc.sources) delete _calc.sources[column];
  }

  /* A click picks the value; the same value again removes it; with shift
   * the value joins (or leaves) the field's list. */
  function toggleValue(column, text, additive) {
    if (!_calc) return;
    disown(column);
    var cur = isArray(_calc.state[column]) ? _calc.state[column].slice() : [];
    var i = pickedIndex(cur, text);
    if (i !== -1) cur.splice(i, 1);
    else if (additive) cur.push(typedValue(column, text));
    else cur = [typedValue(column, text)];
    if (cur.length) _calc.state[column] = cur;
    else delete _calc.state[column];
    selectionChanged();
  }

  function removeValue(column, value) {
    var cur = isArray(_calc.state[column]) ? _calc.state[column] : [];
    cur = cur.filter(function (v) { return liveCell(v) !== liveCell(value); });
    if (cur.length) _calc.state[column] = cur;
    else { delete _calc.state[column]; disown(column); }
    selectionChanged();
  }

  /* Back to the view as built: what Clear and Escape do. */
  function clearSelection() {
    _calc.state = normalSelection(_calc.authored);
    _calc.sources = {};
    selectionChanged();
  }

  function pickFields(sel, fields) {
    var out = {};
    fields.forEach(function (f) { if (sel.hasOwnProperty(f)) out[f] = sel[f]; });
    return out;
  }

  /* ── Table rows (data-tb-select-rows) ── */

  /* Whether a row's value of column *c* is picked. */
  function cellPicked(r, c) {
    return isArray(_calc.state[c]) && pickedIndex(_calc.state[c], String(r[c])) !== -1;
  }

  /* A row is picked when its value of ANY of the table's select columns is
   * (a sector filter marks every row of that sector); null when none of
   * them is picked at all, so no row stands out. */
  function rowPicked(entry, r) {
    var any = false, hit = false;
    entry.selectCols.forEach(function (c) {
      if (!isArray(_calc.state[c])) return;
      any = true;
      if (cellPicked(r, c)) hit = true;
    });
    return any ? hit : null;
  }

  /* A row writes its select columns, owned by this table; clicking a row
   * this table picked clears them; with shift its values join the lists. */
  function selectRow(entry, r, event) {
    var source = ownSource(entry.el), additive = !!(event && event.shiftKey);
    var on = entry.selectCols.every(function (c) {
      return _calc.sources[c] === source && cellPicked(r, c);
    });
    entry.selectCols.forEach(function (c) {
      var text = String(r[c]);
      var cur = isArray(_calc.state[c]) && _calc.sources[c] === source ? _calc.state[c].slice() : [];
      var i = pickedIndex(cur, text);
      if (on) { if (i !== -1) cur.splice(i, 1); }
      else if (additive) { if (i === -1) cur.push(typedValue(c, text)); }
      else cur = [typedValue(c, text)];
      if (cur.length) { _calc.state[c] = cur; _calc.sources[c] = source; }
      else { delete _calc.state[c]; disown(c); }
    });
    selectionChanged();
  }

  function selectableRow(entry, tr, r) {
    if (!entry.selectCols || !entry.selectCols.length) return;
    var picked = entry._pickAll ? null : rowPicked(entry, r);
    tr.setAttribute("aria-selected", picked ? "true" : "false");
    tr.className = (tr.className ? tr.className + " " : "") + "tb-row-select"
      + (picked === false ? " tb-row-dimmed" : "");
    tr.tabIndex = 0;
    tr.addEventListener("click", function (e) { selectRow(entry, r, e); });
    tr.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      e.preventDefault();
      selectRow(entry, r, e);
    });
  }

  /* ── Highlighting (decision 15) ──
   * A chart keeps the other values of its own category and series columns,
   * and a row-select table those of its dimension columns: they draw the
   * figure's query under the rest of the selection, and the picked values
   * stand out (shift-click needs the others to stay). Off with
   * data-tb-highlight="off" on the figure or any ancestor: the figure is
   * then cut by its own field like every other. Presentation only; the
   * rows are still a plan's result under a stated selection. */

  function highlightOff(el) {
    for (var n = el; n && n.getAttribute; n = n.parentNode) {
      if (n.getAttribute("data-tb-highlight") === "off") return true;
    }
    return false;
  }

  function ownFields(el) {
    if (!_calc || !_calc.local || !el || highlightOff(el)) return [];
    var kind = attr(el, "data-tb-figure"), cols = [];
    if (kind === "chart") cols = [attr(el, "data-tb-x"), attr(el, "data-tb-color")];
    else if (kind === "table") {
      /* Only what this table's own rows picked: a field a filter, a mark or
       * another table wrote narrows it like any figure. */
      var source = ownSource(el);
      cols = (el.__tbSelectCols || []).filter(function (c) { return _calc.sources[c] === source; });
    }
    return cols.filter(function (c, i) {
      return c && cols.indexOf(c) === i && isArray(_calc.state[c]) && selectableField(c);
    });
  }

  /* The binding's plan under the state less *own*, run once per change. The
   * authored state's answer is the stamped block itself. */
  function variantResult(binding, own) {
    var calc = _calc, key = binding + "\n" + own.slice().sort().join("\n");
    if (calc.variants.hasOwnProperty(key)) return calc.variants[key];
    var plan = calc.plans[binding], res = calc.results[binding], state = {}, k;
    if (!plan || !res || isFixed(res)) return (calc.variants[key] = null);
    for (k in calc.state) {
      if (calc.state.hasOwnProperty(k) && own.indexOf(k) === -1) state[k] = calc.state[k];
    }
    try { res = root.tracebiCalc.run(plan, state); } catch (e) { res = null; }
    if (res) {
      res.highlights = own.slice();
      res.block = selectionKey(state) === selectionKey(calc.authored)
        ? readBlock(binding) : liveBlock(res);
    }
    return (calc.variants[key] = res);
  }

  function ownBlock(entry) {
    var own = ownFields(entry.el);
    var res = own.length ? variantResult(entry.binding, own) : null;
    return res && res.block ? res.block : null;
  }

  /* The rows a chart or table entry draws: its own result when it
   * highlights, else the binding's (search still narrows either). */
  function entryRows(entry, rows) {
    var block = ownBlock(entry);
    if (!block) return rows || filteredRows(entry.binding);
    var subset = _views[entry.binding], base = readBlock(entry.binding);
    if (!subset || !base) return block.rows;
    return block.rows.filter(function (r) { return rowMatches(r, base.cols, subset); });
  }

  function figureResult(el) {
    var binding = attr(el, "data-tb-binding"), own = ownFields(el);
    var res = own.length ? variantResult(binding, own) : null;
    return res || (_calc ? _calc.results[binding] : null);
  }

  function pickedSet(column) {
    if (!_calc || !_calc.local || !column || !isArray(_calc.state[column])) return null;
    var out = {};
    _calc.state[column].forEach(function (v) { out[liveCell(v)] = true; });
    return out;
  }

  /* ── Ranges (data-tb-range, decision 14) ──
   * A number column: two native range inputs over one track, the bounds as
   * text beside them. A grain-label column (2026-03, 2026-Q1): two pickers,
   * from and to, over the labels present. Either writes {gte, lte}, and
   * removes the field when both ends are back at the domain's. The domain
   * is the column's values under the rest of the selection. */

  function rangeEls() {
    if (typeof document === "undefined") return [];
    return Array.prototype.slice.call(document.querySelectorAll("[data-tb-range][data-tb-column]"));
  }

  function rangeDomain(el) {
    var column = el._tbRangeColumn, dom;
    try { dom = root.tracebiCalc.domains(_calc.columns[column], column, _calc.state); }
    catch (e) { dom = { present: [], rest: [] }; }
    /* The track is the column's whole domain, present or not under the rest
     * of the selection, so it never collapses to one value when another
     * field narrows the page, and "back at both ends" always means the
     * same two values. dom.present stays what the rest of the page shows. */
    var values = dom.present.concat(dom.rest).sort(function (a, b) {
      return a < b ? -1 : a > b ? 1 : 0;
    });
    if (el._tbRangeNumber) {
      values = values.filter(function (v) { return typeof v === "number"; });
      var lo = toNum(attr(el, "data-tb-min")), hi = toNum(attr(el, "data-tb-max"));
      return { lo: lo !== null ? lo : (values.length ? values[0] : 0),
               hi: hi !== null ? hi : (values.length ? values[values.length - 1] : 0),
               values: values };
    }
    return { lo: values[0], hi: values[values.length - 1], values: values.map(String) };
  }

  /* A bound as the bar and the range write it: large numbers compact
   * (11.7M), so a chip stays short; the trace and the address keep it whole. */
  function rangeText(v, column) {
    if (typeof v !== "number") return String(v);
    if (column && plainColumn(column)) return String(v);
    return Math.abs(v) >= 1000 ? fmt(v, "compact") : fmt(v);
  }

  /* A column whose numbers are names, not amounts: derive.py's rule (year,
   * *_year, id, *_key) or, failing that, whole numbers all within
   * 1800-2200, which read as years. Written as they are: 1990, never 1,990. */
  function plainColumn(column) {
    var cache = _calc.plain || (_calc.plain = {});
    if (cache.hasOwnProperty(column)) return cache[column];
    var plain = isIdentity(column), dom, all;
    if (!plain && _calc.types[column] === "number") {
      try {
        dom = root.tracebiCalc.domains(_calc.columns[column], column, {});
        all = dom.present.concat(dom.rest);
        plain = all.length > 0 && all.every(function (v) {
          return typeof v === "number" && v % 1 === 0 && v >= 1800 && v <= 2200;
        });
      } catch (e) { plain = false; }
    }
    return (cache[column] = plain);
  }

  function writeRange(el, lo, hi) {
    var column = el._tbRangeColumn, d = el._tbDomain;
    if (lo > hi) { var t = lo; lo = hi; hi = t; }
    var out = {};
    if (lo > d.lo) out.gte = lo;
    if (hi < d.hi) out.lte = hi;
    disown(column);
    if (out.gte === undefined && out.lte === undefined) delete _calc.state[column];
    else _calc.state[column] = out;
    selectionChanged();
  }

  function stepOf(el, d) {
    var own = toNum(attr(el, "data-tb-step"));
    if (own) return own;
    var whole = d.values.every(function (v) { return v % 1 === 0; });
    var span = d.hi - d.lo;
    if (whole && span <= 200) return 1;
    var raw = span / 100, mag = Math.pow(10, Math.floor(Math.log(raw || 1) / Math.LN10));
    return whole ? Math.max(1, Math.round(raw / mag) * mag) : Math.round(raw / mag) * mag;
  }

  function buildRange(el, column) {
    var label = attr(el, "data-tb-label") || humanise(column);
    el._tbRangeColumn = column;
    el._tbRangeNumber = _calc.types[column] === "number";
    addClass(el, "tb-range");
    while (el.firstChild) el.removeChild(el.firstChild);
    var name = document.createElement("span");
    name.className = "tb-range-label";
    name.textContent = label;
    el.appendChild(name);
    var make = function (tag, cls, aria) {
      var x = document.createElement(tag);
      x.className = cls;
      x.setAttribute("aria-label", label + ", " + aria);
      return x;
    };
    if (el._tbRangeNumber) {
      var track = document.createElement("span");
      track.className = "tb-range-track";
      var a = make("input", "tb-range-lo", "from"), b = make("input", "tb-range-hi", "to");
      a.type = b.type = "range";
      track.appendChild(a);
      track.appendChild(b);
      var text = document.createElement("span");
      text.className = "tb-range-values";
      var oa = document.createElement("output"), ob = document.createElement("output");
      text.appendChild(oa);
      text.appendChild(document.createTextNode(" – "));
      text.appendChild(ob);
      el.appendChild(track);
      el.appendChild(text);
      el._tbInputs = [a, b];
      el._tbOutputs = [oa, ob];
      var show = function () {
        var lo = Number(a.value), hi = Number(b.value);
        oa.textContent = rangeText(Math.min(lo, hi), column);
        ob.textContent = rangeText(Math.max(lo, hi), column);
      };
      var commit = function () {
        var d = el._tbDomain, lo = Number(a.value), hi = Number(b.value);
        /* The ends of the track stand for the domain's own ends: the track
         * runs from a whole step at or below the lowest value to one at or
         * above the highest. */
        if (lo <= Number(a.min)) lo = d.lo;
        if (hi >= Number(b.max)) hi = d.hi;
        writeRange(el, lo, hi);
      };
      a.addEventListener("input", show);
      b.addEventListener("input", show);
      a.addEventListener("change", commit);
      b.addEventListener("change", commit);
    } else {
      var from = make("select", "tb-range-from", "from"), to = make("select", "tb-range-to", "to");
      el.appendChild(from);
      var dash = document.createElement("span");
      dash.className = "tb-range-dash";
      dash.textContent = "to";
      el.appendChild(dash);
      el.appendChild(to);
      el._tbInputs = [from, to];
      var pick = function () { writeRange(el, from.value, to.value); };
      from.addEventListener("change", pick);
      to.addEventListener("change", pick);
    }
    paintRange(el);
  }

  /* The control from the state: its domain under the rest of the
   * selection, its handles where the state (or the hash) put them. */
  function paintRange(el) {
    var d = el._tbDomain = rangeDomain(el);
    var cur = _calc.state[el._tbRangeColumn];
    cur = (cur && !isArray(cur)) ? cur : {};
    var lo = cur.hasOwnProperty("gte") ? cur.gte : cur.hasOwnProperty("gt") ? cur.gt : d.lo;
    var hi = cur.hasOwnProperty("lte") ? cur.lte : cur.hasOwnProperty("lt") ? cur.lt : d.hi;
    var inputs = el._tbInputs;
    if (el._tbRangeNumber) {
      var step = stepOf(el, d);
      var bottom = Math.floor(d.lo / step) * step, top = Math.ceil(d.hi / step) * step;
      inputs.forEach(function (x) { x.min = bottom; x.max = top; x.step = step; });
      inputs[0].value = lo <= d.lo ? bottom : lo;
      inputs[1].value = hi >= d.hi ? top : hi;
      el._tbOutputs[0].textContent = rangeText(lo, el._tbRangeColumn);
      el._tbOutputs[1].textContent = rangeText(hi, el._tbRangeColumn);
      el.setAttribute("data-tb-range-active", cur.gte !== undefined || cur.lte !== undefined
        || cur.gt !== undefined || cur.lt !== undefined ? "true" : "false");
      return;
    }
    inputs.forEach(function (sel, j) {
      while (sel.firstChild) sel.removeChild(sel.firstChild);
      d.values.forEach(function (v) {
        var o = document.createElement("option");
        o.value = v;
        o.textContent = v;
        sel.appendChild(o);
      });
      sel.value = String(j === 0 ? lo : hi);
    });
  }

  function hydrateRanges() {
    fresh(rangeEls(), "range").forEach(function (el) {
      try {
        var column = attr(el, "data-tb-column");
        if (!column || !_calc.columns.hasOwnProperty(column)) {
          el.setAttribute("data-tb-fixed", "column not in slice");
          el.title = "No embedded data carries " + humanise(column || "") + ": this range does nothing";
          return;
        }
        buildRange(el, column);
      } catch (e) { /* defensive */ }
    });
  }

  function paintRanges() {
    rangeEls().forEach(function (el) {
      if (el._tbRangeColumn) { try { paintRange(el); } catch (e) { /* defensive */ } }
    });
  }

  /* ── The selection bar (decision 13) ──
   * One chip per picked value (a range is one chip), each with a × that
   * removes it; Clear when there are two or more; "Download what I see".
   * Under the masthead, or in the author's <div data-tb-selection> (kit
   * <SelectionBar/>). Hidden while the state is the authored one. Printed,
   * it is one plain line, so a paper copy or a PDF says what it shows. */

  var _bar = null;

  function placeSelectionBar() {
    if (!_calc || typeof document === "undefined" || !document.body) return null;
    if (!_bar) {
      _bar = document.createElement("div");
      _bar.className = "tb-selection-bar";
      _bar.setAttribute("data-tb-chrome", "");
      _bar.setAttribute("role", "region");
      _bar.setAttribute("aria-label", "Selection");
      _bar.hidden = true;
    }
    var slot = document.querySelector("[data-tb-selection]");
    if (slot) {
      if (_bar.parentNode !== slot) slot.appendChild(_bar);
      return _bar;
    }
    if (_bar.parentNode && document.documentElement.contains(_bar)) return _bar;
    /* Never inside a React app's tree, which owns its own nodes. */
    var app = document.getElementById("tb-app"), heads = document.querySelectorAll(".tb-masthead");
    var head = null, i;
    for (i = 0; i < heads.length && !head; i++) if (!app || !app.contains(heads[i])) head = heads[i];
    if (head && head.parentNode && !within(head, "tb-tab-bar")) {
      head.parentNode.insertBefore(_bar, head.nextSibling);
    } else if (app && app.parentNode) {
      app.parentNode.insertBefore(_bar, app);
    } else {
      var main = document.querySelector(".tb-page") || document.body;
      main.insertBefore(_bar, main.firstChild);
    }
    return _bar;
  }

  function fieldText(column, v) {
    if (isArray(v)) return v.map(liveCell).join(", ");
    return RANGE_KEYS.filter(function (op) { return v.hasOwnProperty(op); }).length === 2
      ? rangeText(v.hasOwnProperty("gte") ? v.gte : v.gt, column) + "–"
        + rangeText(v.hasOwnProperty("lte") ? v.lte : v.lt, column)
      : RANGE_KEYS.filter(function (op) { return v.hasOwnProperty(op); })
        .map(function (op) { return { gt: ">", gte: "≥", lt: "<", lte: "≤" }[op] + " " + rangeText(v[op], column); })
        .join(" ");
  }

  function paintSelectionBar() {
    var bar = placeSelectionBar();
    if (!bar) return;
    while (bar.firstChild) bar.removeChild(bar.firstChild);
    var calc = _calc, local = calc.local;
    bar.hidden = !local;
    paintFooterFiltered(local);
    if (!local) return;
    var lead = document.createElement("span");
    lead.className = "tb-selection-label";
    lead.textContent = "Filtered to";
    bar.appendChild(lead);
    var list = document.createElement("ul");
    list.className = "tb-selection-chips";
    var printed = [], count = 0;
    var chip = function (text, onRemove) {
      var li = document.createElement("li");
      li.className = "tb-selection-chip";
      var span = document.createElement("span");
      span.textContent = text;
      var x = document.createElement("button");
      x.type = "button";
      x.className = "tb-selection-remove";
      x.setAttribute("aria-label", "Remove " + text);
      x.textContent = "×";
      x.addEventListener("click", onRemove);
      li.appendChild(span);
      li.appendChild(x);
      list.appendChild(li);
      count++;
    };
    Object.keys(calc.state).forEach(function (k) {
      var v = calc.state[k], name = fieldLabel(k);
      if (isArray(v)) {
        v.forEach(function (one) {
          chip(name + ": " + liveCell(one), function () { removeValue(k, one); });
        });
      } else {
        chip(name + ": " + fieldText(k, v), function () { delete calc.state[k]; selectionChanged(); });
      }
      printed.push(name + " " + fieldText(k, v));
    });
    bar.appendChild(list);
    var actions = document.createElement("span");
    actions.className = "tb-selection-actions";
    if (count >= 2) {
      var clear = document.createElement("button");
      clear.type = "button";
      clear.className = "tb-selection-clear";
      clear.textContent = "Clear";
      clear.addEventListener("click", clearSelection);
      actions.appendChild(clear);
    }
    var dl = document.createElement("button");
    dl.type = "button";
    dl.className = "tb-selection-download";
    dl.textContent = "Download what I see";
    dl.addEventListener("click", downloadVisible);
    actions.appendChild(dl);
    bar.appendChild(actions);
    var line = document.createElement("p");
    line.className = "tb-selection-print";
    line.textContent = "Filtered to: " + (printed.join(" · ") || "the authored view");
    bar.appendChild(line);
  }

  /* The footer's built line says the page was filtered, so a printed or
   * PDF copy never passes for the view as built. Shown in print. */
  function paintFooterFiltered(on) {
    Array.prototype.forEach.call(document.querySelectorAll(".tb-footer-line"), function (line) {
      var note = line.querySelector(".tb-footer-filtered");
      if (!note) {
        note = document.createElement("span");
        note.className = "tb-footer-filtered";
        note.setAttribute("data-tb-chrome", "");
        note.textContent = " · filtered on this page";
        line.appendChild(note);
      }
      note.hidden = !on;
    });
  }

  /* Escape clears the selection, unless the reader is typing, reading a
   * chart with the keyboard, or has the trace open (Escape closes it). */
  function onSelectionKey(e) {
    if (e.key !== "Escape" || !_calc || !_calc.local) return;
    var t = e.target, tag = t && t.tagName;
    if (tag === "TEXTAREA" || tag === "SELECT" || (t && t.isContentEditable)) return;
    if (tag === "INPUT" && !/^(range|checkbox|radio|button|submit)$/.test(t.type || "")) return;
    if (t && t.closest && t.closest(".tb-chart-svg, .tb-receipt-drawer")) return;
    var drawer = receiptDrawer();
    if (drawer && (" " + drawer.className + " ").indexOf(" tb-receipt-open ") !== -1) return;
    clearSelection();
  }

  /* ── Download what I see ──
   * One CSV holding each figure the reader can see: its current rows (a
   * chart's or a table's, highlighting included; a value's binding), each
   * under its figure id, the state in the header and the name. */
  function figureVisible(el) {
    return !!(el.getClientRects && el.getClientRects().length);
  }

  function downloadVisible() {
    var parts = [], seen = {};
    var head = "# selection: " + (describeSelection(_calc.state) || "authored");
    Array.prototype.forEach.call(document.querySelectorAll("[data-tb-figure][data-tb-binding]"),
      function (el) {
        try {
          if (!figureVisible(el) || attr(el, "data-tb-figure") === "custom") return;
          var binding = attr(el, "data-tb-binding"), rows = null, i;
          for (i = 0; i < _charts.length && !rows; i++) if (_charts[i].el === el) rows = entryRows(_charts[i]);
          for (i = 0; i < _tables.length && !rows; i++) if (_tables[i].el === el) rows = entryRows(_tables[i]);
          if (!rows) {
            if (seen[binding]) return;
            seen[binding] = true;
            var block = currentBlock(binding);
            rows = block ? block.rows : [];
          }
          parts.push("# figure: " + (el.id || binding) + " (" + binding + ")\n" + selectionCsv(rows));
        } catch (e) { /* defensive */ }
      });
    var body = head + "\n" + parts.join("\n\n") + "\n";
    var name = String(document.title || "report").replace(/[^A-Za-z0-9._-]+/g, "_").slice(0, 40);
    saveText(name + "--" + selectionSlug(_calc.state) + ".csv", body);
  }

  function saveText(filename, text) {
    var blob = new Blob([text], { type: "text/csv" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 0);
  }

  /* A figure's current answer on a live page, as the engine gave it: the
   * plan's raw rows, the selection it applied, what it highlights and what
   * cannot reach it; {fixed} for a build value; null on a page with no
   * slice, or before anything was recomputed. What a test compares with the
   * server's answer, and what a script can read; it computes nothing. */
  function result(figureId) {
    if (!_calc || typeof document === "undefined") return null;
    var el = typeof figureId === "string" ? document.getElementById(figureId) : figureId;
    if (!el || !_calc.local) return null;
    var res = figureResult(el);
    if (!res) return null;
    if (isFixed(res)) return { fixed: res.fixed };
    return JSON.parse(JSON.stringify({
      cols: res.cols, rows: res.rows.map(function (r) { return res.cols.map(function (c) { return r[c]; }); }),
      selection: res.selection, unfiltered_by: res.unfiltered_by,
      highlights: res.highlights || [] }));
  }

  /* ── tracebi.onSelection ── */
  var _selectionListeners = [];

  function onSelection(fn) {
    if (typeof fn !== "function") return function () {};
    _selectionListeners.push(fn);
    return function () {
      var i = _selectionListeners.indexOf(fn);
      if (i !== -1) _selectionListeners.splice(i, 1);
    };
  }

  function notifySelection() {
    if (!_calc || !_selectionListeners.length) return;
    var payload;
    try { payload = selectionPayload(); } catch (e) { return; }
    _selectionListeners.slice().forEach(function (fn) {
      try { fn(JSON.parse(JSON.stringify(payload))); } catch (e) { /* the author's code */ }
    });
  }

  /* The page's selection as the host and tracebi.onSelection receive it:
   * the state, whether it is the authored one, and each figure's state. */
  function selectionPayload() {
    var figures = [];
    Array.prototype.forEach.call(document.querySelectorAll("[data-tb-figure][data-tb-binding]"),
      function (el) {
        var binding = attr(el, "data-tb-binding"), res = figureResult(el);
        if (!res) return;
        figures.push({ id: el.id || null, binding: binding,
                       kind: attr(el, "data-tb-figure"), state: figureState(res) });
      });
    return { selection: JSON.parse(JSON.stringify(_calc.state)), local: true,
             authored: !_calc.local, figures: figures };
  }

  function postLocal() {
    try {
      if (!_hostPost) return;
      _hostPost({ type: "tracebi-selection", payload: selectionPayload() });
    } catch (e) { /* defensive */ }
  }

  /* The options of a filter on a column a slice carries: the values present
   * under the rest of the selection first, then, after a separator, the
   * values it excludes. None is hidden and every one can be chosen. */
  function fillCalcOptions(el) {
    var column = el._tbCalcColumn, dom;
    try { dom = root.tracebiCalc.domains(_calc.columns[column], column, _calc.state); }
    catch (e) { dom = { present: [], rest: [] }; }
    var chosen = _calc.state[column], picked = {};
    if (isArray(chosen)) chosen.forEach(function (v) { picked[String(v)] = true; });
    while (el.firstChild) el.removeChild(el.firstChild);
    el._tbValues = {};
    var add = function (value, text, disabled) {
      var o = document.createElement("option");
      o.value = value;
      o.textContent = text;
      if (disabled) { o.disabled = true; o.setAttribute("disabled", "disabled"); }
      if (!disabled && value !== "" && picked[value]) o.selected = true;
      el.appendChild(o);
      return o;
    };
    var each = function (v) { el._tbValues[String(v)] = v; add(String(v), String(v), false); };
    if (!el.multiple) add("All", "All", false).selected = !isArray(chosen);
    dom.present.forEach(each);
    if (dom.rest.length) {
      /* Short: a select is as wide as its longest option, and the
       * separator must not be what sets the width. */
      add("", "Not in view", true).title = "Not under this selection";
      dom.rest.forEach(each);
    }
  }

  function hydrateCalcControls() {
    fresh(controlEls("data-tb-filter"), "filter").forEach(function (el) {
      try {
        var column = attr(el, "data-tb-column");
        if (!column || !_calc.columns.hasOwnProperty(column)) {
          /* No slice carries it: the filter subsets stamped rows as it
           * always has, and says it does not reach the figures' numbers. */
          el.setAttribute("data-tb-fixed", "column not in slice");
          el.title = "This filter narrows the rows shown; the page has no data to recompute by "
            + humanise(column || "");
          plainFilter(el);
          return;
        }
        el._tbCalcColumn = column;
        fillCalcOptions(el);
        el.addEventListener("change", function () {
          var values = [], i, o;
          for (i = 0; i < el.options.length; i++) {
            o = el.options[i];
            if (o.selected && !o.disabled && el._tbValues.hasOwnProperty(o.value)) {
              values.push(el._tbValues[o.value]);
            }
          }
          disown(column);
          if (values.length) _calc.state[column] = values;
          else delete _calc.state[column];
          selectionChanged();
        });
      } catch (e) { /* defensive */ }
    });
  }

  function selectionChanged() {
    applyLocal(false);
    writeHash();
  }

  /* Run every plan under the state, then paint: figures first, then the
   * control domains, the chips, the trace and the host. On the first pass
   * of a page opened as authored only the marks are set: its figures are
   * already the stamped ones. */
  function applyLocal(initial) {
    computeLocal();
    if (initial && !_calc.local) {
      paintLiveMarks();
      paintLocalTrace();
      try { paintSelectionBar(); } catch (e) { /* defensive */ }
      return;
    }
    paintLocal();
    controlEls("data-tb-filter").forEach(function (el) {
      if (el._tbCalcColumn) { try { fillCalcOptions(el); } catch (e) { /* defensive */ } }
    });
    try { paintRanges(); } catch (e) { /* defensive */ }
    /* A chart whose binding is fixed at build draws the same rows, but its
     * marks and legend still show what the reader picked. */
    _charts.forEach(function (entry) {
      var res = _calc.results[entry.binding];
      if (res && !isFixed(res)) return;      /* redrawn with its binding */
      try { drawChart(entry, null, true); } catch (e) { /* defensive */ }
    });
    try { paintSelectionBar(); } catch (e) { /* defensive */ }
    paintChips();
    paintLocalTrace();
    _lastSelection = _calc.local ? {
      filters: _calc.state,
      figures: Object.keys(_liveBlocks).map(function (b) {
        return { binding: b, rows: _liveBlocks[b].rows };
      })
    } : null;
    paintSelectionReceipt({ filters: _calc.state, local: _calc.local });
    postLocal();
    notifySelection();
  }

  /* ── Download — the binding's embedded canonical CSV, byte-verbatim ──── */

  function hydrateDownloads() {
    fresh(controlEls("data-tb-download"), "download").forEach(function (el) {
      try {
        var binding = attr(el, "data-tb-binding");
        var label = attr(el, "data-tb-label");
        if (label !== null) el.textContent = label;
        else if (!trim(el.textContent)) el.textContent = "CSV";
        var block = readBlock(binding);
        if (!block) { noteUnknown(el, "unknown binding: " + binding); return; }
        el.addEventListener("click", function () {
          try {
            /* Always the FULL binding, never the filtered view — the export
             * cannot be used to pass off a subset as the whole.
             * On a CSV artifact this is the stamped triple's csv string
             * exactly as embedded, i.e. the bytes the fingerprint covers.
             * On a Parquet artifact it is that same data re-serialised from
             * the decoded block (the fingerprinted bytes are not carried in
             * the page), so it is faithful to the embedded values but not
             * byte-identical to the hashed string — the file itself, checked
             * with `verify --file`, remains the receipt. */
            /* Under a selection the file says it is not what the page
             * shows: the header line names it the full binding. As built,
             * it is the block's bytes alone. */
            var text = (_calc && _calc.local)
              ? "# selection: none (full binding)\n" + block.csv : block.csv;
            var blob = new Blob([text], { type: "text/csv" });
            var url = URL.createObjectURL(blob);
            var a = document.createElement("a");
            a.href = url;
            a.download = binding + ".csv";
            a.click();
            URL.revokeObjectURL(url);
          } catch (e) { /* defensive */ }
        });
      } catch (e) { /* defensive */ }
    });
  }

  /* ── Scrollable tables — presentation only ─────────────────────────────
   * Runs after badges: badgeHost must see the table's own parent, so a
   * badge pins to the anchor OUTSIDE the scrolling region and stays put. */

  function hydrateScroll() {
    _scrollReady = true;
    _tables.forEach(function (entry) {
      try {
        if (!fresh([entry.el], "scroll").length) return;
        var el = entry.el;
        var want = attr(el, "data-tb-rows");
        if (want === "all") return; /* the author opted out */
        var n = want === null ? 10 : parseInt(want, 10);
        if (!isFinite(n) || n < 1) n = 10;
        if (entry.rowCount <= n) return;
        var parent = el.parentNode;
        if (!parent) return;
        if ((" " + parent.className + " ").indexOf(" tb-scroll ") !== -1) {
          attachWindow(entry);
          return;
        }
        var wrap = document.createElement("div");
        wrap.className = "tb-scroll";
        /* ~n rows: a row is about 2.6em (line + cell padding), plus the
         * sticky header — em-based so it tracks the report's type size. */
        wrap.style.maxHeight = ((n + 1) * 2.6) + "em";
        parent.insertBefore(wrap, el);
        wrap.appendChild(el);
        /* The box exists now, so a windowed table can measure it and follow
         * its scroll. Tables at or below the threshold never set windowed. */
        attachWindow(entry);
      } catch (e) { /* defensive */ }
    });
    hydrateMore();
  }

  /* More to scroll: a box that scrolls a table (a .tb-scroll, the kit's
   * <Table>, or on a phone a table or card that scrolls itself) says which
   * way more of it lies, data-tb-more="x", "y" or "xy", and tracebi.css
   * fades that edge. Kept current on scroll, on resize, and when the table
   * inside changes size (a filter, a tab shown). Presentation only. */
  var _moreSeen = typeof WeakSet !== "undefined" ? new WeakSet() : null, _moreObserver = null;
  /* A row of the page's controls, which scrolls sideways on a phone (tracebi.css). */
  var CONTROL_ROW = ":is(div, p):has(> label > :is([data-tb-filter], [data-tb-search]), > [data-tb-range])";
  var MORE_BOXES = ".tb-scroll, .tb-table, [data-tb-figure=\"table\"], .tb-card";
  function controlRows() {
    try { return document.querySelectorAll(CONTROL_ROW); } catch (e) { return []; }
  }
  function markMore(box) {
    var cs = getComputedStyle(box);
    var sx = /auto|scroll/.test(cs.overflowX), sy = /auto|scroll/.test(cs.overflowY);
    var more = (sx && box.scrollWidth - box.clientWidth - box.scrollLeft > 1 ? "x" : "")
      + (sy && box.scrollHeight - box.clientHeight - box.scrollTop > 1 ? "y" : "");
    if (more) box.setAttribute("data-tb-more", more);
    else box.removeAttribute("data-tb-more");
  }
  function moreBox(el) {
    if (!el || !el.matches) return false;
    if (el.matches(MORE_BOXES)) return true;
    try { return el.matches(CONTROL_ROW); } catch (e) { return false; }
  }
  function hydrateMore() {
    if (typeof getComputedStyle === "undefined" || !_moreSeen) return;
    if (!_moreObserver) {
      document.addEventListener("scroll", function (e) {
        if (moreBox(e.target)) markMore(e.target);
      }, true);
      root.addEventListener("resize", hydrateMore);
      if (typeof ResizeObserver !== "undefined") {
        _moreObserver = new ResizeObserver(function (entries) {
          entries.forEach(function (en) {
            if (moreBox(en.target)) markMore(en.target);
            if (moreBox(en.target.parentNode)) markMore(en.target.parentNode);
          });
        });
      } else {
        _moreObserver = { observe: function () {} };
      }
    }
    var boxes = Array.prototype.slice.call(document.querySelectorAll(MORE_BOXES))
      .concat(Array.prototype.slice.call(controlRows())), i;
    for (i = 0; i < boxes.length; i++) {
      markMore(boxes[i]);
      if (!_moreSeen.has(boxes[i])) {
        _moreSeen.add(boxes[i]);
        _moreObserver.observe(boxes[i]);
        if (boxes[i].firstElementChild) _moreObserver.observe(boxes[i].firstElementChild);
      }
    }
  }

  /* ── Tabs — the bar is built from the section labels ─────────────────── */

  function hydrateTabs() {
    var groups = Array.prototype.slice.call(
      document.querySelectorAll(".tb-tabs"));
    groups.forEach(function (group) {
      try {
        var sections = [], i, kids = group.children;
        for (i = 0; i < kids.length; i++) {
          if (kids[i].getAttribute && attr(kids[i], "data-tb-tab")) {
            sections.push(kids[i]);
          }
        }
        if (!sections.length) return;
        var bar = document.createElement("div");
        bar.className = "tb-tab-bar";
        /* The buttons, not bar.children: a sidebar may also hold the title. */
        var buttons = [];
        var select = function (idx) {
          for (var j = 0; j < sections.length; j++) {
            if (j === idx) {
              addClass(sections[j], "tb-tab-active");
              addClass(buttons[j], "tb-tab-active");
            } else {
              removeClass(sections[j], "tb-tab-active");
              removeClass(buttons[j], "tb-tab-active");
            }
          }
          /* A chart hidden at init has no size yet — remeasure them all. */
          resizeCharts();
        };
        sections.forEach(function (sec, idx) {
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "tb-tab";
          btn.textContent = attr(sec, "data-tb-tab");
          btn.addEventListener("click", function () { select(idx); });
          buttons.push(btn);
          bar.appendChild(btn);
        });
        /* CSS hides non-active sections only once the bar exists (sibling
         * combinator) — a page whose script never ran shows every section,
         * and charts were measured before this pass hid anything. */
        group.insertBefore(bar, group.firstChild);
        select(0);
      } catch (e) { /* defensive */ }
    });
  }

  /* ── The title — when it was built, and where it sits ─────────────────
   * [data-tb-built] shows when this file was built, read from its own
   * receipt: a fact about the build, never typed in. A title marked
   * data-tb-title="nav" moves to the top of a sidebar tab bar.
   *
   * The masthead (.tb-masthead): its .tb-masthead-meta holds the period
   * (data-tb-period on the masthead), the build time and the verdict chip;
   * whichever a template left out is added, so every masthead carries the
   * chip. The chip's state is read from the file, never from the page's
   * markup: "draft" on a working preview (stage exploration, no receipt),
   * "not-checked" on a built file — nothing has re-run its queries, so the
   * file cannot honestly say they reproduce. An author-written state is
   * overwritten; a chip never turns green on its own say-so. */

  var _VERDICTS = {
    draft: { text: "Draft",
             tip: "A working preview. It carries no trace." },
    "not-checked": { text: "Not checked",
                     tip: "Nothing has re-run this file's queries since it was " +
                          "built. tracebi verify re-runs them against the " +
                          "model and says whether each figure reproduces." },
    /* The three a checker states (tracebi verify, the web app); this file
     * never chooses them for itself. renderReceipt shows them when its
     * host passes one; the chips, when the app framing the file says so. */
    reproduces: { text: "Reproduces",
                  tip: "Re-running every query gave the data this file carries." },
    "needs-a-look": { text: "Needs a look",
                      tip: "The source or the model changed since this build." },
    "does-not-reproduce": { text: "Does not reproduce",
                            tip: "Re-running a query gave different data." },
    /* The reader's selection, not the build's: the page recomputed its
     * figures from the embedded data (The live page). Never green; a
     * figure fixed at build keeps the file's own state. */
    local: { text: "Local",
             tip: "Recomputed on this page from the embedded data" }
  };

  function verdictState() {
    var meta = document.querySelector('meta[name="tracebi-stage"]');
    var stage = meta ? meta.getAttribute("content") : null;
    var receipt = document.getElementById("tracebi-receipt");
    return (stage === "final" && receipt) ? "not-checked" : "draft";
  }

  /* What the chips say. The file's own state, unless the app that shows it
   * in a frame has said what its checker found (Host bridge,
   * "tracebi:verdict"): the one way a chip here reads green, and only
   * because the embedding window said so. Opened on its own (a file, /r/,
   * an email) nothing can say it, and a draft stays a draft whatever it is
   * told. */
  var _hostVerdict = null;
  function builtVerdict() {
    var own = verdictState();
    if (own === "draft" || !_hostVerdict) return { state: own, tip: _VERDICTS[own].tip };
    return _hostVerdict;
  }

  /* While the reader's selection is not the authored one, a built file says
   * Local: what it shows was recomputed here, not what was built or
   * checked. */
  function chipVerdict() {
    var built = builtVerdict();
    if (built.state !== "draft" && _calc && _calc.local) {
      return { state: "local", tip: _VERDICTS.local.tip };
    }
    return built;
  }

  function paintChips() {
    var said = chipVerdict(), spec;
    var chips = document.querySelectorAll(".tb-verdict"), i, chip;
    for (i = 0; i < chips.length; i++) {
      chip = chips[i];
      /* A certificate mounted elsewhere states what its host passed it; the
       * page's own drawer follows the page. */
      if (inReceipt(chip) && !inDrawer(chip)) continue;
      /* A figure's own chip on a binding fixed at build keeps the build's
       * state: Local would claim a recompute that did not happen. */
      said = chipVerdict();
      if (said.state === "local" && chip.__tbFig && chip.__tbFig.getAttribute("data-tb-fixed") !== null) {
        said = builtVerdict();
      }
      spec = _VERDICTS[said.state];
      chip.setAttribute("data-tb-verdict", said.state);
      chip.textContent = spec.text;
      chip.title = said.tip;
      if (chip.getAttribute("role") === "button") {
        chip.setAttribute("aria-label", spec.text + ": how these numbers were made");
      }
    }
  }

  function hydrateMasthead() {
    var heads = document.querySelectorAll(".tb-masthead"), i, head, meta, el;
    for (i = 0; i < heads.length; i++) {
      head = heads[i];
      meta = head.querySelector(".tb-masthead-meta");
      if (!meta) {
        meta = document.createElement("div");
        meta.className = "tb-masthead-meta";
        head.appendChild(meta);
      }
      var period = attr(head, "data-tb-period");
      if (period && !meta.querySelector(".tb-masthead-period")) {
        el = document.createElement("span");
        el.className = "tb-masthead-period";
        el.textContent = period;
        meta.insertBefore(el, meta.firstChild);
      }
      if (!head.querySelector("[data-tb-built]")) {
        el = document.createElement("span");
        el.setAttribute("data-tb-built", "");
        meta.appendChild(el);
      }
      if (!head.querySelector(".tb-verdict")) {
        el = document.createElement("span");
        el.className = "tb-verdict";
        meta.appendChild(el);
      }
      /* A masthead on a filled ground (the editorial hero, a banner, a
       * report's own hero) takes its links in its own ink (tracebi.css). */
      if (typeof getComputedStyle !== "undefined" && filledGround(getComputedStyle(head))) {
        head.setAttribute("data-tb-ground", "filled");
      }
    }
    paintChips();
    hostedMeta();
  }

  function filledGround(cs) {
    if (cs.backgroundImage && cs.backgroundImage !== "none") return true;
    var c = cs.backgroundColor || "";
    return !!c && c !== "transparent" && !/^rgba\(.*,\s*0\)$/.test(c);
  }

  /* Hosted: the app that frames this file said so ("tracebi:verdict" with
   * hosted: true, Host bridge). Its header already shows when the file was
   * built and its verdict, so each masthead's meta keeps the period and the
   * Receipt link and hides the build time and the chip. Opened on its own,
   * nothing is hidden. */
  var _hosted = false;
  function hostedMeta() {
    if (!_hosted) return;
    ["[data-tb-built]", ".tb-verdict"].forEach(function (sel) {
      var els = document.querySelectorAll(".tb-masthead .tb-masthead-meta " + sel), i;
      for (i = 0; i < els.length; i++) els[i].setAttribute("hidden", "");
    });
  }

  function inReceipt(el) { return within(el, "tb-receipt"); }
  function inDrawer(el) { return within(el, "tb-receipt-drawer"); }
  function within(el, cls) {
    for (var n = el.parentNode; n && n.className !== undefined; n = n.parentNode) {
      if ((" " + n.className + " ").indexOf(" " + cls + " ") !== -1) return true;
    }
    return false;
  }

  function hydrateTitle() {
    try { hydrateMasthead(); } catch (e) { /* defensive */ }
    try { placeReceiptTriggers(); } catch (e) { /* defensive */ }
    var el = document.getElementById("tracebi-receipt"), stamp = null, i;
    if (el) {
      try { stamp = JSON.parse(el.textContent).rendered_at || null; } catch (e) { stamp = null; }
    }
    var text = builtText(stamp);
    if (text) {
      var built = document.querySelectorAll("[data-tb-built]");
      for (i = 0; i < built.length; i++) built[i].textContent = text;
    }
    var title = document.querySelector('.tb-title[data-tb-title="nav"]')
      || document.querySelector('.tb-masthead[data-tb-title="nav"]');
    var bar = document.querySelector('.tb-tabs[data-tb-nav="side"] .tb-tab-bar');
    if (title && bar) bar.insertBefore(title, bar.firstChild);
  }

  /* ── The receipt drawer — provenance DISPLAY from #tracebi-receipt ─────
   * Renders ONLY what the build recorded: never re-colored, never
   * re-judged. Locked language: "the sink satisfied its contract" — never
   * "the transform was verified".
   *
   * Two parts. renderReceipt(mount, receipt, options) writes the certificate
   * into any element: the header (report, when it was built, from which
   * model, the verdict chip, the honesty line), how to check the file, one
   * row per figure (its value as shown, its label, the measure's definition,
   * the query in one line, the fingerprint's first 8 characters) with the
   * raw query and full fingerprint behind "Raw", and "About this build"
   * (sink contracts, the stated methodology, who built it, when, git) behind
   * one disclosure. The web app's report page mounts the same function in its
   * side panel. hydrateReceipt is the artifact's chrome around it: the
   * drawer (a sheet on a phone), its close button, and the ways to open it. */

  function receiptLine(parent, text, cls) {
    var div = document.createElement("div");
    div.className = cls || "tb-receipt-line";
    div.textContent = text;
    parent.appendChild(div);
    return div;
  }

  function receiptEl(parent, tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined && text !== null) el.textContent = text;
    parent.appendChild(el);
    return el;
  }

  /* Copy text to the clipboard; say so on the button, or select the text
   * when the browser refuses (a sandboxed frame, an old browser). */
  function receiptCopyButton(parent, text, label, target) {
    var btn = receiptEl(parent, "button", "tb-receipt-copy", "Copy");
    btn.type = "button";
    btn.setAttribute("aria-label", label);
    btn.addEventListener("click", function () {
      var said = function (ok) {
        btn.textContent = ok ? "Copied" : "Select";
        setTimeout(function () { btn.textContent = "Copy"; }, 1400);
        if (!ok && target && root.getSelection && document.createRange) {
          try {
            var range = document.createRange();
            range.selectNodeContents(target);
            var sel = root.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
          } catch (e) {}
        }
      };
      try {
        if (root.navigator && navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(text).then(
            function () { said(true); }, function () { said(false); });
          return;
        }
      } catch (e) {}
      said(false);
    });
    return btn;
  }

  /* The page element this figure record names, if the build placed one. */
  function receiptPageEl(fig, page) {
    if (!fig || !fig.id || !page || !page.getElementById) return null;
    var el = page.getElementById(fig.id);
    return (el && el.getAttribute) ? el : null;
  }

  /* Rows the query returned (recorded), else rows on the page, else the
   * stamped block when the figure has no table. */
  function receiptRowCount(el, binding, rec, page) {
    if (rec && typeof rec.rows === "number") return rec.rows;
    if (el && el.tagName === "TABLE") {
      var body = el.querySelector("tbody");
      if (body) {
        var n = 0, i, row;
        for (i = 0; i < body.children.length; i++) {
          row = body.children[i];
          if ((" " + (row.className || "") + " ").indexOf(" tb-empty ") !== -1) {
            continue;
          }
          n++;
        }
        return n;
      }
    }
    var block = (binding && page) ? readBlock(binding) : null;
    if (block && block.rows) return block.rows.length;
    return null;
  }

  function receiptBinding(receipt, fig) {
    var bindings = receipt && receipt.bindings;
    var rec = (bindings && fig.binding) ? bindings[fig.binding] : null;
    return (rec && typeof rec === "object") ? rec : null;
  }

  function receiptQuery(receipt, fig) {
    if (fig.query && typeof fig.query === "object") return fig.query;
    var rec = receiptBinding(receipt, fig);
    if (!rec) return null;
    return (rec.query && typeof rec.query === "object") ? rec.query : null;
  }

  function queryValue(v) {
    if (v && typeof v === "object" && v.length !== undefined) {
      return "(" + Array.prototype.map.call(v, String).join(", ") + ")";
    }
    return String(v);
  }

  /* {col: value | [values] | {op: value}} → "col = v, col in (a, b), col >= 5". */
  function filterText(filters) {
    if (!filters || typeof filters !== "object") return "";
    var parts = [], k, v, op, bits;
    for (k in filters) {
      if (!Object.prototype.hasOwnProperty.call(filters, k)) continue;
      v = filters[k];
      if (v && typeof v === "object" && v.length !== undefined) {
        parts.push(k + " in " + queryValue(v));
      } else if (v && typeof v === "object") {
        bits = [];
        for (op in v) {
          if (Object.prototype.hasOwnProperty.call(v, op)) {
            bits.push(k + " " + op + " " + queryValue(v[op]));
          }
        }
        parts.push(bits.join(", "));
      } else {
        parts.push(k + " = " + v);
      }
    }
    return parts.join(", ");
  }

  /* The query in one line, in the model's own names:
   * "fair_value by dim_issuer.sector · order fair_value desc · limit 10".
   * Only the ordering keys the author wrote; the rest is the engine's
   * tie-break, which stays in the raw query. */
  function queryLine(query, rec) {
    if (!query || typeof query !== "object") return "";
    if (typeof query.sql === "string") {
      return "sql " + trim(query.sql.replace(/\s+/g, " "));
    }
    var measures = query.measures, names = [], k;
    if (measures && typeof measures === "object" && measures.length === undefined) {
      for (k in measures) if (Object.prototype.hasOwnProperty.call(measures, k)) names.push(k);
    } else if (measures) {
      names = Array.prototype.map.call(measures, String);
    }
    var line = names.join(", ");
    var dims = query.dimensions || [];
    if (dims.length) line += (line ? " by " : "by ") + Array.prototype.join.call(dims, ", ");
    var where = filterText(query.filters);
    if (where) line += " · where " + where;
    var having = filterText(query.having);
    if (having) line += " · having " + having;
    var order = query.order_by || [];
    if (rec && typeof rec.order_stated === "number") order = order.slice(0, rec.order_stated);
    if (order.length) {
      line += " · order " + order.map(function (o) {
        if (o && typeof o === "object") return o.column + (o.desc ? " desc" : "");
        var t = String(o);
        return t.charAt(0) === "-" ? t.slice(1) + " desc" : t;
      }).join(", ");
    }
    if (query.limit !== undefined && query.limit !== null) line += " · limit " + query.limit;
    return line;
  }

  function queryMeasures(query, cell) {
    var m = query && query.measures, out = [], k;
    if (m && typeof m === "object" && m.length === undefined) {
      for (k in m) if (Object.prototype.hasOwnProperty.call(m, k)) out.push(k);
    } else if (m) {
      out = Array.prototype.map.call(m, String);
    }
    if (!out.length && cell) out = [cell];
    return out;
  }

  /* "Built Oct 17, 2026, 7:28 PM" from the file's own stamp, or null. */
  function builtText(stamp) {
    var when = stamp ? new Date(stamp) : null;
    if (!when || isNaN(when.getTime())) return null;
    return "Built " + when.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit" });
  }

  function receiptFigureRow(list, fig, receipt, ctx) {
    if (!fig || !fig.id) return;
    var page = receiptPageEl(fig, ctx.page);
    var kind = fig.kind || (page ? attr(page, "data-tb-figure") : null);
    var binding = fig.binding || (page ? attr(page, "data-tb-binding") : null);
    var cell = fig.cell || (page ? attr(page, "data-tb-cell") : null);
    if (!cell && page && kind === "chart") {
      var y = attr(page, "data-tb-y");
      if (y) cell = splitList(y)[0];
    }
    var rec = receiptBinding(receipt, fig);
    var query = receiptQuery(receipt, fig);

    var row = receiptEl(list, "div", "tb-receipt-row");
    row.setAttribute("data-tb-receipt-fig", String(fig.id));

    /* The label, and what the page shows: the value as formatted there, or
     * the figure's kind and rows. */
    var title = receiptEl(row, "div", "tb-receipt-title");
    var name, shown = "";
    if (kind === "value") {
      var labelEl = page ? page.querySelector(".tb-kpi-label") : null;
      var pageLabel = labelEl ? trim(labelEl.textContent || "") : "";
      /* A column uses the same words as the page's headings. A literal
       * figure has no column, so the label already printed on it is the
       * name. */
      name = cell ? humanise(cell)
        : (pageLabel || (binding ? humanise(binding) : humanise(fig.id)));
      var shownEl = page ? (page.querySelector(".tb-kpi-value") || page) : null;
      shown = shownEl ? trim(shownEl.textContent || "") : "";
    } else {
      name = binding ? humanise(binding) : humanise(fig.id);
    }
    receiptEl(title, "span", "tb-receipt-name", name);
    if (shown) {
      receiptEl(title, "span", "tb-receipt-value", shown);
    } else if (kind) {
      var what = kind;
      if (kind === "table" || kind === "chart") {
        var count = receiptRowCount(page, binding, rec, ctx.page);
        if (count !== null) what += ", " + count + (count === 1 ? " row" : " rows");
      }
      receiptEl(title, "span", "tb-receipt-kind", what);
    }
    if (fig.unverified) {
      /* The recorded status in its existing tone — display, not judgment. */
      receiptEl(title, "span", "tb-badge tb-badge--unverified", "unverified");
    }

    /* The definition in words: the model's description of each measure. */
    var measures = (kind === "value" && cell) ? [cell] : queryMeasures(query, cell);
    var defs = [], i, about;
    for (i = 0; i < measures.length; i++) {
      about = ctx.about.hasOwnProperty(measures[i]) ? ctx.about[measures[i]] : null;
      if (about) defs.push([measures[i], about]);
    }
    if (defs.length === 1 && kind === "value") {
      receiptEl(row, "p", "tb-receipt-def", defs[0][1]);
    } else if (defs.length) {
      var dl = receiptEl(row, "p", "tb-receipt-def");
      defs.forEach(function (d, j) {
        if (j) receiptEl(dl, "br");
        receiptEl(dl, "span", "tb-receipt-term", humanise(d[0]));
        receiptEl(dl, "span", null, " \u2014 " + d[1]);
      });
    }

    var facts = receiptEl(row, "dl", "tb-receipt-facts");
    var line = queryLine(query, rec);
    if (line) {
      receiptEl(facts, "dt", null, "Query");
      var dq = receiptEl(facts, "dd");
      receiptEl(dq, "code", "tb-receipt-query", line);
    } else if (rec && !rec.query) {
      receiptEl(facts, "dt", null, "Query");
      receiptEl(facts, "dd", "tb-receipt-noquery",
                "none: computed in report.py, not query-reproducible");
    }
    if (fig.fingerprint) {
      var full = String(fig.fingerprint);
      receiptEl(facts, "dt", null, "Fingerprint");
      var dfp = receiptEl(facts, "dd");
      var short = receiptEl(dfp, "code", "tb-receipt-fp-short", full.slice(0, 8));
      short.title = full;
      receiptCopyButton(dfp, full, "Copy the full fingerprint", short);
    }

    /* Raw: the addresses, the query exactly as run, the full fingerprint. */
    var details = receiptEl(row, "details", "tb-receipt-details");
    receiptEl(details, "summary", null, "Raw");
    var meta = String(fig.id);
    if (kind) meta += " · " + kind;
    if (binding) meta += " · " + binding;
    if (fig.model) meta += " · " + fig.model;
    receiptLine(details, meta, "tb-receipt-meta");
    if (query) {
      var pre = receiptEl(details, "pre", "tb-receipt-json");
      try { pre.textContent = JSON.stringify(query, null, 2); } catch (e) {}
    }
    if (fig.fingerprint) {
      var fp = receiptEl(details, "span", "tb-receipt-fp", String(fig.fingerprint));
      fp.title = String(fig.fingerprint);
    }
    if (_scriptChanged[fig.id]) paintScriptChange(String(fig.id));
  }

  /* The stated methodology the build recorded, in the author's words. */
  function receiptMethodology(parent, notes) {
    var byNote = {}, order = [], t, n;
    var tn = (notes && notes.transform_notes) || {};
    for (t in tn) {
      if (!Object.prototype.hasOwnProperty.call(tn, t)) continue;
      n = String(tn[t]);
      if (!byNote.hasOwnProperty(n)) { byNote[n] = []; order.push(n); }
      byNote[n].push(t);
    }
    var any = false;
    order.forEach(function (note) {
      receiptLine(parent, "the transform states, for " + byNote[note].join(", ")
                  + ": " + note, "tb-receipt-note");
      any = true;
    });
    ((notes && notes.check_notes) || []).forEach(function (cn) {
      if (!cn || !cn.note) return;
      receiptLine(parent, "the transform '" + cn.transform + "' states, of "
                  + cn.check + "(" + cn.table + "): " + cn.note, "tb-receipt-note");
      any = true;
    });
    var mn = (notes && notes.measure_notes) || {};
    for (t in mn) {
      if (!Object.prototype.hasOwnProperty.call(mn, t)) continue;
      receiptLine(parent, "measure '" + t + "': " + mn[t], "tb-receipt-note");
      any = true;
    }
    return any;
  }

  /* The file name to check, from the address it was opened at. */
  function receiptFileName(receipt) {
    var path = "";
    try { path = (root.location && root.location.pathname) || ""; } catch (e) {}
    var base = decodeURIComponent(String(path).split("/").pop() || "");
    /* Framed by the app (about:srcdoc) the page has no file name of its own. */
    if (!base || base === "srcdoc") {
      base = String(receipt.report || "report").toLowerCase()
        .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "report";
    }
    return /\.html?$/i.test(base) ? base : base + ".html";
  }

  /* Write the receipt certificate into `mount` (its children are replaced).
   *   receipt          the parsed #tracebi-receipt block
   *   options.contracts  the parsed tb-semantic-contract-* blocks, for the
   *                    measures' definitions (default: this page's)
   *   options.verdict  "draft" | "not-checked" | "reproduces" |
   *                    "needs-a-look" | "does-not-reproduce" (default: what
   *                    the page's chips say — the file's own state, never
   *                    green, unless the embedding app said otherwise)
   *   options.page     the document whose figures show the values (default:
   *                    this one; null where the page is out of reach)
   *   options.file     the file name the "how to check" line names
   * Returns the mount. Display only: it re-runs nothing. */
  function renderReceipt(mount, receipt, options) {
    var opts = options || {};
    while (mount.firstChild) mount.removeChild(mount.firstChild);
    addClass(mount, "tb-receipt");
    var page = opts.page !== undefined ? opts.page
      : (typeof document !== "undefined" ? document : null);
    var ctx = {
      page: page,
      about: measureIndex(opts.contracts || (page === document ? pageContracts() : []))
    };

    var head = receiptEl(mount, "header", "tb-receipt-header");
    receiptEl(head, "h2", "tb-receipt-head", receipt.report || "This report");
    receiptEl(head, "p", "tb-receipt-sub", "How each number was made");
    var models = receipt.semantic_contract_models || [], stampLine = [];
    if (!models.length) {
      (receipt.figures || []).forEach(function (f) {
        if (f && f.model && models.indexOf(f.model) === -1) models.push(f.model);
      });
    }
    var built = builtText(receipt.rendered_at);
    if (built) stampLine.push(built);
    if (models.length) stampLine.push(models.join(", "));
    if (stampLine.length) receiptEl(head, "p", "tb-receipt-built", stampLine.join(" · "));
    var said = (opts.verdict && _VERDICTS[opts.verdict])
      ? { state: opts.verdict, tip: _VERDICTS[opts.verdict].tip } : chipVerdict();
    var chipRow = receiptEl(head, "p", "tb-receipt-verdict");
    var chip = receiptEl(chipRow, "span", "tb-verdict", _VERDICTS[said.state].text);
    chip.setAttribute("data-tb-verdict", said.state);
    chip.title = said.tip;
    receiptEl(head, "p", "tb-receipt-honesty",
              "This page does not claim the numbers are right; it records "
              + "how each was made so it can be checked.");

    var file = opts.file || receiptFileName(receipt);
    var check = receiptEl(mount, "section", "tb-receipt-check");
    receiptEl(check, "h3", "tb-receipt-label", "How to check");
    var cmd = receiptEl(check, "div", "tb-receipt-cmd");
    var code = receiptEl(cmd, "code", null, "tracebi verify --file " + file);
    receiptCopyButton(cmd, "tracebi verify --file " + file, "Copy the command", code);
    receiptEl(check, "p", "tb-receipt-note",
              "Keep " + file + ".manifest.json beside the file. This checks "
              + "the file was not altered since it was built; tracebi verify "
              + "on the manifest re-runs each query against the model.");

    var figures = receipt.figures || [], i;
    var section = receiptEl(mount, "section", "tb-receipt-figures");
    receiptEl(section, "h3", "tb-receipt-label",
              figures.length === 1 ? "1 figure" : figures.length + " figures");
    for (i = 0; i < figures.length; i++) {
      try { receiptFigureRow(section, figures[i], receipt, ctx); } catch (e) { /* defensive */ }
    }

    var aboutBox = receiptEl(mount, "details", "tb-receipt-about");
    receiptEl(aboutBox, "summary", null, "About this build");
    var contracts = receipt.transform_contracts, table, rec, status;
    if (contracts && typeof contracts === "object") {
      receiptEl(aboutBox, "h4", "tb-receipt-label", "Sink contracts");
      for (table in contracts) {
        if (!contracts.hasOwnProperty(table)) continue;
        rec = contracts[table];
        status = (rec && typeof rec === "object") ? rec.status : rec;
        if (status === "satisfied") {
          receiptLine(aboutBox, table + ": the sink satisfied its contract");
        } else if (status === "stale") {
          receiptLine(aboutBox, table + ": contract stale — the warehouse "
                      + "has moved since the certificate");
        } else {
          receiptLine(aboutBox, table + ": no contract");
        }
      }
    }
    var stated = receipt.stated_methodology;
    if (stated && typeof stated === "object") {
      receiptEl(aboutBox, "h4", "tb-receipt-label", "Stated methodology");
      receiptMethodology(aboutBox, stated);
    } else if (receipt.methodology === true) {
      receiptLine(aboutBox, "stated methodology aboard");
    }
    if (receipt.app === true) {
      receiptLine(aboutBox, "This page is an app. The figures it shows through "
                  + "the TraceBi kit are traced; anything else it draws is the "
                  + "app's own presentation and is not checked.", "tb-receipt-note");
    }
    receiptEl(aboutBox, "h4", "tb-receipt-label", "The build");
    var mono = "tb-receipt-line tb-receipt-meta";
    if (models.length) receiptLine(aboutBox, "semantic contract: " + models.join(", "), mono);
    if (receipt.rendered_by) receiptLine(aboutBox, "built by " + receipt.rendered_by, mono);
    if (receipt.rendered_at) receiptLine(aboutBox, "rendered " + receipt.rendered_at, mono);
    if (receipt.git_sha) receiptLine(aboutBox, "git " + receipt.git_sha, mono);
    return mount;
  }

  function receiptDrawer() {
    return typeof document === "undefined" ? null
      : document.querySelector(".tb-receipt-drawer");
  }

  var _receiptOpener = null;
  function setReceiptOpen(on) {
    var drawer = receiptDrawer();
    if (!drawer) return false;
    var open = (" " + drawer.className + " ").indexOf(" tb-receipt-open ") !== -1;
    if (on === open) return true;
    if (on) {
      _receiptOpener = document.activeElement || null;
      addClass(drawer, "tb-receipt-open");
      var close = drawer.querySelector(".tb-receipt-close");
      if (close && close.focus) {
        try { close.focus({ preventScroll: true }); } catch (e) {}
      }
    } else {
      removeClass(drawer, "tb-receipt-open");
      if (_receiptOpener && _receiptOpener.focus) {
        try { _receiptOpener.focus(); } catch (e) {}
      }
      _receiptOpener = null;
    }
    var toggles = document.querySelectorAll(".tb-receipt-btn, .tb-receipt-link");
    for (var i = 0; i < toggles.length; i++) toggles[i].setAttribute("aria-expanded", on ? "true" : "false");
    return true;
  }

  function toggleReceipt() {
    var drawer = receiptDrawer();
    if (!drawer) return;
    setReceiptOpen((" " + drawer.className + " ").indexOf(" tb-receipt-open ") === -1);
  }

  /* A quiet "Trace" button for the masthead's meta line (after the
   * verdict chip), and "How these numbers were made" on the footer's line. */
  function receiptLinkButton(text) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "tb-receipt-link";
    b.textContent = text;
    b.setAttribute("aria-expanded", "false");
    b.addEventListener("click", toggleReceipt);
    return b;
  }

  /* Clicking a value figure opens the receipt at its row; the masthead's
   * verdict chip opens it too. Controls, links and selections are left
   * alone. */
  function onReceiptClick(e) {
    var n = e.target, drawer = receiptDrawer();
    if (!drawer) return;
    for (; n && n.nodeType === 1; n = n.parentNode) {
      if (n === drawer) return;
      if (/^(A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY|LABEL)$/.test(n.tagName)) return;
      if ((" " + n.className + " ").indexOf(" tb-verdict ") !== -1
          && n.getAttribute("role") === "button") {
        toggleReceipt();
        return;
      }
      if (n.getAttribute("data-tb-figure") === "value" && n.id) {
        var sel = root.getSelection ? root.getSelection() : null;
        if (sel && String(sel)) return;
        openReceipt(n.id);
        return;
      }
    }
  }

  function onReceiptKey(e) {
    var drawer = receiptDrawer();
    if (!drawer) return;
    if (e.key === "Escape"
        && (" " + drawer.className + " ").indexOf(" tb-receipt-open ") !== -1) {
      setReceiptOpen(false);
      return;
    }
    var t = e.target;
    if ((e.key === "Enter" || e.key === " ") && t && t.getAttribute
        && t.getAttribute("role") === "button"
        && (" " + t.className + " ").indexOf(" tb-verdict ") !== -1) {
      e.preventDefault();
      toggleReceipt();
    }
  }

  /* Where the page offers its trace: after the masthead's verdict chip
   * (the chip itself opens it too), and on the footer's line, which then
   * stands for the footer's disclosure (its notes are the drawer's About
   * this build; the disclosure stays for a reader without the runtime). A
   * page with no masthead keeps the floating Trace button. Safe to call
   * again: a masthead an app mounts later gets its link then. */
  function placeReceiptTriggers() {
    /* The footer's build day in the reader's own words, as the masthead
     * writes its build time (builtText), so one page never shows a date in
     * two shapes. The build writes the stamp; this only rewords it. */
    Array.prototype.forEach.call(document.querySelectorAll(".tb-footer-line time[datetime]"), function (tm) {
      var when = new Date(tm.getAttribute("datetime"));
      if (!isNaN(when.getTime())) {
        tm.textContent = when.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
      }
    });
    var drawer = receiptDrawer();
    if (!drawer) return;
    var metas = document.querySelectorAll(".tb-masthead .tb-masthead-meta"), i, chip;
    for (i = 0; i < metas.length; i++) {
      chip = metas[i].querySelector(".tb-verdict");
      if (chip && chip.getAttribute("role") !== "button") {
        chip.setAttribute("role", "button");
        chip.setAttribute("tabindex", "0");
        chip.setAttribute("aria-label", chip.textContent + ": how these numbers were made");
      }
      if (!metas[i].querySelector(".tb-receipt-link")) {
        metas[i].appendChild(receiptLinkButton("Trace"));
      }
    }
    var lines = document.querySelectorAll(".tb-footer-line");
    for (i = 0; i < lines.length; i++) {
      if (!lines[i].querySelector(".tb-receipt-link")) {
        lines[i].appendChild(document.createTextNode(" "));
        lines[i].appendChild(receiptLinkButton("How these numbers were made"));
      }
      var disclosure = lines[i].nextElementSibling;
      if (disclosure && (" " + disclosure.className + " ").indexOf(" tb-footer-details ") !== -1) {
        disclosure.hidden = true;
      }
    }
    var floating = document.querySelector(".tb-receipt-btn");
    if (metas.length) {
      if (floating && floating.parentNode) floating.parentNode.removeChild(floating);
    } else if (!floating) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tb-receipt-btn";
      btn.textContent = "Trace";
      btn.setAttribute("aria-expanded", "false");
      btn.addEventListener("click", toggleReceipt);
      document.body.appendChild(btn);
    }
  }

  function hydrateReceipt() {
    var el = document.getElementById("tracebi-receipt");
    if (!el || !document.body) return; /* no receipt block → no drawer */
    var receipt;
    try { receipt = JSON.parse(el.textContent); } catch (e) { return; }
    if (!receipt || typeof receipt !== "object") return;

    /* The chrome: a drawer on the right (a full-height sheet on a phone),
     * its close button, and a scrolling body the certificate fills. */
    var drawer = document.createElement("aside");
    drawer.className = "tb-receipt-drawer";
    drawer.setAttribute("aria-label", "How these numbers were made");
    var close = document.createElement("button");
    close.type = "button";
    close.className = "tb-receipt-close";
    close.setAttribute("aria-label", "Close");
    close.textContent = "×";
    close.addEventListener("click", function () { setReceiptOpen(false); });
    drawer.appendChild(close);
    var scroll = document.createElement("div");
    scroll.className = "tb-receipt-scroll";
    drawer.appendChild(scroll);
    var mount = document.createElement("div");
    scroll.appendChild(mount);
    renderReceipt(mount, receipt);

    var selecting = _calc && _calc.controls;
    if (selecting) {
      var about = mount.querySelector(".tb-receipt-about");
      var sel = document.createElement("section");
      sel.className = "tb-receipt-selection";
      var status = receiptLine(sel, "selection: authored", "tb-receipt-line");
      status.id = "tb-selection-status";
      var slice = document.createElement("button");
      slice.type = "button";
      slice.className = "tb-receipt-line";
      slice.textContent = "Download this selection";
      slice.addEventListener("click", downloadSelection);
      sel.appendChild(slice);
      mount.insertBefore(sel, about);
    }

    document.body.appendChild(drawer);
    placeReceiptTriggers();
    document.addEventListener("click", onReceiptClick);
    document.addEventListener("keydown", onReceiptKey);
    if (document.documentElement) addClass(document.documentElement, "tb-has-receipt");
    if (selecting) paintSelectionReceipt({ filters: _calc.state, local: false });
  }

  /* ── Scenarios — the one place the page computes ───────────────────────
   * A data-tb-scenario block holds data-tb-input fields, optional
   * data-tb-preset pickers that fill inputs from a STAMPED row, and
   * data-tb-calc outputs evaluated here from the reader's own inputs. A
   * scenario is never a figure and never in the receipt; the runtime labels
   * every one so a computed number is never read as a receipted one. The
   * formula grammar mirrors tracebi/reports/scenario.py exactly (numbers,
   * input names, + - * / ^, unary minus, parentheses, pmt/min/max/round/abs)
   * and is parsed here by hand: no eval, so the strict CSP holds. */
  var _FUNCS = { pmt: [3, 3], min: [1, 99], max: [1, 99], round: [1, 2], abs: [1, 1] };

  function scenarioTokens(src) {
    var re = /\s*(?:(\d+(?:\.\d*)?|\.\d+)|([A-Za-z_][A-Za-z0-9_]*)|([-+*\/^(),]))/g;
    var out = [], m, pos = 0, text = src.replace(/\s+$/, "");
    while (pos < text.length) {
      re.lastIndex = pos;
      m = re.exec(text);
      if (!m || m.index !== pos || re.lastIndex === pos) throw new Error("bad formula");
      out.push(m[1] !== undefined ? { k: "num", v: Number(m[1]) }
        : m[2] !== undefined ? { k: "name", v: m[2] } : { k: "op", v: m[3] });
      pos = re.lastIndex;
    }
    return out;
  }

  function pmt(rate, periods, principal) {
    if (!(periods > 0)) return NaN;
    if (rate === 0) return principal / periods;
    return principal * rate / (1 - Math.pow(1 + rate, -periods));
  }

  /* Parse and evaluate in one pass over the token list. */
  function evalFormula(src, values) {
    var toks = scenarioTokens(src), i = 0;
    function peek() { return toks[i] || { k: null, v: null }; }
    function take(v) {
      var t = peek();
      if (t.k === null || (v !== undefined && t.v !== v)) throw new Error("bad formula");
      i++;
      return t;
    }
    function expr() {
      var a = term();
      while (peek().v === "+" || peek().v === "-") {
        a = take().v === "+" ? a + term() : a - term();
      }
      return a;
    }
    function term() {
      var a = unary(), b;
      while (peek().v === "*" || peek().v === "/") {
        if (take().v === "*") { a = a * unary(); }
        else { b = unary(); a = b === 0 ? NaN : a / b; }
      }
      return a;
    }
    function unary() {
      if (peek().v === "-" && peek().k === "op") { take(); return -unary(); }
      var base = atom();
      if (peek().v === "^") { take(); return Math.pow(base, unary()); }
      return base;
    }
    function atom() {
      var t = peek(), args, spec, f;
      if (t.k === "num") { take(); return t.v; }
      if (t.k === "name") {
        take();
        if (peek().v !== "(") {
          if (!Object.prototype.hasOwnProperty.call(values, t.v)) throw new Error("unknown input");
          return values[t.v];
        }
        spec = _FUNCS[t.v];
        if (!spec) throw new Error("unknown function");
        take("(");
        args = [expr()];
        while (peek().v === ",") { take(); args.push(expr()); }
        take(")");
        if (args.length < spec[0] || args.length > spec[1]) throw new Error("arity");
        f = t.v;
        if (f === "pmt") return pmt(args[0], args[1], args[2]);
        if (f === "min") return Math.min.apply(null, args);
        if (f === "max") return Math.max.apply(null, args);
        if (f === "abs") return Math.abs(args[0]);
        var factor = Math.pow(10, args.length > 1 ? Math.floor(args[1]) : 0);
        return Math.floor(args[0] * factor + 0.5) / factor;
      }
      if (t.v === "(") { take(); var v = expr(); take(")"); return v; }
      throw new Error("bad formula");
    }
    var result = expr();
    if (i !== toks.length) throw new Error("bad formula");
    return result;
  }

  function hydrateScenarios() {
    var blocks = document.querySelectorAll("[data-tb-scenario]");
    Array.prototype.forEach.call(blocks, function (box) {
      try {
        addClass(box, "tb-scenario");
        if (!box.querySelector(".tb-scenario-label")) {
          var label = document.createElement("div");
          label.className = "tb-scenario-label";
          label.textContent = "Scenario · computed in your browser from these inputs · not part of the trace";
          box.insertBefore(label, box.firstChild);
        }
        var inputs = box.querySelectorAll("[data-tb-input]");
        var calcs = box.querySelectorAll("[data-tb-calc]");
        var recompute = function () {
          var values = {}, ok = true;
          Array.prototype.forEach.call(inputs, function (el) {
            var n = toNum(el.value);
            if (n === null) ok = false;
            values[el.getAttribute("data-tb-input")] = n;
          });
          Array.prototype.forEach.call(calcs, function (el) {
            var out = "—";
            if (ok) {
              try {
                var v = evalFormula(el.getAttribute("data-tb-calc"), values);
                if (isFinite(v)) {
                  var f = attr(el, "data-tb-format");
                  out = f ? applyNamedFormat(v, f) : null;
                  if (out === null) out = fixedGrouped(v, 2);
                }
              } catch (e) { out = "—"; }
            }
            el.textContent = out;
          });
        };
        Array.prototype.forEach.call(box.querySelectorAll("[data-tb-preset]"), function (sel) {
          var block = readBlock(attr(sel, "data-tb-preset"));
          var key = attr(sel, "data-tb-key");
          if (!block || !key) return;
          var fill = {};
          splitList(attr(sel, "data-tb-fill") || "").forEach(function (pair) {
            var p = pair.split("=");
            if (p.length === 2) fill[trim(p[0])] = trim(p[1]);
          });
          if (sel.tagName === "SELECT" && !sel.options.length) {
            block.rows.forEach(function (r) {
              var o = document.createElement("option");
              o.value = r[key];
              o.textContent = r[key];
              sel.appendChild(o);
            });
          }
          var apply = function () {
            var row = null;
            block.rows.forEach(function (r) { if (String(r[key]) === String(sel.value)) row = r; });
            if (!row) return;
            Array.prototype.forEach.call(inputs, function (el) {
              var col = fill[el.getAttribute("data-tb-input")];
              /* The stamped value, written plainly: "84300.0" reads as 84300. */
              if (col && row[col] !== undefined) {
                var n = toNum(row[col]);
                el.value = n === null ? row[col] : String(n);
              }
            });
            recompute();
          };
          var dflt = attr(sel, "data-tb-default");
          if (dflt !== null) sel.value = dflt;
          sel.addEventListener("change", apply);
          apply();
        });
        Array.prototype.forEach.call(inputs, function (el) {
          el.addEventListener("input", recompute);
          el.addEventListener("change", recompute);
        });
        recompute();
      } catch (e) { /* defensive */ }
    });
  }

  /* Hydrate figures mounted since the last pass — what a React app calls
   * after it renders new ones. Entries whose element left the page are
   * dropped, so a filter never redraws a figure nobody can see. */
  function refresh() {
    if (!_dataReady || typeof document === "undefined") return;
    var on = function (e) { return document.documentElement.contains(e.el); };
    for (var i = _tables.length - 1; i >= 0; i--) if (!on(_tables[i])) _tables.splice(i, 1);
    for (var j = _charts.length - 1; j >= 0; j--) {
      if (on(_charts[j])) continue;
      if (_chartResize) { try { _chartResize.unobserve(_charts[j].surface); } catch (e) {} }
      disposeChart(_charts[j]);
      _charts.splice(j, 1);
    }
    try { hydrateValues(); } catch (e) {}
    try { hydrateTables(); } catch (e) {}
    try { hydrateCharts(); } catch (e) {}
    try { hydrateBadges(); } catch (e) {}
    try { hydrateScroll(); } catch (e) {}
    try { hydrateControls(); } catch (e) {}
    try { hydrateDownloads(); } catch (e) {}
    try { hydrateTitle(); } catch (e) {}
    /* Figures an app mounted since were filled from the stamped rows: under
     * a selection they take the current result, and every figure its mark. */
    if (_calc) {
      try { if (_calc.local) paintLocal(); else paintLiveMarks(); } catch (e) {}
      /* The trace's local rows and count follow the figures now on the
       * page: an app's view mounted since names its figures there too. */
      try { if (_calc.local || _calc.error) paintLocalTrace(); } catch (e) {}
      try { paintChips(); } catch (e) {}
      try { paintRanges(); } catch (e) {}
      try { paintSelectionBar(); } catch (e) {}
    }
  }

  function hydrate() {
    try { bindPrintMode(); } catch (e) {}
    try { hydrateValues(); } catch (e) {}
    try { hydrateTables(); } catch (e) {}
    try { hydrateCharts(); } catch (e) {}
    try { hydrateDrawn(); } catch (e) {}
    /* Badges after values (value writes replace textContent and must not
     * eat them) and BEFORE the scroll wrap, so a table's badge anchors
     * outside the scrolling region. */
    try { hydrateBadges(); } catch (e) {}
    try { hydrateScroll(); } catch (e) {}
    /* Tabs after charts: sections hide only once the bar exists, so every
     * chart measured its size while still visible. */
    try { hydrateTabs(); } catch (e) {}
    try { hydrateTitle(); } catch (e) {}
    try { hydrateControls(); } catch (e) {}
    try { hydrateDownloads(); } catch (e) {}
    try { hydrateReceipt(); } catch (e) {}
    try { hydrateScenarios(); } catch (e) {}
    /* A selection from the address applies here, before the first paint;
     * as authored, this only marks the figures fixed at build. */
    if (_calc) { try { applyLocal(true); } catch (e) {} }
    if (_calc) { try { document.addEventListener("keydown", onSelectionKey, true); } catch (e) {} }
    try { watchStampedFigures(); } catch (e) {}
    /* Set once figures are drawn, charts included, and their first fade has
     * finished. A printer waits for this; it changes no number. */
    var waited = 0;
    var markReady = function () {
      if (_introPending > 0 && waited < 1500) {
        waited += 50;
        setTimeout(markReady, 50);
        return;
      }
      try {
        if (document.documentElement && document.documentElement.setAttribute) {
          document.documentElement.setAttribute("data-tb-ready", "1");
        }
      } catch (e) {}
    };
    markReady();
  }

  /* ── Parquet data blocks ───────────────────────────────────────────────
   * Large-detail artifacts embed each binding as Parquet. The page engine
   * (tracebi-calc.js, inlined with any Parquet block) decodes them at boot,
   * before hydration, into _blocks in the SAME {cols, rows, csv} shape
   * readBlock() produces, so the whole runtime below is untouched. A
   * CSV-only artifact carries no Parquet block and behaves exactly as before. */
  function b64ToBytes(b64) {
    var bin = atob(String(b64).replace(/\s+/g, "")), n = bin.length, u = new Uint8Array(n);
    for (var i = 0; i < n; i++) u[i] = bin.charCodeAt(i);
    return u;
  }
  function parquetDataBlocks() {
    var out = [];
    if (typeof document === "undefined") return out;
    var els = document.querySelectorAll('script[type="application/json"][id^="tracebi-data-"]');
    for (var i = 0; i < els.length; i++) {
      var t = els[i].textContent;
      if (!t || t.indexOf('"parquet"') === -1) continue; /* cheap skip of CSV blocks */
      try {
        var p = JSON.parse(t);
        if (p && p.format === "parquet" && typeof p.parquet_b64 === "string") {
          out.push({ name: p.name || els[i].id.slice(13), b64: p.parquet_b64 });
        }
      } catch (e) {}
    }
    return out;
  }

  /* Values leave the decode as the STRINGS the CSV embed would have carried.
   * The runtime was written against the CSV path, where every cell is a
   * string it then parses and formats; handing it numbers would make the
   * same receipted data DISPLAY differently either side of the size
   * threshold. So each cell is spelt as pandas' to_csv spells it: an
   * integral float keeps its ".0", a boolean is True/False, a missing value
   * is empty, and a datetime column is a bare date when EVERY value is
   * midnight (pandas decides per column) and "YYYY-MM-DD HH:MM:SS"
   * otherwise. The build sends only columns this rule covers
   * (embed._renders_identically); anything else stays CSV. */
  function pyRepr(v) {
    /* Python's repr of a finite float: shortest round-trip digits (what
     * toExponential() gives), fixed while the exponent is in [-4, 16) with
     * ".0" kept on integral values, else e+NN / e-NN. */
    var parts = v.toExponential().split("e"), exp = parseInt(parts[1], 10);
    if (exp >= 16 || exp < -4) {
      var mag = String(Math.abs(exp));
      if (mag.length < 2) mag = "0" + mag;
      return parts[0] + "e" + (exp < 0 ? "-" : "+") + mag;
    }
    var m = parts[0], neg = "";
    if (m.charAt(0) === "-") { neg = "-"; m = m.slice(1); }
    var digits = m.replace(".", ""), out;
    if (exp >= 0) {
      out = exp + 1 >= digits.length
        ? digits + new Array(exp + 2 - digits.length).join("0") + ".0"
        : digits.slice(0, exp + 1) + "." + digits.slice(exp + 1);
    } else {
      out = "0." + new Array(-exp).join("0") + digits;
    }
    return neg + out;
  }
  function stampedCell(col, v, dateOnly) {
    if (col.type === "number") {
      if (v !== v) return "";
      if (col.integer) return String(v);
      if (v === Infinity) return "inf";
      if (v === -Infinity) return "-inf";
      if (v === 0 && 1 / v < 0) return "-0.0";
      return pyRepr(v);
    }
    if (col.type === "boolean") return v !== v ? "" : (v ? "True" : "False");
    if (v === null || v === undefined) return "";
    if (col.type === "datetime") return dateOnly ? v.slice(0, 10) : v.slice(0, 19).replace("T", " ");
    return v;
  }
  function stampedRows(table) {
    var cols = table.columns.map(function (c) { return c.name; }), rows = [], r, i, c;
    var values = table.columns.map(function (col) {
      var data = table.data[col.name], dict = table.dict[col.name], out = new Array(table.rows);
      for (r = 0; r < table.rows; r++) {
        out[r] = dict ? (data[r] < 0 ? null : dict[data[r]]) : data[r];
      }
      var dateOnly = col.type === "datetime" && out.every(function (v) {
        return v === null || v.length === 10 || /T00:00:00$/.test(v);
      });
      return out.map(function (v) { return stampedCell(col, v, dateOnly); });
    });
    for (r = 0; r < table.rows; r++) {
      var row = {};
      for (i = 0; i < cols.length; i++) row[cols[i]] = values[i][r];
      rows.push(row);
    }
    /* readBlock() always sets .csv (the download control reads it). */
    var esc = function (s) { return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    var lines = [cols.map(esc).join(",")];
    for (r = 0; r < rows.length; r++) {
      c = rows[r];
      lines.push(cols.map(function (k) { return esc(c[k]); }).join(","));
    }
    return { cols: cols, rows: rows, csv: lines.join("\n") + "\n" };
  }

  /* Decode every Parquet block into _blocks. A block that cannot be read (no
   * engine inlined, a bad block) is skipped: its figures fall back to their
   * server-rendered value or "no data", and the rest of the page hydrates. */
  function decodeDataBlocks() {
    var blocks;
    try { blocks = parquetDataBlocks(); } catch (e) { blocks = []; }
    if (!blocks.length || !root.tracebiCalc) return;
    blocks.forEach(function (b) {
      try { _blocks[b.name] = stampedRows(root.tracebiCalc.decode(b64ToBytes(b.b64))); }
      catch (e) { /* defensive */ }
    });
  }

  /* ── Stamped figures a script changed ─────────────────────────────────────
   * A report's script.js may draw anything, but a stamped value is a claim the
   * receipt backs with a query. When a script rewrites the text of one after
   * the runtime wrote it, the page no longer shows what the receipt covers:
   * the figure gets data-tb-script-changed and its receipt row says so. The
   * runtime's own later writes (a selection) re-stamp the text first, so only
   * somebody else's change counts. Value figures only: a chart or table is
   * redrawn by the runtime itself as controls move. */
  var _stamped = {};
  var _scriptChanged = {};
  var CHANGED_BY_SCRIPT = "changed on the page by a custom script";

  function stampedText(el) {
    var copy = (el.querySelector(".tb-kpi-value") || el).cloneNode(true);
    Array.prototype.forEach.call(copy.querySelectorAll(".tb-badge"), function (b) {
      b.parentNode.removeChild(b);
    });
    return trim(copy.textContent || "");
  }

  function valueFigures() {
    return Array.prototype.slice.call(
      document.querySelectorAll('[data-tb-figure="value"][id]'));
  }

  /* Remember what every value figure shows now, as the runtime left it. */
  function stampFigures() {
    valueFigures().forEach(function (el) { _stamped[el.id] = stampedText(el); });
    paintScriptChanges();
  }

  function paintScriptChange(id) {
    var rows = document.querySelectorAll(".tb-receipt-row[data-tb-receipt-fig]");
    Array.prototype.forEach.call(rows, function (row) {
      if (row.getAttribute("data-tb-receipt-fig") !== id) return;
      var old = row.querySelector(".tb-receipt-changed");
      if (old) old.parentNode.removeChild(old);
      if (!_scriptChanged[id]) return;
      var note = document.createElement("div");
      note.className = "tb-receipt-changed";
      note.textContent = CHANGED_BY_SCRIPT + ": the trace covers \u201c"
        + _stamped[id] + "\u201d, the page shows \u201c" + _scriptChanged[id] + "\u201d";
      var title = row.querySelector(".tb-receipt-title");
      row.insertBefore(note, title ? title.nextSibling : row.firstChild);
    });
  }

  function paintScriptChanges() {
    valueFigures().forEach(function (el) {
      var now = stampedText(el);
      var changed = _stamped.hasOwnProperty(el.id) && now !== _stamped[el.id];
      var was = _scriptChanged[el.id];
      /* Repaint only on a change of state: painting the receipt is itself a DOM
       * change, and must not wake this up again. */
      if (changed && was !== now) {
        _scriptChanged[el.id] = now;
        el.setAttribute("data-tb-script-changed", "1");
        paintScriptChange(el.id);
      } else if (!changed && was !== undefined) {
        delete _scriptChanged[el.id];
        el.removeAttribute("data-tb-script-changed");
        paintScriptChange(el.id);
      }
    });
  }

  function watchStampedFigures() {
    stampFigures();
    if (typeof MutationObserver === "undefined" || !document.body) return;
    new MutationObserver(paintScriptChanges).observe(
      document.body, { subtree: true, childList: true, characterData: true });
  }

  /* ── Build mode, in the frame ────────────────────────────────────────────
   * The web app's Build mode points at things in the report and shows what an
   * edit changed. It cannot read this document (the frame is sandboxed), so
   * the page does that part itself when the app asks: outline what the pointer
   * is over and report what was clicked; read the figures back out; flash the
   * ones that changed. Presentation only, and only on request from the
   * embedding window. */
  var POINT_CHROME = "#tracebi-receipt, .tb-badge, .tb-receipt-btn, .tb-receipt-link, .tb-receipt-drawer, [data-tb-chrome]";
  var POINT_INLINE = { SPAN: 1, B: 1, I: 1, EM: 1, STRONG: 1, A: 1, CODE: 1, SMALL: 1, SUP: 1, SUB: 1, TSPAN: 1 };
  var POINT_STYLE =
    ".tb-point-hover { outline: 2px solid #2563eb !important; outline-offset: 2px; cursor: crosshair !important; }" +
    ".tb-point-picked { outline: 2px solid #2563eb !important; outline-offset: 2px;" +
    " background-color: rgba(37,99,235,.08) !important; }" +
    "body * { cursor: crosshair; }";
  var FLASH_STYLE =
    "@keyframes tb-point-flash { from { outline-color: #d97706; background-color: rgba(217,119,6,.18); }" +
    " to { outline-color: transparent; background-color: transparent; } }" +
    ".tb-point-changed { outline: 2px solid #d97706; outline-offset: 2px; animation: tb-point-flash 3.5s ease-out forwards; }";

  function compactText(t) { return (t || "").replace(/\s+/g, " ").trim(); }

  function addStyle(attr, css) {
    var style = document.createElement("style");
    style.setAttribute(attr, "");
    style.textContent = css;
    document.head.appendChild(style);
    return style;
  }

  /* The element a click means: its figure, else the nearest block. */
  function pointTarget(el) {
    if (!el || el.nodeType !== 1 || el.closest(POINT_CHROME)) return null;
    var figure = el.closest("[data-tb-figure]");
    if (figure) return figure;
    var node = el;
    while (node && POINT_INLINE[node.tagName] && node.parentElement) node = node.parentElement;
    return node && node.tagName !== "HTML" && node.tagName !== "BODY" ? node : null;
  }

  function pointSelector(el) {
    var parts = [];
    for (var node = el; node && node.nodeType === 1 && node.tagName !== "BODY"; node = node.parentElement) {
      var part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift(part + "#" + node.id); break; }
      var cls = Array.prototype.filter.call(node.classList, function (c) { return c.indexOf("tb-point") !== 0; }).slice(0, 2);
      if (cls.length) part += "." + cls.join(".");
      parts.unshift(part);
      if (parts.length >= 4) break;
    }
    return parts.join(" > ");
  }

  /* The nearest heading above the element: which section of the page it is in. */
  function pointSection(el) {
    for (var node = el; node && node.nodeType === 1; node = node.parentElement) {
      for (var sib = node.previousElementSibling; sib; sib = sib.previousElementSibling) {
        if (/^H[1-6]$/.test(sib.tagName)) return sib.textContent;
        var inner = sib.querySelector && sib.querySelector("h1,h2,h3,h4,h5,h6");
        if (inner) return inner.textContent;
      }
    }
    return "";
  }

  /* What the agent is told: the figure's addresses, or the element's selector and text. */
  function describePoint(el) {
    var text = compactText(el.textContent).slice(0, 200);
    var figure = el.getAttribute("data-tb-figure");
    if (figure) {
      return {
        kind: "figure", figure_kind: figure, id: el.id || "",
        binding: el.getAttribute("data-tb-binding") || "",
        cell: el.getAttribute("data-tb-cell") || "", text: text
      };
    }
    return {
      kind: "element", tag: el.tagName.toLowerCase(), id: el.id || "",
      selector: pointSelector(el), text: text,
      section: compactText(pointSection(el)).slice(0, 120)
    };
  }

  var _stopPointing = null;
  function startPointing(post) {
    if (_stopPointing) return;
    var style = addStyle("data-tb-point", POINT_STYLE);
    var hovered = null, picked = null;
    function mark(el, cls, on) { if (el) el.classList[on ? "add" : "remove"](cls); }
    function over(e) {
      var el = pointTarget(e.target);
      if (el === hovered) return;
      mark(hovered, "tb-point-hover", false);
      hovered = el;
      mark(hovered, "tb-point-hover", true);
    }
    function out(e) {
      if (!e.relatedTarget) { mark(hovered, "tb-point-hover", false); hovered = null; }
    }
    function click(e) {
      var el = pointTarget(e.target);
      if (!el) return;
      e.preventDefault();
      e.stopPropagation();
      mark(picked, "tb-point-picked", false);
      picked = el;
      mark(picked, "tb-point-picked", true);
      post({ type: "pointed", point: describePoint(el) });
    }
    function key(e) {
      if (e.key !== "Escape") return;
      mark(picked, "tb-point-picked", false);
      picked = null;
      post({ type: "point-cleared" });
    }
    document.addEventListener("mouseover", over, true);
    document.addEventListener("mouseout", out, true);
    document.addEventListener("click", click, true);
    document.addEventListener("keydown", key, true);
    _stopPointing = function () {
      document.removeEventListener("mouseover", over, true);
      document.removeEventListener("mouseout", out, true);
      document.removeEventListener("click", click, true);
      document.removeEventListener("keydown", key, true);
      mark(hovered, "tb-point-hover", false);
      mark(picked, "tb-point-picked", false);
      if (style.parentNode) style.parentNode.removeChild(style);
      _stopPointing = null;
    };
  }

  /* {figure id: {kind, text, sig}} for every identified figure on the page. */
  function snapshotFigures() {
    var out = {};
    Array.prototype.forEach.call(document.querySelectorAll("[data-tb-figure][id]"), function (el) {
      var kind = el.getAttribute("data-tb-figure");
      var valueEl = el.querySelector(".tb-kpi-value") || el;
      var text = compactText(valueEl.textContent).slice(0, 60);
      /* A value is shown as itself; a chart or table only as "changed". */
      out[el.id] = { kind: kind, text: kind === "value" ? text : "", sig: compactText(el.textContent) };
    });
    return out;
  }

  function flashFigures(ids) {
    if (!ids || !ids.length) return;
    if (!document.querySelector("style[data-tb-flash]")) addStyle("data-tb-flash", FLASH_STYLE);
    ids.forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.classList.remove("tb-point-changed");
      void el.offsetWidth;                       /* restart the animation */
      el.classList.add("tb-point-changed");
    });
  }

  /* ── Host bridge ──────────────────────────────────────────────────────────
   * The web app shows a report in a sandboxed frame with an opaque origin: the
   * app cannot read the frame's DOM and the frame cannot read the app's. The
   * two talk by postMessage, and only about presentation: the frame tells the
   * app how tall it is, what its selection is (tracebi-selection, from
   * postLocal) and which figure was clicked; the app sets a selection, tells it its verdict on this build,
   * or has it take part in Build mode (above). Every
   * message carries tracebiFrame: 1; the frame accepts commands only from the
   * window that embeds it. A report opened on its own (no embedding window)
   * does none of this. */
  function hostBridge() {
    if (typeof document === "undefined" || !root.parent || root.parent === root) return;
    var host = root.parent;
    /* The frame grows to the page's height, so nothing in it can ride the
     * bottom of the screen; tracebi.css keeps the selection bar in flow. */
    if (document.documentElement) document.documentElement.setAttribute("data-tb-framed", "");
    function post(msg) {
      msg.tracebiFrame = 1;
      try { host.postMessage(msg, "*"); } catch (e) { /* defensive */ }
    }
    _hostPost = post;
    var lastHeight = -1;
    function size() {
      var h = Math.max(document.documentElement ? document.documentElement.scrollHeight : 0,
                       document.body ? document.body.scrollHeight : 0);
      if (!h || h === lastHeight) return;
      lastHeight = h;
      /* A frame holding nothing to operate is not a keyboard stop. */
      var focusable = !!document.querySelector(
        "a[href],button,input,select,textarea,summary,[tabindex],[contenteditable]");
      post({ type: "size", height: h, focusable: focusable });
    }
    function watch() {
      size();
      post({ type: "ready" });
      if (typeof ResizeObserver !== "undefined" && document.body) {
        new ResizeObserver(size).observe(document.body);
      }
    }
    if (document.readyState === "complete") watch();
    else root.addEventListener("load", watch);
    /* A click inside a figure tells the app which one, by its id and nothing
     * else, so the trace beside the page follows the figure being read. In
     * the capture phase: a chart's own click handler cannot hide it. */
    document.addEventListener("click", function (e) {
      var el = e.target && e.target.closest ? e.target.closest("[data-tb-figure][id]") : null;
      if (el) post({ type: "figure", id: el.id });
    }, true);

    var commands = {
      /* The app's header clears a field from the selection it shows. */
      "tracebi-set-selection": function (m) { setSelection(m.selection || {}); },
      point: function (m) { if (m.on) startPointing(post); else if (_stopPointing) _stopPointing(); },
      snapshot: function () { post({ type: "snapshot", figures: snapshotFigures() }); },
      flash: function (m) { flashFigures(m.ids); },
      /* The app's verdict on this build (its re-check, in its words): the
       * masthead chip and the drawer's say it instead of "Not checked".
       * Draft, or a state this file does not know, is ignored. hosted: true
       * says the app's header shows the build time and verdict, so the
       * masthead's meta reduces to the Receipt link (hostedMeta). */
      "tracebi:verdict": function (m) {
        if (m.state === "draft" || !_VERDICTS.hasOwnProperty(m.state)) return;
        _hostVerdict = { state: m.state,
                         tip: (typeof m.detail === "string" && m.detail) ? m.detail
                           : _VERDICTS[m.state].tip };
        paintChips();
        if (m.hosted === true) { _hosted = true; hostedMeta(); }
      }
    };
    root.addEventListener("message", function (e) {
      var m = e.data;
      if (e.source !== host || !m || m.tracebiFrame !== 1) return;
      if (commands.hasOwnProperty(m.type)) commands[m.type](m);
    });
  }
  hostBridge();

  /* ── For an author's own chart (app.jsx useBinding, <EChart>) ──
   * rows(name, keep): copies of the binding's rows as the page has them
   * now — on a live page the engine's answer under the selection, else the
   * stamped rows (embed none, a SQL binding, report.py). keep lists fields
   * whose other values stay (the chart's own field: it dims them instead of
   * narrowing). The same answers the kit's figures draw; nothing new is
   * computed, and an author's chart drawn from them still carries no
   * receipt. pick(column, value, event) is a click on a kit chart's mark:
   * the value, shift adds, again removes. */
  function authorRows(name, keep) {
    var block = readBlock(name), src;
    if (!block) return [];
    src = block.rows;
    if (_calc && _calc.local) {
      var own = (keep || []).filter(function (c, i, all) {
        return c && all.indexOf(c) === i && isArray(_calc.state[c]) && selectableField(c);
      });
      var res = own.length ? variantResult(name, own) : null;
      if (res && res.block) src = res.block.rows;
      else if (_liveRows[name]) src = _liveRows[name];
    }
    return src.map(function (r) {
      var o = {}, k;
      for (k in r) if (r.hasOwnProperty(k)) o[k] = r[k];
      return o;
    });
  }

  /* A number in a named format ("currency0", "percent", …; the table's and
   * the charts' formats), the raw value for an unknown one. */
  function formatNamed(v, mode) {
    var n = toNum(v), out;
    if (n === null) return v === null || v === undefined ? "" : String(v);
    out = mode ? applyNamedFormat(n, mode) : null;
    return out === null ? fmt(n) : out;
  }

  function currentSelection() {
    return _calc ? JSON.parse(JSON.stringify(_calc.state)) : {};
  }

  /* true when the pick was made: a column the page can select. */
  function authorPick(column, value, event) {
    var act = markAction(column);
    if (!act || value === null || value === undefined) return false;
    act(value, event);
    return true;
  }

  root.tracebi = {
    data: data,
    ready: ready,
    fmt: fmt,
    configureChart: configureChart,
    draw: draw,
    theme: theme,
    setSelection: setSelection,
    /* fn({selection, authored, figures}) on every change of the selection
     * state, from any control, mark, row, range, chip or setSelection. */
    onSelection: onSelection,
    result: result,
    rows: authorRows,
    selection: currentSelection,
    format: formatNamed,
    pick: authorPick,
    /* Whether a column is one the page's selection can name (a legend chip
     * selects it, or else shows and hides its series). */
    selectable: selectableField,
    refresh: refresh,
    /* For the kit's option-only <EChart>: the chart engine's tokens, its
     * ECharts theme and its dimming, so a chart of the page's own numbers
     * looks like every other. */
    _echarts: {
      tokens: function () { return chartTokens(); },
      theme: function () { return chartTheme(chartTokens()); },
      dim: function (opt, set) { return dimOption(opt, set, chartTokens()); }
    },
    /* The receipt certificate into any element (the web app's side panel
     * mounts it too); see renderReceipt. Display only. */
    renderReceipt: renderReceipt,
    /* The scenario evaluator, exposed so tests and authors can check a
     * formula gives what they expect. It computes from the values passed. */
    evaluate: evalFormula
  };

  /* DOM-ready, then requestAnimationFrame: the author's inline script.js has
   * already run by DOMContentLoaded, so its configureChart patches are
   * registered before any chart is drawn. This runs last, after every helper
   * above (and the host bridge) is set up: a synchronous first hydrate must
   * find them all in place. */
  if (typeof document !== "undefined") {
    var schedule = function () {
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(hydrate);
      else hydrate();
    };
    var boot = function () {
      try { decodeDataBlocks(); } catch (e) { /* defensive */ }
      /* A live page decodes its slices and reads its selection before
       * anything hydrates: an app's figures can mount (and call refresh)
       * before the first hydrate runs. */
      try { bootCalc(); } catch (e) { _calc = null; }
      _dataReady = true; runReady(); schedule();
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot);
    } else {
      boot();
    }
  }
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
