### Added — Scheduled reports retry a failed refresh or build

- A scheduled run whose refresh step or build fails is tried again twice,
  waiting 1 minute and then 5 minutes. If it still fails, the failure is
  recorded as before. The run record in `output/schedule_runs.jsonl`
  includes `attempts` (1 when the first try succeeded).
- `report.json` may set `"retries"` to an integer from 0 to 5. 0 turns
  retries off. The waits stay 1 minute, then 5 minutes.
- A receipt that does not verify (`refused`) and a delivery failure are
  not retried, and a failed send is not repeated.
