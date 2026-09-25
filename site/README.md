# tracebi.com — the marketing site

The public product/explanation page for TraceBi. This is **surface #1** of the
three in [docs/architecture/frontend-surfaces.md](../docs/architecture/frontend-surfaces.md): the pitch,
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

The landing page is a single self-contained `index.html` (styles inline, fonts
from Google Fonts, one small script for the live receipt + theme toggle). It
works in both light and dark, following the visitor's system theme.

## The docs site (`site/docs/`)

`/docs/` is generated from the `docs/` vault at the repo root — that markdown
is the single source, shared with Obsidian and the app's own Docs page.

```bash
python site/build_docs.py     # docs/*.md → site/docs/*.html
```

**Run this whenever you edit `docs/`.** The output is committed on purpose, so
the site still deploys with no build step; the price is that it can go stale,
which is why `tests/test_docs_site.py` regenerates it in CI and fails if the
result differs from what is checked in. The failure names the fix.

The generator takes the palette and the favicon out of `index.html` rather than
keeping a second copy, so the docs site cannot drift into a different blue than
the landing page. Internal documents (`north-star.md`, `ROADMAP.md`) are never
published, and a test asserts the positioning doc never appears.

## Deploy

Any static host. On Vercel/Netlify, add this as its **own project** with the
**root directory set to `site/`** (framework: "Other"; no build command;
output: the directory itself) — separate from the app deploy, at the apex
domain `tracebi.com`. The "Try the demo" links point at `demo.tracebi.com`
(the app UI running the Vercel + Supabase demo topology); wire that host up
when the demo instance is live.

## Status

The **ask / build / schedule page** (2026-09-23, following
`docs/strategy/vision-and-positioning.md`). It leads with the three ways to use
TraceBi — ask a question, build a one-off analysis, schedule a recurring
report — all from one set of approved definitions, then covers the agent and
human roles, scheduling, the three-phase workflow, the semantic layer,
guardrails, styling, the output and its receipt, and open source vs the planned
Cloud.

`assets/` holds the hero screenshot and the Open Graph image; `sample/` holds a
built copy of the reference project's `portfolio_showcase` report and its
manifest, linked as "Download a sample report". Both are copied into the
Vercel output by `vercel-build.sh`. Rebuild the sample when the showcase
changes (`tracebi report build portfolio_showcase` in
`examples/portfolio_project/`, then copy the `.html` and its
`.html.manifest.json`, with `output_path` set to the bare file name).

Numbers on the page (row counts, figure counts, file sizes, verify output) are
copied from real runs of the reference project. Re-check them when the
reference project changes.
