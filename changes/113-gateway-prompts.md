### Changed — the gateway teaches the package lane

- The MCP server's instructions and the `author_report` prompt now lead
  with the package lane: paste `query_model`'s binding stub into
  `report.json`, claim it in `template.html`, `build_report`, then
  `verify_manifest`. The JSON spec lane (`render_report_spec`) is named as
  the simpler alternative, and the path without file access.
- New prompt `answer_question(question, model="")`: answer from the model
  in plain words, each number beside its fingerprint and measure. It never
  estimates and builds no report unless asked.
- New prompt `address_pins(report)`: act on each open workbench pin in
  order, rebuild, then `resolve_pin` each with a one-line note.
