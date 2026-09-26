/* Chart styling for the housing report. configureChart restyles a chart; the
 * series data still comes only from the stamped bytes. */
tracebi.ready(function () {
  var GREEN = "#1f7a4d", GOLD = "#b8860b", SLATE = "#2b6f9e", INK = "#0f3d2a";
  function pct(v) { return (Number(v) * 100).toFixed(1) + "%"; }
  var axes = {
    xAxis: { axisLine: { lineStyle: { color: "#cfc8b6" } } },
    yAxis: { splitLine: { lineStyle: { color: "#ece6d6", type: "dashed" } } }
  };

  /* The one number: measured buyers solid green, projected ones gold. The
   * runtime splits the bars by basis; stacking puts both on one bar slot. */
  tracebi.configureChart("chart-ten-year", {
    grid: { left: 8, right: 16, top: 40, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, textStyle: { color: INK } },
    /* item, not axis: each year has one bar, measured or projected. */
    tooltip: { trigger: "item", valueFormatter: pct },
    color: [GREEN, GOLD],
    xAxis: axes.xAxis, yAxis: axes.yAxis,
    series: [{ type: "bar", stack: "one", barCategoryGap: "25%" },
             { type: "bar", stack: "one", itemStyle: { opacity: 0.8 } }]
  });

  /* The three trends: a line over a soft fill, the peak marked and the
   * latest value written at the end — both points already on the chart. */
  var rows = tracebi.data("history");
  function peakIndex(col) {
    var best = -Infinity, at = -1;
    rows.forEach(function (r, i) { var v = Number(r[col]); if (v > best) { best = v; at = i; } });
    return at;
  }
  function trend(id, col, name, hex, label) {
    var peak = peakIndex(col);
    tracebi.configureChart(id, {
      grid: { left: 8, right: 56, top: 28, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: label },
      xAxis: { boundaryGap: false, axisLine: { lineStyle: { color: "#cfc8b6" } } },
      yAxis: axes.yAxis,
      series: [{
        type: "line", name: name, color: hex, showSymbol: true, symbol: "circle",
        symbolSize: function (_v, p) { return p.dataIndex === peak ? 8 : 0; },
        itemStyle: { color: "#fff", borderColor: hex, borderWidth: 2.5 },
        lineStyle: { width: 2.5, color: hex },
        areaStyle: { color: { type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: hex + "55" }, { offset: 1, color: hex + "05" }] } },
        label: { show: true, position: "top", color: INK, fontWeight: 600,
          formatter: function (p) { return p.dataIndex === peak ? "peak " + label(p.value) : ""; } },
        endLabel: { show: true, color: INK, fontWeight: 600,
          formatter: function (p) { return label(p.value); } }
      }]
    });
  }
  trend("chart-rate", "mortgage_rate", "Rate", SLATE, function (v) { return Number(v).toFixed(2) + "%"; });
  trend("chart-pti", "price_to_income", "Price ÷ income", GOLD, function (v) { return Number(v).toFixed(1) + "×"; });
  trend("chart-share", "payment_share", "Share of income", GREEN, pct);

  /* One line per buyer: the runtime splits the series by purchase year. */
  tracebi.configureChart("chart-paths", {
    grid: { left: 8, right: 24, top: 40, bottom: 8, containLabel: true },
    legend: { top: 0, left: 0, textStyle: { color: INK } },
    tooltip: { trigger: "axis", valueFormatter: pct },
    color: ["#b5523b", SLATE, GREEN],
    xAxis: { name: "years owned", nameLocation: "middle", nameGap: 26,
             boundaryGap: false, axisLine: { lineStyle: { color: "#cfc8b6" } } },
    yAxis: axes.yAxis
  });

  /* Mark the row whose stamped share is larger as the harder one: a
   * comparison of two numbers already on the page, never a new one. */
  function stamped(el) {
    var row = tracebi.data(el.getAttribute("data-tb-binding"))[0];
    return row ? Number(row[el.getAttribute("data-tb-cell")]) : NaN;
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-mp-vs]"), function (card) {
    var a = card.querySelector('[data-tb-vs="a"] strong');
    var b = card.querySelector('[data-tb-vs="b"] strong');
    var va = stamped(a), vb = stamped(b);
    if (!isFinite(va) || !isFinite(vb) || va === vb) return;
    (va > vb ? a : b).parentNode.classList.add("mp-harder");
  });
});
