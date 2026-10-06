### Changed — `tracebi dev` opens the app; `--classic` keeps the old preview

- `tracebi dev <name>` now opens the web app on that report with Build mode on
  (what `tracebi dev <name> --app` did; `--app` still works and is now the
  default). `tracebi dev` with no name opens the app on Reports, where what your
  agent shows you lands before any report exists. The server runs in dev mode on
  `127.0.0.1` only, port 8001 unless `--port` says otherwise.
- `tracebi dev --classic` is the old stdlib preview server and its `/__workbench`
  page, for both forms. It is also what runs, with a one-line note naming
  `pip install 'tracebi[web]'`, when the web extra is not installed. `tracebi serve`
  is unchanged.

### Added — the Build panel shows what only the classic page showed

- **Data**: each binding the report reads, with its model, rows × columns, the
  figures that use it, and a few rows. **Checks**: figures with no data behind
  them, bindings no figure reads, and numbers typed outside figures; it says all
  clear when there is nothing to point at. They point; the final build enforces.
- **A note box** (the classic page's "Leave note"): what you type is a pin your
  agent reads with `workbench_state` and resolves as before.
- **The project feed**: with no report open, Reports shows your agent's exhibits
  and your notes to it, in dev mode only (`GET /api/workbench/project`, `POST
  /api/workbench/project/note`; 403 otherwise). While the dev app is up,
  `tracebi.workbench.show()` from any script in the project posts there with no
  setup, as it did under the classic discovery mode.

Still only on the classic page: the Warehouse, Models and Packages panels, a copy
address and pin per figure, "Keep this" on an exhibit, and the quick-chart picker.
