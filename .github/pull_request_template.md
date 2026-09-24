## What this changes

<!-- In plain words: what a user or agent can now do, or what's fixed. -->

Closes #

## How I know it works

- [ ] `pytest tests/` passes (paste the last line):
- [ ] `ruff check .` passes
- [ ] The issue's "done when" is shown (a test, a command's output, or a screenshot):

## Checklist

- [ ] Follows `CLAUDE.md` (invariants, surgical changes, no new deps outside `pyproject.toml`)
- [ ] If the authoring surface changed: `tracebi/capabilities.py`, `AGENTS.md` and `tracebi/_scaffold/init_agents.md` are updated
- [ ] A `changes/<issue-number>-<short-name>.md` fragment, if a user would notice (do not edit `CHANGELOG.md`)
- [ ] No stray files in `output/` or `data/`
