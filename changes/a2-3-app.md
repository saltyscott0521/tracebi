### Changed — the app, audit pass 2 (A2-3)

- **Data, Model tab.** The views (Diagram · Tables · Measures · Relationships ·
  Storage · Code) are one segmented row in the card's header, with Edit as a
  draft at the row's right; nothing floats above an empty band. The
  "1 FACT · 2 DIMENSIONS · 13 MEASURES" and "3 TABLES" badges are gone (the
  line above says both). The grain reads "Grain: fund · issuer · sector"
  (the labels Ask and the reports use), the identifiers in its title. On a
  phone the row scrolls sideways in one line and Tables (the diagram's list
  form) opens first.
- **Data, Transform tab.** The card is titled with its model's label (the
  pipeline's identifier in the title). A model pipeline's steps read
  "Transform · ran 2 h ago · wrote 3 tables" and "Build · ran 2 h ago ·
  6 reports" in the sans, the step's name in small mono beneath, drawn at the
  app's size rather than zoomed to fill the card. Table checks are chips in
  the verdict's shape and sentence case ("Checks passed", "Changed since
  checked", "No checks"), a new `Chip` in `Shared.jsx` on the `.verdict`
  classes. On a phone the Steps table drops Schedule and Runs after so the
  status shows.
- **History.** One row per report or pipeline, its newest run, with
  "N older runs" (and "· N failed" when any did) folding the rest inline
  under the day headers. "Every run" (`/runs?all=1`) lists them flat; a
  report or pipeline picked in the filter lists all its runs. The report
  page's History tab shows the newest build and folds "N older builds" the
  same way. An empty cell's dash is muted.
- **Map.** Models and reports go by their labels (identifiers in the title),
  measured in the sans so the boxes fit them; transforms keep their file
  name; "shared with" and the readout name models and reports by label.
- **Library.** A description wraps to two lines at every width, all of it
  in the title.
- **Sidebar.** The "Analytics trust layer" tagline under the logo is gone.
