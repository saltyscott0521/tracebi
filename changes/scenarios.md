### Added — scenarios: the reader's what-if, computed in the browser

- A `data-tb-scenario` block holds `data-tb-input` fields, `data-tb-preset`
  pickers (`data-tb-key`, `data-tb-fill`, `data-tb-default`) that fill them
  from a stamped row, and `data-tb-calc` outputs with a closed formula
  (`+ - * / ^`, `pmt`, `min`, `max`, `round`, `abs`) evaluated in the
  browser without `eval`. The build checks every formula and preset. A
  scenario is never a figure: the runtime labels it as computed from the
  reader's inputs and not part of the receipt, and the manifest records its
  declaration under `scenarios` with `verifiable: false`.
- `reports/housing/affordability` in the reference project (and so the demo): mortgage rates, median home prices and
  median household income every year since 1971, the payment they add up
  to, line charts, and a then-vs-now scenario.

### Fixed — dotted year columns keep their digits

- A column like `dim_year.year` is treated as a year, so it reads `1985`,
  not `1,985`, in value figures, tables and derived formats.
