### Added — Draft a model from a dbt manifest

- `tracebi import dbt <path>` reads a dbt project's `target/manifest.json`
  (or a path to the file itself) and writes `models/<name>.py`. It does
  not run dbt and does not load `.env`.
- `--connection <name>` wires the `models/_connections/<name>.py` module
  from `tracebi connect`. `--schema` keeps one schema. `--name` sets the
  model file; the default is the dbt project name.
- Relationships and measures are `# DRAFT: review` comments. Foreign keys
  are not invented. An existing model file is kept unless `--force`.
