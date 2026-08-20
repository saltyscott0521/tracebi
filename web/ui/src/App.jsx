import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Shared'
import Home from './pages/Home'
import Workflow from './pages/Workflow'
import GettingStarted from './pages/GettingStarted'
import Connectors from './pages/Connectors'
import Models from './pages/Models'
import Explore from './pages/Explore'
import Reports from './pages/Reports'
import Pipelines from './pages/Pipelines'

export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/workflow" element={<Workflow />} />
          <Route path="/getting-started" element={<GettingStarted />} />
          <Route path="/connectors" element={<Connectors />} />
          <Route path="/models" element={<Models />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/pipelines" element={<Pipelines />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
