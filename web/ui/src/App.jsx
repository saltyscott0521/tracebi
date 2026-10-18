import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { TABS } from './nav'
import { ToastProvider } from './components/Shared'
import { OneModel, Moved } from './components/Scope'
import GettingStarted from './pages/GettingStarted'
import Docs from './pages/Docs'
import Connectors from './pages/Connectors'
import Data from './pages/Data'
import Overview from './pages/Overview'
import Library, { ReportRoute } from './pages/Reports'
import Ask from './pages/Ask'
import Verify from './pages/Verify'
import Runs from './pages/Runs'
import { DraftPage } from './pages/Drafts'
import Review from './pages/Review'

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

          {/* Data: the models (as a list, or ?view=map as one picture), then one
              model's page: its line, and its tabs. /data/map and a model's
              /reports (the library, now) are Moved. */}
          <Route path="/data" element={<Data />} />
          <Route path="/data/sources" element={<Connectors />} />
          <Route path="/data/map" element={<Moved />} />
          <Route path="/data/:model" element={<OneModel>{m => <Overview key={m} model={m} tab="model" />}</OneModel>} />
          {TABS.map(tab => (
            <Route key={tab} path={`/data/:model/${tab}`}
                   element={<OneModel>{m => <Overview key={m} model={m} tab={tab} />}</OneModel>} />
          ))}

          {/* Review: what needs attention, drafts, and Verify a file; History
              and the full Verify page keep their own addresses. */}
          <Route path="/review" element={<Review />} />
          <Route path="/drafts" element={<Navigate to="/review#drafts" replace />} />
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
