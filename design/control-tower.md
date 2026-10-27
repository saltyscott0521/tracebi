# The Data workshop is a control tower

Decided 2026-10-27 with the owner, after the Data tab restructure (DATA-A/B/C)
still read as "clicks all around". The owner's brief: question why it is set up
this way; we got here by pivoting from human-written code to agent-written
code, and the North Star docs predate that pivot. This note records the
assumptions we found, which ones still hold, and what replaces the rest.

## The assumptions, and whether they survive the pivot

| # | Assumption, and where it comes from | Holds? | What replaces it |
|---|---|---|---|
| A1 | **The project is five folders by kind** (`connections/`, `inputs/`, `transforms/`, `models/`, `reports/`, `pipelines/`), and the app shows them as five lists. A human repo convention, dbt's shape. | As storage, yes. As the thing people look at, no. An agent never browses folders; it reads a graph of contracts. A person approving an agent's work needs the same graph. | **The graph is the structure; folders are where nodes are stored.** The app shows the graph (the map) and the lists become search results and jump points. Files stay by kind: cheap, git-friendly, and a by-model layout would force an owner on sources and transforms that are shared. |
| A2 | **A source is a connection file.** Sources pages show the YAML (url, variable, Save password) first and tables last. | No. Under agent authorship the questions about a source are: which tables, which may agents read, which transform read them, when, how, and what they became. The url is an admin's concern once. | **Sources are tables; connections are setup.** A source table has the same passport as every other node. The connection builder lives behind one Setup button. |
| A3 | **Pipelines are a separate thing** (`pipelines/<model>.yaml`: transform → models → reports), with their own runs, steps and a "not run yet" state that contradicts the certificate beside it. Airflow's shape. | **Yes, by the owner's decision (2026-10-27).** A graph edge says what *depends* on what, never what should *run*. Reports must not rebuild because something upstream moved; running is declared in a pipeline or started by a person's Refresh. | **The pipeline stays the unit of work.** What the graph adds is the picture: select any node and see what is downstream of it, and which of those were built before it last moved. That is information for the person deciding whether to refresh, never a trigger. The contradictory wording was already fixed (DATA-C: a step with no run here says `not run here · written <ago>`). |
| A4 | **We do not trace through the transform.** The manifesto's honest boundary, written when phase ① was "unconstrained pandas". | For pandas, yes, and permanently. For SQL, the premise is gone: the agent's `propose_transform` is SQL only, four of the five reference transforms are SQL, and DuckDB parses SQL into a tree we can read. Lineage through a SQL transform is not a guess; it is the parser's output. | **SQL transforms get column lineage, recorded in the certificate** (`lineage: [{sink: fact_holdings.par, from: [crm.issuer_ratings.rating, inputs/holdings.csv.par]}]`), computed from DuckDB's `json_serialize_sql`, never inferred. Pandas keeps the boundary and says so. The manifesto's refusal is reworded: *we will not guess lineage; we record it where a parser proves it.* *Needs the owner's yes: it amends the manifesto.* |
| A5 | **The trust point is the sink** (contract, certificate). | Yes. Live reads and sink views did not move it: a table still becomes a contract when it lands or is defined. | Kept. The map paints it (Trust lens). |
| A6 | **The agent reads only allowlisted sources and never writes the warehouse.** | Yes. Capability follows accountability. | Kept, and finally *visible*: the Access lens shows the agent's world. |
| A7 | **History is a table of runs under Review.** | As a list, fine. As the way to understand what happened to the project, no. | A run is something that happened to a node: runs move on the map (round 2); History stays as the list. (A time scrubber was considered and dropped: History and verify already answer it.) |
| A8 | **The web app is an authoring surface.** The workbench, drafts, Build panels. | Partly. Authoring moved to agents and laptops. The person's jobs in the app are: set up, approve, read, and see what is covered and trusted. | **The Data workshop is the control tower**: every screen answers "what do I need to know to approve, trust or unblock an agent?" Authoring surfaces stay, but they are not what Data is for. |

## The form: a console (decided 2026-10-27, after the map shipped)

The owner, on seeing the map as Data's home: "This should feel like a console like
AWS, Tableau, Qlik." So the graph, the passport and the lenses stay as data, and the
form is a console: the home is a status board (resource cards with a health pill,
Needs attention from the graph's gaps and unreachable sources, agent access, recent
activity, schedules); every resource list is one table shape (name · type · status
pill · a count · readers · agents · last activity · a row menu, with search, filter
chips and sort in the address); every resource page is one shape (name · type ·
status · actions top right · tabs: Overview, its own, Lineage, Activity, Agents,
Settings). Status is a column and a filter, not a lens. The map is the Lineage view
(`/data/lineage`) and every page's Lineage tab.

## What the map is (now the Lineage view)

One map of the project, read through lenses, with one passport on every piece.

- **Nodes**: sources (connections and input files, with their tables inside),
  transforms, warehouse groups (one per writer, with their tables inside),
  models, reports. **Edges** from facts the API already holds: a source's
  `read_by`, a certificate's `writers`, a model's tables, a report's bindings.
- **Lenses** repaint the same map for one question each. *Coverage* (the
  default: wired on both sides, or a gap), *Flow* (hover lights a path),
  *Freshness* (older than what feeds it), *Trust* (checks and verdicts in the
  locked words), *What agents see* (everything the gateway cannot reach goes
  dark).
- **The passport**: what it is · where it comes from · who reads it (or what it
  writes) · last moved · trust · agents, the same six rows on every node, and
  the node's actions (Open, Zoom to schema, Setup, Refresh, Export). Nothing
  else appears on a reading page.
- **Gaps are drawn**: a file nobody reads, a transform no pipeline runs, a
  table no model reads, a model with no report. Dashed, amber, counted in the
  bar. This is the "what is actually covered" screen.
- **Three altitudes**: the project (the map), the schema (the existing canvas,
  reached by zooming into a model or a writer group), the table (columns and
  rows). The sidebar's Sources · Transforms · Warehouse · Models become jump
  points that open the map with that lane focused; every list keeps its
  address as a search result page.

**One graph, two readers.** The map reads `GET /api/graph`, one function
(`tracebi/graph.py`) that the gateway also serves to agents as
`describe_project`. The person and the agent look at the same picture. That is
the manifesto's "both authors, one contract" applied to the project itself.

## Rounds

1. **Now (GRAPH + MAP):** `tracebi/graph.py`, `/api/graph`, `describe_project`;
   the map as Data's home with the five lenses and the passport; sources as
   tables with Setup behind a button; the source table page's facts pointing
   the right way; gaps drawn. No manifesto change, no pipeline change.
2. **Next:** runs that move on the map, blast radius (select a table or measure; every figure that depends on
   it lights, with its number). Blast radius is read-only: it never starts a run (A3). The time scrubber was
   dropped by the owner (2026-10-27): History and verify already answer it.
3. **Then:** SQL column lineage in the certificate (A4) if approved, drawn on
   the map from source column to figure; the agent's proposals as dashed nodes
   with approval on the passport; build by dragging (drop a file, drag a source
   onto a transform, tick a table for agents).

## What this does not change

The locked language. The sink boundary for pandas. The gateway's read-only
warehouse. Every address that exists today (lists stay as search results; the
old ones redirect as they already do). The connection builder, the allowlist,
the schema canvas and the table grid, all of which the map reuses.
