### Changed — every report on the current framework

- Dashboards are apps (`app.jsx`): `portfolio_overview` (top tabs) and
  `portfolio_concentration` in the reference project, the saas-metrics
  `mrr_dashboard`, the sales-pipeline `pipeline_dashboard` and
  `rep_scorecard` (tabs by rep and by region), the demo app's custom-styled
  `aum_by_branch` (its own fonts and hero, now on the kit), and the sample
  `tracebi init` writes.
- Editorials have a richer look, in the framework: `<article class="tb-article">`
  is a sheet on the page, opened by a hero band in the accent colour; section
  heads carry an accent mark; figures, tables, KPI strips and pull-stats sit in
  it as framed cards; the first chart series follows the accent. Every
  editorial (`portfolio_book`, `cohort_brief`, and `tracebi new-report`) gets it.
- The template grammar (`data-tb-*`) is taught by the showcase and by
  `tracebi new-report`; the init sample teaches the kit.

### Fixed

- A number typed into an `app.jsx`'s text now fails the build and shows in the
  dev panel's checks, as it does in a `template.html`. An app's prose is
  compiled in the browser, so the page's check never saw it.
