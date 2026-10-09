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
          if (entry.d3) renderD3Chart(entry, rows, true);
          else entry.chart.setOption(buildOption(entry.el, entry.plan, rows), true);
        } catch (e) { /* defensive */ }
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
        if (!c.d3) c.chart.resize();
        else if (c.surface.clientWidth !== c.width) {
          renderD3Chart(c, filteredRows(c.binding), false);
        }
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
        renderBody(entry, filteredRows(entry.binding));
      });
    });
  }

  /* data-tb-bars: a bar behind each cell of the named numeric columns,
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
    addClass(td, "tb-bar-cell");
    td.insertBefore(bar, td.firstChild);
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
      if (entry.numeric[col]) {
        td.className = "tb-num";
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
    var apply = function (on) {
      on = !!on;
      if (_printing === on) return;
      _printing = on;
      for (var i = 0; i < _tables.length; i++) {
        try { renderBody(_tables[i], _tables[i].modelRows); } catch (e) {}
      }
      for (var j = 0; j < _charts.length; j++) {
        if (!_charts[j].d3) continue;
        try {
          if (_charts[j].svg) _charts[j].svg.interrupt().style("opacity", 1);
          renderD3Chart(_charts[j], filteredRows(_charts[j].binding), false);
        } catch (e) {}
      }
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
                      rowCount: rows.length, sort: null,
                      bars: barScales(el, rows, cols, numeric) };
        entry.tfoot = totalsRow(el, cols, numeric, formats);
        hydrateSort(entry);
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

  /* ── The D3 chart engine ───────────────────────────────────────────────
   * Draws every declared chart type (bar, barh, line, area, pie, scatter)
   * with the inlined d3, from the same plan and the same filtered stamped
   * rows the ECharts path reads. SVG: every mark is an element, so it prints
   * as vectors, takes the page's tokens and carries its own focus and hover.
   *
   * What it never does: compute a number. Every bar, point and slice is one
   * row's own value; there are no totals, shares or averages drawn. Colours
   * are assigned from the UNFILTERED rows, so a filter that removes a series
   * never repaints the ones that stay. A click on a mark sets the page's own
   * filter control for that column (when the page has one), so filtering
   * goes through the one view layer, never a side channel.
   * ──────────────────────────────────────────────────────────────────── */

  var _MOTION_MS = 450;
  var _introPending = 0;

  function motionOk() {
    if (_printing) return false;
    try {
      if (root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        return false;
      }
    } catch (e) {}
    return true;
  }

  function chartKind(plan) {
    var k = String(plan.type || "bar").toLowerCase();
    return (k === "barh" || k === "line" || k === "area" || k === "pie" ||
            k === "scatter") ? k : "bar";
  }

  /* The format a value is shown in: the author's value format, then the
   * model's declared format for the column, then the shape default — the
   * table's precedence, so a tooltip agrees with the table beside it. */
  function chartFormatter(plan, rows, col) {
    var mode = plan.valueFormat || declaredFormats()[col] || deriveFormat(rows, col);
    var unit = plan.unit || "";
    return function (v) {
      var n = toNum(v);
      if (n === null) return v === null || v === undefined ? "" : String(v);
      var out = mode ? applyNamedFormat(n, mode) : null;
      return (out === null ? String(v) : out) + unit;
    };
  }

  /* Axis ticks are short: compact digits, keeping a currency sign or a
   * percent, so "$20M" rather than "$20,000,000". Tooltips and marks keep
   * the full format. data-tb-unit is a suffix only ("%" on a rate stored
   * as 6.81): it never rescales the number. */
  function tickFormatter(plan) {
    var mode = plan.valueFormat, unit = plan.unit || "";
    return function (v) {
      var n = Number(v), out;
      if (mode === "percent") out = applyNamedFormat(n, "percent");
      else if (mode === "currency" || mode === "currency0") {
        out = (n < 0 ? "-$" : "$") + applyNamedFormat(Math.abs(n), "compact");
      } else out = applyNamedFormat(n, "compact");
      return (out === null ? String(v) : out) + unit;
    };
  }

  /* Series keys in first-seen order over ALL stamped rows: the colour map.
   * A key keeps its slot whatever the filters leave on screen. */
  function seriesKeys(plan, rows, kind) {
    var keys = [];
    if (kind === "pie") {
      rows.forEach(function (r) {
        var c = String(r[plan.x]);
        if (keys.indexOf(c) === -1) keys.push(c);
      });
      return keys;
    }
    if (plan.color) {
      rows.forEach(function (r) {
        var g = groupOf(r[plan.color]);
        if (keys.indexOf(g) === -1) keys.push(g);
      });
      return keys;
    }
    return plan.y.slice();
  }

  function colourOf(entry, key) {
    var pal = entry.plan.palette && entry.plan.palette.length
      ? entry.plan.palette : ["#2a78d6"];
    var i = entry.keys.indexOf(key);
    return pal[(i < 0 ? 0 : i) % pal.length];
  }

  function seriesName(plan, key) {
    return plan.color ? key : humanise(key);
  }

  /* rows → [{key, name, points: [{cat, x, y, row}]}] for the visible keys. */
  function chartSeries(entry, rows, kind) {
    var plan = entry.plan, out = [], byKey = {};
    var valueCol = function (key) { return plan.color ? plan.y[0] : key; };
    entry.keys.forEach(function (key) {
      if (entry.hidden[key]) return;
      var s = { key: key, name: seriesName(plan, key), col: valueCol(key), points: [] };
      byKey[key] = s;
      out.push(s);
    });
    rows.forEach(function (r) {
      var keys = plan.color ? [groupOf(r[plan.color])] : plan.y;
      keys.forEach(function (key) {
        var s = byKey[key];
        if (!s) return;
        var y = toNum(r[s.col]);
        s.points.push({
          key: key, cat: String(r[plan.x]), y: y, row: r,
          x: kind === "scatter" ? toNum(r[plan.x]) : null
        });
      });
    });
    /* A series the filters emptied draws nothing (the legend still names it). */
    return out.filter(function (s) { return s.points.length > 0; });
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

  /* Shorten an SVG text node until it fits *room*, ending in an ellipsis. */
  function fitText(node, room) {
    var full = node.textContent, n = full.length;
    try {
      while (n > 1 && node.getComputedTextLength() > room) {
        node.textContent = full.slice(0, --n) + "…";
      }
    } catch (e) {}
  }

  function textWidth(svg, text, size) {
    var t = svg.append("text").attr("font-size", size).text(text);
    var w = 0;
    try { w = t.node().getComputedTextLength(); } catch (e) {}
    t.remove();
    return w;
  }

  function tipShow(entry, x, y, title, rows) {
    var tip = entry.tip, i, row, line;
    while (tip.firstChild) tip.removeChild(tip.firstChild);
    var head = document.createElement("div");
    head.className = "tb-chart-tip-title";
    head.textContent = title;
    tip.appendChild(head);
    for (i = 0; i < rows.length; i++) {
      row = document.createElement("div");
      row.className = "tb-chart-tip-row";
      line = document.createElement("span");
      line.className = "tb-chart-tip-key";
      line.style.background = rows[i].colour;
      var val = document.createElement("strong");
      val.textContent = rows[i].value;
      var name = document.createElement("span");
      name.textContent = rows[i].name;
      row.appendChild(line);
      row.appendChild(val);
      row.appendChild(name);
      tip.appendChild(row);
    }
    tip.hidden = false;
    var w = entry.surface.clientWidth, tw = tip.offsetWidth, th = tip.offsetHeight;
    var left = x + 14 + tw > w ? Math.max(0, x - 14 - tw) : x + 14;
    var top = Math.max(0, y - th - 10);
    tip.style.left = left + "px";
    tip.style.top = top + "px";
    if (entry.live && entry.keyboard) {
      entry.live.textContent = title + ": " + rows.map(function (r) {
        return r.name + " " + r.value;
      }).join(", ");
    }
  }

  /* Keyboard readouts are placed in svg coordinates; the legend sits above. */
  function tipHide(entry) {
    if (entry.tip) entry.tip.hidden = true;
    if (entry.svg) {
      entry.svg.selectAll(".tb-hover").attr("opacity", 0);
      entry.svg.selectAll(".tb-mark").classed("tb-dim", false);
    }
  }

  function legendFor(entry, kind) {
    var host = entry.legend;
    while (host.firstChild) host.removeChild(host.firstChild);
    var zoomed = !!(entry.zoom || entry.zoomX);
    var show = kind === "pie" || entry.keys.length > 1 || zoomed;
    host.hidden = !show;
    if (zoomed) {
      var reset = document.createElement("button");
      reset.type = "button";
      reset.className = "tb-legend-item tb-legend-reset";
      reset.textContent = "Reset zoom";
      reset.addEventListener("click", function () {
        entry.zoom = null;
        entry.zoomX = null;
        renderD3Chart(entry, filteredRows(entry.binding), true);
      });
      host.appendChild(reset);
    }
    if (!show || (kind !== "pie" && entry.keys.length < 2)) return;
    entry.keys.forEach(function (key) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "tb-legend-item";
      btn.setAttribute("aria-pressed", entry.hidden[key] ? "false" : "true");
      var sw = document.createElement("span");
      sw.className = "tb-legend-swatch tb-legend-swatch--" +
        (kind === "line" ? "line" : kind === "scatter" ? "dot" : "box");
      sw.style.background = colourOf(entry, key);
      var label = document.createElement("span");
      label.textContent = kind === "pie" ? key : seriesName(entry.plan, key);
      btn.appendChild(sw);
      btn.appendChild(label);
      btn.addEventListener("click", function () {
        var visible = entry.keys.filter(function (k) { return !entry.hidden[k]; });
        if (!entry.hidden[key] && visible.length === 1) return; /* keep one */
        entry.hidden[key] = !entry.hidden[key];
        renderD3Chart(entry, filteredRows(entry.binding), true);
      });
      host.appendChild(btn);
    });
  }

  function hoverable(entry, sel, fn) {
    sel.on("pointermove", function (event, d) {
      var p = root.d3.pointer(event, entry.surface);
      entry.keyboard = false;
      fn(d, p[0], p[1]);
    }).on("pointerleave", function () { tipHide(entry); });
  }

  /* Arrow keys walk the marks, Enter filters by the focused one, Escape
   * hides the readout. The same readout a pointer gets, announced. */
  function keyboardWalk(entry, count, show, choose) {
    var svgNode = entry.svg.node();
    entry.focusIndex = Math.min(entry.focusIndex || 0, Math.max(0, count - 1));
    svgNode.onkeydown = function (e) {
      var k = e.key;
      if (!count) return;
      if (k === "ArrowRight" || k === "ArrowDown") entry.focusIndex = (entry.focusIndex + 1) % count;
      else if (k === "ArrowLeft" || k === "ArrowUp") entry.focusIndex = (entry.focusIndex - 1 + count) % count;
      else if (k === "Home") entry.focusIndex = 0;
      else if (k === "End") entry.focusIndex = count - 1;
      else if (k === "Enter" || k === " ") { if (choose) choose(entry.focusIndex); }
      else if (k === "Escape") { tipHide(entry); return; }
      else return;
      e.preventDefault();
      entry.keyboard = true;
      show(entry.focusIndex);
    };
    svgNode.onfocus = function () { entry.keyboard = true; show(entry.focusIndex); };
    svgNode.onblur = function () { tipHide(entry); };
  }

  function transition(entry, sel) {
    return entry.animate ? sel.transition().duration(_MOTION_MS).ease(root.d3.easeCubicOut) : sel;
  }

  /* Where *host* (the chart's svg, or one facet panel) sits in the surface:
   * keyboard readouts are placed in its coordinates. */
  function hostOffset(entry, host) {
    var a = host.node().getBoundingClientRect(), b = entry.surface.getBoundingClientRect();
    return { x: a.left - b.left, y: a.top - b.top };
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

  /* Stacked series: each point gets the band it occupies, y0 → y1, positives
   * up from zero and negatives down. Drawing only: the stack's height is the
   * rows' own values laid end to end, and no total is written anywhere. */
  function stackPoints(series, cats) {
    var up = {}, down = {};
    cats.forEach(function (c) { up[c] = 0; down[c] = 0; });
    series.forEach(function (s) {
      s.points.forEach(function (p) {
        if (p.y === null || !(p.cat in up)) { p.y0 = p.y1 = null; return; }
        if (p.y >= 0) { p.y0 = up[p.cat]; p.y1 = up[p.cat] += p.y; }
        else { p.y0 = down[p.cat]; p.y1 = down[p.cat] += p.y; }
      });
    });
  }

  function valueExtent(series, stacked) {
    var lo = 0, hi = 0;
    series.forEach(function (s) {
      s.points.forEach(function (p) {
        var vs = stacked ? [p.y0, p.y1] : [p.y];
        vs.forEach(function (v) {
          if (v === null || v === undefined) return;
          if (v < lo) lo = v;
          if (v > hi) hi = v;
        });
      });
    });
    if (lo === hi) hi = lo + 1;
    return [lo, hi];
  }

  function zoomable(kind, n) {
    return (kind === "line" || kind === "area") && n >= 8;
  }

  /* One categorical panel (bar, barh, line, area) into *host*. Returns the
   * readout the caller's keyboard walk drives. opt: {domain, title, zoom}. */
  function renderCategorical(entry, host, rows, kind, W, H, t, opt) {
    var d3 = root.d3, plan = entry.plan, svg = host;
    opt = opt || {};
    var series = chartSeries(entry, rows, kind);
    var allCats = opt.cats || categories(plan, rows);
    var cats = allCats;
    if (opt.zoom && zoomable(kind, allCats.length)) {
      cats = allCats.slice(opt.zoom[0], opt.zoom[1] + 1);
      series.forEach(function (s) {
        s.points = s.points.filter(function (p) { return cats.indexOf(p.cat) !== -1; });
      });
    }
    var horizontal = kind === "barh";
    var stacked = !!plan.stack && kind !== "line";
    if (stacked) stackPoints(series, cats);
    var ticks = tickFormatter(plan);
    var ext = opt.domain || valueExtent(series, stacked);
    var lo = ext[0], hi = ext[1];
    var titleH = opt.title ? 20 : 0;
    var m = { top: 10 + titleH, right: 16, bottom: 28, left: 12 };
    var catLabelW = 0, rotate = false, every = 1;
    cats.forEach(function (c) { catLabelW = Math.max(catLabelW, textWidth(svg, c, 12)); });
    var val = d3.scaleLinear().domain([lo, hi]).nice(5);
    var tickW = 0;
    val.ticks(5).forEach(function (v) { tickW = Math.max(tickW, textWidth(svg, ticks(v), 11)); });
    if (horizontal) {
      m.left = Math.min(Math.ceil(catLabelW) + 10, Math.round(W * 0.38));
      m.bottom = 24;
    } else {
      m.left = Math.ceil(tickW) + 10;
      var room = (W - m.left - m.right) / Math.max(1, cats.length);
      /* Names that collide: up to 16 categories turn 30°; more than that
       * (a run of years, months) label every k-th one, flat. */
      if (cats.length && room < catLabelW + 6) {
        if (cats.length > 16) every = Math.ceil((catLabelW + 14) / room);
        else rotate = true;
      }
      m.bottom = rotate ? Math.min(Math.ceil(catLabelW * 0.55) + 22, 96) : 28;
    }
    if (plan.yTitle) m.left += 18;
    if (plan.xTitle) m.bottom += 18;
    var marks = marksWanted(plan);
    if (marks.length && !horizontal) m.top += 14;
    if (marks.length && horizontal) m.right += 56;
    var iw = Math.max(10, W - m.left - m.right), ih = Math.max(10, H - m.top - m.bottom);
    var band = d3.scaleBand().domain(cats).range(horizontal ? [0, ih] : [0, iw])
      .paddingInner(kind === "bar" || kind === "barh" ? 0.28 : 0).paddingOuter(0.14);
    val.range(horizontal ? [0, iw] : [ih, 0]);
    var keys = series.map(function (s) { return s.key; });
    var inner = d3.scaleBand().domain(stacked ? ["all"] : keys)
      .range([0, band.bandwidth()]).paddingInner(0.12);
    var slot = function (k) { return inner(stacked ? "all" : k); };
    var centre = function (c) { return band(c) + band.bandwidth() / 2; };
    var zero = val(Math.max(val.domain()[0], Math.min(0, val.domain()[1])));

    var g = svg.selectAll("g.tb-plot").data([0]).join("g").attr("class", "tb-plot")
      .attr("transform", "translate(" + m.left + "," + m.top + ")");
    if (opt.title) {
      svg.selectAll("text.tb-panel-title").data([opt.title]).join("text")
        .attr("class", "tb-panel-title").attr("x", m.left).attr("y", 14)
        .attr("fill", t.ink).attr("font-size", 12).attr("font-weight", 600)
        .text(function (d) { return d; });
    }

    /* Grid and axes: recessive, in the page's rule and muted ink. */
    var grid = g.selectAll("g.tb-grid").data([0]).join("g").attr("class", "tb-grid");
    transition(entry, grid.selectAll("line").data(val.ticks(5), function (v) { return v; }).join(
      function (en) { return en.append("line").attr("stroke", t.rule); }))
      .attr(horizontal ? "x1" : "y1", function (v) { return val(v); })
      .attr(horizontal ? "x2" : "y2", function (v) { return val(v); })
      .attr(horizontal ? "y1" : "x1", 0)
      .attr(horizontal ? "y2" : "x2", horizontal ? ih : iw)
      .attr("stroke", t.rule)
      .attr("stroke-width", function (v) { return v === 0 ? 1.5 : 1; })
      .attr("stroke-opacity", function (v) { return v === 0 ? 1 : 0.7; });
    var vAxis = horizontal ? d3.axisBottom(val) : d3.axisLeft(val);
    vAxis.ticks(5).tickSize(0).tickPadding(8).tickFormat(ticks);
    var cAxis = horizontal ? d3.axisLeft(band) : d3.axisBottom(band);
    cAxis.tickSize(0).tickPadding(8);
    if (!horizontal && every > 1) {
      cAxis.tickValues(cats.filter(function (c, i) { return (cats.length - 1 - i) % every === 0; }));
    }
    var va = g.selectAll("g.tb-axis-v").data([0]).join("g").attr("class", "tb-axis tb-axis-v")
      .attr("transform", horizontal ? "translate(0," + ih + ")" : null);
    transition(entry, va).call(vAxis);
    var ca = g.selectAll("g.tb-axis-c").data([0]).join("g").attr("class", "tb-axis tb-axis-c")
      .attr("transform", horizontal ? null : "translate(0," + ih + ")");
    ca.call(cAxis);
    g.selectAll(".tb-axis .domain").remove();
    g.selectAll(".tb-axis text").attr("fill", t.muted).attr("font-size", 11)
      .attr("font-family", t.font);
    ca.selectAll("text").attr("font-size", 12).each(function () {
      fitText(this, horizontal ? m.left - 10 - (plan.yTitle ? 18 : 0)
        : rotate ? m.bottom * 1.6 : band.step() * (every || 1));
    });
    if (rotate) {
      ca.selectAll("text").attr("text-anchor", "end").attr("dx", "-0.4em")
        .attr("dy", "0.5em").attr("transform", "rotate(-30)");
    }
    var titles = [];
    if (plan.xTitle) titles.push({ text: plan.xTitle, x: iw / 2, y: ih + m.bottom - 6, rot: 0 });
    if (plan.yTitle) titles.push({ text: plan.yTitle, x: -ih / 2, y: -m.left + 12, rot: -90 });
    g.selectAll("text.tb-axis-title").data(titles).join("text").attr("class", "tb-axis-title")
      .attr("text-anchor", "middle").attr("fill", t.muted).attr("font-size", 11)
      .attr("font-weight", 600).attr("x", function (d) { return d.x; })
      .attr("y", function (d) { return d.y; })
      .attr("transform", function (d) { return d.rot ? "rotate(" + d.rot + ")" : null; })
      .text(function (d) { return d.text; });

    /* Annotations: the author's notes at a category, a dashed rule and a word. */
    var notes = annotations(plan).filter(function (a) { return band(a.at) !== undefined; });
    var ng = g.selectAll("g.tb-annotations").data([0]).join("g").attr("class", "tb-annotations");
    var na = ng.selectAll("g.tb-annotation").data(notes, function (a) { return a.at; }).join(function (en) {
      var e = en.append("g").attr("class", "tb-annotation");
      e.append("line");
      e.append("text");
      return e;
    });
    na.select("line").attr("stroke", t.muted).attr("stroke-dasharray", "4 3").attr("stroke-opacity", 0.8)
      .attr("x1", function (a) { return horizontal ? 0 : centre(a.at); })
      .attr("x2", function (a) { return horizontal ? iw : centre(a.at); })
      .attr("y1", function (a) { return horizontal ? centre(a.at) : 0; })
      .attr("y2", function (a) { return horizontal ? centre(a.at) : ih; });
    na.select("text").attr("fill", t.muted).attr("font-size", 11).attr("font-style", "italic")
      .attr("x", function (a) { return horizontal ? iw - 4 : centre(a.at) + 4; })
      .attr("y", function (a) { return horizontal ? centre(a.at) - 4 : 10; })
      .attr("text-anchor", horizontal ? "end" : "start")
      .text(function (a) { return a.text; });

    var hover = g.selectAll("rect.tb-hover").data([0]).join("rect").attr("class", "tb-hover")
      .attr("fill", t.ink).attr("fill-opacity", 0.05).attr("opacity", 0).attr("rx", 4);
    var cross = g.selectAll("line.tb-hover").data([0]).join("line").attr("class", "tb-hover")
      .attr("stroke", t.muted).attr("stroke-dasharray", "3 3").attr("opacity", 0);

    var colour = function (k) { return colourOf(entry, k); };
    var groups = g.selectAll("g.tb-series").data(series, function (s) { return s.key; }).join(
      function (en) { return en.append("g").attr("class", "tb-series"); },
      function (up) { return up; },
      function (ex) { return transition(entry, ex).attr("opacity", 0).remove(); });
    var from = function (p) { return stacked ? p.y0 : 0; };
    var to = function (p) { return stacked ? p.y1 : p.y; };

    if (kind === "bar" || kind === "barh") {
      var thick = Math.min(inner.bandwidth(), 44);
      var off = (inner.bandwidth() - thick) / 2;
      groups.each(function (s) {
        var pts = s.points.filter(function (p) { return p.y !== null && band(p.cat) !== undefined; });
        var r = d3.select(this).selectAll("path.tb-mark").data(pts, function (p) { return p.cat; });
        var shape = function (p) {
          var a = band(p.cat) + slot(s.key) + off, v = val(to(p)), b = val(from(p));
          var lo2 = Math.min(v, b), len = Math.abs(v - b);
          /* Round only the end that faces away from zero, and only the
           * outermost segment of a stack. */
          var outer = !stacked || p.y1 === (p.y >= 0 ? stackTop(series, p.cat, 1) : stackTop(series, p.cat, -1));
          var rad = outer ? Math.min(4, len, thick / 2) : 0;
          var pos = p.y >= 0;
          if (horizontal) {
            var x0 = lo2, x1 = lo2 + len, y0 = a, y1 = a + thick;
            return pos
              ? "M" + x0 + "," + y0 + "H" + (x1 - rad) + "Q" + x1 + "," + y0 + " " + x1 + "," + (y0 + rad) +
                "V" + (y1 - rad) + "Q" + x1 + "," + y1 + " " + (x1 - rad) + "," + y1 + "H" + x0 + "Z"
              : "M" + x1 + "," + y0 + "H" + (x0 + rad) + "Q" + x0 + "," + y0 + " " + x0 + "," + (y0 + rad) +
                "V" + (y1 - rad) + "Q" + x0 + "," + y1 + " " + (x0 + rad) + "," + y1 + "H" + x1 + "Z";
          }
          var top = lo2, bot = lo2 + len, l = a, rr = a + thick;
          return pos
            ? "M" + l + "," + bot + "V" + (top + rad) + "Q" + l + "," + top + " " + (l + rad) + "," + top +
              "H" + (rr - rad) + "Q" + rr + "," + top + " " + rr + "," + (top + rad) + "V" + bot + "Z"
            : "M" + l + "," + top + "V" + (bot - rad) + "Q" + l + "," + bot + " " + (l + rad) + "," + bot +
              "H" + (rr - rad) + "Q" + rr + "," + bot + " " + rr + "," + (bot - rad) + "V" + top + "Z";
        };
        var flat = function (p) {
          var a = band(p.cat) + slot(s.key) + off, b = val(from(p));
          return horizontal
            ? "M" + b + "," + a + "H" + b + "V" + (a + thick) + "H" + b + "Z"
            : "M" + a + "," + b + "H" + (a + thick) + "V" + b + "H" + a + "Z";
        };
        transition(entry, r.join(
          function (en) { return en.append("path").attr("class", "tb-mark").attr("d", flat); },
          function (up) { return up; },
          /* A leaving bar's category is gone from the axis: it fades where it stood. */
          function (ex) { return transition(entry, ex).attr("opacity", 0).remove(); }))
          .attr("d", shape).attr("fill", colour(s.key))
          .attr("stroke", stacked ? t.bg : null).attr("stroke-width", stacked ? 1 : null);
      });
    } else {
      var lineGen = d3.line().defined(function (p) { return p.y !== null; })
        .x(function (p) { return centre(p.cat); })
        .y(function (p) { return val(to(p)); });
      var areaGen = d3.area().defined(function (p) { return p.y !== null; })
        .x(function (p) { return centre(p.cat); })
        .y0(function (p) { return stacked ? val(p.y0) : zero; })
        .y1(function (p) { return val(to(p)); });
      groups.each(function (s, si) {
        var pts = s.points.filter(function (p) { return band(p.cat) !== undefined; });
        var sel = d3.select(this);
        if (kind === "area") {
          /* A soft vertical gradient: strongest at the line, fading to the base. */
          var gid = entry.uid + "-" + (opt.panel || 0) + "-" + si;
          var defs = svg.selectAll("defs").data([0]).join("defs");
          var grad = defs.selectAll("linearGradient#" + gid).data([0]).join("linearGradient")
            .attr("id", gid).attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 1);
          grad.selectAll("stop").data([[0, 0.32], [1, 0.03]]).join("stop")
            .attr("offset", function (d) { return d[0]; })
            .attr("stop-color", colour(s.key)).attr("stop-opacity", function (d) { return d[1]; });
          var ar = sel.selectAll("path.tb-area").data([pts]).join("path").attr("class", "tb-area")
            .attr("fill", "url(#" + gid + ")");
          transition(entry, ar).attr("d", areaGen);
        }
        var ln = sel.selectAll("path.tb-line").data([pts]).join("path").attr("class", "tb-line tb-mark")
          .attr("fill", "none").attr("stroke", colour(s.key)).attr("stroke-width", 2.25)
          .attr("stroke-linejoin", "round").attr("stroke-linecap", "round");
        transition(entry, ln).attr("d", lineGen);
        var dots = sel.selectAll("circle.tb-dot").data(pts.filter(function (p) { return p.y !== null; }),
          function (p) { return p.cat; });
        transition(entry, dots.join(
          function (en) { return en.append("circle").attr("class", "tb-dot").attr("r", 0)
            .attr("cx", function (p) { return centre(p.cat); }).attr("cy", function (p) { return val(to(p)); }); },
          function (up) { return up; },
          function (ex) { return ex.remove(); }))
          .attr("cx", function (p) { return centre(p.cat); })
          .attr("cy", function (p) { return val(to(p)); })
          .attr("r", cats.length > 24 ? 0 : 3.5)
          .attr("fill", colour(s.key)).attr("stroke", t.bg).attr("stroke-width", 2);
      });
    }

    /* Marked points: the series' own high, low, first or last row, labelled
     * with that row's value. Picking a row never makes a number. */
    var marked = [];
    if (marks.length) {
      series.forEach(function (s) {
        var pts = s.points.filter(function (p) { return p.y !== null && band(p.cat) !== undefined; });
        if (!pts.length) return;
        var pick = {};
        marks.forEach(function (mk) {
          var p = null;
          if (mk === "max" || mk === "high") p = pts.reduce(function (a, b) { return b.y > a.y ? b : a; });
          else if (mk === "min" || mk === "low") p = pts.reduce(function (a, b) { return b.y < a.y ? b : a; });
          else if (mk === "first") p = pts[0];
          else if (mk === "last") p = pts[pts.length - 1];
          if (!p) return;
          var word = mk === "max" || mk === "high" ? "High" : mk === "min" || mk === "low" ? "Low" : "";
          if (pick[p.cat]) { if (word && !pick[p.cat].word) pick[p.cat].word = word; return; }
          pick[p.cat] = { p: p, s: s, word: word, low: mk === "min" || mk === "low" };
        });
        for (var c in pick) if (pick.hasOwnProperty(c)) marked.push(pick[c]);
      });
    }
    var mg = g.selectAll("g.tb-marked").data([0]).join("g").attr("class", "tb-marked");
    var mm = mg.selectAll("g.tb-marked-point").data(marked, function (d) { return d.s.key + "|" + d.p.cat; })
      .join(function (en) {
        var e = en.append("g").attr("class", "tb-marked-point");
        e.append("circle");
        e.append("text");
        return e;
      });
    var fmtCol = function (d) { return chartFormatter(plan, rows, d.s.col)(d.p.y); };
    var bar = kind === "bar" || kind === "barh";
    mm.select("circle")
      .attr("cx", function (d) { return horizontal ? val(to(d.p)) : centre(d.p.cat); })
      .attr("cy", function (d) { return horizontal ? centre(d.p.cat) : val(to(d.p)); })
      .attr("r", bar ? 0 : 5).attr("fill", t.bg)
      .attr("stroke", function (d) { return colour(d.s.key); }).attr("stroke-width", 2.5);
    mm.select("text")
      .attr("x", function (d) {
        return horizontal ? val(to(d.p)) + 6 : centre(d.p.cat);
      })
      .attr("y", function (d) {
        if (horizontal) return centre(d.p.cat) + 4;
        return d.low ? val(to(d.p)) + 18 : val(to(d.p)) - 10;
      })
      .attr("text-anchor", horizontal ? "start" : "middle")
      .attr("fill", t.ink).attr("font-size", 11).attr("font-weight", 600)
      .text(function (d) { return (d.word ? d.word + " " : "") + fmtCol(d); });

    /* One hit target per category, the full plot height: the reader aims at
     * a category, never at a 2px line. */
    var filterable = !opt.noFilter && filterControlsFor(plan.x).length > 0;
    var showAt = function (i, px, py) {
      var c = cats[i];
      if (c === undefined) return;
      var a = band(c);
      if (bar) {
        hover.attr(horizontal ? "y" : "x", a - band.step() * band.paddingInner() / 2)
          .attr(horizontal ? "x" : "y", 0)
          .attr(horizontal ? "height" : "width", band.step())
          .attr(horizontal ? "width" : "height", horizontal ? iw : ih).attr("opacity", 1);
      } else {
        cross.attr("x1", centre(c)).attr("x2", centre(c)).attr("y1", 0).attr("y2", ih)
          .attr("opacity", 1);
      }
      var rowsOut = [];
      series.forEach(function (s) {
        for (var j = 0; j < s.points.length; j++) {
          if (s.points[j].cat === c) {
            rowsOut.push({ colour: colour(s.key), name: s.name,
                           value: chartFormatter(plan, rows, s.col)(s.points[j].y) });
            break;
          }
        }
      });
      var o = px === undefined ? hostOffset(entry, svg) : { x: 0, y: 0 };
      var x = px === undefined ? o.x + m.left + (horizontal ? iw / 2 : centre(c)) : px;
      var y = py === undefined ? o.y + m.top + (horizontal ? centre(c) : ih / 3) : py;
      tipShow(entry, x, y, (opt.title ? opt.title + " · " : "") + c, rowsOut);
    };
    var choose = filterable ? function (i) { filterTo(plan.x, cats[i]); } : null;
    var catAt = function (px) {
      var best = 0, bd = Infinity;
      cats.forEach(function (c, i) {
        var d = Math.abs((horizontal ? centre(c) : centre(c)) - px);
        if (d < bd) { bd = d; best = i; }
      });
      return best;
    };

    if (opt.brush && zoomable(kind, allCats.length)) {
      /* Drag across the plot to zoom to those categories; double-click (or
       * the Reset chip) returns to all of them. Hover reads as before. */
      g.selectAll("rect.tb-hit").remove();
      var bg = g.selectAll("g.tb-brush").data([0]).join("g").attr("class", "tb-brush");
      var brush = d3.brushX().extent([[0, 0], [iw, ih]]).on("end", function (event) {
        if (!event.selection) return;
        var a0 = catAt(event.selection[0]), a1 = catAt(event.selection[1]);
        bg.call(brush.move, null);
        if (a1 - a0 < 1) return;
        var first = allCats.indexOf(cats[a0]), last = allCats.indexOf(cats[a1]);
        opt.brush([first, last]);
      });
      bg.call(brush);
      bg.selectAll(".selection").attr("fill", t.accent || t.ink).attr("fill-opacity", 0.12)
        .attr("stroke", "none");
      bg.selectAll(".overlay").style("cursor", "crosshair")
        .on("pointermove.tb", function (event) {
          var q = d3.pointer(event, g.node());
          var p = d3.pointer(event, entry.surface);
          entry.keyboard = false;
          showAt(catAt(q[0]), p[0], p[1]);
        })
        .on("pointerleave.tb", function () { tipHide(entry); })
        .on("dblclick.tb", function () { opt.brush(null); });
    } else {
      g.selectAll("g.tb-brush").remove();
      var hits = g.selectAll("rect.tb-hit").data(cats, function (c) { return c; }).join("rect")
        .attr("class", "tb-hit").attr("fill", "transparent")
        .style("cursor", filterable ? "pointer" : null)
        .attr(horizontal ? "y" : "x", function (c) { return band(c) - band.step() * band.paddingInner() / 2; })
        .attr(horizontal ? "x" : "y", 0)
        .attr(horizontal ? "height" : "width", band.step())
        .attr(horizontal ? "width" : "height", horizontal ? iw : ih);
      hoverable(entry, hits, function (c, px, py) { showAt(cats.indexOf(c), px, py); });
      hits.on("click", function (event, c) { if (choose) choose(cats.indexOf(c)); });
      hits.raise();
    }
    return { count: cats.length, show: showAt, choose: choose };
  }

  function stackTop(series, cat, sign) {
    var edge = 0;
    series.forEach(function (s) {
      s.points.forEach(function (p) {
        if (p.cat !== cat || p.y1 === null || p.y1 === undefined) return;
        if (sign > 0 ? p.y1 > edge : p.y1 < edge) edge = p.y1;
      });
    });
    return edge;
  }

  /* Small multiples: one panel per value of plan.facet, laid out in a grid,
   * sharing one value scale so the panels compare at a glance. */
  function renderFacets(entry, rows, kind, W, H, t) {
    var d3 = root.d3, plan = entry.plan;
    var block = readBlock(entry.binding);
    var order = [];
    (block ? block.rows : rows).forEach(function (r) {
      var f = groupOf(r[plan.facet]);
      if (order.indexOf(f) === -1) order.push(f);
    });
    var byFacet = {};
    rows.forEach(function (r) {
      var f = groupOf(r[plan.facet]);
      (byFacet[f] = byFacet[f] || []).push(r);
    });
    var facets = order.filter(function (f) { return byFacet[f]; });
    var all = [];
    facets.forEach(function (f) {
      var s = chartSeries(entry, byFacet[f], kind);
      if (plan.stack && kind !== "line") stackPoints(s, categories(plan, byFacet[f]));
      all = all.concat(s);
    });
    var domain = valueExtent(all, !!plan.stack && kind !== "line");
    var shared = categories(plan, rows);
    var cols = Math.max(1, Math.min(facets.length, Math.floor(W / 260)));
    var rowsN = Math.ceil(facets.length / cols);
    var pw = Math.floor(W / cols), ph = Math.max(160, Math.floor((H + (rowsN - 1) * 40) / rowsN));
    entry.svg.attr("height", ph * rowsN).attr("viewBox", "0 0 " + W + " " + (ph * rowsN));
    var panels = entry.svg.selectAll("svg.tb-panel").data(facets, function (f) { return f; }).join("svg")
      .attr("class", "tb-panel").attr("overflow", "visible")
      .attr("x", function (f, i) { return (i % cols) * pw; })
      .attr("y", function (f, i) { return Math.floor(i / cols) * ph; })
      .attr("width", pw).attr("height", ph);
    var readouts = [];
    panels.each(function (f, i) {
      readouts.push(renderCategorical(entry, d3.select(this), byFacet[f], kind, pw, ph, t,
        { domain: domain, title: f, panel: i + 1, cats: shared }));
    });
    return readouts;
  }

  function renderScatter(entry, rows, W, H, t) {
    var d3 = root.d3, plan = entry.plan, svg = entry.svg;
    var series = chartSeries(entry, rows, "scatter");
    var pts = [];
    series.forEach(function (s) {
      s.points.forEach(function (p) { if (p.x !== null && p.y !== null) { p.series = s; pts.push(p); } });
    });
    var ticks = tickFormatter(plan);
    var fx = chartFormatter(plan, rows, plan.x);
    if (entry.zoomX) {
      pts = pts.filter(function (p) { return p.x >= entry.zoomX[0] && p.x <= entry.zoomX[1]; });
    }
    var xs = d3.scaleLinear().domain(d3.extent(pts, function (p) { return p.x; })).nice(6);
    var ys = d3.scaleLinear().domain(d3.extent(pts, function (p) { return p.y; })).nice(5);
    if (!pts.length) { xs.domain([0, 1]); ys.domain([0, 1]); }
    var tickW = 0;
    ys.ticks(5).forEach(function (v) { tickW = Math.max(tickW, textWidth(svg, ticks(v), 11)); });
    /* Both axes are measures, so each is titled: nothing else says which is which. */
    var m = { top: 10, right: 16, bottom: 46, left: Math.ceil(tickW) + 28 };
    var iw = Math.max(10, W - m.left - m.right), ih = Math.max(10, H - m.top - m.bottom);
    xs.range([0, iw]);
    ys.range([ih, 0]);
    var g = svg.selectAll("g.tb-plot").data([0]).join("g").attr("class", "tb-plot")
      .attr("transform", "translate(" + m.left + "," + m.top + ")");
    var grid = g.selectAll("g.tb-grid").data([0]).join("g").attr("class", "tb-grid");
    transition(entry, grid.selectAll("line").data(ys.ticks(5), function (v) { return v; }).join("line"))
      .attr("x1", 0).attr("x2", iw).attr("y1", function (v) { return ys(v); })
      .attr("y2", function (v) { return ys(v); }).attr("stroke", t.rule).attr("stroke-opacity", 0.7);
    transition(entry, g.selectAll("g.tb-axis-y").data([0]).join("g").attr("class", "tb-axis tb-axis-y"))
      .call(d3.axisLeft(ys).ticks(5).tickSize(0).tickPadding(8).tickFormat(ticks));
    transition(entry, g.selectAll("g.tb-axis-x").data([0]).join("g").attr("class", "tb-axis tb-axis-x")
      .attr("transform", "translate(0," + ih + ")"))
      .call(d3.axisBottom(xs).ticks(Math.max(2, Math.floor(iw / 90))).tickSize(0).tickPadding(8)
        .tickFormat(ticks));
    g.selectAll(".tb-axis .domain").remove();
    g.selectAll(".tb-axis text").attr("fill", t.muted).attr("font-size", 11).attr("font-family", t.font);
    g.selectAll("text.tb-axis-title").data([
      { text: plan.xTitle || humanise(plan.x), x: iw / 2, y: ih + 38, rot: 0 },
      { text: plan.yTitle || humanise(plan.y[0]), x: -ih / 2, y: -m.left + 12, rot: -90 }
    ]).join("text").attr("class", "tb-axis-title")
      .attr("text-anchor", "middle").attr("fill", t.ink).attr("font-size", 12)
      .attr("font-weight", 600).attr("x", function (d) { return d.x; })
      .attr("y", function (d) { return d.y; })
      .attr("transform", function (d) { return d.rot ? "rotate(" + d.rot + ")" : null; })
      .text(function (d) { return d.text; });
    var dots = g.selectAll("circle.tb-mark").data(pts, function (p, i) { return p.key + "|" + i; });
    transition(entry, dots.join(
      function (en) { return en.append("circle").attr("class", "tb-mark").attr("r", 0)
        .attr("cx", function (p) { return xs(p.x); }).attr("cy", function (p) { return ys(p.y); }); },
      function (up) { return up; },
      function (ex) { return transition(entry, ex).attr("r", 0).remove(); }))
      .attr("cx", function (p) { return xs(p.x); }).attr("cy", function (p) { return ys(p.y); })
      .attr("r", 5).attr("fill", function (p) { return colourOf(entry, p.key); })
      .attr("fill-opacity", 0.85).attr("stroke", t.bg).attr("stroke-width", 2);
    /* A point is named by its row's first text column (an issuer, a
     * customer), when the binding has one beside the plotted columns. */
    var block = readBlock(entry.binding), labelCol = null;
    (block ? block.cols : []).forEach(function (c) {
      if (labelCol || c === plan.x || c === plan.color || plan.y.indexOf(c) !== -1) return;
      if (!isNumericColumn(rows, c)) labelCol = c;
    });
    var ring = g.selectAll("circle.tb-hover").data([0]).join("circle").attr("class", "tb-hover")
      .attr("r", 9).attr("fill", "none").attr("stroke", t.ink).attr("stroke-width", 1.5).attr("opacity", 0);
    var showAt = function (i, px, py) {
      var p = pts[i];
      if (!p) return;
      ring.attr("cx", xs(p.x)).attr("cy", ys(p.y)).attr("opacity", 1);
      tipShow(entry, px === undefined ? m.left + xs(p.x) : px,
        py === undefined ? hostOffset(entry, entry.svg).y + m.top + ys(p.y) : py,
        labelCol && p.row[labelCol] !== undefined
          ? String(p.row[labelCol]) + (plan.color ? " \u00b7 " + p.series.name : "")
          : p.series.name, [
          { colour: colourOf(entry, p.key), name: humanise(plan.x), value: fx(p.x) },
          { colour: colourOf(entry, p.key), name: humanise(p.series.col),
            value: chartFormatter(plan, rows, p.series.col)(p.y) }
        ]);
    };
    /* Nearest point wins: the reader only has to be closest, not dead on.
     * Dragging across the plot zooms to that range of x; double-click or
     * the Reset chip returns. */
    g.selectAll("rect.tb-hit").remove();
    var bg = g.selectAll("g.tb-brush").data([0]).join("g").attr("class", "tb-brush");
    var brush = d3.brushX().extent([[0, 0], [iw, ih]]).on("end", function (event) {
      if (!event.selection) return;
      var x0 = xs.invert(event.selection[0]), x1 = xs.invert(event.selection[1]);
      bg.call(brush.move, null);
      var inside = pts.filter(function (p) { return p.x >= x0 && p.x <= x1; });
      if (inside.length < 2) return;
      entry.zoomX = [x0, x1];
      renderD3Chart(entry, filteredRows(entry.binding), true);
    });
    bg.call(brush);
    bg.selectAll(".selection").attr("fill", t.accent || t.ink).attr("fill-opacity", 0.12).attr("stroke", "none");
    var overlay = bg.selectAll(".overlay").style("cursor", "crosshair");
    overlay.on("dblclick.tb", function () {
      entry.zoomX = null;
      renderD3Chart(entry, filteredRows(entry.binding), true);
    });
    overlay.on("pointermove.tb", function (event) {
      var q = d3.pointer(event, this), best = -1, bd = Infinity;
      for (var i = 0; i < pts.length; i++) {
        var dx = xs(pts[i].x) - q[0], dy = ys(pts[i].y) - q[1], dd = dx * dx + dy * dy;
        if (dd < bd) { bd = dd; best = i; }
      }
      entry.keyboard = false;
      if (best >= 0 && bd < 40 * 40) {
        var p2 = d3.pointer(event, entry.surface);
        showAt(best, p2[0], p2[1]);
      } else tipHide(entry);
    }).on("pointerleave.tb", function () { tipHide(entry); });
    keyboardWalk(entry, pts.length, function (i) { showAt(i); }, null);
  }

  function renderPie(entry, rows, W, H, t) {
    var d3 = root.d3, plan = entry.plan, svg = entry.svg, y0 = plan.y[0];
    var fmtV = chartFormatter(plan, rows, y0);
    var slices = rows.filter(function (r) { return !entry.hidden[String(r[plan.x])]; })
      .map(function (r) {
        /* |value|: a negative slice has no geometry; the label shows the row's own value. */
        return { key: String(r[plan.x]), raw: toNum(r[y0]), v: Math.abs(toNum(r[y0]) || 0) };
      });
    var R = Math.max(20, Math.min(W, H) / 2 - 8);
    var arcs = d3.pie().sort(null).padAngle(0.012).value(function (s) { return s.v; })(slices);
    var arc = d3.arc().innerRadius(R * 0.6).outerRadius(R).cornerRadius(3);
    var big = d3.arc().innerRadius(R * 0.6).outerRadius(R + 6).cornerRadius(3);
    var g = svg.selectAll("g.tb-plot").data([0]).join("g").attr("class", "tb-plot")
      .attr("transform", "translate(" + W / 2 + "," + H / 2 + ")");
    var paths = g.selectAll("path.tb-mark").data(arcs, function (a) { return a.data.key; });
    var prev = entry.prevArcs || {};
    var joined = paths.join(
      function (en) { return en.append("path").attr("class", "tb-mark")
        .each(function (a) { this._tbArc = { startAngle: a.startAngle, endAngle: a.startAngle }; }); },
      function (up) { return up; },
      function (ex) { return ex.remove(); })
      .attr("fill", function (a) { return colourOf(entry, a.data.key); })
      .attr("stroke", t.bg).attr("stroke-width", 2);
    if (entry.animate) {
      joined.transition().duration(_MOTION_MS).ease(d3.easeCubicOut).attrTween("d", function (a) {
        var from = this._tbArc || prev[a.data.key] || { startAngle: a.startAngle, endAngle: a.startAngle };
        var it = d3.interpolate(from, { startAngle: a.startAngle, endAngle: a.endAngle });
        var node = this;
        return function (k) { node._tbArc = it(k); return arc(node._tbArc); };
      });
    } else {
      joined.attr("d", arc).each(function (a) { this._tbArc = { startAngle: a.startAngle, endAngle: a.endAngle }; });
    }
    entry.prevArcs = {};
    arcs.forEach(function (a) { entry.prevArcs[a.data.key] = a; });
    var filterable = filterControlsFor(plan.x).length > 0;
    var showAt = function (i, px, py) {
      var a = arcs[i];
      if (!a) return;
      g.selectAll("path.tb-mark").attr("d", function (b) { return b === a ? big(b) : arc(b); });
      var c = arc.centroid(a);
      tipShow(entry, px === undefined ? W / 2 + c[0] : px,
        py === undefined ? hostOffset(entry, entry.svg).y + H / 2 + c[1] : py,
        a.data.key, [{ colour: colourOf(entry, a.data.key), name: humanise(y0), value: fmtV(a.data.raw) }]);
    };
    joined.style("cursor", filterable ? "pointer" : null)
      .on("pointermove", function (event, a) {
        var p = d3.pointer(event, entry.surface);
        entry.keyboard = false;
        showAt(arcs.indexOf(a), p[0], p[1]);
      })
      .on("pointerleave", function () {
        g.selectAll("path.tb-mark").attr("d", arc);
        tipHide(entry);
      })
      .on("click", function (event, a) { filterTo(plan.x, a.data.key); });
    keyboardWalk(entry, arcs.length, function (i) { showAt(i); },
      filterable ? function (i) { filterTo(plan.x, arcs[i].data.key); } : null);
  }

  function renderD3Chart(entry, rows, animate) {
    var d3 = root.d3, kind = chartKind(entry.plan);
    var surface = entry.surface;
    var W = surface.clientWidth;
    entry.width = W;
    if (!W) return; /* hidden tab: drawn when shown */
    entry.animate = !!animate && motionOk() && !!entry.svg;
    var t = theme();
    t.rule = t.rule || "#e5e5e5";
    t.muted = t.muted || "#666";
    t.ink = t.ink || "#111";
    t.bg = t.bg || "#fff";
    legendFor(entry, kind);
    var H = Math.max(200, entry.height - entry.legend.offsetHeight - 8);
    if (!entry.svg) {
      entry.svg = d3.select(surface).append("svg").attr("class", "tb-chart-svg")
        .attr("tabindex", 0).attr("role", "img")
        .attr("aria-roledescription", "chart")
        .attr("aria-label", (kind === "barh" ? "bar" : kind) + " chart of " +
          entry.plan.y.map(humanise).join(", ") + " by " + humanise(entry.plan.x) +
          ". Use the arrow keys to read each value.");
    }
    entry.svg.attr("width", W).attr("height", H).attr("viewBox", "0 0 " + W + " " + H)
      .style("font-family", t.font);
    if (entry.kindDrawn && entry.kindDrawn !== kind) entry.svg.selectAll("*").remove();
    entry.kindDrawn = kind;
    tipHide(entry);
    if (kind === "pie") { renderPie(entry, rows, W, H, t); return; }
    if (kind === "scatter") { renderScatter(entry, rows, W, H, t); return; }
    var readouts;
    if (entry.plan.facet) {
      entry.svg.selectAll("g.tb-plot").remove();
      readouts = renderFacets(entry, rows, kind, W, H, t);
    } else {
      entry.svg.selectAll("svg.tb-panel").remove();
      readouts = [renderCategorical(entry, entry.svg, rows, kind, W, H, t, {
        zoom: entry.zoom,
        brush: function (range) {
          entry.zoom = range;
          renderD3Chart(entry, filteredRows(entry.binding), true);
        }
      })];
    }
    /* One keyboard walk across every panel's categories, in reading order. */
    var stops = [];
    readouts.forEach(function (r) { for (var i = 0; i < r.count; i++) stops.push([r, i]); });
    keyboardWalk(entry, stops.length,
      function (n) { stops[n][0].show(stops[n][1]); },
      function (n) { if (stops[n][0].choose) stops[n][0].choose(stops[n][1]); });
  }

  function hydrateD3Chart(el, plan, binding, block) {
    var fb = el.querySelector(".tb-chart-fallback");
    if (fb) el.removeChild(fb);
    /* The figure's own height (CSS, else the 320px minimum), read once:
     * reading it after drawing would measure the chart itself. */
    var height = Math.max(320, el.clientHeight);
    var surface = document.createElement("div");
    surface.className = "tb-chart";
    var legend = document.createElement("div");
    legend.className = "tb-legend-row";
    var tip = document.createElement("div");
    tip.className = "tb-chart-tip";
    tip.hidden = true;
    var live = document.createElement("div");
    live.className = "tb-sr-only";
    live.setAttribute("aria-live", "polite");
    surface.appendChild(legend);
    surface.appendChild(tip);
    surface.appendChild(live);
    el.appendChild(surface);
    var entry = { el: el, binding: binding, plan: plan, surface: surface, legend: legend,
                  tip: tip, live: live, hidden: {}, d3: true, height: height,
                  uid: "tbc" + (_charts.length + 1),
                  keys: seriesKeys(plan, block.rows, chartKind(plan)) };
    _charts.push(entry);
    renderD3Chart(entry, filteredRows(binding), false);
    /* A gentle first draw: bars rise and lines settle once, then the page
     * reports ready (a printer waits for that). */
    if (motionOk() && entry.svg) {
      _introPending++;
      entry.svg.style("opacity", 0).transition().duration(_MOTION_MS)
        .ease(root.d3.easeCubicOut).style("opacity", 1)
        .on("end interrupt", function () { _introPending = Math.max(0, _introPending - 1); });
    }
    return entry;
  }

  function hydrateCharts() {
    if (!root.echarts && !root.d3) return; /* no charting lib on this page */
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
          palette: own ? splitList(own) : palette,
          xTitle: attr(el, "data-tb-x-title"),
          yTitle: attr(el, "data-tb-y-title"),
          stack: el.getAttribute("data-tb-stack") !== null,
          mark: attr(el, "data-tb-mark"),
          annotate: attr(el, "data-tb-annotate"),
          facet: attr(el, "data-tb-facet"),
          unit: attr(el, "data-tb-unit")
        };
        /* Remove the server-rendered static SVG fallback (no-JS picture of the
         * chart) before drawing — echarts.init appends its root without
         * clearing, so a surviving <svg> would stack beside the live chart. */
        /* D3 draws unless the report kept ECharts ("libs": ["echarts"]). */
        if (!root.echarts) { hydrateD3Chart(el, plan, binding, block); return; }
        var fb = el.querySelector(".tb-chart-fallback");
        if (fb) el.removeChild(fb);
        var chart = root.echarts.init(el);
        chart.setOption(buildOption(el, plan, filteredRows(binding)));
        _charts.push({ el: el, binding: binding, plan: plan, chart: chart });
        root.addEventListener("resize", function () { chart.resize(); });
      } catch (e) { /* defensive */ }
    });
    if (!root.echarts && _charts.length && root.addEventListener) {
      var pending = false;
      root.addEventListener("resize", function () {
        if (pending) return;
        pending = true;
        setTimeout(function () { pending = false; resizeCharts(); }, 120);
      });
    }
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
        markDirection(el, target, raw);
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
    _scrollReady = true;
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
          label.textContent = "Scenario · computed in your browser from these inputs · not part of the receipt";
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
    try { hydrateControls(); } catch (e) {}
    try { hydrateDownloads(); } catch (e) {}
    try { hydrateReceipt(); } catch (e) {}
    try { hydrateScenarios(); } catch (e) {}
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
    draw: draw,
    theme: theme,
    setSelection: setSelection,
    /* The scenario evaluator, exposed so tests and authors can check a
     * formula gives what they expect. It computes from the values passed. */
    evaluate: evalFormula
  };
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
