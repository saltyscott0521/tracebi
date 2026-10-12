import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Shared'
import {
  AllModels, OneModel, Home, Legacy, ToStage, NotFound, PageHeader,
} from './components/Scope'
import GettingStarted from './pages/GettingStarted'
import Docs from './pages/Docs'
import Connectors from './pages/Connectors'
import Models from './pages/Models'
import Overview from './pages/Overview'
import Reports from './pages/Reports'
import Explore from './pages/Explore'
import Verify from './pages/Verify'
import Runs from './pages/Runs'
import Drafts, { DraftPage } from './pages/Drafts'
import Map from './pages/Map'

// Every page under the model switcher has two addresses: one model
// (/m/<model>/<page>) and all models (/<page>). See nav.js.
export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Home />} />

          {/* The Overview: one page, three stages, an address each. */}
          <Route path="/m/:model" element={<OneModel>{m => <Overview key={m} model={m} stage="reports" />}</OneModel>} />
          <Route path="/m/:model/reports" element={<OneModel>{m => <Overview key={m} model={m} stage="reports" />}</OneModel>} />
          <Route path="/m/:model/model" element={<OneModel>{m => <Overview key={m} model={m} stage="model" />}</OneModel>} />
          <Route path="/m/:model/transform" element={<OneModel>{m => <Overview key={m} model={m} stage="transform" />}</OneModel>} />
          <Route path="/m/:model/explore" element={<OneModel>{m => (
            <><PageHeader pageKey="explore" model={m} /><Explore key={m} model={m} /></>
          )}</OneModel>} />
          <Route path="/m/:model/runs" element={<OneModel>{m => <Runs key={m} model={m} />}</OneModel>} />
          <Route path="/m/:model/refresh" element={<ToStage stage="transform" />} />
          <Route path="/m/:model/sources" element={<ToStage stage="transform" />} />

          <Route path="/models" element={<AllModels pageKey="overview"><Models pageKey="overview" /></AllModels>} />
          <Route path="/explore" element={<AllModels pageKey="explore"><Models pageKey="explore" /></AllModels>} />
          <Route path="/refresh" element={<Navigate to="/models" replace />} />
          <Route path="/reports" element={<AllModels pageKey="reports"><Reports /></AllModels>} />
          <Route path="/sources" element={<AllModels pageKey="sources"><Connectors /></AllModels>} />
          <Route path="/runs" element={<AllModels pageKey="runs"><Runs /></AllModels>} />

          <Route path="/map" element={<Map />} />
          <Route path="/drafts" element={<Drafts />} />
          <Route path="/drafts/:owner/:kind/*" element={<DraftPage />} />
          <Route path="/verify" element={<Verify />} />
          <Route path="/getting-started" element={<GettingStarted />} />
          <Route path="/handbook" element={<Docs />} />
          <Route path="/workflow" element={<Navigate to="/getting-started#phases" replace />} />

          <Route path="/models/:name" element={<Legacy />} />
          <Route path="/connectors" element={<Legacy />} />
          <Route path="/pipelines" element={<Legacy />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
