### Changed — a new project follows the app's layout

- `tracebi init` now writes `pipelines/sample_model.py` and puts the sample
  report at `reports/sample_model/sample_dashboard/` (it was
  `reports/sample_dashboard/`). The app's Refresh page runs the sample model's
  transform and builds its report out of the box, instead of saying nothing
  refreshes it. The report is named by its path: `tracebi report build
  sample_model/sample_dashboard`, built to `output/sample_model/`.
- The steps `init` prints are now the repo-init line, `tracebi run-pipeline
  sample_model`, `tracebi verify output/sample_model/sample_dashboard.html.manifest.json`
  and `tracebi serve` — down from six commands. `run-pipeline` runs the
  transform and then builds the model's reports.
- The scaffolded `README.md` and `AGENTS.md`, `tracebi context` (the `pipelines/`
  and `reports/` conventions) and the quickstart describe the same layout:
  a model, its pipeline and its reports share a name.
- A project already created with the old layout keeps working; nothing is moved.
