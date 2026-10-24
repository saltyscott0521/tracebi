# TraceBi Docs

**Reports as code — to keep agents in line.**

You build a report the way you build software: the connections, the
transforms, the star schema, the measures and the figures are all files in your
repo — reviewed in a pull request, versioned, tested, and authored as easily by
an agent as by a person.

> This folder is an [[#Using this vault|Obsidian vault]] — pages link to each
> other with wiki links, so you can open `docs/` as a vault and navigate the
> graph. The app serves it as **Docs** (`/docs`), and tracebi.com as `/docs/`,
> in the order below.

---

## Start here

What TraceBi is and your first report, in an afternoon.

- [[plain-english]] — TraceBi makes reports where every number comes with a trace, so anyone can check later that the number still matches what it was built from
- [[quickstart]] — Install, scaffold a project, and build one verified report — about five minutes
- [[your-first-report]] — Author a report package end to end — from `tracebi new-report` to a verified artifact
- [[demo-script]] — A click-by-click script for showing TraceBi to people who read and approve reports: finance, operations, compliance, leadership

## Concepts

The ideas, in the order the data moves. Read these once.

- [[the-three-phase-workflow]] — TraceBi takes data from messy to reportable in three folders, each with its own cadence, separated by [[freeze-points|freeze points]]
- [[transform]] — Unconstrained work that ends by landing clean star-schema tables in the warehouse
- [[sink-contracts]] — Closed, declarative checks a [[transform]]'s tables must satisfy before the data counts
- [[model]] — A declarative star schema over the warehouse: the grain, the keys, and the [[measures]] — in a few dozen lines a reviewer reads in one screen
- [[models-and-connectors]] — A model says what the data means; a connector says where it is
- [[report]] — A package where every figure is a live query
- [[trace]] — Every number drawn through the model has a trace: how it was made
- [[lineage]] — Every data operation appends a node describing what happened
- [[freeze-points]] — A freeze point is a materialized artifact handed from one phase to the next

## Guides

Task-shaped walkthroughs, in the order you meet the tasks.

- [[analyst-guide]] — The analyst's path from messy data to a served, verified report
- [[notebook-guide]] — How to use TraceBi from Jupyter — rich previews while you explore, and how a notebook becomes a phase-① transform once the analysis settles
- [[styling-a-report]] — Your CSS and JS, unrestricted — plus a design system you can lean on instead of fighting
- [[one-server]] — One VM, one folder, one container
- [[sign-in]] — With the company login turned on, everyone signs in to the TraceBi app as themselves, and their role decides what they may do
- [[push-from-a-laptop]] — Build and preview on your own machine, then send the files to the server: `tracebi push`
- [[connect-chatgpt-and-claude]] — People sign in to the TraceBi connector with their company login
- [[web-customization]] — How to point the web server at your own data, add your own reports and restyle or extend the React UI, and deploy
- [[updating]] — `tracebi update`: what's new, and the one command that updates your install

## Reference

Look things up: the project, the data, the model, the report, the server.

- [[cli]] — Every `tracebi` command
- [[tracebi-yaml]] — Where the warehouse lives, and the limits of the engine that answers model queries, in one file at the project root
- [[connections-yaml]] — A source as data: a type and its fields, with every secret kept out of the file as a `${ENV_VAR}` reference
- [[credentials]] — The secrets a project's connections need: which names, where each is set, and a store on the server you can set them in without touching `.env`
- [[environment-variables]] — Every `TRACEBI_*` variable the framework reads
- [[transform-sql]] — A phase ① transform is a `.sql` file by default: DuckDB statements, run top to bottom in one fresh connection to the warehouse
- [[model-json]] — A model as data: the same star schema as a Python `DataModel`, written as a document a person reviews and a remote agent can draft without the server running anyone's code
- [[measures]] — Named, declarative calculations on a [[model]]
- [[queries]] — What a report may ask a [[model]]: measures, dimensions, filters, `having`, ordering, limits — as data, not SQL
- [[pipeline-yaml]] — A pipeline as data: which transform to run, which models it feeds, which reports to rebuild, and when
- [[report-json]] — The package declaration: what data a report binds, and which figures the framework builds for it
- [[app-jsx]] — The React lane: an app-like dashboard from the TraceBi kit, built into the same single offline file
- [[template-html]] — The figure grammar: ordinary HTML, and the `data-tb-*` attributes that turn an element into a live figure
- [[figure-helper]] — Declare a figure in [[report-json]]; the framework builds the element, you keep the layout
- [[number-formats]] — Named formats you apply to a figure, plus the defaults TraceBi derives when you don't
- [[folder-yaml]] — Who may see, build in, publish into and manage a folder of the report library, in a small file that sits in the folder
- [[api-routes]] — The HTTP surface served by `tracebi serve`

## For agents

Standard operating procedures. An agent reads AGENTS.md first.

- [[sop-authoring]] — Authoring a report through the gateway, step by step
- [[sop-model-changes]] — Changing the semantic contract, a model's measures and keys, safely

---

## The canon

Short, stable, opinionated documents at the repo root that define the project.

- `MANIFESTO.md` — what TraceBi is and what it refuses to build
- `AGENTS.md` — the brief an agent reads before authoring
- `CLAUDE.md` — behavioural guidelines for AI assistants in this repo

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
- The order of pages is `docs/toc.yaml`. A new page goes there, and
  `python site/build_docs.py` regenerates this index and the site.
