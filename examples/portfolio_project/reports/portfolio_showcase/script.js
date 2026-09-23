// ─────────────────────────────────────────────────────────────────────────
// Portfolio Showcase: chart restyling.
//
// tracebi.configureChart(id, patch) deep-merges a patch into the ECharts
// option the runtime built for that figure. It can restyle anything
// (colours, gradients, smoothing, labels) but never re-source: every
// series keeps the data read from the embedded, fingerprinted binding.
//
// Library: Apache ECharts (Apache-2.0), inlined because report.json lists
// "libs": ["echarts"]. Gradients use ECharts' plain-object form, so no
// ECharts API is called directly.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  var tb = window.tracebi;

  function vertical(top, bottom) {
    return {
      type: "linear", x: 0, y: 0, x2: 0, y2: 1,
      colorStops: [{ offset: 0, color: top }, { offset: 1, color: bottom }],
    };
  }

  // Bars: an indigo gradient, lighter at the top.
  tb.configureChart("chart-sector", {
    series: [{ itemStyle: { color: vertical("#5c7cfa", "#3b5bdb") } }],
  });

  // Doughnut: this report's palette, with a rounded, gapped ring.
  tb.configureChart("fig-chart_fund", {
    color: ["#3b5bdb", "#0f9d8a", "#f08c00"],
    series: [{ itemStyle: { borderRadius: 6, borderColor: "#fff", borderWidth: 3 } }],
  });

  // Cumulative line: smoothed, teal, with a fading area beneath it.
  tb.configureChart("chart-conc", {
    series: [{
      smooth: true,
      lineStyle: { width: 3, color: "#0f9d8a" },
      itemStyle: { color: "#0f9d8a" },
      areaStyle: { color: vertical("rgba(15,157,138,.28)", "rgba(15,157,138,0)") },
    }],
  });
})();
