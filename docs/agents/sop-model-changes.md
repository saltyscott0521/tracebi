# SOP: Changing the Semantic Contract

**Audience:** an engineer-agent (or a human doing the same job) editing the
**definition plane** — the `models/*.py` files that declare what numbers mean
in this project.

**Where this sits in the three-phase workflow (see `WORKFLOW.md`).** This is
**phase ② — MODEL**, the freeze point between the unconstrained phase-① transform
(`transforms/*.py`, ordinary pandas that sinks the warehouse) and the fast
phase-③ dashboard (`dashboards/*.json`) that queries the model by name. The
model **reads the sink; it never sees the transform** — it is the semantic
contract, a few dozen declarative lines a reviewer reads without opening the
pandas above it (`models/portfolio_model.py` is the reference). It is also where
the trust machinery begins: everything from this boundary onward is stamped and
verifiable; phase ① below it is unverified by design, trusted as reviewed code.

**The rule this whole document unpacks:** *change the contract in git; use the
contract over MCP.* The gateway (`tracebi mcp`) is read-and-compute only. When
an agent authoring a dashboard hits a vocabulary gap — a measure that does not
exist, a definition that should — the fix is a reviewed, committed change to a
model file, never a workaround at the dashboard layer and never a runtime
mutation. Every consumer then inherits the fix (fresh gateway processes immediately;
long-running ones after restart).

---

## 1. Is a model change the right fix?

First, a phase question: **is the data even in the warehouse?** A model can only
name measures over columns and tables phase ① actually sank. If the number needs
a column the transform never wrote — a field it dropped, a table it never built —
no `add_measure` will conjure it; the fix is **upstream in phase ①**, sinking the
missing column or table in `transforms/*.py` (unconstrained pandas), after which
the model can reference it. Only once the underlying data is in the sink is a
model change the right tool. Check the warehouse's tables (`describe_model`, or
the Models page) before assuming this is a phase-② edit.

Then the plane question: **is this shared meaning, or presentation?**

| Situation | Plane | Fix |
|---|---|---|
| A business definition several reports should agree on ("unrealized gain", "margin %") | Definition | `add_measure` in `models/<name>.py` |
| The canonical display format for a measure, everywhere it appears | Definition | `format=` on the measure |
| A new slicing attribute, table, or join everyone needs | Definition | `add_dimension` / `add_table` / `add_relationship` in the model file |
| One report wants a different label, column order, section layout, or a one-off format | Presentation | The report spec (`column_labels`, `number_formats`, sections) |
| One report needs a derived column nothing else will ever use | Presentation first | Keep it in the report/request; promote to a measure only when a second consumer wants it |

The canonical example (see `examples/agent_gateway/README.md`): an agent
wanted an *unrealized gain* column. A spec cannot express arbitrary
computation — by design — so the correct fix was a small, code-reviewed
change in `models/wealth_model.py` (the actual commit also declared
`market_value` and `cost_basis` as named measures with formats; the two
gain measures were the point):

```python
model.add_measure("unrealized_gain", expr="market_value - cost_basis",
                  agg="sum", format="currency0")
model.add_measure("gain_pct", ratio=("unrealized_gain", "cost_basis"),
                  format="percent")
```

Defining it once in the model means every report, query, and agent gets the
*same* "unrealized gain" — instead of each consumer re-deriving it, perhaps
differently. That is the entire point of the semantic contract.

If the ask is genuinely ambiguous ("add a margin column" — to the model, or to
this one report?), surface the interpretations before implementing, per
CLAUDE.md §1.

---

## 2. Mechanics

### 2.1 Where model changes live

- Edit `models/<name>.py`. The file **must** expose a module-level variable
  named `model` (a `DataModel`) — that is the convention the registry looks
  for.
- Files starting with `_` are skipped; model discovery loads only `.py`;
  subdirectories are not scanned. A file that raises on import is skipped
  with a warning, not an error — run `tracebi validate` if something silently
  disappears.
- A one-shot gateway process (stdio, spawned per call) picks up a committed
  change on its next spawn; a long-running gateway keeps already-imported
  model modules cached and must be restarted. Either way a change is
  visible to agents on their **next** gateway call — no server restart, no
  cache to invalidate.

### 2.2 `add_measure` — the exact signature

From `tracebi/model/data_model.py`:

```python
model.add_measure(
    name,                 # positional; everything else is keyword-only
    *,
    column=None,          # simple:     aggregate one column
    agg=None,             # required for column= and expr=; forbidden for ratio=
    expr=None,            # expression: aggregate a row-level arithmetic expr
    ratio=None,           # ratio:      (numerator, denominator) measure names
    description="",       # write this — it is the shared meaning, documented
    format=None,          # presentation hint; becomes the renderer default
)
```

Exactly **one** of `column=`, `expr=`, or `ratio=` must be given. The three
kinds, deliberately closed:

| Kind | Example | Notes |
|---|---|---|
| **simple** | `add_measure("revenue", column="revenue", agg="sum")` | Aggregation of one fact column. `agg` is one of `sum, count, mean` (alias `avg`), `min, max, nunique`. |
| **expression** | `add_measure("gross_margin", expr="revenue - cost", agg="sum")` | Row-level arithmetic, then aggregated. |
| **ratio** | `add_measure("margin_pct", ratio=("gross_margin", "revenue"), format="percent")` | Takes **no** `agg`. Computed *after* aggregation — a true ratio of totals, not a mean of per-row ratios. |

### 2.3 `expr` is arithmetic-only, and callables are rejected — by design

An `expr` may contain **only bare column names, numeric literals, and
`+ - * / ( )`**. No function calls, no quotes, no SQL fragments — an
identifier followed by `(` is rejected as a function call, and the expression
is validated against the fact's actual columns before it ever reaches an
engine. Aggregation is declared separately via `agg=`.

Passing a callable for `column`, `expr`, or `agg` raises `TypeError`. This is
the single most consequential API constraint in the codebase and it is not a
limitation to route around: **a lambda cannot be serialized, diffed, reviewed
as data, validated before execution, or sent over the wire.** Accepting one
would forfeit reproducibility at the root — the model would stop being a
checkable contract and become opaque code. If your calculation does not fit
`column`/`expr`/`ratio`, that is a design conversation (a richer declarative
grammar compiling down to these structures), not a reason to smuggle in a
function. Do not relax `_EXPR_ALLOWED` / `_EXPR_CALL` in `tracebi/model/
data_model.py` for a project need.

### 2.4 Declared formats flow to renderers

`format=` takes a named shortcut — `currency` (`${:,.2f}`), `currency0`,
`percent`, `comma`, `decimal` — or a raw Python format string. With
`HTMLRenderer(derive_defaults=True)` (the default), the precedence for a
column's number format is:

1. the report author's explicit `number_formats` (always wins),
2. **the format declared on the model's measure**,
3. a column-name suffix hint (`_pct`, `_rate`, …),
4. shape-based fallback.

So declaring `format="currency0"` on a measure means every report that names
it renders correctly with **no formatting code in the spec at all** — which is
exactly what an agent composing at volume needs, since nobody is proofreading
its raw output.

---

## 3. Tests, then the full suite

Per CLAUDE.md §4: run `pytest tests/` **before** your change (confirm a green
baseline) and **after**. A passing suite is the minimum bar.

- Measure-definition behavior is tested in `tests/test_phase25.py` (see the
  existing `add_measure` tests around the callable-rejection and expr-
  validation cases) and gateway-visible behavior in
  `tests/test_mcp_gateway.py`. Add your tests to the phase file they belong
  to — test files are phase-scoped; do not reorganize across files or add
  shared cross-phase fixtures.
- Test the *meaning*, not just the plumbing: assert the computed value on a
  small known dataset. Bias toward asserting the **absence of a wrong
  answer** (e.g. a ratio measure is a ratio of totals, not a mean of per-row
  ratios), not just the presence of a right one — silent-wrong-output is this
  framework's named enemy.
- For a demo-model change, re-render affected specs and check fingerprints:
  sections whose data your change touches **should** drift; untouched
  sections' fingerprints must stay byte-identical. Drift where something
  moved, stability where nothing did — that is your review signal.
- **Renaming or removing** a measure is a breaking contract change: grep
  `reports/`, `requests/`, and `examples/` for references and run
  `tracebi spec validate` on any spec that names it.

Useful while working:

```bash
tracebi context --model <name>     # see the vocabulary as an agent sees it
tracebi spec validate report.json  # check a downstream spec without running it
pytest tests/                      # full suite (run it for the current count)
```

---

## 4. Git commit / PR etiquette

Per CLAUDE.md:

- **Surgical diffs.** Every changed line traces directly to the request. Do
  not reformat, "improve", or refactor adjacent code; match existing style.
  A measure addition is typically a handful of lines in one model file plus
  tests.
- **Commit messages** follow the repo's style: one imperative, descriptive
  sentence — e.g. `Declare the wealth model's shared measures; collapse
  gateway model aliases`. Say what changed and, when it matters, why.
- **CHANGELOG.md** is keep-a-changelog format; record user-visible contract
  changes (new/renamed/removed measures, format changes) there.
- **In the PR description**, state the shared-meaning justification (why this
  belongs in the model and not a report), your assumptions, and the
  before/after suite result. Surface open questions rather than deciding them
  silently.
- Suite green before and after is the bar for merging; the model files are
  the contract, and review of this diff **is** the governance step — that is
  why the definition plane lives in git at all.

---

## 5. What NOT to do

- **No runtime mutation of the contract.** Never call `add_measure` (or
  `add_fact`, `add_dimension`, …) from a request script, a report factory, a
  route handler, or anything executed at serve time to patch a gap. The
  registry is populated at startup and read at request time; the gateway is
  read-and-compute only. A measure that exists only in one process's memory
  is exactly the ungoverned state this architecture exists to prevent.
- **No lambdas or callables, ever** — see §2.3. Do not wrap one, do not
  precompute a column in an ad-hoc transform and pretend it is governed.
- **Do not edit `tracebi/` internals for a project need.** Adding a measure,
  a dimension, or a format belongs in `models/*.py`. New measure kinds,
  relaxed expression rules, new aggregation functions, or reaching into
  `_measures` and other `_private` attributes are framework changes with their
  own review bar — propose them, don't sneak them in with a model change.
- **Do not solve presentation problems in the definition plane** (a
  one-report label tweak is `column_labels` in the spec) **or shared-meaning
  problems in the presentation plane** (recomputing "gain" inside a report is
  how two reports disagree about the same number).
- **Do not duplicate a definition.** Before adding a measure, check
  `model.measures()` / `tracebi context --model <name>` — if a near-duplicate
  exists, fix or reuse it; two names for almost the same number is a
  trust-layer bug.

---

## 6. Checklist

Before opening the PR, confirm every box:

- [ ] The change is **shared meaning**, not one report's presentation (§1);
      ambiguity was surfaced, not silently resolved.
- [ ] Edited `models/<name>.py` only; module-level `model` variable intact;
      no `tracebi/` internals touched.
- [ ] Each new measure uses exactly one of `column=` / `expr=` / `ratio=`;
      `agg` present for the first two, absent for `ratio`.
- [ ] Any `expr` is bare-column arithmetic only — no functions, quotes, or
      SQL; no callables anywhere.
- [ ] `description=` written; `format=` declared where a canonical display
      format exists.
- [ ] No duplicate/near-duplicate of an existing measure
      (`tracebi context --model <name>` checked).
- [ ] Tests added in the correct phase-scoped file, asserting computed
      values (including the absence-of-wrong-answer case).
- [ ] `pytest tests/` green **before and after** the change.
- [ ] Renames/removals: downstream specs and reports grepped and
      re-validated (`tracebi spec validate`).
- [ ] Fingerprint drift confined to sections the change actually touches;
      untouched sections byte-identical.
- [ ] CHANGELOG.md updated; diff is surgical; commit message is one
      imperative, descriptive sentence.
- [ ] PR states the shared-meaning rationale and the suite result.
