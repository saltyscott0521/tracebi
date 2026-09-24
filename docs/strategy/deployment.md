# Deployment

**Four ways to run TraceBi, each a step up from the last: local, self-hosted,
Cloud, and inside the customer's network. The same Docker image powers all of
them. Nothing is Cloud-only except running it for you.**

---

## The principle: one product, settings not editions

TraceBi has to suit a five-person startup with no infrastructure team and a
bank with a security review. It does that as **one product whose enterprise
features are switched on by settings**, never a separate edition. A small shop
should be running in an afternoon with nothing extra to set up; a large
company adds its sign-in, network shares and controls to the same install.

| | Small shop / startup | Growing team | Enterprise |
| --- | --- | --- | --- |
| **Runs on** | One server or one container (Railway, Fly, a single VM, a spare office machine) | The same container, plus a managed Postgres | Kubernetes (Helm) or their standard VM build, inside their network |
| **State** | SQLite, a file on disk | Postgres | Postgres, backed up by their team |
| **Reports** | A local folder | A folder or git | Network shares and source control, with folder permissions ([[report-library]]) |
| **Sign-in** | Built-in accounts, or "Sign in with Google/Microsoft" | The same, with roles | Their SSO: proxy header today, OIDC/SAML later; groups mapped to folders |
| **Schedules** | Run inside the web server | A separate worker | Several workers |
| **Email** | Any SMTP account | The same | Their mail relay |
| **Backups** | Copy one folder | Postgres backups | Their standard |
| **Also asks for** | Nothing | Nothing | No calls to the internet, pinned image versions, audit log export, a security overview |

**Rules that keep both ends working:**

1. **The default install needs nothing extra.** No Postgres, Kubernetes, git
   or SSO: SQLite and a folder, one command.
2. **Every enterprise need is a setting on the same image.** If a need
   requires a fork or a special build, the design is wrong.
3. **Nothing calls home.** No telemetry or licence checks unless the customer
   opts in. It costs a startup nothing and is an easy yes for a security team.
4. **Moving up a tier is a configuration change, not a migration project:**
   SQLite to Postgres, one folder to several mounts, built-in accounts to SSO.

**Where we are:**

| Need | For | Status |
| --- | --- | --- |
| One Docker image; docker-compose with Postgres; Railway and Vercel configs | All | ✅ |
| Proxy-header sign-in (for an SSO proxy), viewer/analyst/admin roles | Growing, enterprise | ✅ |
| The Postgres lock that makes several workers safe | Growing, enterprise | ✅ |
| SMTP email delivery | All | ✅ |
| **Several named accounts without an identity provider** (today Basic auth is one shared username and password), or "Sign in with Google/Microsoft" | Small shops | ❌ Next |
| **Schedules inside the web server**, so one process does everything on one box (today `tracebi schedule serve` is a separate process) | Small shops | ❌ Next |
| **A one-page "run it on one server" guide**: Docker, a folder, SMTP, done | Small shops | ❌ Next |
| OIDC/SAML sign-in and group mapping | Enterprise | ❌ |
| Folder permissions | Growing, enterprise | ❌ See [[report-library]] |
| Helm chart; audit log export; a security overview document | Enterprise | ❌ |
| SOC 2 | Cloud | ❌ |

The small-shop gaps come first: they are cheaper, and small teams are where
early adoption comes from. The enterprise items follow the report library's
order of work.

---

## How clients get TraceBi

Two artifacts carry everything; the rest are ways of running them.

| Channel | For | What they get | Status |
| --- | --- | --- | --- |
| **Python package** (`pip install tracebi`) | Analysts and builders on their own machine, and their agents (Claude Code, Cursor) | The engine, the CLI, the MCP gateway, and `tracebi serve` for a local web app | Works from git. Not on PyPI yet |
| **Docker image** | Any team running TraceBi on a server for others: a startup on one VM, an enterprise inside its network | The package plus the web app, run with `docker compose` (Helm later) | A `Dockerfile` exists; clients must build it themselves. No image is published |
| **One-click hosts** (Railway, Render, Fly) | Small teams that don't want to manage a server | The Docker image, deployed from a button | A Railway config exists; no button yet |
| **TraceBi Cloud** | Teams that want no infrastructure | Hosted for them | Planned |

The analyst's laptop runs the package; a shared server runs the image.

**To make these real for a client:**

1. **Publish the Docker image** to a public registry (GHCR is simplest) from
   the existing release workflow, so a client runs
   `docker pull ghcr.io/<owner>/tracebi:<version>` instead of cloning and
   building.
2. **Publish the package to PyPI.** Blocked on confirming who owns the
   `tracebi` name there (versions 0.5.0–0.5.3 exist); until then the README
   installs from git and tests guard against the bare `pip install tracebi`.
3. **A client compose file.** Today's `docker-compose.yml` is the demo stack
   with seeded sample data. A client needs one that points at their own
   project folder (the report library), their state database and their
   warehouse, with no demo seeding.

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
| `docker-compose.yml` | ✅ exists (the demo stack, with Postgres) | A separate client compose file for the customer's own project; add a worker service. |
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
