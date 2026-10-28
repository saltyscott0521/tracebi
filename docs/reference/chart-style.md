# House themes and chart style

Every report and dashboard takes one of three house themes. A house theme is a
whole look: the ground, the cards and their depth, the radius, the type sizes
and weights, the numerals' face, the spacing, the chart tokens, the lead KPI's
tile, an accent and an eight-colour palette, each for the light ground and the
dark one. Template pages and `app.jsx` pages take it alike, and so do the
kit's `<Chart>` and `<EChart>` and a template's charts, because all are drawn by one
ECharts engine that reads only the
tokens. A theme changes how a page looks, never a number.

## The three

| Theme | What it is | For |
|---|---|---|
| `ledger` (the default) | Calm, institutional. A paper ground, white cards that sit on three soft layers of shadow (a faint top highlight on the dark ground), the KPI strip as one panel, one ink-blue accent, flat marks and hairline grids. | A report to read, a monthly pack, anything that should look well kept. |
| `nightdesk` | Dark first and dense. Opens dark (unless the report or the brand names a mode), compact spacing, numerals in Geist Mono, small radii, dotted grids, the KPIs as separate outlined tiles, the lead's number in the accent, lines that glow faintly. | A desk or an operations screen read all day. |
| `signal` | Bold and editorial. Larger numerals and title, the lead KPI a solid accent tile, borderless cards on large soft shadows, large radii, inverted tooltips, a saturated palette. | A board pack or a screen on the wall. |

**Choosing one.** `report.json` `"theme": "signal"` ([[report-json]]) for one
report; `tracebi.yaml` `brand: {theme: nightdesk}` ([[tracebi-yaml]]) for the
project. A report's own theme wins over the project's; no theme anywhere is
Ledger. `tracebi theme list` shows the three, the default and the project's
choice marked. `tracebi new-report` / `new-dashboard --theme <name>` and the
gateway's `start_draft(theme=…)` write it into `report.json`. Any other name
fails the build, naming the three. The reference project shows all three: its
reports are Ledger, `portfolio_desk` is Nightdesk and `portfolio_dashboard` is
Signal.

**A brand on top.** The project's brand ([[tracebi-yaml]] `brand:`) layers
over whichever theme: its accent, palette, font, logo and name replace the
theme's colours and face; the theme keeps its surfaces, depth, density,
radius and numerals. The accent is still checked at 3:1 on the white card, and
on the dark ground the brand's accent and palette are lifted to read against
that theme's own dark card. Signal's lead tile is the brand's accent, with
white or ink on it, whichever reads.

**The six accent presets** (`graphite`, `indigo`, `midnight`, `ocean`, `plum`,
`sand`) are deprecated. A `report.json` that names one still builds: the page
renders in the house theme with that accent pair, and the build prints one
line naming `brand: {accent: …}` or a house theme instead.

**What stacks where.** `tracebi.css` (Ledger's values) → the house theme → the
brand → `reports/_theme.css` → a deprecated accent preset → the report's
`style.css`. Later wins.

## The tokens per theme

Ledger's values are `tracebi.css`'s own. Nightdesk and Signal restate these
(`tracebi/reports/house.py`); a brand replaces the accent and palette rows.

| Token | Ledger | Nightdesk | Signal |
|---|---|---|---|
| `--tb-page` (ground) | `#f6f6f7` · dark `#0b0b0d` | `#eef1f4` · dark `#090c11` | `#fafaf9` · dark `#0e0e10` |
| `--tb-bg` (card) | `#ffffff` · dark `#141417` | `#ffffff` · dark `#0f141b` | `#ffffff` · dark `#19191c` |
| `--tb-card-border` | `--tb-rule` | `--tb-rule` (`#d9dfe6` · dark `#1c242e`) | `transparent` |
| `--tb-card-shadow` | three layers · dark an inset highlight and one deep layer | none · dark a 1px hairline glow | two large soft layers · dark one deep layer |
| `--tb-radius` | `12px` | `6px` | `20px` |
| `--tb-font-num` (numerals) | Geist | Geist Mono | Geist |
| `--tb-num-weight` | `600` | `500` | `700` |
| `--tb-kpi-size` / `--tb-kpi-lead-size` | `28px` / `40px` | `26px` / `32px` | `34px` / `46px` |
| `--tb-title-size` / `--tb-title-weight` | `28px` / `600` | `24px` / `600` | `36px` / `700` |
| Density | comfortable | compact (`look.density` `comfortable` keeps it roomy) | comfortable |
| Mode with none named | `auto` | `dark` | `auto` |
| KPI strip | one panel | separate tiles | separate tiles |
| `--tb-lead-bg` / `--tb-lead-ink` | the card / ink | the card / the accent's text | `--tb-accent-fill` / `--tb-on-accent-fill` |
| `--tb-accent` | `#2f5bea` · dark `#7a9cff` | `#0e7490` · dark `#22d3ee` | `#1f3fff` · dark `#5c74ff` |
| `--tb-chart-2..8` | `#eb6834 #1baf7a #eda100 #e87ba4 #008300 #4a3aa7 #e34948` | `#d97706 #7c3aed #047857 #e11d48 #2563eb #a21caf #4d7c0f` · dark `#f59e0b #a78bfa #34d399 #fb7185 #60a5fa #e879f9 #a3e635` | `#ff6b2b #00a676 #ffb000 #8b5cf6 #e2366b #0891b2 #65a30d` · dark `#ff7d45 #2ed3a0 #ffc233 #a78bfa #ff5c8a #22d3ee #a3e635` |
| `--tb-chart-grid-dash` | `3 4` | `1 3` | `3 4` |
| `--tb-chart-tooltip-bg` | the card | ink (inverted) · dark near-black, an accent rule and glow | ink (inverted) · dark near-white (inverted) |
| `--tb-chart-tooltip-radius` | `8px` | `4px` | `12px` |
| `--tb-chart-dim` | `0.28` | `0.22` | `0.28` |
| `--tb-chart-glow` | `0` | `0` · dark `6` | `0` |

## The chart look

| Part | The house rule |
|---|---|
| Type | Geist (`--tb-chart-font`, the page's face). Axis labels 11px, every number in tabular figures so values align. A chart's title 14px semibold in ink, its subtitle 12px in the label colour. A mark's own value 11px semibold in ink. |
| Axes | No value-axis line and no tick marks. Faint dashed horizontal gridlines (`--tb-chart-grid`, dashed `--tb-chart-grid-dash`), nothing vertical on a column chart. The one solid rule is the baseline at zero (`--tb-chart-axis`). Category labels in the muted label colour (`--tb-chart-label`). Ticks are compact (`$20M`); tooltips and labels keep the full format. |
| Bars | 55% of the category's band (`--tb-chart-bar`), at most 36px thick. The far end rounded at 2px (`--tb-chart-radius`), the end away from zero, so a bar below zero rounds its bottom. One series of few bars writes each bar's value at its free end. |
| Lines | 2px (`--tb-chart-line`), round joins and caps, no point symbols until the pointer is on a category. The line ends in its last value. An area is the line over a flat wash of its colour at 12% (`--tb-chart-area`), no gradient. |
| Pies | Donuts: the inner radius 60% of the outer, 2px card-coloured gaps between slices, rounded corners, no labels on the ring (the legend names them). The centre stays empty: no total is drawn, because a chart never computes a number. |
| Treemap, sunburst, sankey | Cells bordered in the card colour, 2px. Each cell's label (its name, then its value as the page formats it) in whichever of ink and card reads better on that cell's own fill. A cell a selection leaves out fades, and its label takes the muted text colour: never white on a pale cell. |
| Tooltip | A card: the card surface (`--tb-chart-tooltip-bg`), a rule border (`--tb-chart-tooltip-border`), 8px radius (`--tb-chart-tooltip-radius`) and a soft shadow (`--tb-chart-tooltip-shadow`); Signal and Nightdesk's light ground invert it (`--tb-chart-tooltip-ink`, `-title`). The category, then a row per series: its round swatch, its value in the formatted text the page uses, its name. |
| Legend | Small round chips: a pill with a round swatch and the name. On a live page a chip that names a value the page can select selects it, as a click on a mark does; otherwise it shows or hides its series. |
| Selection | The marks a selection leaves out recede to the same strength on every chart, `--tb-chart-dim` (0.28). |
| Motion | 450ms, cubic-out (`--tb-chart-motion`): bars rise, lines settle, slices sweep. None under the reader's reduced-motion setting, and none in print. |
| Palette | `--tb-chart-1..8`, in that order. The first is the accent, so a single-series chart, the links and the hero are one colour; the other seven are checked against it and each other for colour-blind separation, with their own set on the dark ground. A series keeps its colour whatever a selection leaves on screen. |

## The chart tokens

Set in `tracebi.css` for the light ground and the dark one, restated by a house
theme; override them in `reports/_theme.css` or a report's `style.css`.

| Token | Default |
|---|---|
| `--tb-chart-font` | `var(--tb-font)` |
| `--tb-chart-grid` | the ink at 11% |
| `--tb-chart-grid-dash` | `3 4` |
| `--tb-chart-axis` | `var(--tb-rule)` |
| `--tb-chart-label` | `var(--tb-muted)` |
| `--tb-chart-value` | `var(--tb-ink)` |
| `--tb-chart-tooltip-bg` | `var(--tb-bg)` (the raised surface on the dark ground) |
| `--tb-chart-tooltip-border` | `var(--tb-rule)` |
| `--tb-chart-tooltip-shadow` | a soft two-layer shadow |
| `--tb-chart-tooltip-radius` | `8px` |
| `--tb-chart-radius` | `2px` |
| `--tb-chart-bar` | `55%` |
| `--tb-chart-line` | `2px` |
| `--tb-chart-area` | `0.12` |
| `--tb-chart-dim` | `0.28` |
| `--tb-chart-motion` | `450ms` |
| `--tb-chart-num-font` | `var(--tb-font-num)`: value ticks, a mark's value, the readout's numbers |
| `--tb-chart-tooltip-ink` | `var(--tb-muted)`: the readout's text |
| `--tb-chart-tooltip-title` | `var(--tb-ink)`: the readout's title and values |
| `--tb-chart-tooltip-link` | `var(--tb-accent-text)`: the readout's way to its trace (an inverted readout takes a shade that reads on it) |
| `--tb-chart-glow` | `0`: px of glow under a line, in the line's own colour |
| `--tb-chart-1` … `--tb-chart-8` | the accent, then seven checked colours |

## In ECharts

Every chart is drawn by Apache ECharts, with one theme the runtime builds from
these tokens at draw time (read from the figure, so a container that restates
a token, such as Signal's lead tile, restyles its chart) and rebuilds when the
page's mode changes. An option-only `<EChart>` (a sankey the page computes)
takes the same theme. SVG is the default renderer: vectors, tabular figures
and a crisp print; canvas (`data-tb-renderer="canvas"`, `<Chart
renderer="canvas">`, or `report.json` `"charts": {"renderer": "canvas"}`) for
thousands of marks, drawn as SVG while the page prints. A
`tracebi.configureChart` patch or an `<EChart option>` may still style a chart.
Never hard-code a colour in it: a series takes the palette, so the project's
brand reaches it.
