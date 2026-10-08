### Sources and pipelines are declarative

- Sources: `connections/<name>.yaml` (`TRACEBI_CONNECTIONS_DIR`): a type and its fields, closed schema, any value may be `${ENV_VAR}`; a password, or a URL carrying a credential, must be. Variables are read when the connection is used, so an unset one is an error naming it at that moment, not at discovery. They appear in the Sources page; `/api/connectors` never resolves a credential.
- `tracebi connect` writes the YAML (and the secret to `.env`); `--python` keeps the old `models/_connections/<name>.py`. A model's `connection: <x>` reads `connections/<x>.yaml` first, then the legacy module.
- Pipelines: `pipelines/<name>.yaml` (`transform`, `models`, `reports`, `schedule`, `description`) compiles to the `model_pipeline` runner. A `.py` of the same name wins. `tracebi new-pipeline` writes YAML (`--python` for the old form). A schedule runs the whole chain.
- `tracebi migrate connection|pipeline <file.py> [--write]` convert, or refuse with the reason; nothing is deleted.
- The reference project and the `tracebi init` scaffolds are YAML (models, pipelines, `connections/warehouse.yaml`); every report fingerprint is unchanged.
