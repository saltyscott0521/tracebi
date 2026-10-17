import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Shared'
import { AllModels, OneModel, Moved } from './components/Scope'
import { dataPath } from './nav'
import GettingStarted from './pages/GettingStarted'
import Docs from './pages/Docs'
import Connectors from './pages/Connectors'
import Models from './pages/Models'
import Overview from './pages/Overview'
import Library, { ReportRoute } from './pages/Reports'
import Ask from './pages/Ask'
import Verify from './pages/Verify'
import Runs from './pages/Runs'
import Drafts, { DraftPage } from './pages/Drafts'
import Map from './pages/Map'

// Four places: Reports (/), Ask, Data and Review. Every older address lands in
// one of them (Moved). See nav.js.
export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/reports/*" element={<ReportRoute />} />

          <Route path="/ask" element={<Ask />} />

          {/* Data: the models, then one model's line with its three stages. */}
          <Route path="/data" element={<AllModels to={m => dataPath(m)}><Models /></AllModels>} />
          <Route path="/data/map" element={<Map />} />
          <Route path="/data/sources" element={<Connectors />} />
          <Route path="/data/:model" element={<OneModel>{m => <Overview key={m} model={m} stage="model" />}</OneModel>} />
          {['transform', 'model', 'reports'].map(stage => (
            <Route key={stage} path={`/data/:model/${stage}`}
                   element={<OneModel>{m => <Overview key={m} model={m} stage={stage} />}</OneModel>} />
          ))}

          {/* Review: drafts, History and Verify a file. */}
          <Route path="/review" element={<Drafts />} />
          <Route path="/drafts" element={<Drafts />} />
          <Route path="/drafts/:owner/:kind/*" element={<DraftPage />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/verify" element={<Verify />} />

          <Route path="/getting-started" element={<GettingStarted />} />
          <Route path="/handbook" element={<Docs />} />
          <Route path="/workflow" element={<Navigate to="/getting-started#phases" replace />} />

          <Route path="/m/:model/*" element={<Moved />} />
          <Route path="*" element={<Moved />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
