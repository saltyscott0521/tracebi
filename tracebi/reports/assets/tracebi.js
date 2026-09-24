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
 * the same law: they subset WHICH STAMPED ROWS figures display — they NEVER
 * compute new numbers. See the view layer below. A package that embeds
 * #tracebi-selection opts in: data-tb-filter POSTs the selection and paints
 * the query result, value figures included. The browser still does not
 * compute the measure. Offline, further slices need the model unless a
 * sealed grain can recompute simple aggregations and ratio.
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
   * decodes in a worker first, and script.js runs BEFORE that finishes — so a
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
    if (name === "percent") return pyFixed(n * 100, 1) + "%";
    return null; /* unknown name — caller falls back to the raw value */
  }

  /* ── Derived table labels + formats — the derive.py port ─────────────── */

  /* "dim_branch.region" → "Region"; "market_value" → "Market value". */
  function humanise(column) {
    var name = String(column).split(".").pop();
    name = name.replace(/^(dim|fact)_/, "");
    name = trim(name.replace(/_/g, " "));
    if (!name) return String(column);
    return name.charAt(0).toUpperCase() + name.slice(1);
  }

  /* id/key/year columns address a row rather than measure one — no format. */
  function isIdentity(column) {
    var name = String(column).toLowerCase();
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
   * Controls subset WHICH STAMPED ROWS figures display — they NEVER compute
   * new numbers. Client-side aggregation would mint numbers; it is
   * forbidden. Value figures never react to controls (a filtered KPI needs
   * its own binding). */

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

  /* binding → rows from the last selection response (or an offline port).
   * Absent on a package that did not opt in, so filteredRows stays the
   * stamped-row subset. */
  var _liveRows = {};
  var _lastSelection = null;

  /* The one gate reactive figures re-render through. Without a selection
   * block: the stamped rows, subset by the binding's filters and search.
   * With one: column filters were already applied by the query, so only
   * search subsets the live rows — and value figures are painted from the
   * result, not from this gate. */
  function filteredRows(binding) {
    var block = readBlock(binding);
    if (selectionConfig()) {
      var live = _liveRows[binding];
      var rows = live || (block ? block.rows : []);
      var cols = block ? block.cols : [];
      var view = _views[binding];
      if (!view || !view.search) return rows;
      return rows.filter(function (r) {
        return rowMatches(r, cols, { filters: {}, search: view.search });
      });
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

  /* Re-render the binding's table and chart figures from the filtered
   * stamped rows. Value figures are exempt BY CODE: controls subset which
   * stamped rows figures display — they never compute new numbers, and a
   * filtered KPI would be client-side aggregation, which would mint a
   * number. A filtered KPI needs its own binding. */
  function refreshBinding(binding) {
    var rows = filteredRows(binding), i, entry;
    for (i = 0; i < _tables.length; i++) {
      if (_tables[i].binding === binding) {
        try { renderBody(_tables[i], rows); } catch (e) { /* defensive */ }
      }
    }
    for (i = 0; i < _charts.length; i++) {
      entry = _charts[i];
      if (entry.binding === binding) {
        try {
          entry.chart.setOption(buildOption(entry.el, entry.plan, rows), true);
        } catch (e) { /* defensive */ }
      }
    }
  }

  function resizeCharts() {
    for (var i = 0; i < _charts.length; i++) {
      try { _charts[i].chart.resize(); } catch (e) { /* defensive */ }
    }
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

  /* ── ECharts option building (the interactive artifact runtime) ──────── */

  function groupOf(v) {
    return (v === null || v === undefined || v === "") ? "(none)" : String(v);
  }

  function categories(plan, rows) {
    var cats = [];
    rows.forEach(function (r) {
      var c = String(r[plan.x]);
      if (cats.indexOf(c) === -1) cats.push(c);
    });
    return cats;
  }

  function categoricalSeries(plan, rows, cats, kind) {
    var type = (kind === "line" || kind === "area") ? "line" : "bar";
    var mk = function (name, byCat) {
      var s = {
        name: name, type: type,
        data: cats.map(function (c) { return (c in byCat) ? byCat[c] : null; }),
        label: { show: false, position: kind === "barh" ? "right" : "top" }
      };
      if (kind === "area") s.areaStyle = {};
      return s;
    };
    if (plan.color) {
      var y0 = plan.y[0], groups = [], byGroup = {};
      rows.forEach(function (r) {
        var g = groupOf(r[plan.color]);
        if (groups.indexOf(g) === -1) { groups.push(g); byGroup[g] = {}; }
        byGroup[g][String(r[plan.x])] = toNum(r[y0]);
      });
      return groups.map(function (g) { return mk(g, byGroup[g]); });
    }
    return plan.y.map(function (col) {
      var byCat = {};
      rows.forEach(function (r) { byCat[String(r[plan.x])] = toNum(r[col]); });
      return mk(col, byCat);
    });
  }

  function scatterSeries(plan, rows) {
    if (plan.color) {
      var y0 = plan.y[0], groups = [], byGroup = {};
      rows.forEach(function (r) {
        var g = groupOf(r[plan.color]);
        if (groups.indexOf(g) === -1) { groups.push(g); byGroup[g] = []; }
        byGroup[g].push([toNum(r[plan.x]), toNum(r[y0])]);
      });
      return groups.map(function (g) {
        return { name: g, type: "scatter", data: byGroup[g] };
      });
    }
    return plan.y.map(function (col) {
      return { name: col, type: "scatter",
               data: rows.map(function (r) { return [toNum(r[plan.x]), toNum(r[col])]; }) };
    });
  }

  /* Guarded valueFormat, shared by every chart type: a known mode renders
   * the number; an unknown mode returns the raw value unchanged — an
   * attribute may format or do nothing, never blank out a number. */
  function formatChartValue(v, mode) {
    var n = toNum(v);
    if (n === null) return v;
    var formatted = applyNamedFormat(n, mode);
    return formatted === null ? v : formatted;
  }

  function optionFor(plan, rows) {
    var kind = String(plan.type).toLowerCase();
    var opt = { animation: false, color: plan.palette || [] };
    if (kind === "pie") {
      var y0 = plan.y[0];
      opt.tooltip = { trigger: "item" };
      opt.series = [{
        type: "pie", radius: "62%",
        data: rows.map(function (r) {
          return { name: String(r[plan.x]), value: Math.abs(toNum(r[y0]) || 0) };
        }),
        label: { show: true }
      }];
      if (plan.valueFormat) {
        opt.series[0].label.formatter = function (p) {
          return p.name + ": " + formatChartValue(p.value, plan.valueFormat);
        };
        opt.tooltip.valueFormatter = function (v) {
          return formatChartValue(v, plan.valueFormat);
        };
      }
      return opt;
    }
    if (kind === "scatter") {
      var ss = scatterSeries(plan, rows);
      opt.tooltip = { trigger: "item" };
      opt.xAxis = { type: "value" };
      opt.yAxis = { type: "value" };
      if (plan.valueFormat) {
        var sf = function (v) { return formatChartValue(v, plan.valueFormat); };
        opt.xAxis.axisLabel = { formatter: sf };
        opt.yAxis.axisLabel = { formatter: sf };
        opt.tooltip.valueFormatter = sf;
      }
      if (ss.length > 1) opt.legend = {};
      opt.series = ss;
      return opt;
    }
    var cats = categories(plan, rows);
    var series = categoricalSeries(plan, rows, cats, kind);
    opt.tooltip = { trigger: "axis" };
    if (series.length > 1) opt.legend = {};
    var catAxis = { type: "category", data: cats };
    var valAxis = { type: "value" };
    if (plan.valueFormat) {
      valAxis.axisLabel = { formatter: function (v) {
        return formatChartValue(v, plan.valueFormat);
      } };
    }
    if (kind === "barh") { opt.xAxis = valAxis; opt.yAxis = catAxis; }
    else { opt.xAxis = catAxis; opt.yAxis = valAxis; }
    opt.series = series;
    if (plan.valueFormat) {
      opt.tooltip.valueFormatter = function (v) {
        return formatChartValue(v, plan.valueFormat);
      };
      series.forEach(function (s) {
        s.label.formatter = function (p) {
          var v = p.value;
          if (v && typeof v === "object" && v.length !== undefined) v = v[v.length - 1];
          return formatChartValue(v, plan.valueFormat);
        };
      });
    }
    return opt;
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

  /* A value figure's format takes a table column's precedence: the author's
   * data-tb-format, then one the model declares on the measure, then the
   * shape guess — so an unformatted KPI reads 4,846.10, never 4846.1. */
  function valueFormat(el, rows, cell) {
    var name = attr(el, "data-tb-format");
    if (name || !isNumericColumn(rows, cell)) return name;
    return (declaredFormats()[attr(el, "data-tb-binding")] || {})[cell] ||
           deriveFormat(rows, cell);
  }

  function hydrateValues() {
    figureEls("value").forEach(function (el) {
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
      } catch (e) { /* defensive: leave the author's content */ }
    });
  }

  /* Rebuild a hydrated table's body from *rows*. Labels and formats were
   * derived ONCE from the full stamped rows, so a filtered subset can never
   * flip a column's presentation between control states. */
  /* data-tb-totals names a one-row binding the model computed (the table's
   * query with no dimensions): its values fill a <tfoot> row. Nothing is
   * summed here — a ratio's total is the model's ratio of totals. */
  function totalsRow(el, cols, numeric, formats) {
    var name = attr(el, "data-tb-totals");
    if (!name) return null;
    var old = el.querySelector("tfoot");
    if (old) el.removeChild(old);           /* the server-rendered copy */
    var block = readBlock(name);
    if (!block || block.rows.length !== 1) return null;
    var row = block.rows[0];
    if (!el.querySelector("tbody")) el.appendChild(document.createElement("tbody"));
    var tfoot = document.createElement("tfoot");
    var tr = document.createElement("tr");
    tr.className = "tb-total";
    cols.forEach(function (col, i) {
      var td = document.createElement("td");
      if (block.cols.indexOf(col) !== -1) {
        td.className = "tb-num";
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

  function renderBody(entry, rows) {
    var el = entry.el;
    /* A grand total under a filtered view would not add up to the rows
     * shown, so the totals row steps aside while a filter or search is on. */
    if (entry.tfoot) entry.tfoot.hidden = rows.length !== entry.rowCount;
    var tbody = el.querySelector("tbody");
    if (!tbody) {
      tbody = document.createElement("tbody");
      el.appendChild(tbody);
    }
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    if (!rows.length) {
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
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      entry.cols.forEach(function (col) {
        var td = document.createElement("td");
        var raw = r[col], text = (raw === undefined) ? "" : raw;
        if (entry.numeric[col]) {
          td.className = "tb-num";
          var n = toNum(raw);
          if (n !== null && entry.formats[col]) {
            var formatted = applyNamedFormat(n, entry.formats[col]);
            if (formatted !== null) text = formatted;
          }
        }
        td.textContent = text;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
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
    figureEls("table").forEach(function (el) {
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
          numeric[col] = isNumericColumn(rows, col);
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
                      rowCount: rows.length };
        entry.tfoot = totalsRow(el, cols, numeric, formats);
        _tables.push(entry);
        renderBody(entry, filteredRows(binding));
      } catch (e) { /* defensive */ }
    });
  }

  function cssPalette() {
    var out = [];
    if (typeof getComputedStyle === "undefined") return out;
    var cs = getComputedStyle(document.documentElement);
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

  /* Derive ECharts text/line colours from the page's ink tokens, so axis
   * labels, legends and grid lines follow the theme instead of ECharts'
   * near-black default — which is invisible on any dark ground. Only fills a
   * colour the option has not already set, so an author's configureChart patch
   * (applied after this) still wins. A no-op without getComputedStyle (node). */
  function applyThemeColors(option) {
    if (typeof getComputedStyle === "undefined") return option;
    var cs = getComputedStyle(document.documentElement);
    var ink = cssVar(cs, "--tb-ink");
    var muted = cssVar(cs, "--tb-muted");
    var rule = cssVar(cs, "--tb-rule");
    if (!ink && !muted && !rule) return option;
    if (ink) {
      option.textStyle = option.textStyle || {};
      if (option.textStyle.color == null) option.textStyle.color = ink;
    }
    function styleAxis(ax) {
      if (!ax || typeof ax !== "object") return;
      if (ax.length !== undefined) {
        for (var i = 0; i < ax.length; i++) styleAxis(ax[i]);
        return;
      }
      if (muted) {
        ax.axisLabel = ax.axisLabel || {};
        if (ax.axisLabel.color == null) ax.axisLabel.color = muted;
      }
      if (rule) {
        ax.axisLine = ax.axisLine || {};
        ax.axisLine.lineStyle = ax.axisLine.lineStyle || {};
        if (ax.axisLine.lineStyle.color == null) ax.axisLine.lineStyle.color = rule;
        ax.splitLine = ax.splitLine || {};
        ax.splitLine.lineStyle = ax.splitLine.lineStyle || {};
        if (ax.splitLine.lineStyle.color == null) ax.splitLine.lineStyle.color = rule;
      }
    }
    styleAxis(option.xAxis);
    styleAxis(option.yAxis);
    if (option.tooltip) {
      var bg = cssVar(cs, "--tb-bg");
      if (bg && option.tooltip.backgroundColor == null) option.tooltip.backgroundColor = bg;
      if (rule && option.tooltip.borderColor == null) option.tooltip.borderColor = rule;
      if (ink) {
        option.tooltip.textStyle = option.tooltip.textStyle || {};
        if (option.tooltip.textStyle.color == null) option.tooltip.textStyle.color = ink;
      }
    }
    if (option.legend && ink) {
      option.legend.textStyle = option.legend.textStyle || {};
      if (option.legend.textStyle.color == null) option.legend.textStyle.color = ink;
    }
    return option;
  }

  /* House style for a built option: thin rounded bars, 2px lines, a donut
   * for pie, recessive axes, compact value-axis ticks, readable category
   * labels, and a quiet tooltip. Display only — it never touches series
   * data — and it runs before the theme colours and the author's
   * configureChart patch, so either can still override it. */
  function polishOption(option, plan, width) {
    var kind = String(plan.type).toLowerCase();
    option.grid = option.grid || {
      left: 8, right: 24, bottom: 8, top: option.legend ? 40 : 16,
      containLabel: true
    };
    if (option.legend) {
      option.legend.top = option.legend.top == null ? 0 : option.legend.top;
      option.legend.icon = option.legend.icon || "roundRect";
      option.legend.itemWidth = option.legend.itemWidth || 10;
      option.legend.itemHeight = option.legend.itemHeight || 10;
    }
    option.tooltip = option.tooltip || {};
    option.tooltip.borderWidth = 1;
    option.tooltip.extraCssText =
      "box-shadow:0 4px 16px rgba(16,24,40,.12);border-radius:8px;";
    if (option.tooltip.trigger === "axis") {
      option.tooltip.axisPointer = { type: kind === "line" || kind === "area"
        ? "line" : "shadow" };
    }
    function valueAxis(ax) {
      if (!ax) return;
      ax.axisLine = ax.axisLine || { show: false };
      ax.axisTick = ax.axisTick || { show: false };
      ax.axisLabel = ax.axisLabel || {};
      if (!ax.axisLabel.formatter) {
        /* Ticks only: the plotted values and the tooltip keep full precision. */
        ax.axisLabel.formatter = function (v) {
          var f = applyNamedFormat(Number(v), "compact");
          return f === null ? v : f;
        };
      }
    }
    function categoryAxis(ax, isXAxis) {
      if (!ax) return;
      var n = (ax.data || []).length;
      ax.axisTick = ax.axisTick || { show: false };
      ax.axisLabel = ax.axisLabel || {};
      if (n && n <= 12 && ax.axisLabel.interval == null) {
        ax.axisLabel.interval = 0;          /* every category gets its name */
        /* rotate when names would collide: many categories, or little room */
        if (isXAxis && (n > 6 || (width && width / n < 80))) ax.axisLabel.rotate = 30;
      }
    }
    var horizontal = kind === "barh";
    [[option.xAxis, true], [option.yAxis, false]].forEach(function (pair) {
      var ax = pair[0];
      if (!ax) return;
      if (ax.type === "category") categoryAxis(ax, pair[1]);
      else if (ax.type === "value" && kind !== "scatter") valueAxis(ax);
    });
    (option.series || []).forEach(function (s) {
      if (s.type === "bar") {
        s.barMaxWidth = s.barMaxWidth || 44;
        s.itemStyle = s.itemStyle || {};
        if (s.itemStyle.borderRadius == null) {
          s.itemStyle.borderRadius = horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0];
        }
      } else if (s.type === "line") {
        s.symbol = s.symbol || "circle";
        s.symbolSize = s.symbolSize || 7;
        s.lineStyle = s.lineStyle || { width: 2 };
        if (s.areaStyle && s.areaStyle.opacity == null) s.areaStyle.opacity = 0.12;
      } else if (s.type === "pie") {
        s.radius = ["42%", "64%"];
        s.itemStyle = s.itemStyle || { borderColor: "#fff", borderWidth: 2 };
        s.avoidLabelOverlap = true;
        /* Wrap long category names instead of truncating them. */
        if (s.label && s.label.overflow == null) {
          s.label.overflow = "break";
          s.label.width = 110;
        }
        /* In a narrow container, outside labels run off the edge: name the
         * slices in a legend below instead (hover still shows each value). */
        if (width && width < 560) {
          s.label = { show: false };
          s.labelLine = { show: false };
          s.center = ["50%", "44%"];
          option.legend = option.legend || {
            show: true, bottom: 0, icon: "circle", itemWidth: 10, itemHeight: 10
          };
        }
      }
    });
    return option;
  }

  /* The built option for one chart, patch applied — shared by the first
   * hydration and every control-driven re-render. */
  function buildOption(el, plan, rows) {
    var option = applyThemeColors(
      polishOption(optionFor(plan, rows), plan, el && el.clientWidth));

    var patch = el.id ? _patches[el.id] : null;
    if (patch) {
      var built = option.series || [];
      var merged = deepMerge(option, patch);
      /* Config can restyle, never re-source: dataset-style channels are
       * dropped and every series keeps the data built from the stamped
       * bytes. Extra patch series (which could only carry author data)
       * are not drawn. */
      delete merged.dataset;
      var series = [], i, overlay, s;
      var patchSeries = merged.series;
      for (i = 0; i < built.length; i++) {
        overlay = (patchSeries && isPlainObject(patchSeries[i]))
          ? patchSeries[i] : null;
        s = (overlay && overlay !== built[i]) ? deepMerge(built[i], overlay) : built[i];
        s.data = built[i].data;
        series.push(s);
      }
      merged.series = series;
      option = merged;
    }
    return option;
  }

  function hydrateCharts() {
    if (!root.echarts) return; /* no charting lib on this page — skip all */
    var palette = null;
    figureEls("chart").forEach(function (el) {
      try {
        var binding = attr(el, "data-tb-binding");
        var block = readBlock(binding);
        if (!block || !block.rows.length) return;
        var x = attr(el, "data-tb-x");
        var y = attr(el, "data-tb-y");
        if (!x || !y) return;
        var own = attr(el, "data-tb-palette");
        if (palette === null) palette = cssPalette();
        var plan = {
          type: attr(el, "data-tb-type") || "bar",
          x: x,
          y: splitList(y),
          color: attr(el, "data-tb-color"),
          valueFormat: attr(el, "data-tb-value-format"),
          palette: own ? splitList(own) : palette
        };
        /* Remove the server-rendered static SVG fallback (no-JS picture of the
         * chart) before drawing — echarts.init appends its root without
         * clearing, so a surviving <svg> would stack beside the live chart. */
        var fb = el.querySelector(".tb-chart-fallback");
        if (fb) el.removeChild(fb);
        var chart = root.echarts.init(el);
        chart.setOption(buildOption(el, plan, filteredRows(binding)));
        _charts.push({ el: el, binding: binding, plan: plan, chart: chart });
        root.addEventListener("resize", function () { chart.resize(); });
      } catch (e) { /* defensive */ }
    });
  }

  /* ── Receipt badges — provenance from the manifest-derived config only.
   *    Author CSS can restyle a badge; the runtime never lets a grey one
   *    become green, because the class is chosen from provenance here. ──── */

  /* The badge word is what a non-technical reviewer reads, so it must state
   * the actual guarantee, not imply "correct/audited". A green figure's number
   * is query-REPRODUCIBLE (a re-runnable query backs it, matching the verify
   * verdict `reproduces`) — never "verified". Grey is computed in python (not
   * query-reproducible); amber is an honest unbacked figure. The provenance
   * KEY and the CSS class stay as-is; only the reader-facing text changes. */
  var _BADGES = {
    verified:   { cls: "tb-badge--verified",   text: "reproducible" },
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
        badge.textContent = spec.text;
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

  function collectFilters() {
    var cfg = selectionConfig() || {};
    var filters = {}, k, base = cfg.filters || {};
    for (k in base) if (base.hasOwnProperty(k)) filters[k] = base[k];
    controlEls("data-tb-filter").forEach(function (el) {
      var column = attr(el, "data-tb-column");
      if (!column) return;
      if (!el.value || el.value === "All") delete filters[column];
      else filters[column] = el.value;
    });
    return filters;
  }

  function failClosed(filters) {
    /* Do not subset-and-sum. The authored view stays. A sealed grain may
     * recompute simple aggregations and ratio; anything else needs the model. */
    if (!tryOffline(filters)) {
      controlEls("data-tb-filter").forEach(function (el) {
        if (el._tbValue !== undefined) el.value = el._tbValue;
        el.title = "Further slices need the model";
      });
    }
  }

  function tryOffline(filters) {
    var el = document.getElementById("tracebi-grain");
    if (!el || typeof tracebiSelectionEval !== "function") return false;
    var grain;
    try { grain = JSON.parse(el.textContent); } catch (e) { return false; }
    if (!grain || !grain.bindings || !grain.facts) return false;
    var any = false, refused = false, name, plan, fact, result, seen = {};
    for (name in grain.bindings) {
      if (!grain.bindings.hasOwnProperty(name)) continue;
      plan = grain.bindings[name];
      fact = grain.facts[plan.fact];
      if (!fact) { refused = true; continue; }
      result = tracebiSelectionEval(fact.rows || [], plan, filters || {});
      if (result.refused) { refused = true; continue; }
      any = true;
      _liveRows[name] = result.rows;
      seen[name] = true;
      paintValues(name, result.rows);
    }
    for (name in seen) if (seen.hasOwnProperty(name)) refreshBinding(name);
    if (any) {
      paintSelectionReceipt({
        filters: filters || {},
        authored: false,
        offline: true
      });
    }
    if (refused) {
      controlEls("data-tb-filter").forEach(function (ctrl) {
        ctrl.title = "Further slices need the model";
      });
    }
    return any;
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
      } catch (e) { /* defensive */ }
    });
  }

  function applySelection(payload) {
    if (!payload) return;
    _lastSelection = payload;
    var figs = payload.figures || [], i, fig, el, text, target, seen = {};
    for (i = 0; i < figs.length; i++) {
      fig = figs[i];
      if (fig.binding && fig.rows) {
        _liveRows[fig.binding] = fig.rows;
        seen[fig.binding] = true;
      }
      if (fig.kind !== "value" || !fig.id) continue;
      el = document.getElementById(fig.id);
      if (!el) continue;
      text = fig.formatted;
      if (text === null || text === undefined || text === "") {
        text = (fig.value === null || fig.value === undefined) ? "" : String(fig.value);
      }
      target = el.querySelector(".tb-kpi-value") || el;
      target.textContent = text;
    }
    for (i in seen) if (seen.hasOwnProperty(i)) refreshBinding(i);
    applyControlDomains(payload.controls);
    paintSelectionReceipt(payload);
    controlEls("data-tb-filter").forEach(function (ctrl) {
      ctrl._tbValue = ctrl.value;
    });
    try {
      if (root.parent && root.parent !== root) {
        root.parent.postMessage({ type: "tracebi-selection", payload: payload }, "*");
      }
    } catch (e) { /* defensive */ }
  }

  function applyControlDomains(controls) {
    (controls || []).forEach(function (c) {
      var el = null;
      controlEls("data-tb-filter").forEach(function (candidate) {
        if (attr(candidate, "data-tb-binding") === c.binding &&
            attr(candidate, "data-tb-column") === c.column) el = candidate;
      });
      if (!el) return;
      var current = el.value;
      while (el.firstChild) el.removeChild(el.firstChild);
      appendOption(el, "All", false);
      (c.included || []).forEach(function (v) { appendOption(el, v, false); });
      (c.excluded || []).forEach(function (v) { appendOption(el, v, true); });
      el.value = current || "All";
    });
  }

  function appendOption(el, value, disabled) {
    var o = document.createElement("option");
    o.value = String(value);
    o.textContent = String(value);
    if (disabled) {
      o.disabled = true;
      try { o.setAttribute("disabled", "disabled"); } catch (e) { /* defensive */ }
    }
    el.appendChild(o);
  }

  function postSelection(filters) {
    var cfg = selectionConfig();
    if (!cfg || !cfg.report) { failClosed(filters); return; }
    var url = "/api/reports/" + encodeURIComponent(cfg.report) + "/selection";
    try {
      /* A file opened from disk has no server to ask: take the offline path
       * directly rather than logging a failed request in the console. */
      if (typeof fetch !== "function" ||
          (root.location && root.location.protocol === "file:")) {
        failClosed(filters); return;
      }
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filters: filters || {} })
      }).then(function (res) {
        if (!res || !res.ok) throw new Error("selection");
        return res.json();
      }).then(function (payload) {
        applySelection(payload);
      }).catch(function () { failClosed(filters); });
    } catch (e) { failClosed(filters); }
  }

  function setSelection(filters) {
    if (!selectionConfig()) return;
    var wanted = filters || {};
    controlEls("data-tb-filter").forEach(function (el) {
      var column = attr(el, "data-tb-column");
      if (!column) return;
      if (wanted.hasOwnProperty(column) && wanted[column] !== null &&
          wanted[column] !== undefined) {
        el.value = String(wanted[column]);
      } else {
        el.value = "All";
      }
    });
    postSelection(wanted);
  }

  function selectionSlug(filters) {
    var parts = [], k, s;
    for (k in filters) if (filters.hasOwnProperty(k)) parts.push(k + "=" + filters[k]);
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
    header = "# selection: " + (selectionSlug(filters).replace(/_/g, ", ") || "authored");
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
    if (payload.offline) text += " · offline";
    else text += payload.authored ? " · authored" : " · live";
    line.textContent = text;
  }

  function populateFilterOptions(el, column, block) {
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
  }

  function hydrateSelectionFilters() {
    var cfg = selectionConfig();
    controlEls("data-tb-filter").forEach(function (el) {
      try {
        var binding = attr(el, "data-tb-binding");
        var column = attr(el, "data-tb-column");
        var block = readBlock(binding);
        if (!block) { noteUnknown(el, "unknown binding: " + binding); return; }
        if (!column || block.cols.indexOf(column) === -1) {
          noteUnknown(el, "unknown column: " + column);
          return;
        }
        populateFilterOptions(el, column, block);
        var authored = cfg && cfg.filters && cfg.filters.hasOwnProperty(column)
          ? String(cfg.filters[column]) : "All";
        el.value = authored;
        el._tbValue = el.value;
        el.addEventListener("change", function () {
          postSelection(collectFilters());
        });
      } catch (e) { /* defensive */ }
    });
    /* Learn excluded values when the model answers. On failure the authored
     * view stays and the title says further slices need the model. */
    postSelection(collectFilters());
  }

  function hydrateControls() {
    if (selectionConfig()) {
      try { hydrateSelectionFilters(); } catch (e) { /* defensive */ }
    } else controlEls("data-tb-filter").forEach(function (el) {
      try {
        var binding = attr(el, "data-tb-binding");
        var column = attr(el, "data-tb-column");
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
    });
    controlEls("data-tb-search").forEach(function (el) {
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

  /* ── Download — the binding's embedded canonical CSV, byte-verbatim ──── */

  function hydrateDownloads() {
    controlEls("data-tb-download").forEach(function (el) {
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
            var blob = new Blob([block.csv], { type: "text/csv" });
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
    _tables.forEach(function (entry) {
      try {
        var el = entry.el;
        var want = attr(el, "data-tb-rows");
        if (want === "all") return; /* the author opted out */
        var n = want === null ? 10 : parseInt(want, 10);
        if (!isFinite(n) || n < 1) n = 10;
        if (entry.rowCount <= n) return;
        var parent = el.parentNode;
        if (!parent) return;
        if ((" " + parent.className + " ").indexOf(" tb-scroll ") !== -1) return;
        var wrap = document.createElement("div");
        wrap.className = "tb-scroll";
        /* ~n rows: a row is about 2.6em (line + cell padding), plus the
         * sticky header — em-based so it tracks the report's type size. */
        wrap.style.maxHeight = ((n + 1) * 2.6) + "em";
        parent.insertBefore(wrap, el);
        wrap.appendChild(el);
      } catch (e) { /* defensive */ }
    });
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
        var select = function (idx) {
          for (var j = 0; j < sections.length; j++) {
            if (j === idx) {
              addClass(sections[j], "tb-tab-active");
              addClass(bar.children[j], "tb-tab-active");
            } else {
              removeClass(sections[j], "tb-tab-active");
              removeClass(bar.children[j], "tb-tab-active");
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

  /* ── The receipt drawer — provenance DISPLAY from #tracebi-receipt ─────
   * Renders ONLY what the build recorded: never re-colored, never
   * re-judged. Locked language: "the sink satisfied its contract" — never
   * "the transform was verified". */

  function receiptLine(parent, text, cls) {
    var div = document.createElement("div");
    div.className = cls || "tb-receipt-line";
    div.textContent = text;
    parent.appendChild(div);
    return div;
  }

  /* The page element this figure record names, if the build placed one. */
  function receiptPageEl(fig) {
    if (!fig || !fig.id || typeof document === "undefined") return null;
    var el = document.getElementById(fig.id);
    return (el && el.getAttribute) ? el : null;
  }

  /* Rows on the page, or the stamped block when the figure has no table. */
  function receiptRowCount(el, binding) {
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
    var block = binding ? readBlock(binding) : null;
    if (block && block.rows) return block.rows.length;
    return null;
  }

  function receiptQuery(receipt, fig) {
    if (fig.query && typeof fig.query === "object") return fig.query;
    var bindings = receipt && receipt.bindings;
    var rec = (bindings && fig.binding) ? bindings[fig.binding] : null;
    if (!rec || typeof rec !== "object") return null;
    return (rec.query && typeof rec.query === "object") ? rec.query : rec;
  }

  function humanList(items) {
    if (!items || !items.length) return "";
    var out = [], i;
    for (i = 0; i < items.length; i++) out.push(humanise(String(items[i])));
    return out.join(", ");
  }

  function filterPhrase(filters) {
    if (!filters || typeof filters !== "object") return "";
    var parts = [], k, v, op, bits;
    for (k in filters) {
      if (!Object.prototype.hasOwnProperty.call(filters, k)) continue;
      v = filters[k];
      if (v && typeof v === "object") {
        bits = [];
        for (op in v) {
          if (Object.prototype.hasOwnProperty.call(v, op)) {
            bits.push(op + " " + v[op]);
          }
        }
        parts.push(humanise(k) + " " + bits.join(" "));
      } else {
        parts.push(humanise(k) + " is " + v);
      }
    }
    return parts.join(", ");
  }

  function receiptFigureRow(drawer, fig, receipt) {
    if (!fig || !fig.id) return;
    var page = receiptPageEl(fig);
    var kind = fig.kind || (page ? attr(page, "data-tb-figure") : null);
    var binding = fig.binding || (page ? attr(page, "data-tb-binding") : null);
    var cell = fig.cell || (page ? attr(page, "data-tb-cell") : null);
    if (!cell && page && kind === "chart") {
      var y = attr(page, "data-tb-y");
      if (y) cell = splitList(y)[0];
    }

    var row = document.createElement("div");
    row.className = "tb-receipt-row";
    var title = document.createElement("div");
    title.className = "tb-receipt-title";
    var headline;
    if (kind === "value") {
      var labelEl = page ? page.querySelector(".tb-kpi-label") : null;
      var pageLabel = labelEl ? trim(labelEl.textContent || "") : "";
      /* A column uses the same words as the page's headings. A literal
       * figure has no column, so the label already printed on it is the
       * name. */
      var label = cell ? humanise(cell)
        : (pageLabel || (binding ? humanise(binding) : humanise(fig.id)));
      var shownEl = page ? (page.querySelector(".tb-kpi-value") || page) : null;
      var shown = shownEl ? trim(shownEl.textContent || "") : "";
      headline = shown ? (label + " · " + shown) : label;
    } else if (kind === "table" || kind === "chart") {
      headline = (binding ? humanise(binding) : humanise(fig.id)) + " · " + kind;
      var count = receiptRowCount(page, binding);
      if (count !== null) {
        headline += ", " + count + (count === 1 ? " row" : " rows");
      }
    } else {
      headline = binding ? humanise(binding) : humanise(fig.id);
      if (kind) headline += " · " + kind;
    }
    title.textContent = headline;
    if (fig.unverified) {
      /* The recorded status in its existing tone — display, not judgment. */
      var badge = document.createElement("span");
      badge.className = "tb-badge tb-badge--unverified";
      badge.textContent = "unverified";
      title.appendChild(badge);
    }
    row.appendChild(title);

    var query = receiptQuery(receipt, fig);
    var measures = (query && query.measures && query.measures.length)
      ? query.measures : (cell ? [cell] : []);
    var dims = (query && query.dimensions) || [];
    var from = humanList(measures);
    if (dims.length) from += (from ? ", by " : "by ") + humanList(dims);
    var filters = filterPhrase(query && query.filters);
    if (filters) from += (from ? ", " : "") + filters;
    if (from) {
      var quiet = document.createElement("div");
      quiet.className = "tb-receipt-from";
      quiet.textContent = from;
      row.appendChild(quiet);
    }

    var details = document.createElement("details");
    details.className = "tb-receipt-details";
    var summary = document.createElement("summary");
    summary.textContent = "Details";
    details.appendChild(summary);
    var meta = String(fig.id);
    if (kind) meta += " · " + kind;
    if (binding) meta += " · " + binding;
    receiptLine(details, meta, "tb-receipt-meta");
    if (fig.fingerprint) {
      var fp = document.createElement("span");
      fp.className = "tb-receipt-fp";
      fp.textContent = String(fig.fingerprint);
      fp.title = String(fig.fingerprint);
      details.appendChild(fp);
    }
    row.appendChild(details);
    drawer.appendChild(row);
  }

  function hydrateReceipt() {
    var el = document.getElementById("tracebi-receipt");
    if (!el || !document.body) return; /* no receipt block → no drawer */
    var receipt;
    try { receipt = JSON.parse(el.textContent); } catch (e) { return; }
    if (!receipt || typeof receipt !== "object") return;

    var drawer = document.createElement("div");
    drawer.className = "tb-receipt-drawer";
    receiptLine(drawer, receipt.report || "Receipt", "tb-receipt-head");
    if (receipt.rendered_at) {
      receiptLine(drawer, "rendered " + receipt.rendered_at);
    }
    if (receipt.git_sha) receiptLine(drawer, "git " + receipt.git_sha);

    var figures = receipt.figures || [], i;
    for (i = 0; i < figures.length; i++) {
      try { receiptFigureRow(drawer, figures[i], receipt); } catch (e) { /* defensive */ }
    }

    var contracts = receipt.transform_contracts, table, rec, status;
    if (contracts && typeof contracts === "object") {
      for (table in contracts) {
        if (!contracts.hasOwnProperty(table)) continue;
        rec = contracts[table];
        status = (rec && typeof rec === "object") ? rec.status : rec;
        if (status === "satisfied") {
          receiptLine(drawer, table + ": the sink satisfied its contract");
        } else if (status === "stale") {
          receiptLine(drawer, table + ": contract stale — the warehouse "
                      + "has moved since the certificate");
        } else {
          receiptLine(drawer, table + ": no contract");
        }
      }
    }

    var models = receipt.semantic_contract_models;
    if (models && models.length) {
      receiptLine(drawer, "semantic contract: " + models.join(", "));
    }
    if (receipt.methodology === true) {
      receiptLine(drawer, "stated methodology aboard");
    }

    if (selectionConfig()) {
      var status = receiptLine(drawer, "selection: authored", "tb-receipt-line");
      status.id = "tb-selection-status";
      var slice = document.createElement("button");
      slice.type = "button";
      slice.className = "tb-receipt-line";
      slice.textContent = "Download this selection";
      slice.addEventListener("click", downloadSelection);
      drawer.appendChild(slice);
    }

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tb-receipt-btn";
    btn.textContent = "Receipt";
    btn.addEventListener("click", function () {
      if ((" " + drawer.className + " ").indexOf(" tb-receipt-open ") !== -1) {
        removeClass(drawer, "tb-receipt-open");
      } else {
        addClass(drawer, "tb-receipt-open");
      }
    });
    document.body.appendChild(drawer);
    document.body.appendChild(btn);
    if (selectionConfig()) {
      paintSelectionReceipt(_lastSelection || {
        filters: (selectionConfig().filters || {}),
        authored: true
      });
    }
  }

  function hydrate() {
    try { hydrateValues(); } catch (e) {}
    try { hydrateTables(); } catch (e) {}
    try { hydrateCharts(); } catch (e) {}
    /* Badges after values (value writes replace textContent and must not
     * eat them) and BEFORE the scroll wrap, so a table's badge anchors
     * outside the scrolling region. */
    try { hydrateBadges(); } catch (e) {}
    try { hydrateScroll(); } catch (e) {}
    /* Tabs after charts: sections hide only once the bar exists, so every
     * chart measured its size while still visible. */
    try { hydrateTabs(); } catch (e) {}
    try { hydrateControls(); } catch (e) {}
    try { hydrateDownloads(); } catch (e) {}
    try { hydrateReceipt(); } catch (e) {}
  }

  /* ── Parquet data blocks ───────────────────────────────────────────────
   * Large-detail artifacts embed each binding as Parquet, decoded by the
   * inlined worker engine (parquet-wasm + Arquero) before hydration and cached
   * in _blocks in the SAME {cols, rows} shape readBlock() produces — so the
   * whole sync runtime below is untouched. A CSV-only artifact carries no
   * Parquet block, takes the early return, and behaves exactly as before. */
  function inlinedText(id) {
    var el = document.getElementById(id);
    return el ? el.textContent : null;
  }
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
  function gunzip(bytes) {
    var stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
    return new Response(stream).arrayBuffer().then(function (buf) { return new Uint8Array(buf); });
  }
  /* Decode every Parquet block into _blocks, then call done(). Any failure
   * (no engine inlined, unsupported browser, a bad block) degrades to done()
   * so hydration still runs — the figure falls back to its server-rendered
   * value / "no data" rather than hanging. */
  function ensureData(done) {
    var blocks;
    try { blocks = parquetDataBlocks(); } catch (e) { blocks = []; }
    if (!blocks.length) { done(); return; }
    var wsrc = inlinedText("tracebi-engine-worker");
    var wasmB64 = inlinedText("tracebi-engine-wasm");
    if (!wsrc || !wasmB64 || typeof Worker === "undefined" ||
        typeof DecompressionStream === "undefined") { done(); return; }
    gunzip(b64ToBytes(wasmB64)).then(function (wasm) {
      var worker = new Worker(URL.createObjectURL(new Blob([wsrc], { type: "text/javascript" })));
      var remaining = blocks.length, idx = 0, settled = false, timer = null;
      /* done() must run EXACTLY once, and must run even if the worker dies,
       * throws, or never answers — otherwise hydration never happens and the
       * whole page stays blank. Guarded three ways: onerror, a watchdog, and
       * the settled latch. */
      var finish = function () {
        if (settled) return;
        settled = true;
        if (timer) clearTimeout(timer);
        try { worker.terminate(); } catch (e) {}
        done();
      };
      timer = setTimeout(finish, 30000);
      worker.onerror = finish;
      worker.onmessageerror = finish;
      function loadNext() {
        if (idx >= blocks.length) return;
        var b = blocks[idx++], bytes;
        try { bytes = b64ToBytes(b.b64); } catch (e) { step(); return; }
        worker.postMessage({ type: "load", name: b.name, parquet: bytes.buffer }, [bytes.buffer]);
      }
      function step() { if (--remaining <= 0) finish(); else loadNext(); }
      worker.onmessage = function (e) {
        var m = e.data || {};
        try {
          if (m.type === "inited") { loadNext(); }
          else if (m.type === "loaded") { worker.postMessage({ type: "rows", name: m.name, id: 1 }); }
          else if (m.type === "rows") {
            var rows = m.rows || [];
            _blocks[m.name] = {
              cols: m.cols || (rows[0] ? Object.keys(rows[0]) : []),
              rows: rows,
              /* readBlock() always sets .csv (the verbatim download reads it);
               * without it the download control writes the text "undefined". */
              csv: m.csv || ""
            };
            step();
          } else if (m.type === "error") { step(); }
        } catch (err) { finish(); }
      };
      var wbuf = wasm.buffer;
      worker.postMessage({ type: "init", wasm: wbuf }, [wbuf]);
    })["catch"](function () { done(); });
  }

  /* DOM-ready, then requestAnimationFrame: the author's inline script.js has
   * already run by DOMContentLoaded, so its configureChart patches are
   * registered before any chart is drawn. */
  if (typeof document !== "undefined") {
    var schedule = function () {
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(hydrate);
      else hydrate();
    };
    var boot = function () {
      ensureData(function () { _dataReady = true; runReady(); schedule(); });
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot);
    } else {
      boot();
    }
  }

  root.tracebi = {
    data: data,
    ready: ready,
    fmt: fmt,
    configureChart: configureChart,
    setSelection: setSelection
  };
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
