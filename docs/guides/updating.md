# Updating TraceBi

**Run `tracebi update`. It says whether a newer TraceBi is out, what changed,
and the one command that updates *your* install. The web app shows the same
thing as a small "available" badge next to the version in the sidebar.**

---

## Where updates come from

Each TraceBi release is a tagged GitHub release carrying two things:

- a **wheel** with the web app already built in (a plain `git+` install
  has no web UI), and
- a **Docker image** at `ghcr.io/saltyscott0521/tracebi`, tagged with the
  version and, for full releases, `latest`.

Your projects (`transforms/`, `models/`, `reports/`) are yours and are never
touched by an update. Only the TraceBi package or image changes.

## Check

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

The check is one request to GitHub's public releases API, cached for a day.
It sends nothing about your install or your data. Offline, it says it couldn't
reach a release and carries on. Turn it off with `TRACEBI_UPDATE_CHECK=0`, or
point it at an internal mirror with `TRACEBI_UPDATE_URL`
([[environment-variables#Updates]]).

## Update

How depends on how TraceBi was installed; `tracebi update` detects which.

| Installed with | The update | `tracebi update` |
| --- | --- | --- |
| **pip** | `pip install --upgrade "<the release wheel>"` | asks, then runs it (`--yes` skips the question) |
| **Docker** ([[one-server]]) | `TRACEBI_VERSION=<version> docker compose -f deploy/compose.yml pull`, then `… up -d` | prints it; run it on the host |
| **a git checkout** (`pip install -e .`) | `git fetch --tags && git checkout v<version> && pip install -e .`, then rebuild the UI | prints it |

If you installed with extras (`tracebi[web,analyst]`), name them again when
you upgrade so any new dependencies they gained come too:
`pip install --upgrade "tracebi[web,analyst] @ <the release wheel>"`.

Pinning `TRACEBI_VERSION` in `deploy/.env` keeps a server on a known version
until you choose to move it; leaving it at `latest` means every `pull` takes
the newest full release.

## After updating

1. Restart `tracebi serve`, or the container.
2. Check your reports still reproduce on the new version:
   ```bash
   tracebi verify output/<report>.html.manifest.json
   ```
   A changed number shows up here, before anyone reads it.
3. Read the release notes' "Changed" section for anything you need to act on.

## Related

- [[one-server]] — the Docker setup that pulls the image
- [[cli]] — every command
- [[environment-variables]] — the update settings
