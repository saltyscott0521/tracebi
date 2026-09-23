# Deployment

**Four ways to run TraceBi, each a step up from the last: local, self-hosted,
Cloud, and inside the customer's network. The same Docker image powers all of
them. Nothing is Cloud-only except running it for you.**

---

## The four tiers

| Tier | For | What runs | Who operates it | Available |
| --- | --- | --- | --- | --- |
| **Local** | Builders trying it, solo analysts | `pip install tracebi`, `tracebi serve`, DuckDB or a database connection, SQLite state | The user | Now (from git). PyPI in Q1. |
| **Self-hosted** | Teams with an engineer and a cloud account | One Docker image (web + workers) + Postgres + a report library (a folder, a network share or a source control checkout) | The customer | Q1 (image), Q2 (workers + Postgres state) |
| **TraceBi Cloud** | Teams without ops capacity | Managed deployment per customer; connects to their warehouse, and to their source control if they use one | Us | Private beta Q3, GA Q4 |
| **Customer VPC** | Regulated or security-strict buyers | Cloud's management, with workers in the customer's network | Shared | When a paying customer requires it |

## Self-hosted: the reference deployment

```
             ┌──────────────┐
  users ───▶ │ reverse proxy │  TLS, SSO headers (proxy auth mode already exists)
             └──────┬───────┘
     ┌──────────────┴──────────────┐
     │ tracebi web (N replicas)    │  API + UI, stateless
     └──────────────┬──────────────┘
     ┌──────────────┴──────────────┐
     │ tracebi worker (M replicas) │  scheduled runs, builds, delivery
     └───────┬──────────────┬──────┘
             │              │
      ┌──────▼─────┐  ┌─────▼──────────────┐
      │ Postgres   │  │ customer warehouse │ read-only
      └────────────┘  └────────────────────┘
      + the report library: a folder, a network share, or a source control
        checkout synced on publish (webhook or poll)
```

**Packaging:**

| Artifact | Status | Target |
| --- | --- | --- |
| `Dockerfile` (UI + Python) | ✅ exists | Publish to GHCR on every release. Add a `worker` entry point. |
| `docker-compose.yml` | ✅ exists | Add Postgres and a worker service. |
| Railway, Vercel + Supabase configs | ✅ exist | Keep Railway as the one-click path. Vercel suits the read-only demo only (no workers). |
| Helm chart | ❌ | Q2: web, worker, Postgres (external or bundled), secrets, ingress. |
| Terraform module | ❌ | When the first customer asks. |

**Configuration** stays in environment variables (already documented in
`.env.example` and [[environment-variables]]). Add: `TRACEBI_REPO_URL`,
`TRACEBI_REPO_BRANCH`, `TRACEBI_STATE_URL` (Postgres), and worker concurrency.

## TraceBi Cloud

**Shape (v1, single-tenant):** each customer workspace is its own deployment
of the self-hosted image, with its own Postgres database, on one managed
platform. The customer connects:

1. **Their warehouse**, with read-only credentials stored in the platform's
   secret store.
2. **Their source control, if they use one** (git on any host first). Teams
   without one get a hosted library with TraceBi's own version history.
3. **Their identity provider** (Q4). Before that, email sign-in.

**What Cloud stores:** run history, receipts, delivered artifacts (for the
retention period), users, requests and audit logs. **What it doesn't:** raw
warehouse tables. Only the query results a report embeds.

**Operating Cloud.** Keep it boring:
- One region, one cloud provider, one managed Postgres. Infrastructure as code
  from day one.
- Provision workspaces from a script (later a control-plane service), not by
  hand.
- Uptime and failed-run alerts to whoever is on call. A public status page.
- Backups tested monthly.
- A written incident runbook, and agents allowed to diagnose but not to change
  production without approval.

## Environments and releases

| Channel | Cadence | Contents |
| --- | --- | --- |
| `main` | Continuous | Everything merged, CI green |
| PyPI + GHCR release | Every 2–4 weeks | Tagged `0.x`, changelog, migration notes |
| Cloud | Follows releases, one to three days behind, after a canary workspace | Same image |
| Hosted demo | On every release | Reference project, read-only, reset nightly |

**Versioning:** semantic versions after 1.0. Before that, breaking changes are
allowed but listed in the changelog with a migration step. The manifest
`schema_version` keeps old receipts verifiable across upgrades (already
built).

## Data and state migrations

The project today avoids a migration framework on purpose (see "Audit
Attribution" in `CLAUDE.md`). With Postgres state for runs, requests and
users, that changes: **adopt Alembic for the state store in Q2**, and keep
the startup column-reconcile only for the legacy run table.
