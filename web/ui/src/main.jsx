import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
// Self-hosted rather than pulled from a CDN: no third-party request on first
// paint, and it keeps working on a corporate network that does not allow one.
// Geist Sans and Geist Mono (SIL OFL), variable, so every weight the UI uses is
// one file each.
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
})

// Mount point. The default build serves at "/" (local dev, the wheel, Docker);
// a build with --base=/app/ puts the app under /app, behind a marketing page
// at /. Deriving the router basename from BASE_URL keeps a single
// codebase working at either mount with no per-environment branching.
const basename = import.meta.env.BASE_URL.replace(/\/+$/, '') || undefined

ReactDOM.createRoot(document.getElementById('root')).render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </QueryClientProvider>
)
