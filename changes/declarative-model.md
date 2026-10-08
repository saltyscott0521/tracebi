### Added — a model as `models/<name>.json`

- A model can be written as JSON instead of Python, mirroring the `DataModel`
  builder calls (connectors, tables, relationships, dimensions, facts,
  measures). The schema is closed and carries no credentials: a connector is a
  project-relative DuckDB file or a `models/_connections/<name>.py` reference.
- Discovered beside `models/*.py` at startup and by live discovery, validated
  structurally, loaded lazily. A bad file shows as failed in `/api/discovery`
  with its reason; if `x.py` and `x.json` both exist the Python file wins.
- `tracebi.model.model_spec`: `load_model_spec`, `validate_model_spec`,
  `validate_model_file`. Reference: `docs/reference/model-json.md`.
