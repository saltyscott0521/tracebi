# The Agent Gateway Session — a walkthrough

A record of the first real agent session against `tracebi mcp`, kept because
everything the gateway exists for happened in it — including a mistake the
receipts caught that no human reviewer would have.

An AI agent (Claude), connected over the Model Context Protocol, started with
zero knowledge of this project and ended with two published reports and a
self-audit. Every step below is reproducible from this folder: the demo data
is seeded (`rng(42)`), so even the fingerprints come out identical.

## What's in this folder

| File | What it is |
|---|---|
| `gw.py` | The smallest possible agent — a one-shot MCP client |
| `book_review.json` | The report spec the agent authored |
| `verify_report.py` | The audit that re-runs the recorded queries and checks every figure |
| `artifacts/book-of-business-review.html` | The governed render (assurance L2) + its manifest |
| `artifacts/book-review-editorial.html` | The free-form page the agent hand-wrote (assurance L1) |

## What went down

### 1. Discovery — the agent learns what exists

The agent's first call was `list_models`. It saw two models and, on
`wealth_model`, a fact table (`fact_holdings`: units, market_value,
cost_basis) with four dimensions (client, branch, product, account). No
warehouse access, no SQL — only the semantic contract.

```bash
python examples/agent_gateway/gw.py list_models
```

### 2. Exploration — three stamped queries

The agent probed the book before deciding what to write: by asset class, by
advisor, by segment × risk profile. Each response came back **stamped** —
rows plus the resolved query, the full lineage chain, and a SHA-256
fingerprint of the complete result:

```
asset class   6d7152a5a22317e1   (~$7.5M book, all four sleeves in the green)
advisor       7d5f1ad1e0882b4a   (Lisa Chen holds 2x the median book)
segment×risk  3b6a4e8879c2209b   (balanced mandates are half the AUM)
```

### 3. Authoring — a spec, validated before execution

The agent wrote `book_review.json` using only vocabulary the gateway had
shown it, then called `validate_report_spec` — clean on the first try,
checked **without loading a single row**. (When a hallucinated fact name was
deliberately submitted earlier in testing, validation returned
`sections[1].data.query.fact: 'fact_hallucinated' is not a fact on model
'wealth_model'` — a pathed error the agent can repair from.)

### 4. A gap, and the right fix in the right plane

The agent wanted an *unrealized gain* column and couldn't have one: the model
declared no named measures, and a spec cannot express arbitrary computation
(by design). The fix was **not** a workaround at the report layer — it was a
code-reviewed, one-line-per-measure change in the definition plane
(`models/wealth_model.py`):

```python
model.add_measure("unrealized_gain", expr="market_value - cost_basis",
                  agg="sum", format="currency0")
model.add_measure("gain_pct", ratio=("unrealized_gain", "cost_basis"),
                  format="percent")
```

The next gateway call saw the new vocabulary immediately; the spec switched
to naming measures (`["market_value", "unrealized_gain", "gain_pct"]`) and
the declared formats flowed to the renderer with no formatting code in the
spec at all. **Change the contract in git; use the contract over MCP.**

The asset-class fingerprint changed with the data (`6d7152a5…` →
`b3d614c1…`); the untouched sections' fingerprints stayed byte-identical.
Stability where nothing moved, drift where something did.

### 5. Two renders, two assurance levels

- **L2 — governed:** `render_report_spec` produced
  `artifacts/book-of-business-review.html` plus a manifest fingerprinting
  every data-bearing section. Reproducible artifact, refuses invalid specs.
- **L1 — free-form:** the agent then hand-wrote
  `artifacts/book-review-editorial.html` — an editorial page with its own
  design — citing the same three fingerprints in a "Working Papers" section.
  Governed data, ungoverned presentation.

### 6. The audit — and the $1 it caught

L1's honest gap: the agent *transcribed* numbers into its hand-made page, and
nothing machine-checked the transcription. So the agent wrote
`verify_report.py`: re-run the three recorded queries, compare fingerprints,
check every displayed figure.

First run: **fingerprints all matched — one figure failed.** The page's
total unrealized gain read `+$523,045`: the sum of the *rounded* per-row
gains. The true total is `$523,044.32` — round-then-sum vs sum-then-round,
one dollar apart in seven and a half million, invisible to any human eye.
The fingerprint match localized the fault instantly: the data hadn't
drifted; the transcription had.

The page was corrected. The audit now passes 18/18:

```bash
python examples/agent_gateway/verify_report.py
```

## Why this example exists

A beautiful AI-generated artifact contained a wrong number, and the receipts
caught it. The page looked perfect; the error was real; nothing but the
stamped queries would have found it — and they also proved *which kind* of
error it was. This is the failure mode the gateway is built for, demonstrated
by the gateway's own first user on its first day.

## Reproduce it

```bash
pip install -e '.[all]'        # or at minimum: pip install 'tracebi[mcp]'
python examples/agent_gateway/gw.py list_models
python examples/agent_gateway/gw.py validate_report_spec \
  "$(python -c "import json;print(json.dumps({'spec':json.load(open('examples/agent_gateway/book_review.json'))}))")"
python examples/agent_gateway/verify_report.py
```

Or point a real agent at it — from the project root:

```bash
claude mcp add tracebi -- tracebi mcp
```
