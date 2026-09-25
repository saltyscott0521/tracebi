### Added — reports can live in folders

- **Reports can live in folders** (epic E6, step 1). Any subfolder of
  `reports/` that isn't itself a report package is a folder, as deep as you
  like, and a report inside one is named by its path, e.g.
  `finance/weekly_summary`. Two folders can each hold a report of the same
  name. The path is the name everywhere:
  - `tracebi report build finance/weekly_summary` writes
    `output/finance/weekly_summary.html`;
  - `tracebi new-report "Finance/Weekly summary"` scaffolds straight into a
    folder;
  - the web API, the agent gateway, schedules, the workbench and the attention
    checks all use it;
  - the Reports page groups reports under collapsible folder headings.

  Top-level reports keep their plain names, so nothing that exists today
  moves. Code modules (`.py`, `.ipynb`) in `reports/` still load only from the
  top level.
- `tracebi/report_paths.py`: the one check for a report name. It accepts
  `finance/weekly` and refuses anything that could leave `reports/` or
  `output/` (`..`, absolute paths, backslashes, hidden or `_` segments). The
  gateway's name guard now uses it, and refuses `../` as before.
- The reference project and the demo app now use folders:
  - `fund_books/`: `portfolio_book`, `portfolio_overview`
  - `risk/`: `portfolio_concentration`
  - `showcase/`: `portfolio_showcase`
  - `wealth/`: `aum_by_branch`, `aum_by_region`
  - `sales/`: `medallion_revenue`

  `portfolio_dashboard.json` stays at the top level as the "start here"
  example. The reference project's README now matches its reports.

### Fixed — specs in folders, receipts in subfolders, download names

- A JSON spec inside a folder failed to register, because its compiled
  package's temporary directory was named with the `/` in the report's path.
- The `.gitignore` rule that keeps build receipts under version control
  (`!output/*.manifest.json`) only matched the top of `output/`, so receipts
  for reports in folders would have gone untracked. It is now `output/**` with
  subfolders and `*.manifest.json` re-included, in the repo, the reference
  project and the `tracebi init` template.
- A downloaded report is named after the report alone
  (`portfolio_showcase.html`), not its folder path.
