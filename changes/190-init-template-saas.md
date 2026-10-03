### Added — `tracebi init --template saas-metrics`

- `tracebi init <project> --template saas-metrics` (also `saas_metrics`)
  scaffolds a working SaaS metrics mini-project: a small subscriptions
  sample, a sink contract, `models/saas_model.py` (ending MRR, logo churn,
  a signup-cohort cut), and two reports (`saas_model/mrr_dashboard`,
  `saas_model/cohort_brief`). Unknown names are refused with the known
  list. `tracebi init` with no flag is unchanged.
- `tracebi context` lists the starters under `templates`.
