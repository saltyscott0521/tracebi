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
numeric literals in the template outside a figure). The first-build success
rate is the last line.

`borrower-geography` cannot be answered from `portfolio_model` (there is no
geography). The pass condition is a `reports/borrower_geography/REFUSAL.md`
that says so and contains no number, and no `report.json`.

Exit status is 1 when any case fails. That is the score, not a broken scorer.
