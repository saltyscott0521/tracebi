import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Shared'
import Home from './pages/Home'
import Connectors from './pages/Connectors'
import Models from './pages/Models'
import Explore from './pages/Explore'
import Reports from './pages/Reports'
import Requests from './pages/Requests'
import Pipelines from './pages/Pipelines'
import Dashboards from './pages/Dashboards'

export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/connectors" element={<Connectors />} />
          <Route path="/models" element={<Models />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/requests" element={<Requests />} />
          <Route path="/pipelines" element={<Pipelines />} />
          <Route path="/dashboards" element={<Dashboards />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
