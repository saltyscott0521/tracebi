# Data as a flow: the board

**Status: built, 2026-10-23** (package U-10). Follows [Navigation v3 — Docs as a place, Data as the chain](nav-v3.md).

## The decision

The owner looked at Data (Models · Sources · Warehouse · Map) and asked why
some models' first node read "pipeline" and others not, and said sources
came after models when they come first. A mockup of one board, read left to
right in the order the data moves, was approved as drawn ("I like the board,
build it"). Data now opens on that board, and the lists sit behind it in the
same order:

| Tab | Address | What it is |
| --- | --- | --- |
| Flow | `/data` | the board; `?model=<m>` opens it with that model's path lit until the pointer moves |
| Sources | `/data/sources` | every connection and the `inputs/` folder (unchanged) |
| Transforms | `/data/transforms` | new: every file in `transforms/`, its form, the models it feeds, its contract file, when it last wrote, and Run (admin, when a pipeline runs it) |
| Warehouse | `/data/warehouse` | every table, grouped by its writer (unchanged) |
| Models | `/data/models` | the chain rows that were `/data` |

The Map is gone: the board is the picture, and a model's own page draws its
line. `/map`, `/data/map` and `/data?view=map` land on `/data`; with
`model=<m>` they land on `/data/<m>`.

## Three notes from the mockup

**Why the first node read "pipeline".** The chain named the implementation: a
SQL transform by its file, a Python medallion runner (a pipeline with no
transform file) as "pipeline". The stage is always the transform; the
mechanism is a chip. A transform is named by its file with its form beside it
(SQL, Python, notebook); a medallion runner reads "pipeline" with a Python
chip, in the same slot.

**Why sources come first.** The tabs follow the flow. Transforms get a list of
their own (before, they were reachable only through a model), and the landing
page is the picture.

**What stays.** A model's own page, its line and tabs, the table page, the
Sources panel with credentials, the Warehouse list grouped by writer. The
board is the way in; each card opens the page that already exists.

## The lanes

- **⓪ Sources**: one card per connection that is not a warehouse, then one
  per input file a transform reads (`/api/inputs` `read_by`), leaving out a
  file a connection already stands for (a SQLite file under `inputs/`). A
  mark and a chip for its kind (from the connector's dialect, or the file's
  extension), whether it connects here (the Sources tab's own answer,
  `/api/connectors/{name}/tables`; a file has no such state), and where it is.
- **① Transforms**: one card per transform in the flow, that is, one a
  pipeline runs or a certificate says wrote tables (`/api/transforms`). Any
  other file (the pandas twin of a SQL transform) is counted under the lane
  and listed on the Transforms tab.
- **Warehouse**: one card per warehouse (`/api/warehouse`), a group per
  writer, its tables as tags. A green dot means the sink satisfied its
  contract on the run that wrote the table (`contract.status ===
  "satisfied"`); stale or no contract has no dot. Stale never reads green.
- **② Models**: label, identifier, tables, measures.
- **③ Reports**: in model order; "dashboard" (`app.jsx`) or "page"
  (`template.html`), and the models it reads.

## The edges

Drawn only from facts the API already gives: source → transform (`read_by`),
transform → its writer group (the certificate's `writers`), group → model (the
models that read the group's tables), model → report (`reportModels`). A wire
ends at the writer group, not the middle of the warehouse card, so which
transform fed which model reads off the board. Hovering or focusing a model
lights its reports, the groups holding its tables, the transforms that wrote
them (and the one its pipeline runs), the sources those read, and the wires
whose two ends are lit. The lighting is presentation only: every card is a
link either way. When the board is narrower than 980px (its own width, a
container query, since the sidebar takes part of the window) the lanes stack,
no wire is drawn and nothing fades; with reduced motion nothing animates.

Nothing on the board claims a number is right.
