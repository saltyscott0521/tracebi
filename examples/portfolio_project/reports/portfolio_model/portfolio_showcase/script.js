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
// Libraries: Apache ECharts (Apache-2.0) and D3 (ISC), inlined because
// report.json lists "libs": ["echarts", "d3"].
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
// filter the page to it; click again to clear.
// ─────────────────────────────────────────────────────────────────────────
(function () {
  var tb = window.tracebi;
  var SECTOR = "dim_issuer.sector", ISSUER = "dim_issuer.issuer";
  var money = function (v) { return "$" + tb.fmt(v, "compact"); };
  var current = null; // the sector this figure filtered to, if any

  // Shorten each label until it fits its box, ending in an ellipsis.
  function fit(text, room) {
    text.each(function () {
      var full = this.textContent, n = full.length;
      while (n > 1 && this.getComputedTextLength() > room) {
        this.textContent = full.slice(0, --n) + "…";
      }
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
    var tip = d3.select(surface).append("div").attr("class", "sc-tip").attr("hidden", "");

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
        current = current === d.data.name ? null : d.data.name;
        var filters = {};
        if (current) filters[SECTOR] = current;
        tb.setSelection(filters);
      });

    var cells = svg.selectAll("g.cell").data(root.leaves()).join("g")
      .attr("class", "cell")
      .attr("transform", function (d) { return "translate(" + d.x0 + "," + d.y0 + ")"; });
    cells.append("rect")
      .attr("width", function (d) { return d.x1 - d.x0; })
      .attr("height", function (d) { return d.y1 - d.y0; })
      .attr("rx", 4).attr("fill", theme.accent).attr("fill-opacity", 0.85)
      .on("pointermove", function (event, d) {
        d3.select(this).attr("fill-opacity", 1);
        var at = d3.pointer(event, surface);
        tip.attr("hidden", null)
          .style("left", Math.min(at[0] + 12, width - 180) + "px")
          .style("top", (at[1] + 12) + "px");
        tip.selectAll("*").remove();
        tip.append("strong").text(money(d.data.fair_value));
        tip.append("span").text(d.data[ISSUER] + " · " + d.data[SECTOR]);
        tip.append("span").text("Mark " + (d.data.mark * 100).toFixed(1) + "% of cost");
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
