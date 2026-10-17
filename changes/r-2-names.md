### Added — names, not identifiers

- A model may declare a `label`: what people read where it is listed
  (`label: Direct Lending Portfolio` in YAML or JSON, `DataModel(name,
  label=)` in Python). Unset, it is the name title-cased: the last `/`
  segment split at `_`, `-` and camelCase, each word capitalised, nothing
  dropped (`portfolio_model` reads `Portfolio Model`, `WealthModel` reads
  `Wealth Model`). `name` stays the identifier queries, bindings and commands
  take. `tracebi migrate model` carries a declared label into the YAML.
- `GET /api/models`, `GET /api/models/{name}`, `tracebi context --model` and
  the gateway's `list_models` / `describe_model` carry `label`.
- `GET /api/reports` carries `display_name`: `report.json`'s `name`, else the
  identifier title-cased. `name` stays the path. `GET /api/runs` rows carry
  `display_name` beside `target` (a report's name, a published model's label,
  `null` for a pipeline run), and every `report` entry of `GET /api/desk`
  carries it too.
- `tracebi list-models` prints `Label (identifier)  models/<file>`.
- The reference project's, the init templates' and the demo app's models have
  real labels; `portfolio_overview` is named `Portfolio Overview`.
  `tracebi new-model` writes the title typed as the label; `new-report` and
  `new-dashboard` already wrote it as the report's `name`.
