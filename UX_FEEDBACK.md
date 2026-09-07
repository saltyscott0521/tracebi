# TraceBi UX feedback — 2026-09-06
Tester: first-time user agent  
Surfaces tested: `https://www.tracebi.com/` (marketing), `https://www.tracebi.com/app` (live demo — Home, Reports+run, Models, Explore+query, Pipelines, Workflow, Get Started, Docs/handbook, Connectors, Verify), `http://127.0.0.1:4173/` (Vite preview polish — empty/API-down states, mobile ~390px).  
Not reached: `https://demo.tracebi.com` (DNS does not resolve). chrome-devtools MCP timed out / could not auth in this environment; walkthrough used headless Chrome + Puppeteer against the same URLs.

## Verdict (3-5 sentences)

The live app at `/app` is already a credible analyst tool: quiet chrome, clear sidebar IA, and a real “run → receipt → download HTML” loop that sells the trust story better than the docs alone. Marketing is sharp and professional; the product home reinforces the three-phase story well. Biggest first-session gaps: the advertised `demo.tracebi.com` host is dead, trust UI mixed signals (`✓ verifiable` next to grey `no contract` badges), and Learn surfaces still teach two different mental models (three-phase folders vs DataSet chaining / medallion layers). Post-polish nav (Verify in the footer) reads right — the product no longer feels like it’s marketing “trust” in every chrome pixel.

## What worked

- **Marketing (`tracebi.com`)**: Strong hero, honest scope note, clear CTAs to `/app` (“Try the demo” / “See a live report”). Interactive verify/tamper demo on the page reinforces the product claim without needing the app.
- **Home / Workspace**: Three-phase diagram + “Browse reports” CTA orients a new user fast. Populated demo shows 2/3/3/1 counts and named reports with green `✓ verifiable` badges.
- **Reports happy path**: Select `aum_by_branch` → **Run Report** → toast “Report ran successfully” → receipt strip (`🧾 Verifiable artifact`, `6 reproducible`) → Output with real KPIs/chart → **HTML (with receipt)** / Excel / Lineage / Manifest. This is the moment the product clicks.
- **Explore**: Measure pick + Run query returned a stamped result (`ENGINE: DUCKDB`, `22.4 MS`) plus “How this number was made” lineage steps — the trust pitch in miniature.
- **Models**: WealthModel detail (tables / Preview / Relationships / ERD tabs) is enough to feel like a real semantic layer, not a toy list.
- **Verify (footer)**: Quiet placement matches the SaaS polish intent; dropzone copy (“data never leaves this machine”) is clear.
- **Mobile (~390px)**: Hamburger + drawer work; home stacks the workflow diagram readable vertically.
- **Empty-state polish (local `:4173`)**: Home empty copy pointing at `reports/` / `tracebi new-report` is helpful when the registry is genuinely empty.

## Friction / bugs (severity by severity: P0/P1/P2)

### P0
- **`demo.tracebi.com` does not resolve** (no DNS). Anyone given that URL never reaches the product. Marketing correctly uses `https://www.tracebi.com/app` — align every external mention / bookmark / README to that, or restore the hostname.

### P1
- **Receipt strip mixed signals on a successful demo run**: after `aum_by_branch`, green `Verifiable artifact` / `6 reproducible` sit beside grey `branches: no contract`, `holdings: no contract`, `products: no contract`. A first-time user reads “something’s wrong with the trust story” on the flagship report. Either hide `no_contract` in the demo, pre-satisfy contracts, or demote that status so it doesn’t compete with the green verdict.
- **Onboarding teaches two products**: Home/Workflow push **transform → model → report** folders; **Get Started** still centers `DataModel` + immutable **DataSet** chaining (filter/transform/sort) and never mentions `transforms/`. Pipelines still banners **Landing → Manipulation → Final**. Same session, three vocabularies.
- **Reports empty-state vs Home empty-state disagree** (seen on API-less preview): Home says scaffold with `tracebi new-report` / `reports/`; Reports says `Add one with @registry.report() in your app module.` Pick one primary path for humans.
- **API-down looks like “empty product”**: local Vite preview returned **502** on `/api/*` but UI showed **0** connectors/models/reports and normal empty states — plus a **always-green** sidebar status dot. No “backend unreachable” banner. Easy to misdiagnose as “I have no data” rather than “preview has no API.”

### P2
- **Reports require an explicit Run** every visit; opening `?r=aum_by_branch` after a prior success showed Recent runs chips but not the last Output until re-run (~22s on demo). For a live demo, auto-run or “show last successful output” would cut time-to-wow.
- **Explore with zero models** (preview): copy says “No facts defined on this model…” — implies a selected model without facts, not “no models / API down.”
- **Pipelines node chrome**: cron-like strings on nodes (`0 * * * *`, `30 6 * * *`) read as cryptic scores; React Flow a11y strings (“Press enter or space to select a node…”) leak into the accessibility tree / dump-dom as noise.
- **Connectors list** is a dead-thin master-detail (“Select a connector…”) — fine for power users, weak for a demo tour compared to Reports/Explore.
- **~22s** to render the small wealth demo report is noticeable for a first click; worth a progress cue beyond disabling the button (skeleton / phase text).

## Design / polish notes (post SaaS pass)

- Verify-as-footer works: primary nav feels like a workspace (Home → Pipelines), Learn is grouped, trust utility is findable without dominating.
- Typography (IBM Plex), navy sidebar, restrained badges — professional, not juvenile. Toast on successful run is well-judged.
- Home still carries a lot of explanatory chrome (workflow diagram + receipt essay + quick start). Fine for v0.5 demo; for a returning analyst it may want a denser “last reports / last runs” first viewport.
- Mobile header is clean; primary CTAs (“Browse reports” / “Get started”) survive the narrow layout.
- Tagline “Analytics trust layer” under the mark is clear; version `v0.5.2` in the footer is appropriately quiet.

## Suggested next changes (top 5, ordered)

1. **Fix the demo entrypoint**: point everything at `https://www.tracebi.com/app` (or restore `demo.tracebi.com` DNS). Treat hostname 404 as a launch blocker.
2. **Clean the demo receipt**: make the flagship report’s receipt read unambiguously green (seed sink contracts or don’t surface `no_contract` as peer badges to `reproducible`).
3. **One onboarding spine**: rewrite Get Started around the three-phase folders (and/or deep-link Workflow); keep DataSet chaining as an advanced/appendix path. Align Pipelines page language with Transform/Model/Report or clearly label medallion as an alternate older path.
4. **Honest API failure UI**: when `/api/health` fails, show a single banner (“API unreachable — start `python -m tracebi.web.run`”) instead of zeros + green status; unify empty-state CTAs to `tracebi new-report` / `reports/`.
5. **Shorten time-to-first-artifact on Reports**: auto-run the selected demo report (or restore last successful Output), with a visible progress state so the receipt moment arrives in one click.
