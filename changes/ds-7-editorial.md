### Changed — the editorial on the system

- `.tb-article` is a reading column on a sheet: the prose (and the hero's
  lines, the pull-stat and the footer) in one serif column of 68 characters
  (`--tb-measure`), centred; figures, tables and the KPI strip take the
  sheet's full width (62rem), so a strip of three or four cards never
  cramps. The headline starts on the column's edge and may run past it.
- The hero is the project's accent, flat. On a dark ground it is a deep band
  of the accent with the page's own ink (kicker, standfirst and meta above
  8:1), not a pale slab. The sheet no longer rises in; nothing animates.
- One type scale: body `--tb-text-lg`, lede and standfirst `--tb-text-xl`,
  section heads `--tb-text-xl` in the sans with a 3px accent bar. A number in
  the prose (and in the headline) is weight 600 in the prose's own ink.
  Controls in the prose (a download button) are the sans.
- On a phone, an article table wider than the screen scrolls inside its own
  frame instead of being cut off at the sheet's edge, and its cells do not
  wrap.
- `portfolio_book`'s `style.css` is the accent pairs only (it also used the
  wrong attribute for its dark accent); its issuer table, still a custom
  figure drawn by `script.js`, now uses `.tb-table` / `.tb-num` and so
  follows `--tb-cell-pad`.
