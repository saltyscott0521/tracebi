### Changed — build output reads in the project's terms

`tracebi report build` (and so a refresh's run log) prints the built file and its
manifest relative to the project, e.g. `output/sample_model/sample_dashboard.html`,
instead of the full machine path. A file written outside the project still prints
in full.
