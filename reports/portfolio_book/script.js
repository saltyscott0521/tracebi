// Draw the whole page from the embedded, FINGERPRINTED data. Each data block is
// a <script type="application/json"> carrying the canonical triple — including
// the exact `csv` the receipt hashes. The page parses that same csv, so a
// displayed number cannot diverge from a verified one. Values reach the DOM only
// through textContent, never innerHTML, so a hostile issuer name cannot execute
// (architecture §5).
(function () {
  // Minimal RFC-4180 CSV parser: handles quoted fields, escaped "" quotes, and
  // commas inside quotes (issuer names like "Acme Industrial Holdings, LLC").
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
    return rows
      .filter(function (r) { return r.length === head.length; })
      .map(function (r) {
        var o = {};
        head.forEach(function (h, j) { o[h] = r[j]; });
        return o;
      });
  }

  function read(id) {
    var el = document.getElementById(id);
    if (!el) return [];
    var block = JSON.parse(el.textContent);
    return parseCsv(block.csv);
  }

  function money(v) {
    return "$" + Math.round(Number(v)).toLocaleString();
  }

  // Fair value by sector → an ECharts bar chart, drawn from the verified csv.
  // echarts is the inlined global (report.json "libs": ["echarts"]).
  var sectors = read("tracebi-data-by_sector")
    .slice()
    .sort(function (a, b) { return Number(a.fair_value) - Number(b.fair_value); });
  var host = document.getElementById("by-sector");
  function drawSectorChart() {
    if (!host || !sectors.length || !window.echarts) return;
    var chart = echarts.init(host);
    window.addEventListener("resize", function () { chart.resize(); });
    chart.setOption({
      // A report is a static document — render immediately, don't animate.
      animation: false,
      grid: { left: 96, right: 40, top: 16, bottom: 24 },
      tooltip: {
        trigger: "axis",
        valueFormatter: function (v) { return money(v); },
      },
      xAxis: {
        type: "value",
        axisLabel: {
          formatter: function (v) { return "$" + Math.round(v / 1e6) + "M"; },
        },
      },
      yAxis: {
        type: "category",
        data: sectors.map(function (r) { return r["dim_issuer.sector"]; }),
      },
      series: [{
        type: "bar",
        data: sectors.map(function (r) { return Number(r.fair_value); }),
        itemStyle: { color: "#1f4e79" },
        label: {
          show: true, position: "right",
          formatter: function (p) { return money(p.value); },
        },
      }],
    });
  }
  // Draw after layout, so ECharts reads the container's real size (a chart
  // init'd at zero width renders nothing).
  if (document.readyState === "complete") requestAnimationFrame(drawSectorChart);
  else window.addEventListener("load", function () { requestAnimationFrame(drawSectorChart); });

  // Largest issuer exposures → table, top 10 by fair value.
  var issuers = read("tracebi-data-top_issuers");
  var tbody = document.querySelector("#top-issuers tbody");
  if (tbody && issuers.length) {
    issuers
      .slice()
      .sort(function (a, b) { return Number(b.fair_value) - Number(a.fair_value); })
      .slice(0, 10)
      .forEach(function (r) {
        var tr = document.createElement("tr");

        var name = document.createElement("td");
        name.textContent = r["dim_issuer.issuer"];

        var fv = document.createElement("td");
        fv.className = "num";
        fv.textContent = money(r.fair_value);

        var pos = document.createElement("td");
        pos.className = "num";
        pos.textContent = Number(r.positions).toLocaleString();

        tr.appendChild(name);
        tr.appendChild(fv);
        tr.appendChild(pos);
        tbody.appendChild(tr);
      });
  }
})();
