### Changed — Reports opens on "At a glance"; Workflow is part of Get started

- Before a report is opened, Reports shows how many reports there are, how
  many of their last builds reproduce, what needs a look, and the latest
  builds (each opens its report) instead of a blank "Pick a report" pane.
- On a phone, an open report's name is the page heading.
- The Workflow page is now "The three phases" on Get started; `/workflow`
  lands there. Its phase colours read in dark mode.
- `scripts/ui_audit.py` builds every report before it crawls, so it checks
  the app with receipts and verdicts on screen, not only the empty states.
