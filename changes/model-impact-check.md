### Added — an impact check before a model is published

- Publishing a model draft first re-runs the recorded queries of every
  published report that reads it, from each report's last build, against the
  draft. Each report is `unchanged`, `moves` (the figures, old and new),
  `breaks` (the query no longer runs, with the error) or `not_built` (listed,
  never counted unchanged).
- A model that moves or breaks reports is refused (HTTP 409, MCP `ok: false`,
  both carrying the impact) unless the publish passes `accept_impact: true`.
  A break needs accepting too. The accepted impact is recorded in the publish
  run's detail.
- The check stands alone: `drafts.model_impact(owner, path)`,
  `GET /api/drafts/{owner}/models/{path}/impact` and the MCP tool
  `model_impact`. The gateway now has 20 tools.
