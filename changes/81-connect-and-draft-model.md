### Added — Connect your own warehouse and draft a model

- `tracebi connect` tests a Postgres, Snowflake, BigQuery, or DuckDB
  warehouse, writes the secret to `.env`, and writes
  `models/_connections/<name>.py`. That module calls `load_dotenv()` and
  reads `os.environ`; TraceBi still does not load `.env`.
- `tracebi new-model "<Name>" --from <connection> --tables a,b,c` drafts a
  star schema from column metadata only. Lines marked `# DRAFT: review`
  are guesses to edit and approve.
