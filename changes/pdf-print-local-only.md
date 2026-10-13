### Security — printing a report to PDF loads nothing from the network

- `tracebi report build --format pdf` and the PDF download open the built page
  in a headless browser on the server. That browser now refuses every request
  that is not `file:`, `data:` or `blob:`, so a report's own script cannot send
  it to an internal address and have that page printed.
