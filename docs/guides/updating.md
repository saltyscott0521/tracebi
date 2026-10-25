# Update TraceBi

Check for a newer release, see what changed, and run the command that updates
your install. The web app shows a small "available" badge beside the version
in the sidebar when one is out.

## Before you begin

- A TraceBi install: pip, a git checkout, or the Docker image
  ([[one-server]])

Each release is a tagged GitHub release with two things:

- a **wheel** with the web app built in (a plain `git+` install has no web
  app), and
- a **Docker image** at `ghcr.io/saltyscott0521/tracebi`, tagged with the
  version and, for full releases, `latest`.

An update changes only the TraceBi package or image. Your project folders
(`transforms/`, `models/`, `reports/`) are never touched.

## 1. Check

```bash
tracebi update --check
```

```
installed: TraceBi 0.6.0 (pip install)
latest:    0.7.0  https://github.com/saltyscott0521/tracebi/releases/tag/v0.7.0

What's new:
  - Reports can live in folders
  ...

To update:
  pip install --upgrade "https://github.com/.../tracebi-0.7.0-py3-none-any.whl"
```

The check is one request to GitHub's public releases API, cached for a day. It
sends nothing about your install or your data. Offline, it says it couldn't
reach a release and carries on.

## 2. Update

```bash
tracebi update
```

The command detects how TraceBi was installed:

| Installed with | The update | What `tracebi update` does |
| --- | --- | --- |
| pip | `pip install --upgrade "<the release wheel>"` | Asks, then runs it (`--yes` skips the question) |
| Docker | `TRACEBI_VERSION=<version> docker compose -f deploy/compose.yml pull`, then `… up -d` | Prints it; run it on the host |
| A git checkout (`pip install -e .`) | `git fetch --tags && git checkout v<version> && pip install -e .`, then rebuild the UI | Prints it |

If you installed with extras, name them again so new dependencies come too:
`pip install --upgrade "tracebi[web,analyst] @ <the release wheel>"`.

On a server, pin `TRACEBI_VERSION` in `deploy/.env` to stay on a known
version. Left at `latest`, every `pull` takes the newest full release.

## 3. Restart and check your reports

1. Restart `tracebi serve`, or the container.
2. Check your reports still reproduce:

   ```bash
   tracebi verify output/<report>.html.manifest.json
   ```

   A changed number shows here, before anyone reads it.

3. Read the "Changed" section of the release notes for anything you need to
   act on.

## Settings

| Variable | Effect |
| --- | --- |
| `TRACEBI_UPDATE_CHECK=0` | Turns off the check in `tracebi update` and the app's badge |
| `TRACEBI_UPDATE_URL` | Checks an internal mirror instead of GitHub |

See [[environment-variables]].

## Next

- Every command: [[cli]]
