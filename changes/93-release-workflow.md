### Added — a version tag publishes the image and a GitHub release

- A `v*` tag that matches `pyproject.toml` publishes
  `ghcr.io/<owner>/tracebi:<version>` (and `latest` when the version is not a
  prerelease) and a GitHub release carrying the wheel, sdist and SBOM. PyPI
  stays off unless the `PUBLISH_PYPI` repository variable is `true`. The
  Actions tab dry run builds all of that and pushes nothing.
