# Product readiness audit, 2026-09-22

**Verdict: the engine is ready and the product isn't yet. TraceBi has a real,
tested, honest core that no close competitor ships: per-figure receipts, a
`verify` that re-runs them, and an offline tamper check. What's missing is
almost all *outside* the engine: a release, a hosted demo that's always up, a
reader experience written for non-engineers, and one sharply chosen buyer.**

This audit sits alongside [[production-plan]] (the engineering sequence) and
[[ROADMAP]] (the historical backlog). It covers what those don't: fitness as a
*product*, the non-technical experience, and the checklist between here and
something a company can buy.

---

## How this audit was done

Everything below was run, not just read.

- Read the canon ([[MANIFESTO]], [[WORKFLOW]], README, [[production-plan]],
  [[ROADMAP]], `UX_FEEDBACK.md`).
- Ran the full test suite: **1,396 passed, 1 skipped** on `claude/tracebi-audit-readiness-gbl07i`.
  (The first run in a fresh container had 12 failures. All were the
  environment: a broken system `cryptography` wheel and no `tzdata`. See P2-4.)
- Ran the reference project (`examples/portfolio_project/run_workflow.py`):
  about 1 second end to end.
- Walked the new-user path in a scratch folder: `tracebi init` →
  run the transform → `tracebi report build` → `tracebi verify` →
  hand-edited a number → `tracebi verify --file`. Every step behaved as
  documented, apart from the finding in P1-2.
- Served the reference project and drove the web app in headless Chromium: Desk,
  Report, Ask, download, the Verify page with an edited file, and the receipt
  drawer in the standalone file.
- Could not reach `tracebi.com` or `demo.tracebi.com` from the audit
  environment (egress is restricted), so the live-site status in
  `UX_FEEDBACK.md` is carried forward unverified.

## Scorecard

| Area | Grade | One line |
| --- | --- | --- |
| Core engine (model, query, measures, render) | **A** | About 1,400 tests, a 1-second reference run, and every figure in the reference reports reproduces on re-run. |
| Trust mechanism (receipts, verify, tamper check) | **A−** | Works and catches edits precisely. Honest about its limits. Unsigned, so it isn't evidence between parties yet. |
| Honesty of claims | **A** | Unusually disciplined. The locked language ("reproduces", "the sink satisfied its contract") is enforced by tests. |
| Agent surface (MCP, context, guardrails) | **A−** | Mature and tested. The main differentiator for technical buyers. |
| Analyst / developer UX | **B** | The CLI loop is good. Five `tracebi` concepts (sink, freeze point, binding, grain, stage) must be learned before the first report. |
| Non-technical reader UX | **C** | The file and the Verify page work, but the words on screen are engineer-speak, and the "send the file, reader checks it" story has a gap (P1-1). |
| Packaging and release | **C** | Never released to PyPI, `0.6.0.dev0` in `pyproject.toml` while the UI shows `v0.5.2`, no tags. |
| Security and operations | **B−** | Opt-in auth and roles, bearer-token MCP, pip-audit in CI. Identity is self-asserted for agents, and SQLite is single-process. |
| Commercial readiness | **D** | Open-core line is decided on paper. No paid tier built, no pricing, no named design partner in the repo. |

## Is the product fit?

**The problem is real and getting bigger.** AI now drafts reports faster than
anyone can check them, and "a confident wrong number reads exactly like a right
one" is a pain finance, fund operations and compliance teams already feel. The
answer TraceBi gives is mechanical checkability: every number is a query against
declared definitions, with a fingerprint and a re-run command. That's a better
answer than "trust the dashboard", and better than "review the AI's pandas".

**The risk is that trust is a feature, not a product, unless the buyer is
someone whose job is trust.** An analytics team choosing a BI tool will compare
TraceBi to report-as-code tools (Evidence, Observable Framework), dbt-based BI
(Lightdash, the dbt Semantic Layer) and notebooks (Hex). On chart drawing and
connectors, TraceBi loses or ties. It wins only when someone *has to be able to
prove a number later*. So the buyer should be:

- **Primary: fund administrators, private-credit and asset managers, and
  their auditors.** Recurring investor and board reports, numbers that get
  challenged months later, AI drafting coming in fast, and a compliance function
  that already speaks "receipt". The reference demo (a direct-lending holdings
  book) is already in this domain. Lean in.
- **Secondary: any regulated reporting team** (insurance, banking MI, pharma
  ops) where "reproduce the number from last quarter's pack" is a recurring
  request.
- **Not the buyer: self-serve BI for business users.** TraceBi deliberately
  refuses drag-and-drop authoring ([[production-plan]] "Out of scope"). Don't
  market to that audience, or the refusal reads as a missing feature.

**Who is "non-technical" in this product?** They aren't authors. Authoring is
code, by design. They are the **readers, approvers and budget holders**: the
CFO who receives the pack, the reviewer who approves it, the auditor who checks
it. Making TraceBi easier for them means (1) explaining it in their words, (2)
making the file they receive self-explanatory, and (3) making "check this
number" a one-click act. It does **not** mean adding a chart builder.

## Findings

Ranked by what they cost a first-time viewer or buyer. **Fixed** means fixed in
this change.

### P0: blocks a demo or misstates the product

| # | Finding | Status |
| --- | --- | --- |
| P0-1 | **The main download button was invisible.** On every report, **↓ HTML (with receipt)** rendered white-on-white because `Reports.jsx` used `var(--accent)`, a CSS variable that's never defined. The single most important action in the product (take the file with its receipt) couldn't be seen. | **Fixed**: uses `var(--blue)`, like the other primary buttons. |
| P0-2 | **The advertised demo host may be down.** `UX_FEEDBACK.md` (2026-09-06) found `demo.tracebi.com` doesn't resolve, and `site/README.md` still says "Try the demo" points there. It couldn't be re-checked from here. | Open. Check DNS. Make `site/README.md` and every external link agree on one URL. |

### P1: confuses a non-technical viewer or breaks the story

| # | Finding | Recommendation |
| --- | --- | --- |
| P1-1 | **The receipt can't be downloaded from the app.** The Verify page requires the `.html` *and* its `.manifest.json`, but the Reports page offers only HTML and Excel. The Manifest tab shows raw JSON. Worse, each HTML download *re-renders*, so a receipt saved from an earlier build can fail against a later download if the data moved. | Now: a **↓ Report + receipt** download that serves a `.zip` of the html and manifest *from the same render*. Later, once receipts are signed (P2-3): embed the signed manifest in the HTML so `verify --file` needs one file. "Email one file, anyone can check it" is the pitch. Embedding *before* signing makes the file vouch for itself, which catches accidental edits but not deliberate ones. Keep the separate receipt until then, so it can travel by a different channel (or be retained server-side). |
| P1-2 | **The CLI said the offline check "needs only the .html"**, and [[receipts]] said "Checks the file alone". Both are false: `verify --file` looks for `<file>.manifest.json` beside it. | **Fixed** (wording). The product fix is P1-1. |
| P1-3 | **The flagship dashboard's Ask box is a trap.** Its placeholder suggests `what about Software`, and applying it returns a red developer error ("…has no selection block. Controls on this report subset stamped rows…"). Ask works only on `portfolio_showcase`. | Either opt `portfolio_dashboard` into `selection`, or hide Ask on reports that can't answer and show a plain sentence instead. |
| P1-4 | **Ask's answers are unlabeled.** A successful cut shows `60M · 89f4b924a04d`, `4 · 89f4b924a04d`, `96.9% · …`: numbers and hashes with no measure names. | Label each line with the measure's display name. Put the fingerprint behind a "receipt" disclosure. |
| P1-5 | **The in-report receipt drawer is written for engineers.** Rows read `kpi-fv · value · kpis ea55a070ee46`. In the app's embedded view the Receipt button sits at the bottom of the scroll area, so it's hard to find. | Rows should read "Fair value · $285.9M · fingerprint ea55…". Pin the button to the app viewport, not the iframe's. |
| P1-6 | **The demo's Desk says the product is unfinished.** Three of the five reference reports show as **DRAFT · exploration** under "Needs a person". A first-time viewer lands on a to-do list. | Publish the reference reports (strip exploration blocks), or start a non-authenticated demo on **Report**. |
| P1-7 | **Every surface speaks the engine's vocabulary.** Counted on the pages a newcomer sees: "sink" ×14 on Home + Get Started, "lineage" ×34 and "manifest" ×24 in README. Report descriptions read like changelogs ("kitchen-sink demo… trust affordance"). The Desk subtitle is "an open pin, a draft that still explores, a receipt that does not reproduce, a sink that is stale or has no contract." | **Partly fixed**: added [[plain-english]] (explainer and glossary) and [[demo-script]], and linked them first in the docs. Still to do: a plain-language pass on the Desk subtitle, report descriptions and the marketing hero. Keep the locked terms, and put the plain word first. |
| P1-8 | **No release exists.** `pyproject.toml` is `0.6.0.dev0`, there are no git tags, and the install is from git. The UI footer is hard-coded to `v0.5.2` (`Layout.jsx`). | Tag and publish 0.6.0 to PyPI (the [[ROADMAP]]'s stated near-term target). Serve the version from `/api/health` and render it, instead of a literal. |

### P2: polish and hygiene

| # | Finding | Recommendation |
| --- | --- | --- |
| P2-1 | The test suite writes receipts into the repo's `output/` (`bg_report`, `byreg`, `t_report` manifests), and serving the example writes into `examples/portfolio_project/output/`. That's untracked noise in every contributor's `git status`. | Point the tests at `tmp_path`. |
| P2-2 | Charts drop every other category label at the default width (sector bars show Consumer, Software, Financials only). | Rotate or wrap axis labels in the ECharts defaults. |
| P2-3 | Unsigned receipts: `verify --file` checks the file against a manifest supplied by the same sender, so anyone who can edit both can re-seal them. [[receipts]] already says this honestly. It's the reason for the signing tier. | Keep the honesty. Schedule signing (see "Institutional tier" below). |
| P2-4 | `tests/test_parquet_embed.py` needs the IANA tz database (`US/Eastern`), which isn't a declared dependency. It fails at collection on slim Linux images with no system `tzdata`. | Add `tzdata` to the `dev` extra (and to `uv.lock`), or skip when `zoneinfo` can't load. |

## What "an actual product" needs, in order

### 1. Ship the library (weeks, not months)

- [ ] Fix P0-1 (done), P1-1 and P1-3 so the core demo story holds with no
      caveats.
- [ ] Tag and publish **0.6.0 to PyPI**, with `pip install tracebi` in the
      README's first screen. Version comes from one place (P1-8).
- [ ] A **hosted demo that's always up** on the reference project, read-only,
      starting on the Report page. It's the most-clicked link the product will
      ever have. Monitor it.
- [ ] A 90-second screen recording of [[demo-script]] beats 1–3 on the
      homepage. Most buyers will never run a command.

### 2. Make the reader's experience the product

The file is what travels. It should explain itself to someone who has never
heard of TraceBi.

- [ ] **Report and receipt from one download** (P1-1). After signing ships,
      **one file, one check**: the signed receipt embedded, so "drag the file
      onto the Verify page" or "open it and click *Check this report*" is the
      whole story.
- [ ] A **plain-language receipt panel** (P1-5): for each figure, what it is, its
      value, "re-runs to the same number" / "edited since it was built" /
      "not checkable", and one line on what that means.
- [ ] A plain-language **"About this report"** footer that's on by default:
      who built it, when, from which definitions, and what the receipt does and
      doesn't prove. It exists today as the `methodology` block. Make it the
      default and write it in plain words.
- [ ] A copy pass on the Desk, report descriptions and the marketing hero
      (P1-7), using [[plain-english]] as the style guide.

### 3. Prove it with design partners (in parallel with 1–2)

- [ ] **Three design partners in fund administration or private credit.** Run
      [[demo-script]] with each. Success means one of their real recurring
      reports rebuilt in TraceBi and sent to *their* reviewer.
- [ ] Write down the before/after: hours spent answering "where did this
      number come from?" last quarter versus this one. That becomes the case
      study and the pricing anchor.
- [ ] Decide the **wedge sentence** and put it everywhere. Suggested: *"Every
      number in your investor reports, with a receipt, including the ones AI
      wrote."*

### 4. The institutional tier (the paid product)

The [[ROADMAP]] already draws this line: producing a receipt is free, and
institutionalising a book of them is the product. In order of what a
compliance buyer asks first:

1. **Retention.** Every receipt ever issued, kept and searchable, not just a
   file in git.
2. **Identity.** Who built and who approved each report, authenticated (SSO),
   not self-declared (`TRACEBI_MCP_ACTOR` today).
3. **Signing.** Receipts signed by the organisation, so a receipt is evidence
   between parties, not only documentation (P2-3).
4. **The auditor's view.** One page to check any report ever sent, by dropping
   in the file.
5. Row-level security, then SOC 2 once a partner asks for it.

### 5. Business basics that aren't code

- [ ] Pricing hypothesis (per published report or per seat of approver,
      not per analyst).
- [ ] Terms, privacy policy, and a data-handling statement ("runs in your
      environment, nothing is sent to us" is a strong line: make it
      contractual).
- [ ] A support channel and a public changelog cadence.
- [ ] A trademark and domain check on the name.

## What not to do

- **Don't add drag-and-drop authoring** to win non-technical users. The
  non-technical user is the reader, not the author. Serve them with the file.
- **Don't soften the locked language** to sound friendlier. Put a plain
  explanation *next to* "reproduces", never replace it with "verified". The
  honesty is the brand.
- **Don't pitch "Tableau replacement".** [[ROADMAP]] already says why. Pitch
  "the numbers you can prove".
