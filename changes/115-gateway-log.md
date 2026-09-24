### Added — an opt-in gateway call log

- `TRACEBI_MCP_LOG=1` makes the MCP gateway append one line per tool call
  to `.tracebi/gateway_log.jsonl`: the tool, ok or error, the duration, the
  actor, and the names of the arguments passed. Argument values, results
  and tokens are never written; an argument value an error message echoes
  is masked. Off by default, and nothing leaves the machine.
- `tracebi agent log [--since 7d] [--json]` summarizes it: calls and error
  rate per tool, the top ten errors, and the first-build success rate.
