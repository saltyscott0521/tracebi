### Added — a browser smoke of the real app

- Optional extra `e2e` (`playwright`). CI job `ui-smoke` builds the UI and
  opens the Desk, `portfolio_showcase`, its Source tab, and the HTML download.
  `pytest tests/` skips `tests/test_ui_smoke.py` unless `TRACEBI_E2E=1`.
