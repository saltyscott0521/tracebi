### Added — design policies baked into the shipped stylesheet and scaffolds

- Five more `design-` lessons: hierarchy and emphasis, grid and spacing, tables
  that read, words on the page, and theming with tokens. Now 18 in total, all
  named in the `tracebi-designer` skill and both agent guides. Drawn from the
  Urban Institute's chart style guide and common UI patterns for hierarchy,
  grids, tables and design tokens, restated in TraceBi's terms.
- `tracebi.css` now sets these defaults for every report:
  - `.tb-lede`, for the page's answer sentence under the title.
  - `.tb-kpi-context`, for a KPI's comparison line.
  - `.tb-good` / `.tb-bad`, with `--tb-good` / `--tb-bad` tokens (both clear
    4.5:1 contrast).
  - A `--tb-cell-pad` table-density token.
  - Visible keyboard focus.
  - Balanced headings and a 75-character line length.
  - Tabular KPI digits, and numbers that never wrap.
  - The receipt drawer's slide-in stops under `prefers-reduced-motion`.
- The pages from `tracebi init` and `tracebi new-report` open with an
  answer-first lede bound to a new one-row `top_region` / `top` binding. They
  also give the KPI a context line, and put the search and filter controls
  inside real `<label>`s, with search first.

### Changed

- A value figure with no `data-tb-format` is now formatted the way a table
  column is: the model's declared format first, then the shape default. So an
  unformatted KPI reads `4,846.10`, not `4846.1`. The server render and the
  browser runtime share this rule. Presentation only; no fingerprint moves.
