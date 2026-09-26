/* Name the two lines in the legend. configureChart restyles a chart; the
 * series data still comes only from the stamped bytes. */
tracebi.configureChart("chart-price-income", {
  series: [{ name: "Median home price" }, { name: "Median household income" }]
});
