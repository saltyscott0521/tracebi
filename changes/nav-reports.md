### Changed — the Reports stage is a list beside the last build; an open report is a page

- On a model's Overview, the **Reports** stage is the list (search, **All**,
  **Needs a look**, **Scheduled**) and, beside it, the report you picked:
  **Preview** shows its last build as readers see it, scaled to fit and
  read-only; **Config** shows the files that define it, read-only, with **Edit
  as a draft**. **Open** gives the report the whole page. The pick is in the
  URL (`?r=<report>`, `&open=1` for the page), so a link can name one; under
  1100px there is no preview and a row opens the report.
- Each row says its report's name as authored, a line about it, when it was
  last built and when it is scheduled, in words (`Mondays 07:00`). Only an
  exception is marked, with words and a glyph: `△ Source changed`, `○ Never
  built`. Under the list one sentence says the built reports re-run to the same
  numbers (and when that was checked) only when they all do; otherwise it says
  how many do not and why.
- Looking at a report never builds it. A report with no build says `○ Never
  built` and offers **Build it now**; before, opening it built it as a side
  effect of a read.
- An open report is a page of its own: no sidebar, one light bar (back to its
  model, its name, when it was built and `△ Source changed since` if so, then
  **Rebuild**, **Share** and **More**) and the report on the rest of the screen.
  It scrolls inside its own frame, so each figure's receipt drawer opens where
  you are looking. **More** holds the downloads (HTML, Excel, PDF, each with
  its caveat), **Lineage and manifest**, **Code**, **Check it again**,
  **Schedule** and **Past builds**, which open over the report. The tab row
  (Output, Lineage, Manifest, Code), the Full screen button and the green run
  badges are gone.
