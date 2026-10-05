### Changed — Refresh has one list of runs, and links the reports each rebuilt

- The Refresh page's **Log** and **History** tabs are one **Runs** tab: the
  pipeline's runs newest first (when, who, status, how long, which steps). Pick
  one to read its log; a run that is going is followed as before. A step's own
  history is a **History** button on its row in the Steps tab.
- A finished run lists the reports its build step rebuilt, under the log, each a
  link to that report's page. Only the reports actually built in that run: a run
  that stops after two of five lists two.

### Added — `tracebi run-pipeline` records its runs

- A run from the command line (the whole pipeline or `--layer`) now leaves the
  same run row and log file as one started from the app, so a cron job's run
  appears in the Runs tab and on the Runs page. The terminal prints what it
  always did. `--status` records nothing. If the state store cannot be reached
  the pipeline still runs and says it is not recording; Ctrl-C ends the run as
  failed rather than leaving it "running".
- `GET /api/pipelines/{name}/runs` summaries gain `actor_role` (`cli` for these)
  and `reports`. The recording lives in `tracebi/pipeline/run_record.py`; the
  web app keeps only its worker pool and the "already running" join.
