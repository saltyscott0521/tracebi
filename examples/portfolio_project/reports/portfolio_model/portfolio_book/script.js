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
})();
