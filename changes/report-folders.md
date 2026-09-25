### Added

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
