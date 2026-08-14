import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Point the dev proxy at a non-default API port with TRACEBI_API_PORT.
const apiTarget = `http://localhost:${process.env.TRACEBI_API_PORT || 8000}`

export default defineConfig({
  plugins: [react()],
  // The bundle is built into the Python package, not next to this config.
  // tracebi/web/api/main.py resolves the UI as `<its own dir>/../ui/dist`, which is
  // tracebi/web/ui/dist now that the app lives at tracebi.web.api — so the
  // wheel carries the bundle and `tracebi serve` from an installed package
  // serves the real SPA. The Node workspace stays here; only its output moves.
  build: { outDir: '../../tracebi/web/ui/dist', emptyOutDir: true },
  server: {
    proxy: {
      '/api': apiTarget,
    },
  },
})
