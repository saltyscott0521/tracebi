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
 * compute new numbers. See the view layer below.
 *
 * Every hydration step is defensive: a missing block, empty rows, or absent
 * echarts skips that figure silently — the author's content still shows.
 */
(function (root) {
  "use strict";

  /* ── CSV parsing (the RFC-4180 parser, promoted out of _CHART_INIT_JS —
   *    one parser, both lanes) ─────────────────────────────────────────── */

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
    if (name === "currency") return "$" + fixedGrouped(n, 2);
    if (name === "currency0") return "$" + fixedGrouped(n, 0);
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

  function columnValues(rows, col) {
    var out = [];
    for (var i = 0; i < rows.length; i++) {
      if (rows[i][col] !== undefined && rows[i][col] !== "") out.push(rows[i][col]);
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

  /* The one gate reactive figures re-render through: the stamped rows,
   * subset by the binding's active filters (AND across columns) and its
   * search term (case-insensitive substring across all columns, ANDed in). */
  function filteredRows(binding) {
    var block = readBlock(binding);
    if (!block) return [];
    var view = _views[binding];
    if (!view) return block.rows;
    return block.rows.filter(function (r) {
      return rowMatches(r, block.cols, view);
    });
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

  /* ── ECharts option building — mirrors _CHART_INIT_JS semantics ──────── */

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
        var name = attr(el, "data-tb-format");
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
  function renderBody(entry, rows) {
    var el = entry.el;
    var tbody = el.querySelector("tbody");
    if (!tbody) {
      tbody = document.createElement("tbody");
      el.appendChild(tbody);
    }
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
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

  function hydrateTables() {
    figureEls("table").forEach(function (el) {
      try {
        if (el.tagName !== "TABLE") return;
        /* An author-rendered table is left alone (and never reactive). */
        if (el.querySelector("tbody tr")) return;
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

        var numeric = {}, formats = {};
        cols.forEach(function (col) {
          numeric[col] = isNumericColumn(rows, col);
          formats[col] = numeric[col] ? deriveFormat(rows, col) : null;
        });

        /* Build via createElement/textContent only — data never becomes
         * markup. An existing author thead is honoured. */
        if (!el.querySelector("thead")) {
          var thead = document.createElement("thead");
          var htr = document.createElement("tr");
          cols.forEach(function (col) {
            var th = document.createElement("th");
            th.textContent = humanise(col);
            if (numeric[col]) th.className = "tb-num";
            htr.appendChild(th);
          });
          thead.appendChild(htr);
          el.appendChild(thead);
        }
        var entry = { el: el, binding: binding, cols: cols,
                      numeric: numeric, formats: formats,
                      rowCount: rows.length };
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

  /* The built option for one chart, patch applied — shared by the first
   * hydration and every control-driven re-render. */
  function buildOption(el, plan, rows) {
    var option = optionFor(plan, rows);

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

  var _BADGES = {
    verified:   { cls: "tb-badge--verified",   text: "verified" },
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

  function hydrateControls() {
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
            /* The stamped triple's csv string exactly as embedded — the
             * bytes the fingerprint covers. A receipt-preserving export:
             * never the filtered view, never a re-serialisation. */
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

  function receiptFigureRow(drawer, fig) {
    if (!fig || !fig.id) return;
    var row = document.createElement("div");
    row.className = "tb-receipt-row";
    var label = document.createElement("span");
    var text = String(fig.id);
    if (fig.kind) text += " · " + fig.kind;
    if (!fig.unverified && fig.binding) text += " · " + fig.binding;
    label.textContent = text;
    row.appendChild(label);
    if (fig.unverified) {
      /* The recorded status in its existing tone — display, not judgment. */
      var badge = document.createElement("span");
      badge.className = "tb-badge tb-badge--unverified";
      badge.textContent = "unverified";
      row.appendChild(badge);
    }
    if (fig.fingerprint) {
      var fp = document.createElement("span");
      fp.className = "tb-receipt-fp";
      fp.textContent = String(fig.fingerprint).slice(0, 12);
      fp.title = String(fig.fingerprint);
      row.appendChild(fp);
    }
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
      try { receiptFigureRow(drawer, figures[i]); } catch (e) { /* defensive */ }
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

  /* DOM-ready, then requestAnimationFrame (mirroring _CHART_INIT_JS): the
   * author's inline script.js has already run by DOMContentLoaded, so its
   * configureChart patches are registered before any chart is drawn. */
  if (typeof document !== "undefined") {
    var schedule = function () {
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(hydrate);
      else hydrate();
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", schedule);
    } else {
      schedule();
    }
  }

  root.tracebi = {
    data: data,
    fmt: fmt,
    configureChart: configureChart
  };
})(typeof window !== "undefined" ? window
   : typeof globalThis !== "undefined" ? globalThis : this);
