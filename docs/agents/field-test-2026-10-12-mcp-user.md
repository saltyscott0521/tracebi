# Field test: building a report as a generic MCP user (2026-10-12)

**Setup.** An agent session with the TraceBi MCP connector pointed at the hosted
demo (`tracebi.com`), no local install, no repo access to the running app. Goal:
report on *net new assets = purchases minus sales* from `fact_activities` in
`wealth_model`, then iterate on it live. Tools used: `get_context`, `query_model`,
`validate_report_spec`, `render_report_spec`, `verify_manifest`, `fetch_artifact`,
`start_draft`, `write_draft_file`, `preview_draft`.

**What I could not see.** I never opened the draft page in a browser. Everything
below about the page is inferred from tool results, plus the user's own
reports of what he saw (blank bar charts, a "kind: custom" label).

## What worked

- `query_model` stamped results are good: resolved query, fingerprint, and a
  `binding` that pastes straight into `report.json`.
- `verify_manifest` returned `reproduces` for both sections of the first report.
  The receipt loop is easy to follow once you have a manifest path.
- `validate_report_spec` errors name the path of the fault
  (`sections[1].sections[0].data.query.measures.purchases`).
- Draft → `write_draft_file` → `preview_draft` gives a real live URL.

## Obstacles, most costly first

1. **The metric the user asked for cannot be a stamped figure.** Net new assets
   needs a conditional (`activity_type = purchase` minus `= sale`). `expr` is
   arithmetic only, so there is no conditional measure, and `activity_type` /
   `trade_date` are not dimensions of `wealth_model`. A spec section runs one
   query and cannot subtract across sections. Result: the report shows purchases
   and sales side by side and the reader subtracts. A generic user hits this on
   the first realistic "X minus Y by condition" question.
   *Suggestion:* a declarative conditional/filtered measure (for example a
   measure with its own `filters`), or let a value figure combine two bindings
   in the receipt.
2. **A Python model cannot be changed through the gateway.** `wealth_model` is
   Python, and `start_draft` refuses Python models ("edit it from a laptop"), so
   the only way to add measures was a code change in the repo. The message is
   accurate but the user had no way to know before trying.
   *Suggestion:* `describe_model` / `list_models` could say whether a model is
   draftable remotely.
3. **Authoring a draft has an undocumented template contract.** My hand-written
   chart `<div data-tb-figure="chart" ...>` rendered blank. The publish error
   later said the template must place declared figures with
   `{{ figure("id") }}`. The guide's worked example shows `data-tb-figure`
   markup, not `{{ figure() }}`, and nothing at draft time warned that the
   charts would not draw (`preview_draft` returned `ok: true`).
   *Suggestion:* make `preview_draft` fail (or warn) when `report.json`
   declares figures the template never places, as publish does. Show
   `{{ figure("id") }}` in the guide's worked example.
4. **No custom JS or Python in a remote draft.** `write_draft_file` accepts only
   `report.json`, `template.html`, `style.css`. The user asked for "custom JS",
   which is a git-only path. The reason is not written down anywhere I could
   find (my guess: executable code from a remote token). The restriction is
   reasonable, but should be stated in the guide and the tool error.
5. **Spec vs. query measure syntax differ.** `query_model` accepts
   `{"name": {"agg": "sum", "expr": "amount"}}`; a report spec section rejects
   that form and wants `{"amount": "sum"}`. Easy to trip on.
6. **Spec renderer options silently do nothing.** `show_values` and `ylabel` on a
   chart validate, then render with a warning that they have "no runtime
   equivalent". They should fail validation or not be in the schema.
7. **Warnings that are wrong or vague.** `validate_report_spec` warns that
   `activity_type` is "not among the declared columns" of `fact_activities`,
   yet the filter works at run time. A warning that is always false trains the
   reader to ignore warnings.
8. **Detail tables need a workaround.** With `aggregate: false`, only dimension
   attributes and measures come back. To show `activity_type` and `trade_date`
   I passed them as ad-hoc `max` measures on single-trade rows. It works, but it
   is a trick a generic user would not find, and it relies on rows not collapsing.
9. **Large outputs.** `fetch_artifact` of a rendered page is ~400 KB of HTML
   (vendored libs inline) and overflows the tool-result limit. There is no way
   to fetch only the report body.
10. **Small papercuts.** A spec needs `name` and rejects a top-level `title`
    (the error lists the allowed fields, which helped). The `kind: custom`
    label the user saw on the draft is unexplained to a reader; in code
    `custom` is a figure kind (`tracebi/reports/figures.py`), which this report
    did not declare. I did not find where that label is rendered.

## Where the user's real goal went unmet

- The user wanted to *watch the report being built*. The draft URL works for
  that, but it is a refresh loop, not live push, and I could not confirm the
  page looked right without a browser. A way to read back the draft's rendered
  HTML (as `fetch_artifact` does for builds) would let an agent check its own
  work.

## Unverified / not done

- Whether the filter dropdowns (`data-tb-filter`) and the detail table render
  correctly on the draft. The preview call returned `ok`.
- Why the draft page shows "kind: custom".
- Publishing the draft to the demo. It is still a draft.
- Related work on branch `wealth-net-new-assets` (three measures that make a
  stamped `net_new_assets` possible) was set aside by the user; not a finding.
