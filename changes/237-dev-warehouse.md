### Fixed — re-running a transform while the dev app is open

In dev mode the app lets go of the warehouse after each request, and a write waits
briefly for another process's read, so `tracebi run-transform` works with the app open.
