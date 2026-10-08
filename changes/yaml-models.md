### Added — models are YAML

- `models/<name>.yaml` (also `.yml`) loads through the same closed schema and
  builder as `.json`. Files are parsed with a safe loader only, and a repeated
  key is an error instead of last-wins. `pyyaml` is now a base dependency.
- `time_grains` and `value_bins` keys cover `add_time_grain` and
  `add_value_bins`, so a declarative model no longer needs Python for them.
- One model, one file: a `.py` beats any declarative form, and two declarative
  forms of one name (`x.yaml` and `x.json`) are both refused, with a reason
  naming each file in `/api/discovery`.
- A model draft may be `<name>.yaml` or `<name>.json` (one at a time; writing
  the other form replaces it). New drafts start as YAML.
- `tracebi migrate model models/x.py [--write]` writes the equivalent YAML from
  the loaded model, or refuses with the reason. The `.py` is left in place.

### Changed — `tracebi new-model` writes YAML

- `tracebi new-model "Sales"` writes a commented `models/sales.yaml`. Pass
  `--python` for the previous `.py` scaffold. `tracebi list-models` lists every
  model form.
