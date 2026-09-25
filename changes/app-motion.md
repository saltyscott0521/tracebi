### Added — motion and illustrations in the web app

- The web app has motion and illustrations, each one showing something
  TraceBi does:
  - The sidebar logo draws itself on load: brackets, rising bars, and a trace
    dot running across. It replays on hover.
  - **A report assembling itself**, drawn in SVG: the numbers, bars, trend
    line and donut build in. It is the Reports page's empty state, and a
    looping version replaces the spinner while a report opens or rebuilds.
  - **Verify:** the drop zone shows a report and its manifest linked, with data
    running between them. A scan beam and a ticking fingerprint play while
    the file is checked. The verdict lands like a stamp, and an altered file
    shudders. The stamp replays on every check.
  - **The workflow diagram:** data packets travel the arrows left to right,
    the freeze points shimmer like frost, and the phases rise in turn.
  - Report lists rise in with a stagger, and folder carets turn.
- A global `prefers-reduced-motion` switch turns all of it off. The app had
  none before.

### Fixed — the Verify page no longer claims files stay on your machine

- The Verify page said "The data never leaves this machine". The check runs
  on the TraceBi server, so on a hosted server the file is uploaded. It now
  says the files are checked by this server, which keeps nothing, and that
  is what the endpoint does.

### Changed — the app says "receipt" much less

- The app says "receipt" much less. The Reports page reads "Pick a report" and
  the download button is **↓ HTML**. The "🧾 Verifiable artifact" badge is now
  **Verifiable**, and the attention labels and the workflow diagram drop the
  word. The Verify page calls the second file what it is, the
  `.manifest.json`.
