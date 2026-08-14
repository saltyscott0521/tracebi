// Draw the whole page from the embedded, FINGERPRINTED data. Each data block is
// a <script type="application/json"> carrying the canonical triple — including
// the exact `csv` the receipt hashes. The page parses that same csv, so a
// displayed number cannot diverge from a verified one. Values reach the DOM only
// through textContent, never innerHTML, so a hostile issuer name cannot execute
// (architecture §5).
(function () {
  // Minimal RFC-4180 CSV parser: handles quoted fields, escaped "" quotes, and
  // commas inside quotes (issuer names like "Acme Industrial Holdings, LLC").
  function parseCsv(text) {
    var rows = [], row = [], field = "", inQ = false, i = 0, c;
    while (i < text.length) {
      c = text[i];
      if (inQ) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; } else { inQ = false; }
        } else { field += c; }
      } else if (c === '"') {
        inQ = true;
      } else if (c === ',') {
        row.push(field); field = "";
      } else if (c === '\n') {
        row.push(field); rows.push(row); row = []; field = "";
      } else if (c !== '\r') {
        field += c;
      }
      i++;
    }
    if (field !== "" || row.length) { row.push(field); rows.push(row); }
    var head = rows.shift() || [];
    return rows
      .filter(function (r) { return r.length === head.length; })
      .map(function (r) {
        var o = {};
        head.forEach(function (h, j) { o[h] = r[j]; });
        return o;
      });
  }

  function read(id) {
    var el = document.getElementById(id);
    if (!el) return [];
    var block = JSON.parse(el.textContent);
    return parseCsv(block.csv);
  }

  function money(v) {
    return "$" + Math.round(Number(v)).toLocaleString();
  }

  // Fair value by sector → horizontal bars.
  var sectors = read("tracebi-data-by_sector");
  var host = document.getElementById("by-sector");
  if (host && sectors.length) {
    var max = Math.max.apply(null, sectors.map(function (r) { return Number(r.fair_value); }));
    sectors
      .slice()
      .sort(function (a, b) { return Number(b.fair_value) - Number(a.fair_value); })
      .forEach(function (r) {
        var row = document.createElement("div");
        row.className = "bar-row";

        var label = document.createElement("div");
        label.className = "bar-label";
        label.textContent = r["dim_issuer.sector"];

        var track = document.createElement("div");
        track.className = "bar-track";
        var fill = document.createElement("div");
        fill.className = "bar-fill";
        fill.style.width = (max ? (100 * Number(r.fair_value) / max) : 0) + "%";
        track.appendChild(fill);

        var value = document.createElement("div");
        value.className = "bar-value";
        value.textContent = money(r.fair_value);

        row.appendChild(label);
        row.appendChild(track);
        row.appendChild(value);
        host.appendChild(row);
      });
  }

  // Largest issuer exposures → table, top 10 by fair value.
  var issuers = read("tracebi-data-top_issuers");
  var tbody = document.querySelector("#top-issuers tbody");
  if (tbody && issuers.length) {
    issuers
      .slice()
      .sort(function (a, b) { return Number(b.fair_value) - Number(a.fair_value); })
      .slice(0, 10)
      .forEach(function (r) {
        var tr = document.createElement("tr");

        var name = document.createElement("td");
        name.textContent = r["dim_issuer.issuer"];

        var fv = document.createElement("td");
        fv.className = "num";
        fv.textContent = money(r.fair_value);

        var pos = document.createElement("td");
        pos.className = "num";
        pos.textContent = Number(r.positions).toLocaleString();

        tr.appendChild(name);
        tr.appendChild(fv);
        tr.appendChild(pos);
        tbody.appendChild(tr);
      });
  }
})();
