### Changed — changelog entries are fragments

- A pull request adds `changes/<issue-number>-<short-name>.md` instead of
  editing `CHANGELOG.md`. `scripts/collect_changes.py` folds those files
  under `[Unreleased]` in issue-number order and deletes them. A release
  build refuses to run while any fragment is still uncollected.
