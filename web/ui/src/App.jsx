import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Shared'
import {
  AllModels, OneModel, Home, Legacy, NotFound, PageHeader,
} from './components/Scope'
import Workflow from './pages/Workflow'
import GettingStarted from './pages/GettingStarted'
import Docs from './pages/Docs'
import Connectors from './pages/Connectors'
import Models, { ModelDetail } from './pages/Models'
import Reports from './pages/Reports'
import Pipelines from './pages/Pipelines'
import Explore from './pages/Explore'
import Verify from './pages/Verify'
import Runs from './pages/Runs'

// Every page under the model switcher has two addresses: one model
// (/m/<model>/<page>) and all models (/<page>). See nav.js.
export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />

          <Route path="/m/:model" element={<OneModel>{m => (
            <><PageHeader pageKey="model" model={m} /><ModelDetail key={m} name={m} /></>
          )}</OneModel>} />
          <Route path="/m/:model/explore" element={<OneModel>{m => (
            <><PageHeader pageKey="explore" model={m} /><Explore key={m} model={m} /></>
          )}</OneModel>} />
          <Route path="/m/:model/refresh" element={<OneModel>{m => <Pipelines key={m} model={m} />}</OneModel>} />
          <Route path="/m/:model/reports" element={<OneModel>{m => <Reports key={m} model={m} />}</OneModel>} />
          <Route path="/m/:model/sources" element={<OneModel>{m => <Connectors key={m} model={m} />}</OneModel>} />
          <Route path="/m/:model/runs" element={<OneModel>{m => <Runs key={m} model={m} />}</OneModel>} />

          <Route path="/models" element={<AllModels pageKey="model"><Models pageKey="model" /></AllModels>} />
          <Route path="/explore" element={<AllModels pageKey="explore"><Models pageKey="explore" /></AllModels>} />
          <Route path="/refresh" element={<AllModels pageKey="refresh"><Pipelines /></AllModels>} />
          <Route path="/reports" element={<AllModels pageKey="reports"><Reports /></AllModels>} />
          <Route path="/sources" element={<AllModels pageKey="sources"><Connectors /></AllModels>} />
          <Route path="/runs" element={<AllModels pageKey="runs"><Runs /></AllModels>} />

          <Route path="/verify" element={<Verify />} />
          <Route path="/getting-started" element={<GettingStarted />} />
          <Route path="/handbook" element={<Docs />} />
          <Route path="/workflow" element={<Workflow />} />

          <Route path="/models/:name" element={<Legacy />} />
          <Route path="/connectors" element={<Legacy />} />
          <Route path="/pipelines" element={<Legacy />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
