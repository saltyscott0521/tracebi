### Added — warehouse table columns from metadata

- `tracebi warehouse tables` and the MCP tool `describe_table` list a
  warehouse's tables and one table's column names and types. Both read
  connector metadata and do not scan rows. A connector that raises is
  reported in place (`error`: exception type plus the first message
  line); the others still list.
