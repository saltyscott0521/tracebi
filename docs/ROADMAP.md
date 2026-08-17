# TraceBi end-to-end: what to build next

> **2026-08-16:** The report layer is being reshaped — one lane, free
> presentation, per-figure verification, transform contracts. The build plan
> is `docs/report-architecture-v2.md`; it absorbs field-notes findings
> #1/#2/#5/#10/#11/#13 structurally. Items below that intersect it are
> sequenced there.

## The commercial line — open core (decided 2026-08-14)

TraceBi is **open core**: the library is the product's distribution, not a
teaser for it. The dbt Core / dbt Cloud shape, drawn along the assurance
ladder.

- **Free, in the library (MIT):** everything that *produces* trustworthy
  analytics. The three-phase workflow, the stamp, the manifest, `verify`, the
  MCP gateway, the self-hostable web app, self-contained report artifacts.
  This is L0→L2 — a single team can prove its own numbers reproduce, on its
  own machine, today. Producing analysis is cheap; TraceBi makes believing it
  cheap too, for free.
- **Paid, in the product (later):** everything that makes trust
  *institutional* rather than local — the L3 rung and its prerequisites.
  **Keeping** receipts (org-wide durable retention, not a file in git),
  **signing** them (L3 cryptographic attestation), knowing **who** rendered
  one (authenticated identity, not operator-asserted), and giving an auditor
  **one place** to check them all. These are exactly the audit's unfinished
  Tier-1 gaps (G3 identity, G4 retention/evidence, L3=0%) — they are not
  missing library features, they are the product's feature list.

The line: *producing* a receipt is free; *institutionalizing* a book of them
is the product. The manifesto already draws this boundary ("hosted topologies
are demos of TraceBi, not the shape of it") — this section names which side of
it each roadmap item falls on, so the work sorts itself. The **library
release (0.6.0, PyPI) is the near-term target**; it needs only the L0→L2
polish below (the "pilot-ready" set), never the product tier.

The gap-audit items at the bottom of this file are tagged **[free]** (belongs
in the library release) or **[product]** (the commercial tier) where the split
is not obvious.

---

**Thesis check, in one paragraph.** TraceBi's pitch is a trust layer for AI-generated analytics: agents speak a semantic contract, every answer carries a stamp (query + lineage + SHA-256 fingerprint), specs validate before execution, and the assurance ladder (L0–L3, NOTES.md 2026-08-03) grades what a company can prove. Four independent audits (new analyst, MCP-only agent, platform operator, fund-ops design partner) agree on the verdict: **the stamping kernel is real and production-shaped** — fingerprints verified identical across Python, CLI, and a live MCP round trip; render refuses invalid specs; cap-invariance is test-pinned. What's missing is everything that lets someone *check* a receipt, *trust* the checker's identity, or *keep* the receipt. L2 is ~80% built, L1 is ~50% (stamps yes, receipts no), L3 is 0%. The roadmap below is one merged, deduped, ranked list. The ordering principle: a trust layer that cannot verify its own receipts, whose validator misses the most common agent errors, and whose flagship surface has no auth is not yet making a true claim — fix that before selling it. *(Update 2026-08: the verify loop, validate coverage, and gateway bearer auth from the Now tier have since shipped — see CHANGELOG [Unreleased]; the identity now lives in MANIFESTO.md.)*

---

## Now — unblocks the thesis

These five items are the difference between "we stamp things" and "we are a trust layer." Every persona hit at least two of them.

### 1. Close the verify loop: `tracebi verify` + a `verify` gateway tool + input fingerprints at render

- **What:** (a) Record source/input fingerprints in the manifest at render time; (b) ship `tracebi verify <manifest>` that re-runs each section's recorded `query_spec` and classifies the outcome as *reproduces / source-drift / unexplained*; (c) expose the same as an 8th MCP tool (`verify_fingerprint(model, query, expected)`) so an unattended agent can close its own loop. Add a `schema_version` field to the manifest in the same change so archived manifests stay verifiable across upgrades.
- **Why:** This is the #1 finding in two audits and implicated in a third. The agent audit: "the entire trust thesis rests on receipts someone can check, and today the only checker is a hand-written example script" (examples/agent_gateway/verify_report.py, with hardcoded figures). The fund-ops audit: no `verify` among cli.py's 15 subcommands; manifests carry no input fingerprints, so a mismatch "is just DRIFT with no diagnosis." NOTES.md itself lists this as open ("Needs input fingerprints recorded at render"). Crucially, the agent audit confirmed manifests *already* record each section's resolved query_spec — the tool is mechanically buildable today. The $1 audit catch is the product's best story; right now it demos a missing feature.
- **Effort:** M

### 2. Make "validation before execution" true: close the validate gaps and unify the render error channel

- **What:** Extend `_check_data_ref` (tracebi/spec.py:366–419) to check filter columns, aggregation names, ad-hoc dict-measure columns, dimension *attributes* (after the dot), and chart x/y references against the model — the same checks `DataModel._validate_query_columns` (data_model.py:1393) already performs at execution. Wrap `gateway_render_spec` (mcp_server.py:262–264 has no try/except) so *every* failure returns the documented `{ok, errors:[...]}` shape. Special-case the `dataset`-vs-`data` key confusion: today `{"dataset": {...}}` validates `ok:true` then dies with a pathless `AttributeError: 'dict' object has no attribute 'to_pandas'` — the exact trap the vocabulary invites, since get_context calls the field "dataset."
- **Why:** The agent audit verified by direct execution that four whole error classes — the typo classes an LLM agent produces most — pass `gateway_validate_spec` with `{ok:true}` and detonate at render as raw exceptions. "Validation before execution" is the keystone claim; it currently holds only for section structure, fact names, named measures, and dim names. The analyst audit found the same shape at project level: `tracebi validate` blesses a scaffold whose only table doesn't exist. Depends partly on item 7 (column schema in describe_model) for the dict-measure check, but the spec-side checks need no new surface.
- **Effort:** M

### 3. Put auth on the gateway (and defuse `output_dir`)

- **What:** Bearer-token auth and a `--host` bind flag for `tracebi mcp --transport http`; constrain `gateway_render_spec`'s agent-controlled `output_dir` (mcp_server.py:230, 257 — currently an arbitrary-path mkdir+write as the server user) to a configured root; replace the self-declared `TRACEBI_MCP_ACTOR` env var (mcp_server.py:49) with per-connection authenticated identity. Until shipped, README.md:459–460 must stop recommending the HTTP transport without a caveat.
- **Why:** The operator audit's first-flag finding: the flagship surface has *zero* auth on HTTP — no token, no TLS, no host bind — yet the README tells remote agents to use it, and anyone reaching the port gets full query access with the process's warehouse credentials plus a file-write primitive. The fund-ops audit lands the thesis blow: "a trust layer whose audit trail records whatever the caller claims to be" — identity is asserted, not authenticated, so concurrent agents are indistinguishable in the audit log. NOTES.md admits this is open; the operator journey is exactly the "revisit trigger" NOTES.md 2026-06-09 named.
- **Effort:** M

### 4. Give manifests a durable home

- **What:** A retention story for the evidentiary artifact: stop gitignoring receipts by default (.gitignore:13–14 excludes `output/` and `*.manifest.json` *by name*), persist manifests from the web render path (tracebi/web/api/main.py:158–159 currently returns them in-memory only, `output_path='(in-memory)'`), and document/back the compose bind mount. Ship the manifest `schema_version` with item 1.
- **Why:** The operator audit calls this the buyer's deal-breaker: "a trust layer that cannot retain its receipts cannot testify." Nearly every deployment plane loses them — git excludes them and Vercel can't write them; compose does bind-mount ./output, but nothing versions or retains what lands there. L3 and `tracebi verify` are both unreachable without retained manifests; the $1 audit only worked because artifacts were hand-committed. The analyst audit adds the git half: every init'd project records `git_sha: "unknown"` silently — `tracebi init` should `git init` (or loudly warn), because "git as courtroom record" is half the pitch.
- **Effort:** M

### 5. Fix the installed-package last mile: make `tracebi serve` work from a pip install

- **What:** ~~Ship the web app in the wheel~~ (done — and then moved: the app is `tracebi.web.api`, packaged as part of `tracebi` with `artifacts = ["tracebi/web/ui/dist/**"]`, guarded by a CI job that asserts the bundle is in the wheel *and* that nothing top-level named `web` ships. Shipping a second top-level `web` package collided with the `web.py` distribution on PyPI, which owns that path in site-packages. This item originally offered "or move the app under `tracebi.web`" as the alternative; that is the one that survived). ~~so a fresh clone doesn't serve a silent 404 homepage~~ (done: without a bundle `/` explains itself instead of 404ing, with the remedy that fits a checkout or an installed package). Still open on the UI half: only a wheel from `.github/workflows/release.yml` carries the bundle — the documented `pip install "tracebi[web] @ git+https://…"` builds from a tree where `tracebi/web/ui/dist` is gitignored, so it ships the API and no UI. Auto-building it (a hatch build hook running npm) or publishing the release wheel would close that. Still open: fix the init-generated README's bare-PyPI `pip install "tracebi[...]"` instructions (cli.py:471, 479 — a dependency-confusion shape while the package isn't on PyPI); make init's closing message match the `[analyst]` extras it just recommended; and make `spec render` / `spec validate` / `context` honour `TRACEBI_MODELS_DIR` and `--models-dir` — `_default_models_dir()` (cli.py:38–39) is hardcoded `Path.cwd() / "models"` while tracebi/web/api/main.py:219, mcp_server.py:94 and verify.py:78 all read the env var, and CLAUDE.md and .env.example:65 document it as supported.
- **Why:** The analyst audit's fatal break: the scaffolded golden path — init's own success message — walked every pip-installed user into `ModuleNotFoundError: No module named 'web'`. The kernel delivers its receipts; "what loses analysts is the last mile between the installed package and the browser." This is the cheapest high-severity fix on the board and it gates every evaluation that starts with an install.
- **Effort:** S

---

## Next — design-partner readiness

What a 90-day fund-ops pilot and a real unattended agent need once the thesis holds.

### 6. L1 receipts for foreign renderers

- **What:** A stable URL or token per stamped query that an agent's own HTML can cite and a reviewer can click/check — plus a generic transcription checker replacing the per-report hardcoded script.
- **Why:** L1 claims "every number traceable," but there is no receipt artifact; verify_report.py:36–109 hardcodes three queries and every expected figure. Named open in NOTES.md:100–101; flagged high by both the agent and fund-ops audits. Depends on items 1 and 4 (something durable to point the token at).
- **Effort:** M

### 7. Agent-facing ergonomics bundle: get_context, describe_model columns, list_reports, artifact fetch

- **What:** (a) Rewrite `get_context`: drop the ~7KB of Python-library surface an MCP agent can't invoke; add the model roster, row-cap semantics (50 default / 500 hard cap appear in no payload), the spec data-envelope schema (serve `tracebi.spec.json_schema()` over MCP — it already exists on CLI and HTTP), the fingerprint-citation convention, and the ladder. (b) Add column names/dtypes to `describe_model` (currently tables are `{name, connector, source}` only — agents must learn columns from error messages). (c) Fix `list_reports`, which returns `[]` unconditionally because `cmd_mcp` (cli.py:1050–1067) never runs discovery. (d) Add an artifact-retrieval tool so the HTTP-transport agent can read the HTML/manifest it just produced instead of receiving unreachable file paths.
- **Why:** The agent audit's discover phase findings: half of get_context's tokens are unusable, a "call this first" tool names zero models, and list_reports is "dead on arrival." (b) is also a prerequisite for finishing item 2's dict-measure/filter-column validation. These are individually small; together they're the difference between an agent that self-repairs and one that guesses.
- **Effort:** M (bundle of S items)

### 8. Excel output over the gateway

- **What:** Let `render_report_spec` (and the CLI spec path) target `ExcelRenderer`, which already exists in the library; mcp_server.py:239, 264 currently import and call only `HTMLRenderer`.
- **Why:** The fund-ops audit is blunt: "fund ops lives in Excel." This is the highest-leverage/lowest-cost design-partner ask on the list because the renderer is already built. (Deprioritize PDF: there is no standalone `PDFRenderer`, though the `[pdf]` extras key is live — it powers `HTMLRenderer.render_pdf()`.)
- **Effort:** S

### 9. Bind facts to governed sinks: model↔pipeline lineage checks

- **What:** Validate-time (and lineage-diagram) checks that a `FinalLayer` fact's `table_name` resolves to a pipeline sink, warning loudly when a gold-layer fact reads a raw landing table; make `tracebi validate` resolve declared tables against their connectors instead of passing scaffolds whose tables don't exist.
- **Why:** The analyst audit reproduced the exact governance leak the layer contracts exist to prevent: a fact pointed at `orders_raw`, pipeline ran green, and "governed" gold numbers were computed over un-deduplicated raw rows — coupling is hand-matched table-name strings with no check. For a product whose differentiator is lineage, this is a silent integrity hole in the happy path.
- **Effort:** M

### 10. Harden web auth defaults: revisit warn-only

- **Done:** the role-header spoof is closed. `_Authorizer` takes a required `trust_role_header` — proxy mode passes `True`, Basic auth `False` — so under Basic a client's `X-Forwarded-Groups: admin` no longer promotes anybody, and proxy mode reads the *last* occurrence so an appending proxy's own claim wins over a client copy. The strip-inbound-headers requirement is documented in `tracebi/web/api/auth.py`, `docs/web-customization.md` and `.env.example`.
- **What's left:** make the deliberate call NOTES.md deferred: warn-only fallbacks (no auth → serve everything; no *usable* role source → everyone is admin) were a demo posture whose stated revisit trigger — someone deploying this as a company trust layer — has now fired. The remaining gap is Basic auth configured with only a role header and no `TRACEBI_AUTH_ROLE_MAP` or `TRACEBI_AUTH_DEFAULT_ROLE`: it warns loudly and leaves everyone `admin`, because switching enforcement on there would pin the deployment to `viewer` with no way to grant anything more.
- **Why:** The fund-ops audit flagged "every principal resolves to admin" as the quietest gap in a trust product.
- **Effort:** S

### 11. Scheduled delivery (email/Slack) with the manifest link

- **What:** First-class scheduled distribution — "the Tuesday-morning book review in the ops inbox" — carrying the manifest/receipt link; plus one worked, safe recipe for cron on serverless (the current doc hand-waves pg_cron/Vercel Cron past the pg_net and admin-credential problems, so demo schedules are silently decorative).
- **Why:** Flagged missing in the 2026-05-22 review (NOTES.md:1077), still missing; the fund-ops audit calls it a first ask; the operator audit shows the workaround path is undeployable as documented. A trust layer nobody receives reports from doesn't get evaluated.
- **Effort:** M

### 11b. The legacy spec render gains the presentation stack (round-2 field test)

- **What:** A JSON-spec render today produces zero `tb-` classes and zero provenance badges — it is still the legacy renderer, so a spec-authored page and a package-authored page differ in look *and* trust affordances. Either route spec renders through the compiled-package path (compile in memory via `compile_spec`, render the artifact) or teach `HTMLRenderer` to emit the stack.
- **Why:** Round-2 field test, finding 2: "If specs are staying, they need the stack." The scaffold no longer steers anyone to specs (fixed), but every un-migrated spec still renders without badges — the trust affordances silently downgrade on the serialization that claims to be equivalent. Routing through `compile_spec` is likely a day and retires the divergence permanently.
- **Effort:** S–M

### 12. A real release path: PyPI, tagged images, versioned artifacts

- **What:** Publish to PyPI (also retires item 5's dependency-confusion risk permanently), tag container images instead of compose-builds-from-checkout, and replace the "remember to update `_RUNS_ADDED_COLUMNS`" invariant with a checked migration step.
- **Why:** The operator audit: v0.5.2, no PyPI, no tagged images, no migration framework — "thin upgrade path for a compliance-positioned product." The re-verify-in-6-months promise (item 1) needs the 6-months-later software to install reproducibly.
- **Effort:** M

---

## Later — scale

### 13. As-of / point-in-time reporting

- **What:** Replayable lineage — query the model "as of 6/30" via warehouse time-travel or snapshotting, so a cited fingerprint can be reproduced after upstream refreshes.
- **Why:** Fund-ops runs on NAV cycles; today every query recomputes from live source and any refresh flips every fingerprint to DRIFT with no way back. Named a killer feature in 2026-05 (NOTES.md:1075–1076), never built. It is the deepest cut on this list (touches the load path and every connector), which is the only reason it isn't in Next — item 1's source-drift *classification* is the affordable down payment.
- **Effort:** L

### 14. Per-agent scopes → gated pipeline writes over MCP

- **What:** Which models/measures/operations per credential; only then expose pipeline execution to agents. NOTES.md already states the right principle: writes before scopes would put the highest-privilege operation on the least-attributable surface.
- **Why:** The named gate in NOTES.md's open list; both operator and fund-ops audits agree scopes also strengthen today's audit trail, not just future writes. Depends on item 3's authenticated identity.
- **Effort:** L

### 15. Query pushdown — retire `SELECT *`

- **What:** Push filters/aggregations to source instead of `DataModel.load()`'s wholesale `SELECT *` into pandas frames registered in DuckDB (NOTES.md:980–982, 420–423: "a local aggregation engine, not a query engine").
- **Why:** The fund-ops scale ceiling: position-level data (millions of rows) pulled into memory per gateway query, re-paid every time since nothing caches. Fine for the pilot's demo data; fatal at fund scale.
- **Effort:** L

### 16. Multi-process run registry

- **What:** Move background-run state (run_ids, discovery registry) from in-process memory to the database so `uvicorn --workers 4` — the documented prod command — doesn't 404 polls nondeterministically.
- **Why:** Operator audit: breaks under *any* multi-process deployment, and intermittently — worse than Vercel's consistent failure. Pipeline advisory locks show the team already knows the pattern.
- **Effort:** M

### 17. L3: signed manifests + attestation

- **What:** Sign the manifest (and hash the HTML it describes) so the artifact chain is tamper-evident; today both are plain editable files with zero signing code anywhere in the library.
- **Why:** Honestly labeled "(future)" in the ladder, and it should stay sequenced after items 1/4/6 — signing a receipt nobody can verify or retain is theater. But the ladder table is the sales asset, and its top rung needs to stop being vapor before a compliance buyer reads it as shipped.
- **Effort:** M

### 18. Docs-and-drift sweep

- **What:** ~~Reconcile the stale test counts, Quick Start numbering, template-sections mismatch, rewrite docs/overview.html~~ — done in the story-sync pass (2026-08-04). Remaining: `spec render`'s CWD-default output path.
- **Why:** Analyst audit lows — individually trivial, collectively the kind of drift a skeptical evaluator reads as a proxy for rigor, which is expensive for a product selling exactness.
- **Effort:** S

---

## The opinionated summary

If only three things get built this quarter: **verify loop (1), validate coverage + error contract (2), gateway auth (3)** — in that order. They convert the ladder's L1/L2 rows from aspiration to fact, and they're all M-effort because the kernel underneath them already works. Item 5 (packaging) should be done this week regardless; it's small and it's the first thing every evaluator hits. Excel over the gateway (8) is the cheapest design-partner win on the board. Resist the temptation to start as-of reporting (13) before the verify loop exists: drift you can *classify* buys most of the pilot-era trust that time-travel eventually delivers, at a tenth of the cost.

---

## 2026-08-14 — five-lens gap audit

A ten-agent audit (readers over every surface, then five critics: skeptical
analyst, agent substrate, packaging, enterprise platform engineer, product
coherence) produced 33 findings. Mapped here so the list above stays the one
ranked backlog. Full detail in the audit synthesis (session artifact).

**Closed by the manifesto + packaging arc (2026-08-14):**

- Identity unsettled, thesis nowhere in the repo → `MANIFESTO.md` + the
  canonical sentence on all six first-contact surfaces (G1)
- `tracebi init` scaffolded the pre-three-phase product; first verify read
  NOTHING VERIFIED → full three-phase scaffold ending in REPRODUCES, pinned
  by tests (G2); `new-transform` added; conventions name `inputs/` +
  `transforms/` (part of G12)
- Framework/demo mixing at the repo root → `examples/portfolio_project/` +
  self-contained demo_app + `TRACEBI_APP` default flipped (G23)
- Phase-name collision (Manipulate vs ManipulationLayer) and the
  dashboard/report noun split → TRANSFORM / REPORT everywhere (G20, G21)
- CLI ignored `TRACEBI_*_DIR` (G24); new-model connected at import (G25);
  init `.env.example` omitted the auth story (G27); "Qlik-style" framing
  survived in CLAUDE.md (G31)

**Already covered by items above:** authenticated audit identity → 3/14;
evidence-grade receipts (web manifests unpersisted, no signing) → 4/17;
no release/PyPI → 12; read/query audit → new sub-item of 4; multi-worker
RunStore → 16; full-scan pushdown → 15.

**New items this audit adds (unranked; slot on the next grooming pass).**
All **[free]** — they are first-run, agent-loop, connector, and auth-config
fixes that belong in the library. The **[product]** tier (authenticated
identity G3, evidence-grade retention G4, L3 signing) lives in the ranked
list above as items 3, 4, and 17.

- **Model-cache invalidation over MCP** — the canonical agent loop (edit
  model → use measure) breaks against `ModelRegistry`'s forever-cache; no
  reload tool exists. mtime-based invalidation in `get()` fixes CLI, web,
  and MCP at once. *The single worst agent-loop break found.* (G5)
- **Snowflake/BigQuery auth modes** — password-only today; no
  `authenticator`, key-pair, or `role`, while Snowflake sunsets single-factor
  passwords. A `**connect_kwargs` passthrough covers every mode. (G7)
- **The documented `.env` wiring fails** — nothing loads dotenv; scaffolds
  don't either; `tracebi validate` prints "✓ .env file found" above the
  KeyError caused by not reading it. (G8)
- **MCP surface honesty bundle** — broken models vanish silently
  (`skipped: []` payload needed); `gateway_reports()` empty on a bare
  gateway; `get_context` cheat-sheet advertises kwargs that raise TypeError;
  ~~spec JSON-schema unobtainable over MCP~~. (G9–G11)
  *Partly closed 2026-08-15 by the MCP 2.0 work: the ReportSpec schema is now
  the `tracebi://spec-schema` resource (G11 done); the skipped-models payload
  and the cheat-sheet kwargs fix (G9/G10) remain.*
- **Warehouse introspection** — no surface returns table columns + dtypes;
  agents learn schemas from error messages. `tracebi warehouse tables` + a
  `describe_table` MCP tool. (G12 rest)
- **Authorization strict mode** — `_parse_map` silently drops malformed
  entries: two typos → empty map → everyone admin, zero warning. Warn on
  unknown roles; `TRACEBI_AUTH_STRICT=1`; log the resolved posture at
  startup. (G13)
- **`gateway_render_spec` output_dir is still live** — writes anywhere as
  the server user, including the served SPA dist; retries clobber receipts.
  Roadmap item 3's "defuse output_dir" half never landed. (G14)
- **Transport hardening** — same-origin check on non-GET (Basic auth is
  CSRF-able), dev CORS behind TRACEBI_DEV_MODE, reference reverse-proxy
  compose profile. (G17)
- **Security-review readiness** — SECURITY.md, dependabot/pip-audit,
  non-root Docker USER, lockfile. All mechanical. (G18)
- **Housekeeping riding the next release:** extras drift (`medallion`
  fossil, `csv`→`excel` + xlrd) (G26); `verify` accepts multiple manifests
  for CI globs (G28); ~~AGENTS.md registered as an MCP resource + caveats in
  the server instructions string~~ (G29 **closed 2026-08-15**: the authoring
  SOP is the `tracebi://guide` resource and the caveats are in the
  instructions string); `validate --json` + no raw
  tracebacks from `context --model` (G30); name the local-by-default
  residency commitment in deploy docs and label Vercel as demo topology
  (G33, the manifesto now states the commitment); a missing-warehouse error
  hint (`report build` before the transform surfaces a raw DuckDB
  CatalogException instead of "run phase ① first"); receipt coverage for
  metric literals (a hand-typed KPI value is neither checked nor marked —
  record it in the manifest as unverified so verify can name it).
