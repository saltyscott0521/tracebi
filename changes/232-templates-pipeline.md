### Changed — template starters get a pipeline too

`tracebi init --template saas-metrics` and `--template sales-pipeline` now write
`pipelines/<model>.py` (`model_pipeline`), like plain `init`, so the app's
Refresh page runs the starter's transform and builds its reports, and the
printed steps are `tracebi run-pipeline <model>`, `verify`, `serve` instead of
one `report build` per report.
