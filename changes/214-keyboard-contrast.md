### Fixed — the web app works from a keyboard and reads in dark mode

- List rows (reports, sources, pipelines) and the Verify drop zone are
  reachable with Tab and open with Enter or Space. Focus is always visible:
  one ring for the whole app. Diagram edges no longer take focus.
- Dark mode's status text — the green, amber and red that say whether a report
  reproduces — was at 2:1 contrast; its grey text at 3:1. Both now read at
  4.5:1 or better on every surface. Unstyled links take the accent colour.
- On a phone, the header names the model you're in (tap it to switch), the
  menu button has a name, small buttons are at least 24px tall, and Refresh
  opens on its list of steps, where the run buttons are full size.
- `scripts/ui_audit.py` checks every text colour token against every surface
  token in both themes, because axe-core skips text on blurred backgrounds.
