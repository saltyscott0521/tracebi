import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { TABS } from './nav'
import { ToastProvider } from './components/Shared'
import { OneModel, Moved } from './components/Scope'
import Docs from './pages/Docs'
import Connectors from './pages/Connectors'
import Data, { DataFrame } from './pages/Data'
import Warehouses from './pages/Warehouses'
import MapView from './pages/Map'
import TablePage from './pages/Table'
import Overview from './pages/Overview'
import Library, { ReportRoute } from './pages/Reports'
import Ask from './pages/Ask'
import Verify from './pages/Verify'
import Runs from './pages/Runs'
import { DraftPage } from './pages/Drafts'
import Review, { ReviewDrafts, ReviewFrame } from './pages/Review'

// Five places: Reports (/), Ask, Data, Review and Docs. Every older address
// lands in one of them (Moved). See nav.js.
export default function App() {
  return (
    <ToastProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/reports/*" element={<ReportRoute />} />

          <Route path="/ask" element={<Ask />} />

          {/* Data: its four tabs (Models, Sources, Warehouse, Map), then one
              model's page: its line, and its tabs. A model's /reports (the
              library, now) is Moved. */}
          <Route path="/data" element={<Data />} />
          <Route path="/data/sources" element={<DataFrame tab="sources"><Connectors /></DataFrame>} />
          <Route path="/data/warehouse" element={<DataFrame tab="warehouse"><Warehouses /></DataFrame>} />
          <Route path="/data/map" element={<DataFrame tab="map"><MapView /></DataFrame>} />
          {/* One table, wherever it lives: a connector's name or inputs, then
              the table (a path under inputs/ keeps its slashes). */}
          <Route path="/data/tables/:source/*" element={<TablePage />} />
          <Route path="/data/:model" element={<OneModel>{m => <Overview key={m} model={m} tab="model" />}</OneModel>} />
          {TABS.map(tab => (
            <Route key={tab} path={`/data/:model/${tab}`}
                   element={<OneModel>{m => <Overview key={m} model={m} tab={tab} />}</OneModel>} />
          ))}

          {/* Review: its tabs Attention, Drafts, History and Verify, each at its
              own address in Review's frame. */}
          <Route path="/review" element={<Review />} />
          <Route path="/review/drafts" element={<ReviewDrafts />} />
          <Route path="/drafts" element={<Navigate to="/review/drafts" replace />} />
          <Route path="/drafts/:owner/:kind/*" element={<DraftPage />} />
          <Route path="/runs" element={<ReviewFrame><Runs /></ReviewFrame>} />
          <Route path="/verify" element={<ReviewFrame><Verify /></ReviewFrame>} />

          {/* Docs: the handbook, Get started first. /handbook and
              /getting-started are Moved, page for page. */}
          <Route path="/docs/*" element={<Docs />} />
          <Route path="/workflow" element={<Navigate to="/docs/get-started#phases" replace />} />

          <Route path="/m/:model/*" element={<Moved />} />
          <Route path="*" element={<Moved />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
