One file per pull request: `changes/<issue-number>-<short-name>.md`, the `[Unreleased]` entry (`### Added|Changed|Fixed|Deprecated — ...` and its bullets).
Do not edit `CHANGELOG.md`. `python scripts/collect_changes.py` folds these files in, lowest issue number first, when a release is cut.
