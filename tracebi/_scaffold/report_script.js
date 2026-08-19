(function () {
  // Minimal RFC-4180 CSV parser — handles quoted fields and commas inside them.
  function parseCsv(text) {
    var rows = [], row = [], field = "", inQ = false, i = 0, c;
    while (i < text.length) {
      c = text[i];
      if (inQ) {
        if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else { inQ = false; } }
        else { field += c; }
      } else if (c === '"') { inQ = true; }
      else if (c === ',') { row.push(field); field = ""; }
      else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ""; }
      else if (c !== '\r') { field += c; }
      i++;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    var head = rows.shift() || [];
    return rows.filter(function (r) { return r.length === head.length; })
      .map(function (r) { var o = {}; head.forEach(function (h, j) { o[h] = r[j]; }); return o; });
  }

  var el = document.getElementById("tracebi-data-rows");
  if (!el) return;
  // Draw from the fingerprinted `csv` — the exact bytes the receipt covers — so
  // a displayed number cannot diverge from a verified one.
  var rows = parseCsv(JSON.parse(el.textContent).csv || "");
  var table = document.getElementById("rows");
  if (!rows.length || !table) return;
  var cols = Object.keys(rows[0]);

  // A starter bar chart: first column as category, first numeric column as
  // value. ECharts is the inlined global (report.json "libs": ["echarts"]).
  (function () {
    var host = document.getElementById("chart");
    var val = null;
    for (var k = 1; k < cols.length; k++) {
      if (rows[0][cols[k]] !== "" && !isNaN(Number(rows[0][cols[k]]))) { val = cols[k]; break; }
    }
    if (!host || !window.echarts || !val) { if (host) host.style.display = "none"; return; }
    var cat = cols[0];
    function draw() {
      // A report is a static document — render immediately, don't animate (and
      // the tree-shaken bundle's grow-animation does not complete).
      var chart = echarts.init(host);
      window.addEventListener("resize", function () { chart.resize(); });
      chart.setOption({
        animation: false,
        tooltip: { trigger: "axis" },
        grid: { left: 64, right: 24, top: 16, bottom: 72 },
        xAxis: { type: "category", axisLabel: { rotate: 30 },
                 data: rows.map(function (r) { return r[cat]; }) },
        yAxis: { type: "value" },
        series: [{ type: "bar", name: val, itemStyle: { color: "#1f4e79" },
                   data: rows.map(function (r) { return Number(r[val]); }) }],
      });
    }
    // Draw after layout so ECharts reads the container's real size.
    if (document.readyState === "complete") requestAnimationFrame(draw);
    else window.addEventListener("load", function () { requestAnimationFrame(draw); });
  })();

  var thead = table.querySelector("thead");
  var htr = document.createElement("tr");
  cols.forEach(function (c) {
    var th = document.createElement("th");
    th.textContent = c;
    htr.appendChild(th);
  });
  thead.appendChild(htr);
  var tbody = table.querySelector("tbody");
  rows.forEach(function (row) {
    var tr = document.createElement("tr");
    cols.forEach(function (c) {
      var td = document.createElement("td");
      var v = row[c];
      if (v !== "" && v != null && !isNaN(Number(v))) {
        td.className = "num";
        td.textContent = Number(v).toLocaleString();
      } else {
        td.textContent = v == null ? "" : String(v);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
})();
