# TraceBi Docs

**Reports as code, with a trace behind every number.**

You build a report the way you build software. The connections, transforms,
star schema, measures and figures are files in your repository: reviewed in
a pull request, versioned, tested, and written as easily by an agent as by a
person.

> This folder is an [[#Using this vault|Obsidian vault]]. Pages link to each
> other with wiki links, so you can open `docs/` as a vault and browse the
> graph. The app serves it as **Docs** (`/docs`), and tracebi.com as
> `/docs/`, in the order below.

---

## Start here

Install TraceBi and build your first report.

- [[plain-english]] — TraceBi makes reports where every number carries a record of how it was made, so anyone can check later that the number still matches its source
- [[quickstart]] — In five minutes you will install TraceBi, create a project, build a report and open it in the app
- [[your-first-report]] — Change the query behind one number in the sample report, rebuild it, and see the trace follow
- [[demo-script]] — A click-by-click script for showing TraceBi to people who read and approve reports: finance, operations, compliance, leadership

## Concepts

How data moves from raw files to a checked report.

- [[the-three-phase-workflow]] — A TraceBi project moves data through three folders: a transform cleans it, a model defines it, and a report presents it
- [[transform]] — A transform is a file in `transforms/` that reads raw data, cleans it, and writes star-schema tables into the warehouse
- [[sink-contracts]] — A sink contract is a list of checks a transform's tables must pass before the data counts
- [[model]] — A model is a YAML file in `models/` that names the warehouse tables a report may read, how they join, and the measures it can compute
- [[models-and-connectors]] — A model says what the data means; a connector says where it is
- [[report]] — A report is a folder in `reports/` whose every figure is a query against a model
- [[trace]] — Every number a report draws from a model has a trace: a record of how it was made
- [[lineage]] — Every data operation in TraceBi adds a node to a chain that records what happened
- [[freeze-points]] — A freeze point is a stored artifact one stage hands to the next

## Guides

Step-by-step instructions for common tasks.

- [[analyst-guide]] — Build a report, check it, send it, and work with a model in Python
- [[notebook-guide]] — Explore data in Jupyter with rich previews, then turn the notebook into a transform that writes the warehouse
- [[styling-a-report]] — Give a report your colours, fonts and layout by setting design tokens, using the shipped components, and adding your own CSS and JavaScript
- [[one-server]] — Serve a project, its schedules and its email from one container on one virtual machine
- [[connect-a-database]] — Add a database, or a file, as a source from the app, and choose which of its tables an agent may read
- [[sign-in]] — Turn on single sign-on so people sign in to TraceBi with their company account and get a role from their groups
- [[push-from-a-laptop]] — Build and preview on your own machine, then send the files to the server with `tracebi push`
- [[connect-chatgpt-and-claude]] — Let people add TraceBi as a connector in ChatGPT or Claude and sign in with their company login
- [[web-customization]] — Point the web server at your own project, add resources in code when files are not enough, restyle or extend the React UI, and deploy it
- [[updating]] — Check for a new release and update your install with `tracebi update`

## Reference

Every file, key, command and route.

- [[cli]] — Every `tracebi` command, grouped by task
- [[tracebi-yaml]] — `tracebi.yaml` at the project root says where the warehouse lives and sets the limits of the engine that answers model queries
- [[connections-yaml]] — A file in `connections/` declares a database or folder that holds data: its type and fields, with every secret kept out of the file as `${ENV_VAR}`
- [[credentials]] — The secrets a project's connections need: which names, where each is set, and an encrypted store on the server
- [[environment-variables]] — Every `TRACEBI_*` variable TraceBi reads
- [[transform-sql]] — A transform is a `.sql` file of DuckDB statements, run top to bottom in one fresh connection to the warehouse, with its sink contract beside it in a `.contract.yaml`
- [[model-json]] — A model file declares a star schema: the same model as a Python `DataModel`, written as data that runs no code
- [[measures]] — A measure is a named calculation on a [[model]]
- [[queries]] — A query is what a report asks a [[model]]: measures, dimensions, filters, `having`, ordering and a limit, written as data rather than SQL
- [[pipeline-yaml]] — A pipeline file names the transform to run, the models it feeds, the reports to rebuild, and when
- [[report-json]] — `report.json` declares a report package's data: the queries it runs, and the figures TraceBi builds for it
- [[app-jsx]] — Build a dashboard from the TraceBi kit in React, into the same single offline file
- [[template-html]] — Turn ordinary HTML into live figures with `data-tb-*` attributes
- [[figure-helper]] — Declare a figure in [[report-json]] and place it in your page with one call
- [[number-formats]] — The named formats you can give a figure, and the defaults TraceBi picks when you give none
- [[folder-yaml]] — A `_folder.yaml` in a library folder says who may see, build in, publish into and manage that folder
- [[api-routes]] — The HTTP API `tracebi serve` provides

## For agents

Procedures for AI agents. An agent reads AGENTS.md first.

- [[sop-onboarding]] — From a connection a person set up to a model and a report
- [[sop-authoring]] — Author a report through the gateway, step by step
- [[sop-model-changes]] — Change a model's measures and keys safely

---

## The canon

Short, stable documents at the repository root that define the project.

- `MANIFESTO.md`: what TraceBi is and what it will not build
- `AGENTS.md`: the brief an agent reads before authoring
- `CLAUDE.md`: guidelines for AI assistants working in this repository

---

## Using this vault

Open the `docs/` folder as an Obsidian vault for backlinks, the graph view
and wiki-link autocomplete. Everything is plain Markdown, so it also reads in
an editor or on GitHub, where a wiki link shows as plain text.

**Conventions:**

- Each page is about one thing.
- Each page opens with one sentence saying what you will do or get.
- Reference pages list what the code accepts, and the refusal it gives when
  you get it wrong.
- Some phrases are fixed because the product uses them exactly: *"the sink
  satisfied its contract"* and *"reproduces"* (never "verified"). See
  [[trace]].
- The order of pages is `docs/toc.yaml`. Add a new page there, then run
  `python site/build_docs.py` to regenerate this index and the site.
