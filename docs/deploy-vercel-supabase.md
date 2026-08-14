# Deploying TraceBi on Vercel with Supabase

Vercel hosts the React UI and the FastAPI layer as Python serverless
functions; Supabase Postgres holds your data and, if you use pipelines, their
run history.

This pairing works because of one property of each side. TraceBi never caches
a query — every call recomputes from source, which is exactly what an
ephemeral function wants. And Supabase gives you a *remote* Postgres, which
solves the thing serverless otherwise breaks: TraceBi's default SQLite sits on
a local disk that Vercel functions cannot write to.

---

## What works, and what does not

Be clear-eyed about this before you deploy.

**Works on Vercel**

- Models, tables, previews, CSV export
- Explore: star-schema queries with dimension filters and named measures
- Reports: synchronous run, HTML/Excel download, lineage graphs
- Report specs: `POST /api/spec/validate` and `/api/spec/render`
- The capability schema (`/api/schema`) and discovery diagnostics
- Requests (ad-hoc scripts) executed on demand

**Does not work on Vercel, architecturally**

| Feature | Why | What to do instead |
|---|---|---|
| Scheduled reports and pipelines | APScheduler needs a process that outlives a request | Supabase `pg_cron`, or Vercel Cron hitting a run endpoint |
| Background report runs (`POST /reports/{n}/runs` then poll) | The `run_id` lives in an in-process thread pool; the next poll lands in a different, fresh process | Use the synchronous `POST /reports/{n}/run` |
| Local SQLite | The filesystem is read-only outside `/tmp`, and `/tmp` is not shared between invocations | Point everything at Supabase Postgres |

Cold starts cost roughly a second importing pandas. That is inherent, not a
misconfiguration.

If you need scheduling badly enough, run the API in a container (Fly, Render,
Railway) and keep only the UI on Vercel — set `VITE_API_BASE` and everything
else here still applies.

---

## 1. Get your Supabase connection string

In the Supabase dashboard: **Project Settings → Database → Connection string
→ URI**. You want the **connection pooler** (port `6543`), not the direct
connection — serverless functions open and drop connections constantly, and
the pooler is built for that.

Convert it to a SQLAlchemy URL by naming the driver:

```
postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

Set it in Vercel under **Settings → Environment Variables**:

| Variable | Value |
|---|---|
| `TRACEBI_SUPABASE_URL` | the URL above |
| `TRACEBI_APP` | *(empty string)* — skip the bundled demo app |
| `TRACEBI_AUTH_USER` / `TRACEBI_AUTH_PASS` | pick something; see §4 |
| `TRACEBI_DEMO_DB_URL` | *(only when running the bundled demo, `TRACEBI_APP=tracebi.web.demo_app`)* — same URL. See below. |

### Running the bundled demo against Postgres

If you deploy the demo app rather than your own project, point
`TRACEBI_DEMO_DB_URL` at the same database. That changes what importing the
app module does:

- **With it set**, importing only *defines* layers. Nothing is seeded, nothing
  is executed, and the web process does no batch work at all — it reads
  results that are already in Postgres.
- **Without it**, the demo falls back to an ephemeral SQLite file and seeds
  and runs itself at import, because otherwise there would be nowhere for
  anything else to have written and the demo would come up empty.

Seed it once, from anywhere with the URL — a laptop, a CI job, a container:

```bash
TRACEBI_DEMO_DB_URL='postgresql+psycopg://…' \
  python -c "from tracebi.web.demo_app.pipeline import seed_and_run; seed_and_run()"
```

That command is the execution plane. For a project of your own with pipelines
in `pipelines/`, the equivalent is `tracebi run-pipeline <name>`, which needs
no web server and exits non-zero if a layer fails — so cron, a Kubernetes
CronJob, an Airflow task or a CI step can own the schedule instead of the API
process. See NOTES.md, "Deployment planes".

Never commit the password. The framework reads connector URLs only from
`os.environ`, deliberately — see [.env.example](../.env.example).

## 2. Define a model against Supabase

Create `models/supabase.py` — the file convention the server discovers at
startup. It must expose a module-level `model`:

```python
import os

from tracebi import DataModel, SQLConnector

# Fail loudly at import if it is missing, rather than at first query.
url = os.environ["TRACEBI_SUPABASE_URL"]

db = SQLConnector("supabase", url=url)

model = DataModel("Sales")
model.add_connector(db)
model.add_table("orders",    connector="supabase", source="orders")
model.add_table("customers", connector="supabase", source="customers")

model.add_dimension(
    "dim_customer", table_name="customers",
    key_col="customer_id", attributes=["region", "tier"],
)
model.add_fact(
    "fact_orders", table_name="orders",
    measures=["revenue", "cost"],
    foreign_keys={"dim_customer": "customer_id"},
)

# Define measures once here, reference them by name everywhere.
model.add_measure("revenue", column="revenue", agg="sum",
                  description="Gross booked revenue")
model.add_measure("gross_margin", expr="revenue - cost", agg="sum")
model.add_measure("margin_pct", ratio=("gross_margin", "revenue"),
                  format="percent")

model.connect()
```

Then, **before you trust a number**:

```bash
TRACEBI_SUPABASE_URL=... tracebi validate
```

That loads the model and checks every dimension key is unique. A duplicate key
silently inflates every additive measure, so this is worth running in CI.

## 3. Deploy

The repo already contains [`vercel.json`](../vercel.json) and
[`api/index.py`](../api/index.py).

```bash
npm i -g vercel
vercel link
vercel --prod
```

Vercel will:

1. run `cd web/ui && npm ci && npm run build` → `tracebi/web/ui/dist`
2. build `api/index.py` as a Python function from
   [`api/requirements.txt`](../api/requirements.txt)
3. rewrite `/api/*` to the function and everything else to `index.html`

### Why `api/requirements.txt` is narrower than the project extras

Vercel functions have a 250 MB unzipped limit. That set measures ~150 MB
because it omits three things it no longer needs:

- **matplotlib** (~35 MB) — HTML charts are inline SVG and Excel charts are
  openpyxl-native
- **networkx** (~17 MB) — only used for drawing lineage graphs;
  `LineageDiagram.to_mermaid()` works without it
- **apscheduler** — a scheduler cannot outlive a request here

## 4. Auth — do not skip this

With no auth configured the API is open to anyone who finds the URL, and that
includes the endpoints that execute request scripts. The server prints a
warning at startup; take it seriously on a public deployment.

The quickest safe thing is HTTP Basic:

```
TRACEBI_AUTH_USER=someone
TRACEBI_AUTH_PASS=<a real password>
```

For per-user identity, put the deployment behind a proxy that authenticates
and set `TRACEBI_AUTH_PROXY_HEADER` plus `TRACEBI_AUTH_PROXY_TRUSTED_IPS` —
without the trusted-IP list, anyone can spoof the header.

## 5. Pipelines, if you want them

Point `PipelineRunner` at Supabase so run history survives, in
`pipelines/<name>.py`:

```python
import os
from tracebi import PipelineRunner

runner = PipelineRunner(db_url=os.environ["TRACEBI_SUPABASE_URL"])
# runner.register(layer, name="orders_landing", ...)
```

Layers still run on demand via `POST /api/pipelines/{name}/layers/{layer}/run`.
For a *schedule*, trigger that endpoint from Supabase `pg_cron` or Vercel Cron
— `runner.start()` will not survive on serverless.

---

## Hosting only the UI on Vercel

If the API lives elsewhere, build the UI against it:

```bash
VITE_API_BASE=https://your-api.example.com/api  npm run build
```

Then deploy `tracebi/web/ui/dist` as a static site and drop `api/` and the `functions`
block from `vercel.json`. Make sure the API allows your Vercel origin in
`tracebi/web/api/main.py`'s CORS list.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Reports list is empty | `reports/` is empty, or a file failed to import — check `GET /api/discovery` |
| Models list is empty | `models/` files did not expose `model`, or the Supabase URL is unset. `GET /api/discovery` names the failure |
| `250 MB` build error | Something heavy crept into `api/requirements.txt` |
| Every request slow | Cold start. Raise `memory` in `vercel.json`; Vercel scales CPU with it |
| Queries hang or drop | Use the pooler on `6543`, not the direct connection on `5432` |
