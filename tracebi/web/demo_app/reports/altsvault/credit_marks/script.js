/* Dark-ground chart theming.
 *
 * The runtime reads --tb-chart-N for series colours but does not derive
 * ECharts' TEXT colours from --tb-ink, so on a dark ground axis labels and
 * legends render in ECharts' near-black default and disappear. configureChart
 * is the sanctioned escape valve: it deep-merges a patch into the built option
 * and then re-sources every series from the stamped bytes — restyle, never
 * re-source. No number is touched here.
 *
 * Tokens are read from the live stylesheet rather than re-typed, so this can
 * never drift out of sync with style.css. */
(function () {
  var css = getComputedStyle(document.documentElement);
  function token(name, fallback) {
    var v = (css.getPropertyValue(name) || "").trim();
    return v || fallback;
  }

  var INK     = token("--tb-ink", "#D7DDD8");
  var MUTED   = token("--tb-muted", "#8C9C92");
  var RULE    = token("--tb-rule", "#233B30");
  var SURFACE = token("--surface", "#14271D");

  var axis = {
    axisLabel: { color: MUTED },
    axisLine:  { lineStyle: { color: RULE } },
    axisTick:  { lineStyle: { color: RULE } },
    splitLine: { lineStyle: { color: RULE } }
  };

  var darkTheme = {
    textStyle: { color: INK },
    xAxis: axis,
    yAxis: axis,
    legend: { textStyle: { color: MUTED } },
    tooltip: {
      backgroundColor: SURFACE,
      borderColor: RULE,
      textStyle: { color: INK }
    }
  };

  ["chart-by-band", "chart-by-structure", "chart-by-crowding", "chart-staleness"]
    .forEach(function (id) { tracebi.configureChart(id, darkTheme); });
})();
