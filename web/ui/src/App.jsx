import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Connectors from './pages/Connectors'
import Models from './pages/Models'
import Reports from './pages/Reports'
import Pipelines from './pages/Pipelines'
import Dashboards from './pages/Dashboards'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/connectors" element={<Connectors />} />
        <Route path="/models" element={<Models />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/pipelines" element={<Pipelines />} />
        <Route path="/dashboards" element={<Dashboards />} />
      </Routes>
    </Layout>
  )
}
