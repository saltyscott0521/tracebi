import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Point the dev proxy at a non-default API port with TRACEBI_API_PORT.
const apiTarget = `http://localhost:${process.env.TRACEBI_API_PORT || 8000}`

export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist' },
  server: {
    proxy: {
      '/api': apiTarget,
      '/dashboards': apiTarget,
    },
  },
})
