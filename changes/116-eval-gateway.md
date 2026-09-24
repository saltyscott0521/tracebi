### Added — the agent eval set runs through the gateway

- `evals/agent/README.md` has a gateway-only mode: one fresh agent session
  per case with the TraceBi MCP tools and file editing but no shell, the
  call log on, and each case's log saved as `<case-id>.jsonl`.
- `python evals/agent/score.py <project> --gateway-log <dir>` adds, per
  case, the tool calls, the errors hit, and whether `build_report`
  succeeded on its first call, and ends with the top three errors across
  all cases.
