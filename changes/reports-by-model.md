### Changed

- **Reports are organised by model**: a report's folder is its model's name. The reference project's reports moved to `reports/portfolio_model/` (`portfolio_dashboard`, `portfolio_book`, `portfolio_overview`, `portfolio_concentration`, `portfolio_showcase`) and `reports/housing_model/affordability`; the demo app's to `wealth_model/` and `sales_model/`. **Report names, share links and `output/` paths change with them** (`showcase/portfolio_showcase` is now `portfolio_model/portfolio_showcase`).
- Every model has a pipeline. The reference project gets `pipelines/portfolio_model.py` and `pipelines/housing_model.py`; the demo app's `wealth_model` gets a medallion pipeline beside the sales one.

### Added

- `model_pipeline(model, transform=...)`: one line gives a model a pipeline with a **transform** step (rebuild its warehouse) and a **build** step (rebuild every report in `reports/<model>/`, each with its receipt). The build step refuses to run after a transform that failed. See `docs/concepts/models-and-connectors.md`.
- `PipelineRunner.register_step(name, fn, ...)`: register any function as a pipeline step, with the same run history, dependency order and schedule as a layer. A step that ends with `sys.exit()` is a failed step, not a dead runner.
- `DataModel.disconnect()`: release a model's warehouse handle before rewriting the data.
