### Added — Download a built report as PDF

- `tracebi report build <name> --format pdf` writes `output/<name>.pdf`
  beside the HTML: a print of the built page by headless Chromium, so
  charts render. The PDF carries no receipt; the HTML and its manifest
  stay the checkable artifact. The same print is
  `GET /api/reports/{name}/download?format=pdf` (the last build) and
  `build_report(format="pdf")`. Needs `pip install 'tracebi[pdf]'` and
  `python -m playwright install chromium`.
