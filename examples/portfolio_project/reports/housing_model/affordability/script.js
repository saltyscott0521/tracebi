/* The charts are declared in template.html (data-tb-* attributes, palette,
 * marks); this file only compares two numbers already on the page. */
tracebi.ready(function () {
  /* A figure's current number: the page engine's answer under the reader's
   * selection when there is one (tracebi.result), else the stamped row. */
  function current(el) {
    var res = tracebi.result(el.id);
    var cell = el.getAttribute("data-tb-cell");
    if (res && res.cols) {
      var i = res.cols.indexOf(cell);
      return res.rows.length && i !== -1 ? Number(res.rows[0][i]) : NaN;
    }
    var row = tracebi.data(el.getAttribute("data-tb-binding"))[0];
    return row ? Number(row[cell]) : NaN;
  }
  /* Mark the row whose share is larger as the harder one: a comparison of
   * two numbers the page shows, never a new one. Again on every selection,
   * so the mark follows the numbers it compares. */
  function mark() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-mp-vs]"), function (card) {
      var a = card.querySelector('[data-tb-vs="a"] strong');
      var b = card.querySelector('[data-tb-vs="b"] strong');
      a.parentNode.classList.remove("mp-harder");
      b.parentNode.classList.remove("mp-harder");
      var va = current(a), vb = current(b);
      if (!isFinite(va) || !isFinite(vb) || va === vb) return;
      (va > vb ? a : b).parentNode.classList.add("mp-harder");
    });
  }
  mark();
  tracebi.onSelection(mark);
});
