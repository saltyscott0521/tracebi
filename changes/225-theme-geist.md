### Changed — the app's look: Geist, monochrome, console-quiet

- **Type:** Geist Sans and Geist Mono (self-hosted, variable) replace Source
  Sans, Inter and Source Code Pro. Every number uses tabular figures.
- **Colour is for meaning.** The navy brand and gradients are gone. Ink (near-
  black, near-white in dark) is the one "brand" colour: the primary button, the
  selected row, the active tab. Green means reproduces, amber needs a look, red
  does not reproduce, and blue is only a link or the focus ring.
- **Light and dark follow your OS** until you choose, and both are neutral
  (`#fafafa` / `#0f0f0f` grounds, hairline borders). The sidebar sits on the
  page's own ground instead of a navy slab. No blur, no gradients, no resting
  shadows; a popover keeps one.
- Reports rows show only what exists (no more "Schedule —  Last run —"), the
  authoring-form chip is neutral, the model switcher and logo follow the theme,
  diagram nodes lose their tints, and the "warehouse.duckdb" pill is no longer
  clipped.
- `scripts/ui_audit.py` enforces the look: Geist loaded, neutral brand tokens,
  no resting shadows, no decorative gradients or blur.
