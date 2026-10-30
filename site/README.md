# tracebi.com — the marketing site

The public product/explanation page for TraceBi. This is **surface #1** of the
three in [design/frontend-surfaces.md](../design/frontend-surfaces.md): the pitch,
docs, and pricing, whose primary call to action branches into the live demo app.

**It is a separate front-end from the distributed app UI** (`web/ui/`). It is a
static site, it ships to **nobody's deployment**, and it is never packaged in
the wheel (the wheel only carries `tracebi/**`; a top-level `site/` is outside
it). Keep it that way — marketing content must never leak into `web/ui/`.

## Preview locally

Just open `index.html`, or serve the folder:

```bash
cd site && python3 -m http.server 8899   # → http://localhost:8899
```

The landing page is a single self-contained `index.html` (styles and one small
script inline: the theme switch, scroll reveals, the hero's trace, the "trace a
number" demo, the filter before/after and the on-demand live report). Its type is
Geist and Geist Mono, self-hosted in `assets/fonts/` (the files TraceBi's reports
and app use; SIL OFL, `assets/fonts/Geist-OFL.txt`), so the page requests nothing
from any other host. It works in light and dark, following the visitor's system
theme until they pick one, and honours `prefers-reduced-motion`.

## The docs site (`site/docs/`)

`/docs/` is generated from the `docs/` vault at the repo root — that markdown
is the single source, shared with Obsidian and the app's own Docs page.

```bash
python site/build_docs.py     # docs/*.md → site/docs/*.html, and docs/index.md
```

The order of sections and pages is `docs/toc.yaml`, the one list the site's nav,
the app's Docs sidebar (through `/api/docs`) and the generated `docs/index.md`
all read. A page that changes folder is listed under `moved:` there, and the
generator writes a forwarding page at its old address.

**Run this whenever you edit `docs/`.** The output is committed on purpose, so
the site still deploys with no build step; the price is that it can go stale,
which is why `tests/test_docs_site.py` regenerates it in CI and fails if the
result differs from what is checked in. The failure names the fix.

The generator takes the palette and the favicon out of `index.html` rather than
keeping a second copy, so the docs site cannot drift into a different blue than
the landing page. The internal positioning doc (`north-star.md`) is never
published, and a test asserts it never appears. Design notes and strategy live
in `design/` at the repo root, outside the vault, so nothing renders them.

## Deploy

Any static host. On Vercel/Netlify, add this as its **own project** with the
**root directory set to `site/`** (framework: "Other"; no build command;
output: the directory itself) — separate from the app deploy, at the apex
domain `tracebi.com`. The "Try the demo" links point at
`https://tracebi.com/app` (nginx proxies `/app` to the demo container; the
internal hostname is not a public URL). nginx also proxies
`https://tracebi.com/mcp` to the hosted agent gateway (internal host
`mcp.tracebi.com`) — see `deploy/mcp/README.md`.

## Status

The **"every number shows its work" page** (2026-10-30, SITE-2; NOTES.md has
the story and the honesty choices). Plain words first, for a reader with no
glossary: the problem (a number nobody can explain), what TraceBi is, how it
works in three steps, why it matters, who it is for; then the proof (trace a
number, live reports, agents and the workbench, print), teams, open source, a
"for engineers" layer (the three phases, the CLI, verify, what a trace does and
does not claim), the FAQ and how to start. Technical detail sits behind "For
engineers" disclosures and links into `/docs/`. The word "receipt" is retired
for **trace** and **manifest**.

What is real on it:

- `sample/` holds three builds of the reference workspace, each with its
  manifest: `portfolio_showcase` (the app lane, Signal), `affordability` (the
  editorial long read) and `portfolio_dashboard`. Rebuild them when the reports
  change: in `examples/portfolio_project/` run `python run_workflow.py` (or
  `tracebi report build <name>`), copy each `output/<model>/<name>.html` and its
  `.html.manifest.json` here with `output_path` set to the bare file name, and
  check `tracebi verify --file site/sample/<name>.html` reads FILE INTACT.
  Restore the tracked manifests under `examples/portfolio_project/output/`
  afterwards.
- `assets/shots/` are captures of those builds (1440 × 900 at 2×, light and
  dark; one with the trace drawer open, one filtered to Software), the
  workbench MCP Apps panel running against the reference workspace (the chat
  beside it is labelled an illustration), and pages 1 and 4 of
  `portfolio_dashboard`'s PDF (`--format pdf`, page 4 is "How these numbers
  were made"). Each is AVIF and WebP at two widths plus a JPEG fallback
  (the affordability and dashboard captures, used only as thumbnails: AVIF at
  800 and the JPEG).
- `assets/og.jpg` is a 1200 × 630 card: the headline and the showcase capture.
- The trace demo's facts (sources, `fact_holdings` 25 rows and 5 checks, the
  measure, the query, fingerprint `f1abefad…`) and the verify lines are copied
  from the sample's manifest and from running `tracebi verify` on it.
  Re-check them when the reference workspace changes.
