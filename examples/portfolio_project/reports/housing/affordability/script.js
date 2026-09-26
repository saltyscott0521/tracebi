/* Chart styling for Then vs Now. configureChart restyles a chart; the series
 * data still comes only from the stamped bytes. The labels below show values
 * already on the chart (the last point, the peak), never new numbers. */
tracebi.ready(function () {
  var GREEN = "#1f7a4d", GOLD = "#b8860b", SLATE = "#2b6f9e", INK = "#0f3d2a";
  var rows = tracebi.data("history");

  function money(v) { return "$" + tracebi.fmt(v, "compact"); }
  function pct(v) { return (Number(v) * 100).toFixed(1) + "%"; }
  function rate(v) { return Number(v).toFixed(2) + "%"; }

  /* Which stamped row holds a column's largest value: the point to label. */
  function peakIndex(column) {
    var best = -1, at = -1;
    rows.forEach(function (r, i) {
      var v = Number(r[column]);
      if (isFinite(v) && v > best) { best = v; at = i; }
    });
    return at;
  }

  function fill(hex) {
    return {
      type: "linear", x: 0, y: 0, x2: 0, y2: 1,
      colorStops: [{ offset: 0, color: hex + "59" }, { offset: 1, color: hex + "05" }]
    };
  }

  /* One series: a 2.5px line over a soft gradient, its last value written
   * at the end of the line and, for a peak column, that point marked. */
  function line(name, hex, label, peakColumn) {
    var peak = peakColumn ? peakIndex(peakColumn) : -1;
    return {
      name: name,
      color: hex,
      showSymbol: peak >= 0,
      symbol: "circle",
      symbolSize: function (_v, p) { return p.dataIndex === peak ? 9 : 0; },
      itemStyle: { color: "#fff", borderColor: hex, borderWidth: 2.5 },
      lineStyle: { width: 2.5, color: hex },
      areaStyle: { color: fill(hex) },
      label: {
        show: peak >= 0, position: "top", distance: 8,
        color: INK, fontWeight: 600,
        formatter: function (p) {
          return p.dataIndex === peak ? "peak " + label(p.value) : "";
        }
      },
      endLabel: {
        show: true, color: INK, fontWeight: 600, distance: 6,
        formatter: function (p) { return label(p.value); }
      }
    };
  }

  function chart(id, series, valueLabel, legend) {
    tracebi.configureChart(id, {
      grid: { left: 8, right: 64, top: legend ? 40 : 30, bottom: 8, containLabel: true },
      legend: legend ? { top: 0, left: 0, textStyle: { color: INK } } : undefined,
      tooltip: { trigger: "axis", valueFormatter: valueLabel },
      xAxis: { boundaryGap: false, axisLine: { lineStyle: { color: "#cfc8b6" } } },
      yAxis: { splitLine: { lineStyle: { color: "#ece6d6", type: "dashed" } } },
      animationDuration: 1400,
      animationEasing: "cubicOut",
      series: series
    });
  }

  chart("chart-rate", [line("Rate", SLATE, rate, "mortgage_rate")], rate);
  chart("chart-price-income", [
    line("Median home price", GREEN, money),
    line("Median household income", GOLD, money)
  ], money, true);
  chart("chart-payment", [line("Monthly payment", GREEN, money)], money);
  chart("chart-share", [line("Share of income", GREEN, pct, "payment_share")], pct);
});
