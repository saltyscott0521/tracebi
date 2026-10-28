# Chart style

Every chart a report draws, in the house look: the kit's `<EChart>` (Apache
ECharts) and the runtime's D3 charts (a template's `data-tb-figure="chart"`,
the kit's `<Chart>`) draw from the same tokens, so a dashboard that mixes them
reads as one designed thing. Nothing below needs a setting. A theme
([[report-json]] `"theme"`, `reports/_theme.css`) or the project's brand
([[tracebi-yaml]] `brand:`) changes the tokens, and every chart follows.

## The look

| Part | The house rule |
|---|---|
| Type | Geist (`--tb-chart-font`, the page's face). Axis labels 11px, every number in tabular figures so values align. A chart's title 14px semibold in ink, its subtitle 12px in the label colour. A mark's own value 11px semibold in ink. |
| Axes | No value-axis line and no tick marks. Faint dashed horizontal gridlines (`--tb-chart-grid`, dashed `--tb-chart-grid-dash`), nothing vertical on a column chart. The one solid rule is the baseline at zero (`--tb-chart-axis`). Category labels in the muted label colour (`--tb-chart-label`). Ticks are compact (`$20M`); tooltips and labels keep the full format. |
| Bars | 55% of the category's band (`--tb-chart-bar`), at most 36px thick. The far end rounded at 2px (`--tb-chart-radius`), the end away from zero, so a bar below zero rounds its bottom. One series of few bars writes each bar's value at its free end. |
| Lines | 2px (`--tb-chart-line`), round joins and caps, no point symbols until the pointer is on a category. The line ends in its last value. An area is the line over a flat wash of its colour at 12% (`--tb-chart-area`), no gradient. |
| Pies | Donuts: the inner radius 60% of the outer, 2px card-coloured gaps between slices, rounded corners, no labels on the ring (the legend names them). The centre stays empty: no total is drawn, because a chart never computes a number. |
| Treemap, sunburst, sankey | Cells bordered in the card colour, 2px. Each cell's label (its name, then its value as the page formats it) in whichever of ink and card reads better on that cell's own fill. A cell a selection leaves out fades, and its label takes the muted text colour: never white on a pale cell. |
| Tooltip | A card: the card surface (`--tb-chart-tooltip-bg`), a rule border (`--tb-chart-tooltip-border`), 8px radius (`--tb-chart-tooltip-radius`) and a soft shadow (`--tb-chart-tooltip-shadow`). The category, then a row per series: its round swatch, its value in the formatted text the page uses, its name. |
| Legend | Small round chips: a pill with a round swatch and the name. On a live page a chip that names a value the page can select selects it, as a click on a mark does; otherwise it shows or hides its series. |
| Selection | The marks a selection leaves out recede to the same strength on every chart, `--tb-chart-dim` (0.28). |
| Motion | 450ms, cubic-out (`--tb-chart-motion`): bars rise, lines settle, slices sweep. None under the reader's reduced-motion setting, and none in print. |
| Palette | `--tb-chart-1..8`, in that order. The first is the accent, so a single-series chart, the links and the hero are one colour; the other seven are checked against it and each other for colour-blind separation, with their own set on the dark ground. A series keeps its colour whatever a selection leaves on screen. |

## The tokens

Set in `tracebi.css` for the light ground and the dark one; override them in
`reports/_theme.css` or a report's `style.css`.

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
| `--tb-chart-1` … `--tb-chart-8` | the accent, then seven checked colours |

## In an `<EChart>`

The kit hands ECharts a theme built from these tokens, so an option-only chart
(a sankey the page computes) takes the look too, and redraws when the page's
mode changes. `renderer="svg"` is the default: vectors, tabular figures and a
crisp print; `renderer="canvas"` for thousands of marks. An `option` may still
style a chart. Never hard-code a colour in it: a series takes the palette, so
the project's brand reaches it.
