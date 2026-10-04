### Fixed — every demo model has a pipeline

- The demo's `sales` and `wealth` pipelines were hand-built, so no model was
  stamped on them and Refresh read "Nothing refreshes" for SalesModel,
  SalesPipelineModel and WealthModel. They now say which models they touch
  (`runner.models`): `sales` lands data seeded from SalesModel and builds
  SalesPipelineModel; `wealth` does the same for WealthModel.
- `GET /api/pipelines` returns `models` for each pipeline (the list a runner
  names, else its stamped `model`, else empty). A pipeline can belong to more
  than one model; each model's Refresh page shows all of its pipelines.
- `scripts/ui_audit.py` flags any model nothing refreshes (`model-without-pipeline`).
