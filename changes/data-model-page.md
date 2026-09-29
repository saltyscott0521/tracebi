### Changed

- **"Contract" is now "Data model"** in the sidebar, command palette and Getting Started (sink contracts keep their name, on the Verify page and in reports).
- The Data model page draws its diagram from what a model **declares**: each fact's `foreign_keys` become many-to-one joins to its dimensions, and roles (fact, dimension, both) come from `add_fact` / `add_dimension`. Before, the diagram came only from `add_relationship`, so a model written the recommended star-schema way had no diagram at all.
- Tables in the diagram list their columns with types, keys first: `PK` on a dimension's key, `FK` on a fact's foreign keys, `Σ` on its measure columns. Click a table to preview its rows. A model with joins opens on its diagram.
- A **Measures** tab lists every named measure with what it is (aggregate, ratio of totals, rank, share, running total, and so on) and how it is defined. The Relationships tab now shows the declared joins too.
- `GET /api/models` also returns each model's `facts`, `dimensions` and `measures`, so the list reads "1 fact · 2 dim · 13 measures" instead of "0 rel".

### Fixed

- The Docs page in the container image was always empty: the package is pip-installed, so its "docs next to the repo" fallback pointed into `site-packages`. The image now sets `TRACEBI_DOCS_DIR=/app/docs`.
