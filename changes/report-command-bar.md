### Changed — an open report looks like a BI report page

- The app's nav stays beside an open report as a slim icon rail (the full menu
  opens over it; on a phone it is a Menu button).
- The page has a two-row header (model › Reports, then the name, an exception
  chip only when something is not fine, and when it was built, when the data was
  last refreshed and its schedule) and a toolbar of labelled commands:
  **Rebuild**, **Export** (PDF, Excel, HTML; only the HTML carries its receipt),
  **Share** (copy the link) and **Edit as a draft** on the left, **Lineage**,
  **History** and **Details** on the right. The **More** menu is gone.
- Those three open a panel docked beside the report (a drawer over it on narrow
  screens): **Details** (the re-run check with Check again, each table's sink
  contract, model, figures, schedule, files), **Lineage** (stage by stage, with
  the full graph and the manifest download), **History** and **Code**. It
  remembers whether it was open.
- A build that is not fine gets a bar under the toolbar saying so in words, with
  Rebuild and Details; a fine one shows nothing.
