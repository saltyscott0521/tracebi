### Added — `tracebi mcp` can bind a host

- `tracebi mcp --transport http --host` defaults to `127.0.0.1` and is
  passed to the server. `--insecure` on a non-loopback host refuses to
  start unless `--allow-insecure-bind` is also passed.
