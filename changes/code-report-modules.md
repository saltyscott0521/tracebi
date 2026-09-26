### Changed — a code module's package-less report is flagged

- A `.py` or `.ipynb` file directly in `reports/` still loads at startup,
  but a report it registers with no package behind it cannot render. That
  is now a warning in `/api/discovery` and `tracebi validate`, naming
  `tracebi new-report` as the fix.

### Removed — the Vercel deployment files

- `vercel.json`, `vercel-build.sh`, `api/` and the Vercel + Supabase guide.
  The demo runs on one server; see the one-server guide.
