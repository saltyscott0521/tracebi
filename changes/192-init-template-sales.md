### Added — `tracebi init --template sales-pipeline`

- `tracebi init <project> --template sales-pipeline` (also `sales_pipeline`)
  scaffolds a working sales pipeline mini-project: a small opportunities
  sample, a sink contract, `models/sales_pipeline_model.py` (stage, rep,
  and region; open pipeline value; win rate as won deals over closed
  deals, a ratio of totals), and two reports
  (`sales_pipeline_model/pipeline_dashboard`,
  `sales_pipeline_model/rep_scorecard`). Unknown names are refused with
  the known list. `tracebi init` with no flag is unchanged.
- `tracebi context` lists the starter under `templates`, next to
  saas-metrics.
