### Fixed — a built report lays out at a phone's width

- A built page that names no viewport now gets
  `<meta name="viewport" content="width=device-width, initial-scale=1">`.
  Without it a phone laid every report out 980px wide and shrank it, so the
  stylesheet's narrow-screen rules (the stacked KPI strip, the receipt sheet,
  tables scrolling in their frame) never applied on a real phone, from the
  share link, a download or an email. A template's own viewport meta is kept.

### Added — the UI audit renders every report

- `scripts/ui_audit.py` opens every report as delivered (`/r/<name>`) at 1440
  and 390 wide, light and dark, into one `report-sheet.png`, and counts per
  project the font families, accents, resting shadows, gradients and looks
  (display face + accent) its reports use; `--baseline` refuses a count that
  grows or a new look. Baselines for the reference project and the demo app
  are in `docs/architecture/`.
