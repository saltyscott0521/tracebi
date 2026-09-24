# Run TraceBi on one server

**One VM, one folder, one container.** The app, the schedules, and the
email all run in that container. You do not need Kubernetes. Git is
optional for the project folder. The server still needs a copy of this
repository, because `deploy/compose.yml` builds from its `Dockerfile`.

---

## What you need

- A virtual machine with Docker and Docker Compose.
- A domain name, if you want a public address. The app works on the
  machine's own address without one.
- An SMTP account, if a schedule should send email. Without one, a
  schedule can still rebuild the report and write the run down.

## Put your project on the server

On your own machine, create a project (or use one you already have):

```bash
tracebi init my-project
```

Copy that folder onto the server, or clone it. Git is optional for this
folder. The folder is the application: `models/`, `reports/`, and
`data/`.

## Start it

The server needs a copy of this repository. `deploy/compose.yml` builds
from `..`, the repository's `Dockerfile`. Clone it:

```bash
git clone https://github.com/saltyscott0521/tracebi
```

Or download the source archive from a
[GitHub release](https://github.com/saltyscott0521/tracebi/releases) and
unpack it.

From that copy, on the server:

```bash
cp deploy/.env.example deploy/.env
```

In `deploy/.env`, set `TRACEBI_PROJECT_DIR` to the project folder from
the previous step. Then:

```bash
docker compose -f deploy/compose.yml up -d
```

Open `http://<the-machine>:8000`.

The container serves that folder. SQLite is the default. Add
`--profile postgres` when you want Postgres, and set `POSTGRES_PASSWORD`
in `deploy/.env`.

The image name is `ghcr.io/saltyscott0521/tracebi`. Set `TRACEBI_VERSION`
in `deploy/.env` when you want a pinned tag. If that image is not on the
machine, Compose builds it from the `Dockerfile` in this repository.

## Turn on schedules and email

In `deploy/.env`:

```bash
TRACEBI_SCHEDULES_IN_SERVER=1
TRACEBI_SMTP_URL=smtp://user:password@host:587
TRACEBI_SMTP_FROM=reports@example.com
```

In the report you want to send, add a `schedule` block to `report.json`
([[report-json]]):

```json
"schedule": {
  "cron": "0 9 * * MON",
  "timezone": "America/New_York",
  "to": ["cfo@example.com"]
}
```

`cron` is five fields. `to` is who receives the email. Leave `to` out
and the run still rebuilds the report and records it, and sends nothing.

Apply the env file:

```bash
docker compose -f deploy/compose.yml up -d
```

This assumes **one process**. Do not run several copies of the
container: each copy would send the email. A separate worker is
`tracebi schedule serve`, for when the web server should not be the
thing that sends.

## Sign-in

For one team, set `TRACEBI_AUTH_USER` and `TRACEBI_AUTH_PASS` in
`deploy/.env`. To put the app behind an SSO proxy instead, follow
[[web-customization#Auth|Sign-in]] (`TRACEBI_AUTH_PROXY_HEADER` and
`TRACEBI_AUTH_PROXY_TRUSTED_IPS`).

With neither set, anyone who can reach the port can use the app. That
is fine on a machine that is not reachable from anywhere else.

## With Coolify

Create a Docker Compose resource. Point it at this repository, or at
the image `ghcr.io/saltyscott0521/tracebi`. Set the same variables from
`deploy/.env` in Coolify's environment screen. Bind-mount a folder on
the host (Coolify's directory mount, a host path) at `/project`. The
compose file's `output-perms` service mounts `output/` and `data/` from
that same folder. A backup is still a copy of that folder.

Give the resource a domain in Coolify if you have one. TLS ends at
Coolify. This page does not name a host, an address, or a password.

## Backups

Copy the project folder (`TRACEBI_PROJECT_DIR`). That folder is the
reports, the warehouse file, and the run log. If you started the
Postgres profile, also copy `TRACEBI_PGDATA_DIR`.

## Check it

On the server:

```bash
curl -s http://127.0.0.1:8000/api/health
```

You want `"status": "ok"`. The container's own health check calls the
same path.

`GET /api/status` is available. It is the longer page: output folder,
files that failed to load, whether SMTP is set, whether schedules are
on, and the sign-in posture. It is not a substitute for `/api/health`,
which stays the cheap check.

Then open the app in a browser and open the report.
