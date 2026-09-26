### Fixed

- Live discovery no longer drops an app module's own reports. With `TRACEBI_APP=tracebi.web.demo_app`, the demo's reports (`sales/medallion_revenue`, `wealth/aum_by_branch`, `wealth/aum_by_region`) vanished from a running server a few seconds after startup, because the watcher read them as deleted from the project's `reports/` folder they never lived in.
