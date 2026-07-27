import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
// Self-hosted rather than pulled from a CDN: no third-party request on first
// paint, and it keeps working on a corporate network that does not allow one.
// The variable font is a single file covering the whole 100–900 range, which
// is fewer bytes than the four static weights this UI uses (400/600/700/800).
import '@fontsource-variable/inter'
import './styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } },
})

ReactDOM.createRoot(document.getElementById('root')).render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </QueryClientProvider>
)
