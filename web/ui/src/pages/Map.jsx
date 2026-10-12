import { useEffect, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import { useConnectors, useDesk, useModel, useModels, usePipelines, useReports } from '../api'
import { lastModel, rememberModel } from '../nav'
import { Empty, ErrorDetail, SkeletonCard } from '../components/Shared'
import MapCanvas from '../components/map/MapCanvas'
import { Legend, Readout } from '../components/map/Readout'
import { analyze, modelLayout, parseSel, validSel } from '../components/map/model'
import { projectLayout } from '../components/map/project'
import { modelReadout, projectReadout } from '../components/map/readout'
import '../components/map/map.css'

// The Map: the project as one picture, from what is written (transform, model,
// report) to what is handed on (the warehouse, its tables, the measures).
//
//   ?model=<name>             zoomed into one model; absent: every model
//   ?model=<name>&sel=measure:<m>   a measure's path is lit
//   ?model=<name>&sel=report:<r>    a report's path is lit
//
// The URL holds the zoom and the selection, so the browser's back and forward
// buttons walk through them. This page is not routed yet: mount it wherever
// the sidebar's Map item points. (Named MapPage so it does not shadow the
// global Map; it is the default export.)

const Back = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
    <path d="M15 18l-6-6 6-6" />
  </svg>
)

export default function MapPage() {
  const [params, setParams] = useSearchParams()
  const models = useModels()
  const reports = useReports()
  const pipelines = usePipelines()
  const connectors = useConnectors()
  const desk = useDesk()

  const names = (models.data || []).map(m => m.name)
  const asked = params.get('model') || ''
  const zoomed = names.includes(asked) ? asked : ''
  const info = useModel(zoomed)

  // The model you were last in stays tinted on the whole-project map.
  useEffect(() => { if (zoomed) rememberModel(zoomed) }, [zoomed])
  const tinted = names.includes(lastModel()) ? lastModel() : ''

  const builds = useMemo(
    () => Object.fromEntries((desk.data?.builds || []).map(b => [b.report, b])), [desk.data])
  const byName = useMemo(
    () => Object.fromEntries((connectors.data || []).map(c => [c.name, c])), [connectors.data])

  const analysis = useMemo(
    () => (zoomed && info.data ? analyze(info.data, reports.data || [], zoomed) : null),
    [zoomed, info.data, reports.data])
  const sel = zoomed && analysis ? validSel(parseSel(params.get('sel')), analysis) : null

  const layout = useMemo(() => {
    if (!models.data) return null
    if (!zoomed) {
      return projectLayout({
        models: models.data, connectors: byName, pipelines: pipelines.data || [],
        reports: reports.data || [], builds, tinted,
      })
    }
    return analysis && modelLayout({
      name: zoomed, info: info.data, a: analysis, pipelines: pipelines.data || [], builds, sel,
    })
  }, [models.data, zoomed, byName, pipelines.data, reports.data, builds, tinted, analysis, info.data, sel])

  if (models.error) return <ErrorDetail error={models.error} />
  const waiting = [models, reports, pipelines, connectors, desk].some(q => q.isLoading) || (zoomed && info.isLoading)
  if (waiting) return <SkeletonCard />
  if (!names.length) {
    return <Empty message="No models yet. Add one with tracebi new-model and it appears here, with its transform and its reports." />
  }
  if (zoomed && info.error) return <ErrorDetail error={info.error} />
  if (!layout) return <SkeletonCard />

  const go = next => setParams(next)
  const open = (model, pick) => go(pick ? { model, sel: pick } : { model })
  const activate = node => {
    const { zoom, select } = node.action
    if (zoom) return open(zoom, node.action.sel)
    return go(params.get('sel') === select ? { model: zoomed } : { model: zoomed, sel: select })
  }

  const readout = zoomed
    ? modelReadout({ name: zoomed, info: info.data, a: analysis, sel, builds })
    : projectReadout(layout.summary, layout.bands.some(b => b.tinted))

  return (
    <div className="map-page">
      <header className="map-head">
        <div className="map-head__main">
          <nav aria-label="Zoom" className="map-head__crumb">
            {zoomed && <button type="button" className="map-btn" onClick={() => go({})}><Back />All models</button>}
            <span className="map-cap">Map</span>
          </nav>
          <h1 className={zoomed ? 'map-mono' : ''}>{zoomed || 'All models'}</h1>
        </div>
        <p className="map-head__hint">
          {zoomed ? 'Pick a measure or a report to light its path.' : 'Open a model to see its measures and which reports use them.'}
        </p>
      </header>

      {asked && !zoomed && <p className="map-note" role="status">No model named “{asked}”. Showing every model.</p>}
      <p className="map-narrow">The map is wide; scroll sideways, or use Overview, which shows the same line stacked.</p>

      <MapCanvas layout={layout} label={zoomed ? `Map of ${zoomed}` : 'Map of every model'}
                 onActivate={activate} onOpen={model => open(model)} />

      <div className="map-under">
        <Readout readout={readout} />
        <Legend />
      </div>
    </div>
  )
}
