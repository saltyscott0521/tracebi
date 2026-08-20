#!/usr/bin/env bash
# Vercel build: one deploy, three surfaces on a single GitHub auto-deploy.
#
#   /       → the marketing site   (site/index.html — the front door)
#   /app/*  → the demo app         (web/ui, built with --base=/app/)
#   /api/*  → the Python function  (api/index.py, routed by vercel.json)
#
# The app is built with --base=/app/ ONLY here; the default build (the wheel,
# Docker, `python -m tracebi.web.run`, local dev) stays mounted at / — the
# router basename is derived from BASE_URL, so one codebase serves either mount.
set -euo pipefail

# Build the app so its asset URLs resolve under /app.
(cd web/ui && npm ci && npm run build -- --base=/app/)

# Assemble the directory Vercel serves.
rm -rf .vercel_out
mkdir -p .vercel_out/app
cp -r tracebi/web/ui/dist/. .vercel_out/app/
cp site/index.html .vercel_out/index.html

echo "Assembled .vercel_out: / = marketing, /app = demo app"
