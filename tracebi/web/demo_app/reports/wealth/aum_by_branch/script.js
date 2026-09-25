// ─────────────────────────────────────────────────────────────────────────
// AUM by Branch: chart restyling.
//
// tracebi.configureChart(id, patch) merges a patch into the ECharts option
// the runtime built for that figure. It restyles only: every series keeps
// the data read from the embedded, fingerprinted binding.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  var tb = window.tracebi;

  // Bars: pine, lighter at the top.
  tb.configureChart("chart-branch", {
    series: [{
      itemStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [{ offset: 0, color: "#3f9a83" }, { offset: 1, color: "#1f6f5c" }],
        },
      },
    }],
  });

  // Doughnut: this report's palette, with a gapped ring and a legend below
  // (outside labels clip in a half-width card).
  tb.configureChart("chart-asset", {
    color: ["#1f6f5c", "#c08a2b", "#4c6ea8", "#b5563c"],
    legend: { show: true, bottom: 0, icon: "circle" },
    series: [{
      center: ["50%", "44%"],
      label: { show: false },
      labelLine: { show: false },
      itemStyle: { borderRadius: 5, borderColor: "#fff", borderWidth: 3 },
    }],
  });
})();
