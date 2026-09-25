// Presentation only: list the largest issuer at the top of the bar chart.
// configureChart restyles a figure; its data still comes from the stamped
// binding.
window.tracebi.configureChart("fig-share_chart", {
  yAxis: { inverse: true },
  xAxis: { splitNumber: 4 },
});
window.tracebi.configureChart("fig-curve_chart", {
  xAxis: { name: "Issuers, by rank", nameLocation: "middle", nameGap: 28 },
});
