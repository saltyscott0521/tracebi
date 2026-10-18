### Changed — the brand mark says "traced" (A2-5)

The cobalt stays (`#2f5bea`). The mark, the wordmark and the tagline change.

- **The mark is a trace:** one stroke rising through two open points to a
  filled one, the number you arrived at. White on the cobalt tile, flat. It
  replaces the brackets-and-bars mark (which said "a chart", not "traced").
  `BrandMark` (`web/ui/src/components/Art.jsx`) draws it at 18px in its 28px
  tile; on hover the trace replays, point to point, and stops under reduced
  motion like every other animation.
- **Where it appears:** the sidebar header, the 56px rail on a report page,
  the phone header (new: the mark before "TraceBi" and the place), the browser
  tab (`web/ui/public/favicon.svg`, wired in `web/ui/index.html`; it replaces
  an inline navy-gradient favicon, the last gradient on the brand), the
  gateway's sign-in page (`tracebi/mcp_oauth.py`), and the site header and
  favicon (`site/index.html`, carried to `site/docs/` by `build_docs.py`).
  Never on a report: `.tb-masthead-mark` stays the customer's slot.
- **Wordmark:** "TraceBi", 15px/600 in the app's sans, tracking -0.01em, with
  nothing beneath it.
- **Tagline:** *Every number, traced.* It is the mark's `title`, the line above
  "Sign in to TraceBi", and the start of Get started's first line. Never under
  the logo.
- **`ReportArt`** (shown while a report's last build opens): its trend line
  was a hard-coded sky blue (`#38bdf8`), a second blue that did not follow the
  theme. It is now the cobalt (`--accent-text`) ending on a filled point, the
  mark's language, with the bars behind it lighter so the line reads.
- Documented in `docs/architecture/design-direction.md`, "The mark".

#### The three candidates

Drawn on a 20-unit grid, rendered at 16, 20 and 32px on the tile, light and
dark, before choosing.

**A, Three points.** A straight line through two small dots to a large one.
At 16px it collapses into a plain diagonal: a slash, or a pin.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" color="#2f5bea"><path d="M4.5 15.5 L15 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="4.5" cy="15.5" r="1.6" fill="currentColor"/><circle cx="9.75" cy="10.25" r="1.6" fill="currentColor"/><circle cx="15" cy="5" r="2.7" fill="currentColor"/></svg>
```

**B, Rising trace (chosen, refined).** Open points, the last filled: the
points a number came through, and the number. The open nodes keep the stroke
reading as a path rather than a line at every size. Refined with a knee (a
shallow rise, then a steep one), so it reads as a trace rather than a ruler.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" color="#2f5bea"><path d="M5.39 14.03 L7.61 12.47 M10.20 10.30 L13.66 6.84" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="4" cy="15" r="1.7" stroke="currentColor" stroke-width="1.4"/><circle cx="9" cy="11.5" r="1.7" stroke="currentColor" stroke-width="1.4"/><circle cx="15.5" cy="5" r="2.6" fill="currentColor"/></svg>
```

**C, Traced to the number (ringed).** The last point in a ring. It read as a
key or a magnifier.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" color="#2f5bea"><path d="M4 15.5 L8.5 10 L12 8.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="4" cy="15.5" r="1.5" fill="currentColor"/><circle cx="8.5" cy="10" r="1.5" fill="currentColor"/><circle cx="14" cy="7.5" r="1.9" fill="currentColor"/><circle cx="14" cy="7.5" r="3.9" stroke="currentColor" stroke-width="1.3"/></svg>
```

The shipped mark (`web/ui/public/favicon.svg`):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><title>TraceBi: every number, traced.</title><rect width="32" height="32" rx="7" fill="#2f5bea"/><g transform="translate(3 3) scale(1.3)" fill="none" stroke="#fff" stroke-width="1.6" stroke-linecap="round"><circle cx="4" cy="15.5" r="2"/><path d="M5.85 14.73 L8.15 13.77 M11.1 11.3 L13.9 6.95"/><circle cx="10" cy="13" r="2"/><circle cx="15.5" cy="4.5" r="2.9" fill="#fff" stroke="none"/></g></svg>
```
