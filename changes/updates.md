### Added

- **`tracebi update`.** It checks for a newer published release and says what
  changed. It also prints the one command that updates this install:
  - **pip:** the release wheel, which has the web UI built in;
  - **Docker:** `docker compose pull` / `up -d`, run on the host;
  - **git checkout:** check out the tag and reinstall.

  A pip install can run the command there after asking (`--yes` skips the
  question); `--check` never runs it.
- **An "available" badge in the web app.** It sits next to the version in the
  sidebar when a newer release is out, with the update command in its tooltip.
  `/api/status` carries the same `update` block. It answers from a cached
  check and refreshes in the background, so no request waits on GitHub.
- **The check itself** is one anonymous GET to GitHub's releases API, cached
  for a day, retried at most every ten minutes when offline, and nothing about
  the install is sent. `TRACEBI_UPDATE_CHECK=0` turns it off;
  `TRACEBI_UPDATE_URL` points it at a mirror. The Docker image sets
  `TRACEBI_IN_DOCKER`.
- `docs/guides/updating.md`: where releases come from, and the update for each
  kind of install.
