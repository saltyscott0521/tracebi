(function () {
  // Minimal RFC-4180 CSV parser — handles quoted fields and commas inside them.
  function parseCsv(text) {
    var rows = [], row = [], field = "", inQ = false, i = 0, c;
    while (i < text.length) {
      c = text[i];
      if (inQ) {
        if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else { inQ = false; } }
        else { field += c; }
      } else if (c === '"') { inQ = true; }
      else if (c === ',') { row.push(field); field = ""; }
      else if (c === '\n') { row.push(field); rows.push(row); row = []; field = ""; }
      else if (c !== '\r') { field += c; }
      i++;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    var head = rows.shift() || [];
    return rows.filter(function (r) { return r.length === head.length; })
      .map(function (r) { var o = {}; head.forEach(function (h, j) { o[h] = r[j]; }); return o; });
  }

  // Draw from the python-derived output block — the same fingerprinted `csv`
  // bytes the receipt covers, parsed with JSON.parse and rendered with DOM
  // APIs only (never innerHTML), so a hostile cell value cannot execute.
  var el = document.getElementById("tracebi-data-concentration");
  if (!el) return;
  var rows = parseCsv(JSON.parse(el.textContent).csv || "");
  var table = document.getElementById("concentration");
  if (!rows.length || !table) return;
  var cols = Object.keys(rows[0]);
  var htr = document.createElement("tr");
  cols.forEach(function (c) {
    var th = document.createElement("th");
    th.textContent = c;
    htr.appendChild(th);
  });
  table.querySelector("thead").appendChild(htr);
  var tbody = table.querySelector("tbody");
  rows.forEach(function (row) {
    var tr = document.createElement("tr");
    cols.forEach(function (c) {
      var td = document.createElement("td");
      var v = row[c];
      if (v !== "" && v != null && !isNaN(Number(v))) {
        td.className = "num";
        td.textContent = Number(v).toLocaleString();
      } else {
        td.textContent = v == null ? "" : String(v);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
})();
