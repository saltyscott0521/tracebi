# Run TraceBi on one server

Serve a project, its schedules and its email from one container on one
virtual machine. No Kubernetes needed.

## Before you begin

- A virtual machine with Docker and Docker Compose
- A copy of this repository on that machine: `deploy/compose.yml` builds from
  its `Dockerfile`. Clone it, or unpack the source archive from a
  [GitHub release](https://github.com/saltyscott0521/tracebi/releases).
- A domain name, if you want a public address (optional)
- An SMTP account, if a schedule should send email (optional)

## For admins: start the server

1. On your own machine, create a project, or use one you have:

   ```bash
   tracebi init my-project
   ```

2. Copy the project folder onto the server, or clone it. Git is optional for
   this folder. It holds everything: `tracebi.yaml`, `connections/`,
   `transforms/`, `models/`, `reports/`, `pipelines/` and `data/`.
3. On the server, get the repository and make the settings file:

   ```bash
   git clone https://github.com/saltyscott0521/tracebi
   cd tracebi
   cp deploy/.env.example deploy/.env
   ```

4. In `deploy/.env`, set `TRACEBI_PROJECT_DIR` to the project folder.
5. Start it:

   ```bash
   docker compose -f deploy/compose.yml up -d
   ```

6. Open `http://<the-machine>:8000`.

The image is `ghcr.io/saltyscott0521/tracebi`. Set `TRACEBI_VERSION` in
`deploy/.env` to pin a tag. If the image is not on the machine, Compose builds
it from the repository's `Dockerfile`.

## Check it

```bash
curl -s http://127.0.0.1:8000/api/health
```

You want `"status": "ok"`. The container's health check calls the same path.
`GET /api/status` is the longer report: the output folder, files that failed
to load, whether SMTP is set, whether schedules are on, and the sign-in setup.

## Choose a database for TraceBi's own state

SQLite is the default. For Postgres, add `--profile postgres` to the
`docker compose` command and set `POSTGRES_PASSWORD` in `deploy/.env`.

`TRACEBI_STATE_URL` holds TraceBi's own state: run history, sign-in sessions
and OAuth tokens. Give it its own database or schema, and never point a
connection at it, or the demo app's `TRACEBI_DEMO_DB_URL`: people browse
connections. The repository's `docker-compose.yml` uses two databases on one
Postgres server, `crm` for the reference project's CRM and `tracebi_state` for
the store. The app hides TraceBi's own tables (`tracebi_*`, `alembic_version`)
from every source listing and says how many it hid.

## Add or change a report while it runs

Copy a report folder into `reports/`, a model into `models/` or a pipeline
into `pipelines/`. The server picks it up within a few seconds without a
restart: it rescans every `TRACEBI_DISCOVERY_INTERVAL` seconds (default 5).
Deleting a report folder removes it the same way. An edit to an existing
report shows on its next view.

## Turn on schedules and email

1. In `deploy/.env`:

   ```bash
   TRACEBI_SCHEDULES_IN_SERVER=1
   TRACEBI_SMTP_URL=smtp://user:password@host:587
   TRACEBI_SMTP_FROM=reports@example.com
   ```

2. Add a `schedule` block to the report's `report.json` ([[report-json]]):

   ```json
   "schedule": {
     "cron": "0 9 * * MON",
     "timezone": "America/New_York",
     "to": ["cfo@example.com"]
   }
   ```

   `cron` has five fields. `to` lists who gets the email. Without `to`, a run
   rebuilds and records the report and sends nothing.

3. Apply the settings:

   ```bash
   docker compose -f deploy/compose.yml up -d
   ```

Run one container only. Each copy would send the email. To keep sending out of
the web server, run `tracebi schedule serve` as a separate worker instead.

## Set connection secrets

A connection keeps its secret out of the file as `${NAME}`, for example
`url: ${TRACEBI_CRM_URL}` in `connections/crm.yaml`. Set the value in one of
two places:

- `deploy/.env`. The environment wins over everything else.
- The project's encrypted store: run `tracebi secret set TRACEBI_CRM_URL`
  inside the container, or click **Set…** on the connection under
  Data → Sources as a signed-in admin.

The store is `.tracebi/secrets.yml.enc`, encrypted with `TRACEBI_SECRET_KEY`
(or a `.tracebi/secret.key` made on first use). Several containers must share
the key. See [[credentials]].

## Turn on sign-in

- For one team: set `TRACEBI_AUTH_USER` and `TRACEBI_AUTH_PASS`, or name each
  person with `TRACEBI_LOCAL_USERS`.
- For your company login: set `TRACEBI_OIDC_ISSUER` ([[sign-in]]).
- Behind an SSO proxy: set `TRACEBI_AUTH_PROXY_HEADER` and
  `TRACEBI_AUTH_PROXY_TRUSTED_IPS` ([[web-customization]]).

With none set, anyone who can reach the port can use the app. That is fine
only on a machine nothing else can reach.

To serve the agent gateway on the same host, see `deploy/mcp/README.md`. The
public demo uses `https://tracebi.com/mcp`.

## Back it up

Copy the project folder (`TRACEBI_PROJECT_DIR`): the reports, the warehouse,
the run log and the credential store in `.tracebi/`. Keep `TRACEBI_SECRET_KEY`
with it, or the store cannot be read. With the Postgres profile, also copy
`TRACEBI_PGDATA_DIR`.

## Update it

`tracebi update --check` inside the container prints the `docker compose pull`
and `up -d` lines to run on the host. See [[updating]].

## Run it on Coolify

Use a **Docker Image** resource that pulls a GHCR tag. Don't let Coolify build
the repository's Dockerfile on every push: that leaves a multi-GB image per
commit on the machine.

| Tag | For | How it updates |
| --- | --- | --- |
| `ghcr.io/saltyscott0521/tracebi:<version>` | A client install that matches a release | You change the tag when you cut a release |
| `ghcr.io/saltyscott0521/tracebi:main` | The hosted demo (built with `UI_BASE=/app/`) | After CI passes on `main`, `publish-demo.yml` pushes the image and calls Coolify's deploy webhook |

1. Turn git **auto-deploy** off on the resource. The webhook redeploys it.
2. Copy the variables from `deploy/.env` into Coolify's environment screen.
3. To serve a live project folder, bind-mount it at `/project`. The compose
   file's `output-perms` service mounts `output/` and `data/` from the same
   folder.
4. Give the resource a domain if you have one. TLS ends at Coolify.
5. Keep image retention low (`docker_images_to_keep`, or prune unused images)
   so old tags do not fill the disk.

The image ships `curl`, so Coolify's health check against `/api/health` works.

The demo image, like the repository's `docker-compose.yml`, serves one
project: `examples/portfolio_project`, with its warehouse built into the image.
`TRACEBI_APP` is unset; the bundled demo app is opt-in
(`TRACEBI_APP=tracebi.web.demo_app`) and never served beside a project. The
reference project's CRM is a mock Postgres database: `docker-compose.yml`'s
Postgres creates `crm` from `examples/portfolio_project/inputs/seed_crm.sql`
when its volume is empty (`docker/postgres-init.sql`), and `TRACEBI_CRM_URL`
points at it. Nothing in the app writes to it. Without `TRACEBI_CRM_URL` the
transform reads the committed snapshot, and the certificate says so.

## Next

- Let people sign in as themselves: [[sign-in]]
- Connect ChatGPT and Claude: [[connect-chatgpt-and-claude]]
