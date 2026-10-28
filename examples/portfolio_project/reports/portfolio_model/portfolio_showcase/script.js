// ─────────────────────────────────────────────────────────────────────────
// Holdings treemap: a figure the declared chart types cannot draw, in d3.
//
// tracebi.draw(id, fn) calls fn(surface, rows, theme) once the data is
// loaded, and again whenever the figure's rows change (the sector filter,
// the search) or its width does. rows are the stamped holdings_detail rows
// as the page's filters leave them; theme holds the page's tokens, so the
// figure follows style.css. Drawing never computes a new number: every
// size and label is a row's own fair_value.
//
// Colour carries nothing here. Sectors are labelled groups separated by
// gaps, so no reader has to tell two hues apart. Click a sector's label to
// select it on the page; click again to clear. tracebi.onSelection keeps
// the figure in step with every other way the selection changes (a filter,
// a bar, the selection bar), so a click adds to the reader's selection
// rather than replacing it.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  var tb = window.tracebi;
  var SECTOR = "dim_issuer.sector", ISSUER = "dim_issuer.issuer";
  var money = function (v) { return "$" + tb.fmt(v, "compact"); };
  var state = {}; // the page's selection, as tracebi.onSelection last gave it
  tb.onSelection(function (change) { state = change.selection; });

  // A label that does not fit its box is left out, never cut: the
  // tooltip and the table below carry every name and value.
  function fit(text, room) {
    text.each(function () {
      if (this.getComputedTextLength() > room) this.remove();
    });
  }

  tb.draw("fig-treemap", function (surface, rows, theme) {
    var d3 = window.d3;
    var width = surface.clientWidth, height = 340, head = 18;
    var bySector = d3.groups(rows, function (r) { return r[SECTOR]; });
    var root = d3.hierarchy({ children: bySector.map(function (g) {
      return { name: g[0], children: g[1] };
    }) }).sum(function (d) { return d.fair_value || 0; })
      .sort(function (a, b) { return b.value - a.value; });
    d3.treemap().size([width, height]).paddingOuter(2).paddingTop(head)
      .paddingInner(2).round(true)(root);

    var svg = d3.select(surface).append("svg")
      .attr("width", width).attr("height", height)
      .attr("role", "img").style("font-family", theme.font);
    // The system's chart readout (.tb-chart-tip), so the treemap's tooltip
    // reads like every other chart's.
    var tip = d3.select(surface).append("div").attr("class", "tb-chart-tip").attr("hidden", "");

    var groups = svg.selectAll("g.sector").data(root.children || []).join("g")
      .attr("class", "sector");
    groups.append("text").attr("class", "sc-sector")
      .attr("x", function (d) { return d.x0 + 4; })
      .attr("y", function (d) { return d.y0 + 13; })
      .attr("fill", theme.ink).attr("font-weight", 600).attr("font-size", 12)
      .style("cursor", "pointer")
      .text(function (d) { return d.data.name + " · " + money(d.value); })
      .call(function (t) { t.each(function (d) { fit(d3.select(this), d.x1 - d.x0 - 8); }); })
      .on("click", function (event, d) {
        var next = JSON.parse(JSON.stringify(state));
        var picked = next[SECTOR] || [];
        if (picked.length === 1 && picked[0] === d.data.name) delete next[SECTOR];
        else next[SECTOR] = [d.data.name];
        tb.setSelection(next);
      });

    var cells = svg.selectAll("g.cell").data(root.leaves()).join("g")
      .attr("class", "cell")
      .attr("transform", function (d) { return "translate(" + d.x0 + "," + d.y0 + ")"; });
    cells.append("rect")
      .attr("width", function (d) { return d.x1 - d.x0; })
      .attr("height", function (d) { return d.y1 - d.y0; })
      .attr("rx", 2).attr("fill", theme.accent).attr("fill-opacity", 0.85)
      .on("pointermove", function (event, d) {
        d3.select(this).attr("fill-opacity", 1);
        var at = d3.pointer(event, surface);
        tip.attr("hidden", null)
          .style("left", Math.min(at[0] + 12, width - 180) + "px")
          .style("top", (at[1] + 12) + "px");
        tip.selectAll("*").remove();
        tip.append("div").attr("class", "tb-chart-tip-title").text(d.data[ISSUER]);
        tip.append("div").text(d.data[SECTOR]);
        var row = tip.append("div").attr("class", "tb-chart-tip-row");
        row.append("strong").text(money(d.data.fair_value));
        row.append("span").text("fair value · mark " + (d.data.mark * 100).toFixed(1) + "%");
      })
      .on("pointerleave", function () {
        d3.select(this).attr("fill-opacity", 0.85);
        tip.attr("hidden", "");
      });
    // Direct labels only where they fit; the tooltip and the table below
    // carry every value regardless.
    var labelled = cells.filter(function (d) { return d.x1 - d.x0 > 48 && d.y1 - d.y0 > 36; });
    labelled.append("text").attr("x", 6).attr("y", 16)
      .attr("fill", theme.bg).attr("font-size", 12).attr("pointer-events", "none")
      .text(function (d) { return d.data[ISSUER]; })
      .each(function (d) { fit(d3.select(this), d.x1 - d.x0 - 12); });
    labelled.append("text").attr("x", 6).attr("y", 31)
      .attr("fill", theme.bg).attr("fill-opacity", 0.85).attr("font-size", 12)
      .attr("pointer-events", "none")
      .text(function (d) { return money(d.data.fair_value); });
  });
})();

// ─────────────────────────────────────────────────────────────────────────
// Every chart is drawn by Apache ECharts. tracebi.configureChart(id, patch)
// deep-merges a raw ECharts option into one: here a zoom slider under the
// monthly flows. It restyles and never re-sources: the series keep the data
// built from the stamped rows.
// ─────────────────────────────────────────────────────────────────────────
window.tracebi.configureChart("chart-flows-month", {
  dataZoom: [{ type: "slider", height: 18, bottom: 6, brushSelect: false }],
  grid: [{ bottom: 44 }]
});
