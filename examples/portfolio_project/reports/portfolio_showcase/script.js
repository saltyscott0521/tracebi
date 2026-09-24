// ─────────────────────────────────────────────────────────────────────────
// Portfolio Showcase: chart restyling.
//
// tracebi.configureChart(id, patch) deep-merges a patch into the ECharts
// option the runtime built for that figure. It can restyle anything
// (colours, labels, spacing) but never re-source: every series keeps the
// data read from the embedded, fingerprinted binding.
//
// What it is used for here is deliberately small. Gradient bars and a
// smoothed, filled cumulative line used to live in this file; they were
// decoration, and smoothing a cumulative across categories draws values that
// do not exist (`tracebi knowledge design-honest-axes`). Restyle to clarify,
// never to decorate.
//
// Library: Apache ECharts (Apache-2.0), inlined because report.json lists
// "libs": ["echarts"].
// ─────────────────────────────────────────────────────────────────────────
(function () {
  var tb = window.tracebi;

  // Fund mix: this report's palette, in the same order as everywhere else
  // on the page, so each fund keeps its colour.
  tb.configureChart("fig-chart_fund", {
    color: ["#3b5bdb", "#0f9d8a", "#f08c00"],
    series: [{ itemStyle: { borderColor: "#fff", borderWidth: 2 } }],
  });

  // Cumulative share: straight segments between the points it actually has,
  // with the points shown — each is one sector added.
  tb.configureChart("chart-conc", {
    series: [{ smooth: false, showSymbol: true, lineStyle: { width: 2 } }],
  });
})();
