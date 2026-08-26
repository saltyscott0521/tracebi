# tracebi.com — the marketing site

The public product/explanation page for TraceBi. This is **surface #1** of the
three in [docs/frontend-surfaces.md](../docs/frontend-surfaces.md): the pitch,
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

No build step — a single self-contained `index.html` (styles inline, fonts from
Google Fonts, one small script for the live receipt + theme toggle). It works
in both light and dark, following the visitor's system theme.

## Deploy

Any static host. On Vercel/Netlify, add this as its **own project** with the
**root directory set to `site/`** (framework: "Other"; no build command;
output: the directory itself) — separate from the app deploy, at the apex
domain `tracebi.com`. The "Try the demo" links point at `demo.tracebi.com`
(the app UI running the Vercel + Supabase demo topology); wire that host up
when the demo instance is live.

## Status

The **framework-first marketing page** (ratified 2026-08-26 — see the North Star
positioning). It leads with the framework — *"Reports as code — to keep agents
in line"* — treats the dual-author model (built for agents, controlled by
humans) as a top pillar, walks the three-phase workflow and a stepped user loop,
foregrounds the semantic layer, and demotes the receipt to one property of the
output. Grow the copy and
add pages (pricing, docs) as the product firms up.

Identity: **follows the product theme** — the web UI + report system, so a
visitor lands in a coherent world. **IBM Plex Sans + IBM Plex Mono**; the cool
blue-grey ground (`#eef2f8`), navy ink, the TraceBi blue (`#2e74b5`) as the
accent and deep navy for solid buttons; green/amber/red reserved for the verdict
badges only; the three-phase "layers" motif. It follows the visitor's system
theme and offers a toggle. Links: "Try the demo" → `/app`; GitHub → the repo.
