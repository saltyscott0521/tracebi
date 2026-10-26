import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Shared'
import { OneModel, Moved } from './components/Scope'
import Docs from './pages/Docs'
import Connectors from './pages/Connectors'
import ModelList, { DataFrame, ModelTransform } from './pages/Data'
import Flow from './pages/Flow'
import Transforms from './pages/Transforms'
import Warehouses from './pages/Warehouses'
import Transform from './pages/Transform'
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

          {/* Data: Overview (the board) and its four folders, Sources,
              Transforms, Warehouse and Models, each with a page per thing in
              it, all in Data's frame. /data/models/<m>/transform lands on the
              model's transform. Data's older addresses (a model at /data/<m>
              and its tabs, /data/tables/…, the Map) are Moved. */}
          <Route path="/data" element={<Flow />} />
          <Route path="/data/sources" element={<DataFrame folder="sources"><Connectors /></DataFrame>} />
          <Route path="/data/sources/:name" element={<DataFrame folder="sources"><Connectors /></DataFrame>} />
          {/* One source table: a connection's, or a file under inputs/ (its
              path keeps its slashes). */}
          <Route path="/data/sources/:source/*" element={<TablePage />} />
          <Route path="/data/transforms" element={<DataFrame folder="transforms"><Transforms /></DataFrame>} />
          <Route path="/data/transforms/:name" element={<Transform />} />
          <Route path="/data/warehouse" element={<DataFrame folder="warehouse"><Warehouses /></DataFrame>} />
          <Route path="/data/warehouse/:table" element={<TablePage warehouse />} />
          <Route path="/data/models" element={<ModelList />} />
          <Route path="/data/models/:model" element={<OneModel>{m => <Overview key={m} model={m} />}</OneModel>} />
          <Route path="/data/models/:model/transform" element={<ModelTransform />} />
          <Route path="/data/*" element={<Moved />} />

          {/* Review: its tabs Attention, Drafts, History and Verify, each at its
              own address in Review's frame. */}
          <Route path="/review" element={<Review />} />
          <Route path="/review/drafts" element={<ReviewDrafts />} />
          <Route path="/drafts" element={<Navigate to="/review/drafts" replace />} />
          <Route path="/drafts/:owner/:kind/*" element={<DraftPage />} />
          <Route path="/runs" element={<ReviewFrame><Runs /></ReviewFrame>} />
          <Route path="/verify" element={<ReviewFrame><Verify /></ReviewFrame>} />

          {/* Docs: the handbook, in docs/toc.yaml's order. /handbook and
              /getting-started are Moved, page for page. */}
          <Route path="/docs/*" element={<Docs />} />
          <Route path="/workflow" element={<Navigate to="/docs/concepts/the-three-phase-workflow" replace />} />

          <Route path="/m/:model/*" element={<Moved />} />
          <Route path="*" element={<Moved />} />
        </Routes>
      </Layout>
    </ToastProvider>
  )
}
