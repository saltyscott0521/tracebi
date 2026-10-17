### Changed — the app opens on the library; four places in the sidebar

- `/` is the library: every report the person may see, grouped by folder
  under its model's label (My published first when signed in). Each row is
  the report's name (`display_name`), one line of its description (two on a
  phone, the rest in its tooltip), its verdict chip, when it was built, and
  its schedule in words. The row opens the report. Above the list: a slim
  "At a glance" strip (N reports · N reproduce · N need a look · N never
  built, plus Does not reproduce / Not checked when any), a chip per model
  with its count (`?model=<name>` in the URL), and a search over name,
  path and description. No Rebuild or Refresh here; the form badge
  ("Custom", "JSON spec"), owner, last run, build count and "Latest builds"
  are gone from the list.
- A folder's permissions are a small "Permissions" disclosure at its
  header, shown only where they differ from the rest of the library: a
  `_folder.yaml` applies, it is a personal folder, it accepts only
  checkable reports, or the person's level there is not their usual one.
  With no folder file, nothing is said.
- The sidebar is four places: **Reports** (`/`), **Ask** (`/ask`), **Data**
  (`/data`), **Review** (`/review`), then Help in the footer. The model
  switcher is gone from the sidebar: a model is a chip on Reports, a card or
  the path on Data, and Ask's own pick. The ⌘K palette lists the four
  places, then History, Verify a file, Map and Help; models and reports by
  their labels. On a phone the header names the place instead of the model.
- A report's page is `/reports/<folder>/<slug>` (each segment encoded);
  `tracebi dev <name>` opens `/reports/<name>?build=1`. Its breadcrumb is
  Reports › the model's label, and its title is the report's name.
- Ask (`/ask?model=<name>`) is the query builder (Explore) with a Model
  pick; with no model it lists them. Data is the models (`/data`), one
  model's line (`/data/<model>`, opening on its Model stage), its stages
  (`/data/<model>/transform|model|reports`), the Map (`/data/map`) and
  Sources (`/data/sources`). Review (`/review`) is Drafts with History and
  Verify a file linked at the top; `/drafts`, `/runs` and `/verify` keep
  their addresses and mark Review as current. History takes
  `?model=<name>`.
- The "Needs attention" strip moved from the library to Review. Your notes
  to the agent and "From your agent" left the library: per report they are
  in Build mode's panel, as before; the project feed (no report open) is on
  Data in dev mode, and `tracebi dev` with no name opens `/data`.
- Every older address redirects, query kept (`movedTo` in `nav.js`):
  `/reports?r=<n>`, `/?r=<n>` and `/m/<m>/reports?r=<n>` → `/reports/<n>`
  (`&build=1` kept); `/m/<m>/reports` → `/?model=<m>`; `/m/<m>` →
  `/data/<m>`; `/m/<m>/model|transform` → `/data/<m>/model|transform`;
  `/m/<m>/refresh|sources` → `/data/<m>/transform`; `/m/<m>/explore` →
  `/ask?model=<m>`; `/m/<m>/runs` → `/runs?model=<m>`; `/models` → `/data`;
  `/models/<m>?tab=…` → Data, Ask or the library; `/explore` → `/ask`;
  `/sources`, `/connectors` → `/data/sources`; `/map` → `/data/map`;
  `/refresh` → `/data`; `/pipelines?model=<m>` → `/data/<m>/transform`;
  `/reports` → `/`.
- `scripts/ui_audit.py` crawls the new addresses (and the old ones, which
  must land), checks `scope-mismatch` on `/?model=<m>` by the rows'
  `data-report`, and counts the rail's current entry on an open report.
