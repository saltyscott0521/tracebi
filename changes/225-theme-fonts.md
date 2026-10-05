### Changed — the app's look: Hanken Grotesk type, one cobalt, a nav that follows the data

- **Type:** Hanken Grotesk (variable) and IBM Plex Mono, both self-hosted,
  replace Source Sans, Inter and Source Code Pro. Every number uses tabular figures.
- **Colour:** one cobalt blue (`#2f5bea`, lighter on dark) used where you act or
  are: the primary button, the selected row, the active tab, links, focus, the
  logo tile. Grounds are neutral, borders are hairlines, and the sidebar is a
  near-black slab in both themes. The navy, the gradients, the blur and the glow
  are gone. Other colour means something: green reproduces, amber needs a look,
  red does not reproduce.
- **Light and dark follow your OS** until you choose.
- **The nav** lists pages in the order the data moves, in two groups:
  **Build** (Sources, Refresh, Data model), then **Use** (Explore, Reports,
  Runs). The active page's icon picks up the lighter cobalt.
- Reports rows show only what exists (no more "Schedule —  Last run —"), the
  authoring-form chip is neutral, hardcoded colours in components 90 -> 13
  (tokens with dark values), pipeline edges regained their stroke, and the
  "warehouse.duckdb" pill is no longer clipped.
- `scripts/ui_audit.py` enforces the look: Hanken Grotesk loaded, a brand that stays in
  its blue family, dark sets its own ink, no resting shadows, no decorative
  gradients or blur.
