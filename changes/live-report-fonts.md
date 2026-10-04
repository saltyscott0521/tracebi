### Live-view report fonts

Reports opened in the web UI, at `/r/<name>`, or under `tracebi dev` use
**Source Sans 3** / **Source Code Pro** (vendored under
`tracebi/reports/assets/fonts/`). Built `output/*.html` files and HTML
downloads stay on the offline `system-ui` stack — no font bytes in the
artifact.
