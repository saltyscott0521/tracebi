# Navigation v3 — Docs as a place, Data as the chain

**Status: built, 2026-10-21; Data reshaped as a board on 2026-10-23 (v3.1,
below).** Follows the 2026-10-17 plan (the four places) and the three rounds of [Live reports — the plan](live-reports-plan.md). Two things the
maintainer named after using the app: the docs are hidden behind a small
"Help" link at the foot of the sidebar, and from the Data place it is hard to
see what is available, database by database, table by table, on the way to a
model. This round fixes both without reopening the four-place structure.

## What is wrong, from the captures

1. **Docs are not a place.** `/handbook` and `/getting-started` are reached
   only from "Help" at the bottom of the sidebar, in 12px. The handbook is
   the product's manual (concepts, guides, reference) and every role needs it.
   Its own index still lists "Receipts", a retired word.
2. **Sources have no entry.** `/data/sources` exists (every connection, with
   "where the data lives" and "used by"), but nothing in the frame leads
   there except a tab inside one model's page. A connection's detail does not
   say which tables it holds, and "Used by: no model reads from this
   connector" is false in spirit for `crm`: the transform reads it.
3. **The Data landing is a list of models.** The useful picture, which the
   per-model page already draws as a stage line (Transform → warehouse →
   Model → Reports), is missing its first stage (the sources the transform
   reads) and is not visible at the level of the whole project.
4. **The warehouse has no page of its own.** Its tables are reachable only
   through a connector's "Warehouse" button. Which transform wrote a table,
   which model reads it and whether its contract holds is the question an
   operator asks first.

## Decisions (closed)

1. **Docs becomes the fifth place**, visible to every role, last in the
   sidebar: `Docs` at `/docs` (today's `/handbook` content; `/handbook` and
   `/getting-started` redirect). Its left nav starts with **Get started**
   (today's getting-started page), then Concepts, Guides, Reference. The
   sidebar foot keeps only the version, the update badge and the theme
   toggle. The ⌘K palette searches docs titles too.
2. **Data is organised as the chain, left to right: Sources → Warehouse →
   Models → Map.** Four tabs at the top of `/data` (the same tab strip the
   model page uses), each a page with its own address:
   - `/data` (**Models**, default, as today's list) — every model as a chain
     row: `sources → transform → warehouse tables → model → reports`, each
     segment a link and a count ("2 sources · holdings_transform · 7 tables ·
     15 measures · 6 reports"), with the existing status chips.
   - `/data/sources` (**Sources**) — every connection and the project's
     `inputs/` folder. A connection's detail gains **Tables**: what the
     database or file holds (`list_tables` + `column_schema` through the
     connector, lazily, read-only, only when its `${VAR}` resolves; otherwise
     "Not connected here: set TRACEBI_CRM_URL" with no error), and **Read
     by** replaces "Used by": the transforms that name it in a `-- source:`
     line (parsed from the transform files, with the table), the medallion
     layers whose source it is, and the models that read it directly.
   - `/data/warehouse` (**Warehouse**) — the project's warehouse on its tier
     (`tracebi.yaml`): every table with rows, columns, the transform that
     wrote it (from the certificate), the models that read it, and its
     contract status (`satisfied / stale / no contract`) and, where the
     certificate records one, the external source it was fed from
     (`crm.issuer_ratings`, fingerprint, or `snapshot`). One page per
     warehouse when a project has several connectors of the warehouse kind.
   - `/data?view=map` becomes `/data/map` (**Map**), unchanged in content.
3. **A model's stage line gains stage ⓪, Sources**: the connections and
   input files its transform reads, before Transform. Clicking it opens
   `/data/sources` filtered to them.
4. **Roles unchanged**: Data stays admin-only; Docs is for everyone. (Since
   2026-10-23 Data is for analysts and admins: `minRole` in `web/ui/src/nav.js`.) Older
   addresses redirect (`movedTo`).
5. **Words**: "Sources" for connections and input files, "Warehouse" for the
   sink, "Models" for the contracts. No new nouns.

## Package

**N-1** (one agent): `web/ui/src/nav.js` (PAGES gains `docs`; `DATA_TABS`;
`dataPath` grows a `warehouse`/`sources`/`map` form; `movedTo` for
`/handbook`, `/getting-started`, `/data?view=map`), `Layout.jsx` (the fifth
item; the foot), `pages/Docs.jsx` (Get started first; the docs index stops
naming receipts: `docs/index.md` and the concepts folder entry are renamed
to the trace, `receipts.md` redirects to `trace.md` in the reader), a new
`pages/Warehouse.jsx` and the Sources detail's Tables + Read by sections,
the chain row in `pages/Data.jsx`, stage ⓪ in the model page's line; the
API: `GET /api/connectors/{name}/tables` (lazy, read-only, resolves the
connection only on request; 200 with `{connected: false, reason}` when the
variable is unset), `GET /api/warehouse` (tables with rows, columns,
written_by, read_by, contract, source), `GET /api/connectors/{name}` gains
`read_by: {transforms: [{name, tables}], layers: [...], models: [...]}`;
`web/ui/src/nav.js` tests and the web journey cover each address and the
role tiers; `scripts/ui_audit.py` crawls the new pages; captures of every
new page at 1440/390, light/dark; vocabulary + guides mention `/data/sources`
and `/data/warehouse` where they describe the app; CLAUDE.md's API Routes
and the `GET /` line (five places) via the orchestrator.

## v3.1: the board (2026-10-23)

The owner, after using Data: some models' first node read "pipeline" and
others a transform's name, sources sat after models, and the four tabs did not
say how the data moves. Data now opens on **Flow**, a board of five lanes
(⓪ Sources, ① Transforms, Warehouse, ② Models, ③ Reports) with wires between
the cards; the tabs follow the flow: Flow (`/data`), Sources, Transforms (new,
`/data/transforms`), Warehouse, Models (the chain rows, now `/data/models`).
The Map is gone: its picture is the board, and a model's map is the model
page's line (`/data/map` and `/data?view=map` redirect). The decision, the
lane and edge rules: [Data as a flow: the board](data-flow-board.md).
