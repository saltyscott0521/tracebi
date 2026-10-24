/* The charts are declared in template.html (data-tb-* attributes, palette,
 * marks); this file only compares numbers already on the page, and picks
 * which of two worded forms to show. */
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
  /* How many years are in view is itself a figure (#years-in-view, the
   * "span" binding's count). With one, a comparison would set a year
   * against itself, so the page shows each comparison's one-year form
   * (data-mp-one) instead of its two-year form (data-mp-many). */
  function update() {
    var one = current(document.getElementById("years-in-view")) === 1;
    /* The hardest and easiest buyers count only buyers whose ten years are
     * all measured; with none in view (every buyer projected), the page says
     * so instead of comparing against a dash. */
    var measured = isFinite(current(document.getElementById("ten-worst")));
    function show(sel, on) {
      Array.prototype.forEach.call(document.querySelectorAll(sel), function (el) {
        el.hidden = !on(el);
      });
    }
    show("[data-mp-one]", function () { return one; });
    show("[data-mp-unmeasured]", function () { return !measured; });
    show("[data-mp-many], [data-mp-measured]", function (el) {
      return !(el.hasAttribute("data-mp-many") && one) &&
             !(el.hasAttribute("data-mp-measured") && !measured);
    });
    /* Mark the row whose share is larger as the harder one: a comparison of
     * two numbers the page shows, never a new one. Again on every selection,
     * so the mark follows the numbers it compares; none with one year. The
     * mark is the system's own: the value in --tb-bad (.tb-bad) and the
     * row's word shown. */
    function mark(strong, on) {
      strong.classList.toggle("tb-bad", on);
      strong.closest("tr").querySelector("[data-mp-harder]").hidden = !on;
    }
    Array.prototype.forEach.call(document.querySelectorAll("[data-mp-vs]"), function (card) {
      var a = card.querySelector('[data-tb-vs="a"] strong');
      var b = card.querySelector('[data-tb-vs="b"] strong');
      mark(a, false);
      mark(b, false);
      if (one) return;
      var va = current(a), vb = current(b);
      if (!isFinite(va) || !isFinite(vb) || va === vb) return;
      mark(va > vb ? a : b, true);
    });
  }
  update();
  tracebi.onSelection(update);
});
