// Draw the issuer table (the sector chart and the sector table are declared in
// template.html and drawn by the runtime). tracebi.draw hands this function
// the top_issuers binding's rows as the page's selection leaves them: the
// stamped rows as built, the query re-run over the embedded data after a
// sector, a fund or a bar is picked. The query already orders and limits
// them (largest ten by fair value), so the script only lays them out; it
// cannot add a number. Values reach the DOM only through textContent, never
// innerHTML, so a hostile issuer name cannot execute (architecture §5).
(function () {
  function money(v) {
    return "$" + Math.round(Number(v)).toLocaleString();
  }

  function cell(tag, text, numeric) {
    var td = document.createElement(tag);
    if (numeric) td.className = "tb-num";
    td.textContent = text;
    return td;
  }

  tracebi.draw("top-issuers", function (surface, rows) {
    var table = document.createElement("table");
    table.className = "tb-table";
    var head = document.createElement("tr");
    head.appendChild(cell("th", "Issuer"));
    head.appendChild(cell("th", "Fair value", true));
    head.appendChild(cell("th", "Positions", true));
    table.appendChild(document.createElement("thead")).appendChild(head);
    var tbody = table.appendChild(document.createElement("tbody"));
    rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.appendChild(cell("td", r["dim_issuer.issuer"]));
      tr.appendChild(cell("td", money(r.fair_value), true));
      tr.appendChild(cell("td", Number(r.positions).toLocaleString(), true));
      tbody.appendChild(tr);
    });
    surface.appendChild(table);
  });

  // A sentence that compares (the lowest, the largest, of the funds in view)
  // needs more than one thing in view. Each data-book-when="<what><op><n>"
  // variant shows only while its count holds; the counts are query results
  // the page already has: the sector table's rows, the positions count, and
  // the in_view binding's distinct funds and issuers. As built (no
  // selection, tracebi.result is null) the template's own visible variants
  // stand.
  var COUNTED = { positions: "val-positions", funds: "val-funds-in-view",
                  issuers: "val-issuers-in-view" };

  function counts() {
    var tb = window.tracebi, out = {};
    var sectors = tb.result("tbl-sector-marks");
    if (sectors) out.sectors = sectors.rows.length;
    Object.keys(COUNTED).forEach(function (name) {
      var res = tb.result(COUNTED[name]);
      if (res) out[name] = res.rows.length ? Number(res.rows[0][res.cols.indexOf(name)]) || 0 : 0;
    });
    return out;
  }

  function showVariants() {
    var n = counts();
    document.querySelectorAll("[data-book-when]").forEach(function (el) {
      var m = /^(\w+)([<=>])(\d+)$/.exec(el.getAttribute("data-book-when"));
      if (!m || !(m[1] in n)) {
        el.hidden = el.hasAttribute("data-book-hidden");
        return;
      }
      var v = n[m[1]], k = Number(m[3]);
      el.hidden = !(m[2] === ">" ? v > k : m[2] === "<" ? v < k : v === k);
    });
  }

  // Remember which variants the template hides, for the return to as built.
  document.querySelectorAll("[data-book-when][hidden]").forEach(function (el) {
    el.setAttribute("data-book-hidden", "");
  });
  tracebi.onSelection(showVariants);
  showVariants();
})();
