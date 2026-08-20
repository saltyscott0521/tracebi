import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
// Self-hosted rather than pulled from a CDN: no third-party request on first
// paint, and it keeps working on a corporate network that does not allow one.
// IBM Plex — the engineered-precision pairing the marketing site and the app
// share, so TraceBi reads as one product. Only the weights this UI uses.
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-sans/700.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css'
import './styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
})

// Mount point. The default build serves at "/" (local dev, the wheel, Docker);
// the Vercel build passes --base=/app/ so the demo app sits under /app behind
// the marketing page. Deriving the router basename from BASE_URL keeps a single
// codebase working at either mount with no per-environment branching.
const basename = import.meta.env.BASE_URL.replace(/\/+$/, '') || undefined

ReactDOM.createRoot(document.getElementById('root')).render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </QueryClientProvider>
)
