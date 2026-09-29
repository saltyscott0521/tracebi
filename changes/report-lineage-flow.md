### Changed

- **A report's Lineage tab is now a layered flow**: transform → stored tables → model → queries → figures, read from the last build's receipt instead of re-running the report. It replaces the raw chain of every step of every query (78 nodes and 77 edges for the housing report, the same `load` repeated per query) with one node per table, model, query and figure group (28 nodes).
- Select a node to trace it: its upstream and downstream light up, and a figure lights only the tables its own query read. The detail below shows a table's connector, where it is stored, rows read and fingerprint; a transform's sink contract and what it states; the model's joins (with a link to the Data model page); a query's definition and steps; and the figures in a group.
- A python-derived query is drawn dashed and marked as unreplayable; figures typed in without a query are shown apart. The graph says where lineage stops: at the sink.
- `GET /api/reports/{name}/lineage` returns `{report, built_at, flow}` (`flow` has `columns`, `nodes`, `edges`, `notes`, `summary`); the old `combined_graph` and per-section `sections` are gone. Per-step chains are on each query node's detail.
