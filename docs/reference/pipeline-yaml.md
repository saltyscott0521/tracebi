# Pipeline files (YAML)

**A pipeline as data: which transform to run, which models it feeds, which
reports to rebuild, and when. Transforms stay Python; a pipeline only names one.**

`pipelines/<name>.yaml` (or `.yml`) compiles to the same runner as
`model_pipeline(...)`: `tracebi run-pipeline <name>` and the app's Refresh page
run the transform fresh (`tracebi run-transform`), then rebuild the reports,
recording each run. `tracebi new-pipeline "Sales ETL"` writes a commented
starter; `--python` writes the old `pipelines/<name>.py`.

The file loads with `yaml.safe_load` semantics, a repeated key is an error,
and the schema is closed.

---

## Example

```yaml
# pipelines/portfolio_model.yaml
name: portfolio_model          # equals the file name
description: Rebuild the portfolio warehouse, then its reports.
transform: holdings_transform  # transforms/holdings_transform.py (or .ipynb)
models: [portfolio_model]
reports: all
schedule: null
```

---

## Keys

| key | |
|---|---|
| `name` | required; letters, digits, underscore; equals the file name |
| `transform` | required; a bare name of `transforms/<x>.py` or `.ipynb` (an extension is allowed, a folder is not) |
| `models` | required; a list of model names the transform feeds |
| `reports` | `all` (default): every report in `reports/<model>/` of each model; or a list of report names (`<model>/<report>`) |
| `schedule` | a 5-field cron expression, or `null` (on demand only). When the scheduler fires it, the whole chain runs: transform, then reports |
| `description` | free text |

## One file per name

A pipeline is one file. `x.py` beside `x.yaml` -> the Python file wins and the
YAML is refused (reported in `/api/discovery`); `x.yaml` and `x.yml` together
are both refused.

## Migrating

`tracebi migrate pipeline pipelines/x.py [--write]` writes the YAML for a
runner built by `model_pipeline(...)` and leaves the `.py` in place. It refuses,
with the reason, a runner that registers anything else (medallion layers,
custom steps), keeps its history at a custom `db_url`, builds reports from
another folder, or is named differently from its file.
