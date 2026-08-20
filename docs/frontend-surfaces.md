# Front-end surfaces — tracebi.com vs. the distributed app

**Status: decided (2026-08-20).** How the web front-ends are split, so the
public product site and the UI that ships to customer deployments stay cleanly
separable as both grow.

## Three surfaces, three audiences

| Surface | Who it's for | Talks to | Home | In the wheel? |
|---|---|---|---|---|
| **tracebi.com** | strangers — marketing, explanation, docs, pricing | nothing (or a demo instance) | its **own** project | ❌ never |
| **The app UI** (`web/ui/` → `tracebi/web/ui/dist`) | a customer, against *their own* registry | the customer's own FastAPI | the wheel, served at their `/` | ✅ yes |
| **Hosted control plane** (later) | paying orgs — auditor pane, retention, identity | the paid backend | separate SaaS | ❌ its own thing |

## The boundary rule

> If a logged-out stranger should see it, it belongs on **tracebi.com**. If it
> only means anything with a customer's models and warehouse loaded, it belongs
> in the **app**.

Hold that line and the two never entangle: they are different codebases talking
to different things. The app is a pure API client of the customer's own
FastAPI — it needs **zero** knowledge that tracebi.com exists.

## The adopted flow: marketing → demo

`tracebi.com` is the marketing and explanation page for the product. It carries
the pitch (the receipt, the offline verifier, the self-contained artifact),
the docs, and pricing — and its primary call to action **branches into a live
demo app**: a hosted instance of the distributed app UI, seeded with the
reference project, so a visitor can click through real models, run a report,
and verify a file without installing anything.

The demo instance is exactly the app UI running the
[Vercel + Supabase](deploy-vercel-supabase.md) deploy — which is honestly a
**demo topology** (rendered receipts don't persist on a read-only serverless
FS; see that doc). That is the right role for it: a try-it surface, not a
production claim.

```
tracebi.com  ──"Try the demo"──▶  demo.tracebi.com   (the app UI, seeded)
 (marketing, its own project)      (a hosted instance of tracebi/web/ui/dist)
                                            │
                                   a customer installs the wheel and gets
                                   the SAME app UI against THEIR data, at /
```

## What ships where

- The **wheel packages only the app UI** (`artifacts = ["tracebi/web/ui/dist/**"]`).
  A CI job asserts the bundle is in the wheel and that nothing top-level named
  `web` ships. The marketing site is a **different build**, deployed
  independently, and must never touch the wheel.
- No route collision: `tracebi.com` is a public apex domain; the app is served
  at each customer's own `/`.

## Keeping them separable (set up when tracebi.com is built)

1. **Its own project.** Build tracebi.com in a separate repo, or — if it must
   live here — a top-level `site/` that is explicitly excluded from wheel
   packaging. Never nest it inside `web/ui/`.
2. **Share brand, not runtime.** If you want one visual identity, extract a
   tiny `@tracebi/brand` package (tokens, logo, fonts) both import. That keeps
   them *looking* like one product without either *depending* on the other.
3. **Two deploys, always.** The day tracebi.com ships, keep marketing and the
   demo app as separate deployments (`tracebi.com` vs. `demo.tracebi.com`).
   Don't let marketing content — pricing, "about", the pitch — creep into
   `web/ui/`.

## Growing the app into a real app (on-thesis)

Making the distributed UI a full **app** is the direction — but as an
**operational + trust console**, not a viz builder. On-thesis growth:

- browse and run published reports; download the HTML-with-receipt
- **verify status at a glance**, click-to-verify a file, the receipt drawer
  front-and-centre — making the trust *visible* is the UI's highest-leverage
  work
- manage models and pipelines; schedule and deliver reports

The one line to hold: **the product is the verifiable file, not a dashboard
server.** Don't grow the app into drag-and-drop chart authoring — that is the
Tableau turf the self-contained artifact exists to displace. Authoring already
has two better homes: the CLI / `tracebi dev` for humans, and the MCP gateway
for agents.
