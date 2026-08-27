# TraceBi Docs

**Reports as code — to keep agents in line.**

You build a report the way you build software: the connectors, the star schema,
the measures and the figures are all code in your repo — reviewed in a pull
request, versioned, tested, and authored as easily by an agent as by a person.

> This folder is an [[#Using this vault|Obsidian vault]] — pages link to each
> other with wiki links, so you can open `docs/` as a vault and navigate the
> graph.

---

## Start here

| If you want to… | Read |
| --- | --- |
| Understand what TraceBi is in five minutes | [[the-three-phase-workflow]] |
| Get something running | [[quickstart]] |
| Build your first report | [[your-first-report]] |
| Look up a specific thing | [[#Reference]] |

## Concepts

The ideas. Read these once and the rest of the docs make sense.

- [[the-three-phase-workflow]] — the spine: transform → model → report
- [[transform]] — phase ①: unconstrained pandas that lands clean tables
- [[model]] — phase ②: the star-schema contract over those tables
- [[report]] — phase ③: figures that are live queries, not typed-in numbers
- [[freeze-points]] — why the three phases don't block each other
- [[receipts]] — what a receipt proves, and what it deliberately does not
- [[lineage]] — every operation leaves a node; nothing is untracked
- [[sink-contracts]] — checks a transform must satisfy before its data counts

## Guides

Task-shaped walkthroughs.

- [[quickstart]] — install, scaffold, and build one report
- [[your-first-report]] — author a report package end to end
- [[styling-a-report]] — your own CSS and JS, and where the framework stops
- [[analyst-guide]] — the longer analyst walkthrough
- [[notebook-guide]] — working in notebooks
- [[web-customization]] — theming the served web UI
- [[deploy-vercel-supabase]] — hosting

## Reference

Look-up pages. These are kept in step with `tracebi context`, the generated
vocabulary, so they describe what the code actually accepts.

- [[report-json]] — the package declaration, key by key
- [[template-html]] — the `data-tb-*` figure grammar
- [[figure-helper]] — `{{ figure("name") }}`: framework-built figures, your layout
- [[measures]] — every measure kind the semantic layer knows
- [[queries]] — filters, `having`, ordering, limits
- [[number-formats]] — the named formats and how defaults are derived
- [[cli]] — every `tracebi` command
- [[environment-variables]] — every `TRACEBI_*` variable
- [[api-routes]] — the HTTP surface

## Architecture

Deep design documents. Written for someone changing the framework, not using it.

- [[report-architecture-v2]] — the current report artifact design
- [[large-detail-artifacts]] — how big datasets ship inside one HTML file
- [[frontend-surfaces]] — the three separate front ends and why
- [[report-generator-architecture]] — superseded; kept for its kernel sections

## The canon

Short, stable, opinionated documents that define the project.

- [[MANIFESTO]] — what TraceBi is and what it refuses to build
- [[WORKFLOW]] — the three-phase workflow, stated normatively
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
  *"reproduces"* (never "verified"). See [[receipts]] for why the wording is
  load-bearing.
