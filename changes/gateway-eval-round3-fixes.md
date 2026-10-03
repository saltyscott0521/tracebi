### Added

- `get_context` (brief included) and the `tracebi://guide` resource include one complete `report.json`. `libs` is optional; a chart needs `"echarts"` in it or the interactive panel stays blank. The no-JS picture of the chart still draws.
- `query_model` sets `order_by_note` when it appends the remaining result columns, dimension columns first, as ascending tie-breakers. The receipt still records that full order.
- `describe_model` names the base measure of a `share` measure. A `ratio` measure already lists its numerator and denominator.
- A lesson body is the MCP resource `tracebi://knowledge/{slug}`, the same text as `tracebi knowledge <slug>`. The tool list stays at thirteen.

### Fixed

- The no-JavaScript picture of a chart applies the figure's value format to axis ticks and labels. `percent` shows as a percentage; the stored number is unchanged.
- A value figure needs a one-row binding (its own query with no dimensions, or `order_by` plus `limit` 1). The cell may be text, such as the top sector's name.
