### Added — Excel over the gateway

- `build_report(..., format="xlsx")` writes `<name>.xlsx` beside the HTML
  and manifest. The spreadsheet carries no receipt and is not verifiable;
  the result says so and points at the HTML and manifest.
- `fetch_artifact` returns that workbook base64-encoded, with the
  spreadsheet media type. Every other suffix stays refused.
