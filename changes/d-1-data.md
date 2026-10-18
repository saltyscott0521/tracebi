### Changed — Data is one page per model, with the line as its header

- `/data` lists the models, one row each: the model's label (its identifier
  beside it, small and in mono), "N tables · N measures · N reports", its
  built reports' verdicts as chip counts ("4 reproduce", "1 needs a look",
  "1 never built"), and when its data was last refreshed. On a phone each row
  is a card. A **List | Map** toggle draws the same models as one picture
  (`/data?view=map`, zoom with `&model=<m>`); `/data/map` and `/map`
  redirect there. In dev mode the project feed sits below, folded under one
  line.
- `/data/<model>` leads with the model's label (identifier beside it) and one
  line, "Defined in models/x.yaml · reads data/warehouse.duckdb", then the
  line, compact: Transform · Model · Reports, the warehouse file and the
  measures between them, and the reports' verdicts as chip counts on the
  Reports station. Transform and Model select their tab; Reports opens the
  library narrowed to the model (`/?model=<m>`). Then four tabs, each with
  its address: **Model** (`/data/<m>`: diagram, tables, measures,
  relationships, storage, code), **Transform** (`/transform`: flow, steps,
  runs, code, what it produces), **Sources** (`/sources`: the sources this
  model reads) and **Runs** (`/runs`: History narrowed to the model, linking
  to History). The tabs scroll sideways on a phone; the Transform flow opens
  on its list of steps there.
- **Refresh data** is the Transform tab's one primary action and appears
  nowhere else on the page. It, Run all and every per-step run button render
  only for an admin (no sign-in: everyone is admin); a viewer or analyst sees
  the flow and its status without them.
- The model's Reports stage, with its split preview and Preview/Config
  switch, is retired: `/data/<m>/reports` redirects to the library
  (`?r=<name>` to the report's page).
- The Map draws its nodes with the line's node (`LineNode`): one card, one
  pill, and the same marks; a report's state is the verdict chip (Never
  built, Needs a look, Does not reproduce), a failed transform or a table
  past its checks a flag. The Map's own node styles are gone.
- Words: "DuckDB file" (not `DUCKDBCONNECTOR`), "Not run yet" (not "never
  run"), no "STEP" chip in the flow, warehouse tables "checks passed",
  "changed since checked" or "no checks" ("The sink satisfied its contract"
  stays where it is the claim); model labels where identifiers were.
- `/m/<m>/sources` now lands on the model's Sources tab.
