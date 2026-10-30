# SOP: Change a model's measures and keys

The procedure an engineer agent (or a person doing the same job) follows to
change what a model's numbers mean: the `models/<name>.yaml` files, or a
`models/<name>.py` for anything YAML cannot say.

Read `AGENTS.md` first. It is the brief every agent reads before working in a
TraceBi workspace (`tracebi init` writes one into each). This SOP is one job
from it.

## Before you begin

- **You work at the model stage.** The model sits between the transform that
  writes the warehouse (`transforms/<name>.sql`, or pandas) and the reports in
  `reports/<model>/` that query it by name. It reads the warehouse and never
  sees the transform. `models/portfolio_model.yaml` is the reference. See
  [[the-three-phase-workflow]].
- **Change the contract in git; use it over MCP.** The gateway (`tracebi mcp`)
  only reads and computes. When a report author hits a missing measure, the
  fix is a reviewed, committed change to a model file: never a workaround in a
  report, never a change at runtime. Every consumer then gets the fix (a fresh
  gateway process at once, a long-running one after a restart).

## 1. Decide whether a model change is the fix

1. **Is the data in the warehouse?** A model can only name columns and tables
   the transform wrote. If the number needs a column the transform dropped or
   a table it never built, the fix is in the transform. Check the tables first
   (`describe_model`, `describe_table`, or Data → Warehouse in the app).
2. **Is it shared meaning or presentation?**

| Situation | Where it goes | Fix |
|---|---|---|
| A business definition several reports should agree on ("unrealized gain", "margin %") | The model | A `measures:` entry in `models/<name>.yaml` (`add_measure` in a `.py`) |
| The standard display format for a measure | The model | `format` on the measure |
| A new attribute, table or join everyone needs | The model | `dimensions`, `tables` or `relationships` in the model file |
| One report wants a different label, column order, layout or one-off format | The report | The report package (`report.json`, the page) |
| One report needs a derived column nothing else uses | The report first | A report calculation in `report.json` (`measures`, `sql_calculations`); promote it to the model when a second report wants it |

3. **If the request is ambiguous** ("add a margin column": to the model, or to
   this report?), list the interpretations and ask before you change anything
   (CLAUDE.md §1).

The standard example (`examples/agent_gateway/README.md`): an agent wanted an
*unrealized gain* column. A spec cannot express arbitrary computation, so the
fix was a small, reviewed change to the wealth model. In
`models/wealth_model.yaml`:

```yaml
  - name: unrealized_gain
    expr: market_value - cost_basis
    agg: sum
    format: currency0
  - name: gain_pct
    ratio: [unrealized_gain, cost_basis]
    format: percent
```

Defined once in the model, every report, query and agent gets the same
"unrealized gain" instead of each deriving it, possibly differently.

## 2. Make the change

### Where model files live

- Edit `models/<name>.yaml` (`.yml` and `.json` use the same schema,
  [[model-json]]). A `models/<name>.py` must define a module-level variable
  named `model` (a `DataModel`).
- Files starting with `_` are skipped, and subfolders are not scanned. Two
  declarative forms of one name are both refused; a `.py` beside a declarative
  file wins. A file that fails to load is a failed entry in `/api/discovery`,
  not a startup error: run `tracebi validate` if something disappears.
- Through the server, a model change is a draft: edit it as a draft in the
  app, or with `start_draft(kind="models", path=<name>)` (it starts from the
  published copy) and `write_draft_file` over MCP, then `model_impact` and
  publish.
  Publishing re-runs every published report that reads the model against the
  draft (the impact check) and asks for `accept_impact` when numbers move.
  `preview_draft` also refuses a `time_grains` entry whose `source` the
  warehouse holds as anything but a DATE or TIMESTAMP (a text month such as
  `2025-07` is grouped by as the attribute it is), since every query grouping
  by it would fail.
- A gateway process started per call (stdio) sees a committed change on its
  next start. A long-running gateway caches imported model modules and must be
  restarted. Either way agents see the change on their next call.

### Declare a measure

A YAML measure entry takes the same keys as `add_measure` (`name`, `column`,
`agg`, `expr`, `ratio`, `description`, `format`, and the other kinds in
[[measures]]). From `tracebi/model/data_model.py`:

```python
model.add_measure(
    name,                 # positional; everything else is keyword-only
    *,
    column=None,          # simple: aggregate one column
    agg=None,             # required for column= and expr=; refused for ratio=
    expr=None,            # expression: aggregate row-level arithmetic
    ratio=None,           # ratio: (numerator, denominator) measure names
    description="",       # write this: it documents the shared meaning
    format=None,          # display hint; becomes the renderer's default
)
```

Give exactly one of `column=`, `expr=` or `ratio=` for these three kinds:

| Kind | Example | Notes |
|---|---|---|
| Simple | `add_measure("revenue", column="revenue", agg="sum")` | One fact column, aggregated. `agg` is `sum`, `count`, `mean` (alias `avg`), `min`, `max` or `nunique`. |
| Expression | `add_measure("gross_margin", expr="revenue - cost", agg="sum")` | Row arithmetic, then aggregated. |
| Ratio | `add_measure("margin_pct", ratio=("gross_margin", "revenue"), format="percent")` | No `agg`. Computed after aggregation: a ratio of totals, not a mean of row ratios. |

### Expressions and callables

An `expr` may contain only column names, numbers and `+ - * / ( )`. A name
followed by `(` is refused as a function call, and the expression is checked
against the fact's columns before it reaches an engine. The aggregation is
`agg=`.

A callable for `column`, `expr` or `agg` raises `TypeError`. A function cannot
be serialized, diffed, reviewed as data, checked before it runs or sent over
the wire, so accepting one would make the model opaque code instead of a
checkable contract. If a calculation does not fit `column`, `expr` or `ratio`,
propose a richer declarative form; don't relax `_EXPR_ALLOWED` or `_EXPR_CALL`
in `tracebi/model/data_model.py` for a workspace's need.

### Declared formats reach every report

`format=` takes `currency` (`${:,.2f}`), `currency0`, `percent`, `comma`,
`decimal`, or a Python format string. With `HTMLRenderer(derive_defaults=True)`
(the default), a column's format comes from, in order:

1. the report author's `number_formats`;
2. the format declared on the model's measure;
3. a column-name hint (`_pct`, `_rate`, …);
4. the value's shape.

So `format="currency0"` on a measure formats it in every report that names it,
with no formatting in the spec.

## 3. Test it

1. Run `pytest tests/` before the change, to confirm a green baseline
   (CLAUDE.md §4).
2. Add coverage. Prefer a step in an end-to-end journey (`tests/e2e/`) that
   uses the measure. Add a unit test only for query semantics a journey cannot
   pin (`tests/test_phase25.py` holds the callable and expression cases). Keep
   tests in their own files, with no shared cross-phase fixtures. Before adding
   one, ask what bug it would catch (`design/test-suite-review.md`).
3. Test the meaning: assert the computed value on a small known dataset, and
   assert a wrong answer is absent (a ratio is a ratio of totals, not a mean
   of row ratios).
4. For a demo-model change, re-render the affected specs and compare
   fingerprints. Sections your change touches should change; every other
   section's fingerprint must stay identical.
5. **Renaming or removing a measure breaks the contract.** Over MCP,
   `downstream(node='measure:<model>:<measure>')` (or
   `node='table:<warehouse>.<table>'` for a table the model would stop
   reading) names every built report figure that reads it, from the builds'
   manifests, each report with its verdict. To prove it, write the removal
   into a model draft and run `model_impact(path)`: the reports it lists as
   `breaks` are the ones that would. `delete_draft(kind="models", path=<name>)`
   drops a what-if draft once it has answered. On a laptop, search `reports/`
   and `examples/` for it, and `tracebi report build` each package that binds
   it (a binding to a missing measure fails the build). A published model's
   impact check lists the reports that break.
6. Run `pytest tests/` again. A passing suite is the minimum.

Useful while working:

```bash
tracebi context --model <name>     # the vocabulary as an agent sees it
tracebi spec validate report.json  # check a downstream spec without running it
pytest tests/                      # the full suite
```

## 4. Commit and open the pull request

1. Keep the diff small. Every changed line traces to the request; don't
   reformat or refactor nearby code. Adding a measure is usually a few lines in
   one model file, plus tests.
2. Write the commit message as one imperative sentence in the repository's
   style, such as `Declare the wealth model's shared measures; collapse
   gateway model aliases`.
3. Record user-visible contract changes (new, renamed or removed measures,
   format changes) in `CHANGELOG.md` (keep-a-changelog format).
4. In the pull request, say why this belongs in the model and not a report,
   list your assumptions, and give the suite result before and after. Ask open
   questions instead of deciding them.

Reviewing this diff is the governance step; that is why model files live in
git.

## What not to do

- **Don't change the contract at runtime.** Never call `add_measure` (or
  `add_fact`, `add_dimension`, …) from a request script, a report factory, a
  route handler or anything that runs while serving. A measure that exists
  only in one process's memory is ungoverned.
- **No lambdas or callables.** Don't wrap one, and don't compute a column in
  an ad-hoc transform and present it as governed.
- **Don't edit `tracebi/` for a workspace's need.** New measure kinds, looser
  expression rules, new aggregations, or reaching into `_measures` are
  framework changes with their own review.
- **Keep each fix in its place.** A label tweak for one report belongs in the
  report; a shared definition belongs in the model. Recomputing "gain" inside
  a report is how two reports disagree about the same number.
- **Don't duplicate a definition.** Check `model.measures()` or
  `tracebi context --model <name>` first. Two names for nearly the same number
  is a trust bug.

## Checklist

- [ ] The change is shared meaning, not one report's presentation, and any
      ambiguity was raised, not resolved silently.
- [ ] Only the model file changed (a `.py` keeps its module-level `model`);
      nothing in `tracebi/`.
- [ ] Each new measure uses exactly one of `column`, `expr` or `ratio`; `agg`
      present for the first two and absent for `ratio`.
- [ ] Every `expr` is column arithmetic only: no functions, quotes or SQL, and
      no callables anywhere.
- [ ] `description` written; `format` declared where there is a standard
      display.
- [ ] No duplicate or near-duplicate measure (`tracebi context --model <name>`
      checked).
- [ ] A journey step (or, for query semantics, a unit test) asserts computed
      values, including that a wrong answer is absent.
- [ ] `pytest tests/` green before and after.
- [ ] Renames and removals: downstream reports found and rebuilt
      (`tracebi report build`).
- [ ] Fingerprint changes only in sections the change touches.
- [ ] `CHANGELOG.md` updated; the diff is small; the commit message is one
      imperative sentence.
- [ ] The pull request states why this belongs in the model, and the suite
      result.
