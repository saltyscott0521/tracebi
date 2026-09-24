---
slug: design-accessible-by-default
title: Readable for everyone — enough contrast, colorblind-safe series, never color alone
when: choosing colors or chart series, restyling tokens, or a report will be printed or read by many people
---
**The pitfall.** About one in twelve men has some color-vision deficiency. A
chart that separates "actual" from "plan" only by red and green, pale grey text
on white, or a status shown only as a colored dot is unreadable to them — and
to anyone reading a greyscale printout or a phone in the sun. Nobody notices,
because the author can see it fine.

**What TraceBi gives you.** The default text and background tokens have strong
contrast, and the first two chart colors (`--tb-chart-1` blue,
`--tb-chart-2` orange) are a colorblind-safe pair.

**What you have to watch.**

- **Past two or three series, the default palette is not colorblind-safe.** It
  contains both greens (`--tb-chart-3`, `--tb-chart-6`) and a red
  (`--tb-chart-8`), which the most common forms of colorblindness confuse. Keep
  categorical charts to few series; beyond three, label the series directly or
  split the chart rather than relying on color to tell them apart
  ([[design-choose-the-chart]]).
- **Never use color as the only signal.** Pair it with a label, a position or a
  sign: "−8.4% vs plan", not just a red number.
- **Contrast.** Text and labels need at least 4.5:1 against their background;
  chart lines and bars at least 3:1. If you override `--tb-muted` or chart
  colors in `_theme.css`, check them — light greys and pastels usually fail.
- **Avoid the classic confusable pairs** when you choose colors: red with green,
  green with brown, blue with purple, and any two pastels. Blue with orange is
  the safe default pairing.
- **Test it.** View the built page in greyscale, or through a colorblindness
  simulator. If the point survives, the design is sound.

**The tell.** If the page would stop making sense printed in black and white,
it depends on color alone. See [[design-color-with-meaning]] for when to use
color at all.
