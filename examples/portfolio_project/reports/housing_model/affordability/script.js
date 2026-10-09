/* The charts are declared in template.html (data-tb-* attributes, palette,
 * marks); this file only compares two stamped numbers. */
tracebi.ready(function () {
  /* Mark the row whose stamped share is larger as the harder one: a
   * comparison of two numbers already on the page, never a new one. */
  function stamped(el) {
    var row = tracebi.data(el.getAttribute("data-tb-binding"))[0];
    return row ? Number(row[el.getAttribute("data-tb-cell")]) : NaN;
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-mp-vs]"), function (card) {
    var a = card.querySelector('[data-tb-vs="a"] strong');
    var b = card.querySelector('[data-tb-vs="b"] strong');
    var va = stamped(a), vb = stamped(b);
    if (!isFinite(va) || !isFinite(vb) || va === vb) return;
    (va > vb ? a : b).parentNode.classList.add("mp-harder");
  });
});
