### Added — report schedules can run inside the web server

- `TRACEBI_SCHEDULES_IN_SERVER=1` starts each package's `schedule` block
  when the server starts, with the same job as `tracebi schedule serve`,
  and stops it on shutdown. Off by default. It assumes one process: several
  workers would each send the email. A missing APScheduler fails startup
  with `pip install 'tracebi[pipeline]'`.
