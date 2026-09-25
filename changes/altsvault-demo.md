### Added

- **A live AltsVault pipeline in the demo app.** The Refresh page's
  `altsvault` pipeline has three steps, each depending on the one before:
  - **pull**: the five exports the report needs, from
    `alts-vault.com/api/v1`, saved as CSV;
  - **transform**: the credit-marks pandas, sinking a star schema into its
    own DuckDB warehouse and checking the sink contract;
  - **build**: `altsvault/credit_marks`, so the Reports page opens the fresh
    build.

  Two safeguards:
  - The public demo has no login, so a pull less than an hour old is reused
    rather than hitting the API again.
  - On a fresh start with `ALTSVAULT_API_KEY` set and no data yet, the
    pipeline runs once in the background.

  Ported from the `TraceBiXAltsVault` project, with the changes live data
  needed:
  - The API now serves each fund's history (164 funds, 1,754 reporting
    periods), so the transform keeps each fund's latest period. The report is
    about where marks sit now, and summing a fund across its quarters would
    count its book several times; the sink contract caught exactly that on
    the first live run.
  - The contract checks the pull's own counts instead of an August snapshot's.
  - The report's text no longer carries numbers typed from that snapshot.
  - Its dark theme sets the newer page and surface tokens.
  - Median marks show as percentages.
