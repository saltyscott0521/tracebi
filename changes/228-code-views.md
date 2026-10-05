### Added — see the code behind a page

- A **Code** tab (or **View code**) on Data model, Refresh and Sources shows the
  file that defines what you are looking at, read-only, with line numbers and
  Copy: the model's file; the pipeline file and the transform it runs (one tab
  each); the model file(s) that declare a source's connector. Something
  registered in Python code, with no file, says so instead of showing nothing.
- **Explore** shows the query you just ran as code, two ways: Python
  (`model.query(...)`) and a `report.json` data binding to paste into a report.
  Both are built from the request Explore sent.
- The Reports tab that was called "Source" is now "Code", and uses the same
  viewer, so every page says the same thing.
- `GET /api/models/{name}/source`, `…/connectors/{name}/source`,
  `…/pipelines/{name}/source` (viewer, like a report's `/source`): the files come
  from where discovery found them, never a path in the request, cut at 256 KB.
