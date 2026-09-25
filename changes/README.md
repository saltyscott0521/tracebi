One file per pull request: `changes/<issue-number>-<short-name>.md`, or `changes/<short-name>.md` when there is no issue, the `[Unreleased]` entry (`### Added|Changed|Fixed|Deprecated — ...` and its bullets).
Do not edit `CHANGELOG.md`. `python scripts/collect_changes.py` folds these files in, lowest issue number first and then the unnumbered ones by name, when a release is cut.
