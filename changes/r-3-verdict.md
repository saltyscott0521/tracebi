### Changed — one trust vocabulary in the app

- A `Verdict` chip (`web/ui/src/components/Shared.jsx`) says whether a
  report's numbers still hold, in the artifact's words and colours:
  Reproduces (green), Needs a look (amber), Does not reproduce (red), Not
  checked (neutral), plus Draft (dashed) and Never built (hollow dot) where
  the app needs them. It is the app's copy of the artifact's `.tb-verdict`.
- One rule derives the state, `verdictOf` in `web/ui/src/verdict.js`, from
  the desk's re-check (`/api/desk` `builds`), the report's `last_change`
  (`/api/reports`) and, on an open report, its receipt's
  `transform_contracts`:
  - no build: Never built;
  - the re-check did not reproduce: Does not reproduce;
  - the report's files were saved after the build ("Source changed since this
    build"), the data changed (`source_drift`), the check could not run, or a
    verdict the app does not know: Needs a look;
  - a table it reads was past its sink checks when it was built ("Checks
    stale"): Needs a look;
  - numbers from `report.py`, nothing recorded, or built by a newer TraceBi:
    Not checked;
  - otherwise the re-check's Reproduces. Nothing else is ever green.
- Used everywhere a verdict shows: the report rows and "Latest builds" on
  Reports, the model's report list and its preview header, the open report's
  header (the chip opens Details) and its bar, Details ("Numbers", with
  "checked …" and why), History's Verdict column, the Needs attention strip,
  the Overview line's counts and the Map. So a source changed since the build
  reads Needs a look in all of them at once.
- The sentence under a model's list is led by the chip of the worst build:
  "All 6 built reports reproduce", or "5 of 6 built reports reproduce. 1
  needs a look." The "At a glance" tiles count Reproduces, Needs a look,
  Does not reproduce (when any) and Never built.
- Build mode: a figure backed by a re-runnable query no longer carries a
  green "REPRODUCIBLE" badge. `tracebi.js` gives it the small verdict chip
  with the file's own state: Draft on a working preview, Not checked on a
  built file. Python-derived and unverified figures keep their badges.
- Removed: the "Source changed", "Doesn't reproduce", "Check failed",
  "Nothing to check" and "Newer build" labels, the "△/✕/○" flags on report
  rows, and the `.tb-badge--verified` style.
