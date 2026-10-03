### Fixed

- A fragment `template.html` (no `<html>` or `<head>`) builds: it is wrapped into a minimal document before the runtime is injected. A page that already has those tags but no `</head>` still fails.
- Gateway guides name the argument that feeds the next call. `build_report` returns `output_path` and `manifest_path`; pass `manifest_path` as `verify_manifest(manifest=...)` and `output_path` as `fetch_artifact(path=...)`.
- `get_context(brief=true)` keeps the presentation grammar and number formats. In that tier `cheat_sheets`, `report_sections`, and `dataset_verbs` are null or absent; `model` is null or absent unless `model=` is passed.
- `query_model`'s `binding` object is what to paste as the value of `data.<name>` in `report.json`.
- `verify_manifest` reports a package section's type as the figure kind (value, chart, table, or custom) when every figure on that binding shares one kind.
- The `address_pins` prompt runs `verify_manifest` after `build_report` and before resolving pins.
- Gateway instructions name `describe_table`, `list_models`, `list_reports`, and the lesson index before a CLI command.
- The gateway call log masks an argument value only as a whole token, and records a call rejected for a wrong argument name.
- `evals/agent/score.py --gateway-log` reports gateway first-call success separately from builds on rescore.
