### Changed — the demo reports, upgraded

- Reference project: `portfolio_model/portfolio_desk` is new, the book as an
  app (`app.jsx`) with Overview, Holdings and Funds views. `portfolio_book` is
  an editorial report with its own house CSS; `portfolio_overview` and
  `portfolio_concentration` lead with the answer and a KPI strip ("The five
  largest issuers hold 55.6% of the book" is the fifth issuer's row, picked by
  `having`).
- `tracebi init --template saas-metrics`: the cohort brief reads as an
  editorial brief, cohorts in signup order; the MRR dashboard headline is the
  finding. The reference project's copies match the template again.
- `tracebi init --template sales-pipeline`: title blocks with the build time;
  no search box on three-row panels.

### Added

- `currency_compact`, a named number format: `$285.9M`, `-$6.3M`.

### Fixed

- The server-rendered `compact` format now matches the browser's byte for byte
  (it rounded differently: `0.005` was "0.01" before hydration, "0" after).
- On a phone, a narrow table inside a card spans the card again; a wide one
  still scrolls inside it.
