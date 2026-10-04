### Changed — one sales model; SaaS metrics in the demo; every model named `<thing>_model`

- The demo had two sales models over the same data: `SalesModel` (typed-in
  tables in memory) and `SalesPipelineModel` (the same rows after a round trip
  through the sales pipeline). They returned identical figures. There is now
  one, `sales_model`, a star schema over the pipeline's cleaned tables; both
  sales reports and the `sales` pipeline belong to it. Its customer attribute
  is `segment` (was `tier`), and the unused `trend` table is gone.
- Every model is named like its file: `sales_model`, `wealth_model`,
  `housing_model`, `portfolio_model`, `saas_model` (the demo's were
  `SalesModel`, `WealthModel`, `SalesPipelineModel`).
- The reference project (and so the live demo) gains `saas_model`: the
  `init --template saas-metrics` project's transform, model, two reports
  (MRR dashboard, cohort brief) and a pipeline, sinking into the shared
  warehouse. `run_workflow.py` runs its transform.
