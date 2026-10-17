### Changed — the report page is the report

- A report's page (`/reports/<folder>/<slug>`) is the artifact as delivered,
  full width, under a slim header: the breadcrumb (Reports › the model's
  label), the report's name, the app's verdict chip and the build time. When
  the verdict asks for a look, its detail is one line under the name (no
  coloured bar).
- One command bar. Left, for everyone: **Open** (the build in a new tab,
  `/r/<name>`), **Share** (copy the link), **Export** (HTML with receipt ·
  Excel · PDF, and the line that only the HTML carries the receipt). Right:
  **Rebuild** and **Edit as a draft** for an analyst or admin, **Build** in dev
  mode, then **About this build**. A command the role cannot use is not
  rendered (`/api/me`; with no sign-in everyone is admin). On a phone the bar
  is Open · Share · "…", a menu of the rest.
- One panel, **About this build** (a sheet from the bottom on a phone), with
  four tabs:
  - **Receipt**: whether the check still holds (when it was checked, why if it
    does not reproduce, **Check again**), the model, the figures, the schedule,
    the kind; then the build's own certificate, drawn by its own `tracebi.js`
    (`renderReceipt`) and `tracebi.css` in a sandboxed frame, its chip in the
    app's verdict.
  - **Lineage**: as before.
  - **History**: every build of the report from the run store (`/api/runs?target=`:
    the app, `tracebi report build`, schedules), each with when, how long, who,
    and its verdict (the newest build the page's, older builds Not checked),
    and a link to all of them in History.
  - **Files**: the report's files, read-only with Copy, and how to edit them
    (the old Code tab). The Data page's Reports-stage preview keeps its Config
    view until Step 3 retires that preview.
  Details, Code and the amber bar are gone. Build mode still replaces the panel
  while it is on.
- The report's masthead chip says what the app's check found. The app tells
  its frame `{type: "tracebi:verdict", state, detail}` (the state `verdictOf`
  computed, nothing while it has none, never for Build mode's working preview);
  `tracebi.js` shows it on the masthead chip and in the drawer. Outside the app
  (the file, `/r/`, an email) the chip stays what the file can say, Not
  checked; a draft stays Draft whatever it is told. The model's Reports-stage
  preview gets the same message.
- A receipt read inside the app's frame names the built file in its "how to
  check" line instead of `srcdoc.html`.
