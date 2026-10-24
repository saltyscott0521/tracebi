# TraceBi Docs

**Reports as code — to keep agents in line.**

You build a report the way you build software: the connections, the
transforms, the star schema, the measures and the figures are all files in your
repo — reviewed in a pull request, versioned, tested, and authored as easily by
an agent as by a person.

> This folder is an [[#Using this vault|Obsidian vault]] — pages link to each
> other with wiki links, so you can open `docs/` as a vault and navigate the
> graph. The app serves it as **Docs** (`/docs`), with **Get started** first.

---

## Start here

| If you want to… | Read |
| --- | --- |
| Understand TraceBi without a technical background | [[plain-english]] |
| Show TraceBi to someone in ten minutes | [[demo-script]] |
| Understand what TraceBi is in five minutes | [[the-three-phase-workflow]] |
| Get something running | [[quickstart]] |
| Build your first report | [[your-first-report]] |
| Run it for a team | [[one-server]] |
| Look up a specific thing | [[#Reference]] |
| Understand where TraceBi is going and why | [[vision-and-positioning]] |

## Concepts

The ideas. Read these once and the rest of the docs make sense.

- [[the-three-phase-workflow]] — the spine: transform → model → report, and the app's five places
- [[transform]] — phase ①: SQL (or pandas, the escape hatch) that lands clean tables
- [[model]] — phase ②: the star-schema contract over those tables
- [[models-and-connectors]] — a model says what the data means; a connector says where it is
- [[report]] — phase ③: figures that are live queries, not typed-in numbers
- [[freeze-points]] — why the three phases don't block each other
- [[trace]] — what a trace proves, and what it deliberately does not
- [[lineage]] — every operation leaves a node; nothing is untracked
- [[sink-contracts]] — checks a transform's tables must satisfy before the data counts

## Guides

Task-shaped walkthroughs.

- [[plain-english]] — what TraceBi does, for readers and approvers who don't code
- [[demo-script]] — a click-by-click ten-minute demo for a non-technical audience
- [[quickstart]] — install, scaffold, and build one report
- [[your-first-report]] — author a report package end to end
- [[styling-a-report]] — your own CSS and JS, and where the framework stops
- [[analyst-guide]] — the longer analyst walkthrough, from messy data to a served report
- [[notebook-guide]] — working in notebooks, and a notebook as a transform
- [[web-customization]] — pointing the web app at your project, extending its UI and API
- [[one-server]] — one VM, Docker or Coolify, a folder, connection secrets, SMTP, a schedule
- [[sign-in]] — the app's and the CLI's sign-in through your identity provider
- [[updating]] — `tracebi update`: what's new, and the command for your install
- [[connect-chatgpt-and-claude]] — a sign-in per person for the MCP connector
- [[push-from-a-laptop]] — `tracebi push`: drafts from your machine, code an admin approves

## Reference

Look-up pages. These are kept in step with `tracebi context`, the generated
vocabulary, so they describe what the code actually accepts.

- [[report-json]] — the package declaration, key by key
- [[template-html]] — the `data-tb-*` figure grammar
- [[app-jsx]] — the React lane: an app-like dashboard from the TraceBi kit
- [[figure-helper]] — `{{ figure("name") }}`: framework-built figures, your layout
- [[measures]] — every measure kind the semantic layer knows
- [[model-json]] — a model as data: `models/<name>.yaml` (or `.json`)
- [[transform-sql]] — a transform as SQL, its `-- source:` lines and its `.contract.yaml`
- [[connections-yaml]] — a source as data: `connections/<name>.yaml`, secrets as `${NAME}`
- [[credentials]] — where a `${NAME}` resolves, and the encrypted store (`tracebi secret`)
- [[pipeline-yaml]] — a pipeline as data: transform, models, reports, schedule
- [[tracebi-yaml]] — the project's settings: the warehouse's tier and the engine's limits
- [[folder-yaml]] — folder permissions: who may view, build, publish and manage
- [[queries]] — filters, `having`, ordering, limits
- [[number-formats]] — the named formats and how defaults are derived
- [[cli]] — every `tracebi` command
- [[environment-variables]] — every `TRACEBI_*` variable
- [[api-routes]] — the HTTP surface, and the app's addresses

## Architecture

Design notes. Written for someone changing the framework, not using it; each
records a decision and why. The app's Docs sidebar does not list them; a link
opens them.

- [[duckdb-first]] — one engine from the sink to the page: SQL transforms, the locked query connection, storage tiers
- [[live-reports-plan]] — how a built page recomputes every figure under one selection, offline
- [[report-architecture-v2]] — the one-lane report artifact: per-figure claims, manifest v2, the loop
- [[report-generator-architecture]] — the two-lane design it replaced; kept for its kernel sections
- [[large-detail-artifacts]] — how big datasets ship inside one HTML file, still verifiable
- [[frontend-surfaces]] — tracebi.com, the app, and a hosted plane: three front ends and why
- [[nav-v3]] — Docs as a place and Data as the chain: the app's five places
- [[data-flow-board]] — Data as a board: the lanes, the edges, what the board never claims
- [[one-demo]] — what tracebi.com serves, and the conventions every model follows
- `architecture/credentials.md` — the credential store's design: resolution order, the key, the API
- [[design-direction]] — who the builder experience is for, and what the app looks like
- [[ui-quality]] — the UI quality bar and the audit that checks it
- [[ui-backlog]] — the UI items still open
- [[test-suite-review]] — what the tests should cover, what was removed, and why

## Agent SOPs

- [[pitfalls]] — bugs already hit in this repo, and the rule that prevents each
- [[sop-authoring]] — authoring a report through the gateway
- [[sop-model-changes]] — changing the semantic contract

## Strategy

Where the product is going and why. Intent, not documentation of what ships
today, so neither the app's Docs sidebar nor the docs site lists it; a link
opens each page.

- [[vision-and-positioning]] — the bet, the positioning, the principles
- [[users-and-jobs]] — the seven user types and their journeys
- [[product-strategy]] — the ask, build and schedule paths, BI parity, templates
- [[deployment]] — local, self-hosted, Cloud, customer VPC
- [[report-library]] — folders, permissions, drafts and publishing
- [[remote-authoring]] — building from a hosted chat or a laptop: drafts, sign-in, code requests
- [[analyst-freedom]] — calculating anything, labelled: model, report, SQL and code

## The canon

Short, stable, opinionated documents that define the project.

- [[MANIFESTO]] — what TraceBi is and what it refuses to build
- [[AGENTS]] — the brief an agent reads before authoring
- [[CLAUDE]] — behavioural guidelines for AI assistants in this repo

---

## Using this vault

Open the `docs/` folder as an Obsidian vault to get backlinks, the graph view,
and wiki-link autocomplete. Everything is plain Markdown, so it also reads fine
in an editor or on GitHub — GitHub renders a wiki link as literal text rather
than a link, which is the one cost of this style.

**Conventions used throughout:**

- One page is about **one thing**. If a page needs two headings that could each
  be a page, it becomes two pages.
- Every page opens with a one-sentence answer to *"what is this?"*
- Reference pages state what the code accepts, with the refusal it raises when
  you get it wrong — the refusals are part of the contract, not an afterthought.
- Locked language is quoted exactly: *"the sink satisfied its contract"*,
  *"reproduces"* (never "verified"). See [[trace]] for why the wording is
  load-bearing.
