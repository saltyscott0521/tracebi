### Fixed — a pipeline run from the app no longer fails on a passing read

- A transform's write now waits (up to `DuckDBConnector.WRITE_LOCK_WAIT`, 10s)
  for a read-only warehouse handle in the same process, as it already did for
  one in another process. The web app opens a short read-only handle per
  request (the model page's warehouse status); one landing between the
  pipeline releasing its models and the transform's write failed the run with
  "another tracebi process holds the warehouse open", intermittently.
