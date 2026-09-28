### Fixed

- `tracebi dev`: the file watcher now stops when the server stops. Its stop
  event was never set, so an in-process caller that shut the server down kept
  a thread polling (and re-rendering) paths relative to whatever directory the
  process moved to next.

### Changed

- The test suite leads with end-to-end journeys (`tests/e2e/`): the analyst
  loop, the reference project, the web app, the MCP gateway, scheduling,
  pipelines and the dev workbench, each driving the real entry points. 247
  low-value unit tests went; coverage rose from 85% to 86%. See
  `docs/architecture/test-suite-review.md`.
