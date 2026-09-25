import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Shared'
import Workflow from './pages/Workflow'
import GettingStarted from './pages/GettingStarted'
import Docs from './pages/Docs'
import Connectors from './pages/Connectors'
import Models from './pages/Models'
import Explore from './pages/Explore'
import Reports from './pages/Reports'
import Verify from './pages/Verify'
import Pipelines from './pages/Pipelines'

export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/reports" replace />} />
          <Route path="/workflow" element={<Workflow />} />
          <Route path="/getting-started" element={<GettingStarted />} />
          <Route path="/handbook" element={<Docs />} />
          <Route path="/connectors" element={<Connectors />} />
          <Route path="/models" element={<Models />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/pipelines" element={<Pipelines />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
