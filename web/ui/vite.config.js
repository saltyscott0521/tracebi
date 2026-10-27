import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { redact } from '@tanstack/redact/vite'

// Point the dev proxy at a non-default API port with TRACEBI_API_PORT.
const apiTarget = `http://localhost:${process.env.TRACEBI_API_PORT || 8000}`

export default defineConfig({
  // TanStack Redact stands in for React: the same API, a smaller runtime,
  // synchronous rendering. React Flow's store imports use-sync-external-store's
  // selector shim as a default object, which the swap cannot follow, so that
  // one module is left as it is.
  plugins: [
    redact({ skip: ['use-sync-external-store/shim/with-selector', 'use-sync-external-store/shim/with-selector.js', 'use-sync-external-store/with-selector', 'use-sync-external-store/with-selector.js'] }),
    react(),
  ],
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
