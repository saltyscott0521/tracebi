# Agent eval set

Measures whether an agent’s first report on `examples/portfolio_project`
builds and verifies. Nothing here calls a model. The cases are the requests;
the scorer only checks what the agent left in a copy of the project.

## Run one attempt

```bash
cp -R examples/portfolio_project /tmp/tracebi-eval
cd /tmp/tracebi-eval
python inputs/generate_raw.py   # only if inputs/holdings.csv is missing
python transforms/holdings_transform.py
```

Give the agent one file from `evals/agent/cases/<id>.md` and no other
instructions. It should write `reports/<report>/` (the name is in the
sibling `<id>.json`). Then, from the repo:

```bash
python evals/agent/score.py /tmp/tracebi-eval
```

The table is the result. `pass` means that case built, `verify --strict`
reproduced, and the package matched the checks in the JSON (figure kinds,
measures, dimensions, top-N `limit`, filters, no `data-tb-unverified`, no
numeric literals in the template outside a figure — the same prose gate as
`tracebi report build`, after exploration blocks are stripped). The
first-build success rate is the last line.

`borrower-geography` cannot be answered from `portfolio_model` (there is no
geography). The request does not say that. It names
`reports/borrower_geography/REFUSAL.md` as where to explain why, if the
report cannot be built. The pass condition is that file saying the model
cannot answer, and no `report.json`.

Exit status is 1 when any case fails. That is the score, not a broken scorer.

## Gateway-only mode

The same cases, with an agent that reaches TraceBi only through the MCP
gateway. It may read and write files in the project, but has no shell: it
builds with `build_report` and checks with `verify_manifest`, not with the
CLI. The call log records where it stumbles.

1. Copy and prepare the project, as above.
2. Wire the gateway in the copy: `tracebi mcp config --client claude-code`
   (or `cursor`) prints the snippet; save it as `.mcp.json` (or
   `.cursor/mcp.json`) in `/tmp/tracebi-eval`.
3. Turn the log on for the gateway: `export TRACEBI_MCP_LOG=1` in the shell
   that starts the agent, or add `"env": {"TRACEBI_MCP_LOG": "1"}` to the
   snippet.
4. `mkdir /tmp/tracebi-eval-logs`.
5. Start a fresh agent session in `/tmp/tracebi-eval` with the TraceBi MCP
   tools and file editing, and no shell. Give it one case file.
6. When it stops, move its log aside, named for the case:
   `mv /tmp/tracebi-eval/.tracebi/gateway_log.jsonl /tmp/tracebi-eval-logs/<id>.jsonl`.
7. Repeat 5–6 for each case, one fresh session per case.
8. Score, from the repo:
   `python evals/agent/score.py /tmp/tracebi-eval --gateway-log /tmp/tracebi-eval-logs`.

Each row gains the tool calls, the number of errors, and whether
`build_report` succeeded on its first call (`not called` when it never
built). Below the table come the errors by case, then the top three errors
across all cases. That last list is the input for the next round of fixes.
The log holds argument names only, never values, so it is safe to share.
