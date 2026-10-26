# Pipeline files (YAML)

A pipeline file names the transform to run, the models it feeds, the reports
to rebuild, and when.

```yaml
# pipelines/portfolio_model.yaml
name: portfolio_model          # equals the file name
description: Rebuild the portfolio warehouse, then its reports.
transform: holdings_transform  # transforms/holdings_transform.sql (or .py, .ipynb)
models: [portfolio_model]
reports: all
schedule: null
```

- `tracebi run-pipeline <name>` and **Refresh data** in the app run the
  transform fresh (as `tracebi run-transform` does), then rebuild the reports,
  recording each run.
- It compiles to the same runner as `model_pipeline(...)` in Python.
- `tracebi new-pipeline "Sales ETL"` writes a commented starter; `--python`
  writes `pipelines/<name>.py`.
- `.yml` works too. The file loads with `yaml.safe_load` rules, a repeated key
  is an error, and unknown keys are refused.

## Keys

| Key | Meaning |
|---|---|
| `name` | Required. Letters, digits and underscores; equals the file name. |
| `transform` | Required. The name of `transforms/<x>.sql`, `.py` or `.ipynb` (an extension is allowed, a folder is not). The step runs it, then the `<x>.contract.yaml` beside it, and records the form (`sql`, `python`, `notebook`), shown by `tracebi run-pipeline <name> --status` and the transform's page in the app (Data › Transforms). See [[transform-sql]]. |
| `models` | Required. The models the transform feeds. |
| `reports` | `all` (default): every report in `reports/<model>/` of each model. Or a list of names (`<model>/<report>`). |
| `schedule` | A five-field cron expression, or `null` for on demand only. A scheduled run does the whole chain: transform, then reports. |
| `description` | Free text. |

## One file per name

| Files present | Result |
|---|---|
| `x.py` and `x.yaml` | The Python file wins; the YAML is refused and reported in `/api/discovery`. |
| `x.yaml` and `x.yml` | Both are refused. |

## Convert a Python pipeline

```bash
tracebi migrate pipeline pipelines/x.py [--write]
```

Writes the YAML for a runner built by `model_pipeline(...)` and leaves the
`.py` in place. It refuses, with the reason, a runner that registers anything
else (medallion layers, custom steps), keeps its history at a custom
`db_url`, builds reports from another folder, or is named differently from its
file.
