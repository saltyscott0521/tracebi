### Fixed — gateway replies that schema-checking clients rejected

- MCP clients that check results against the tool's declared schema rejected
  most gateway replies; now they don't. A field the tool left unset was sent
  as null, and the schema said that field was a string, number, or list, so a
  successful query, build, verify, or workbench read looked like a failure.
