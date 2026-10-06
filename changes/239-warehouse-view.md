### Added

- Sources has a **Warehouse** view for a file-backed DuckDB source: every table with its row count, a collapsed column profile, and its sink-contract status (satisfied, stale or no contract). Stale and uncovered tables never read green. Behind it, `GET /api/connectors/{name}/warehouse` opens the file read-only and closes it within the request.
