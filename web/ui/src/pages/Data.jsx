import { Link, Navigate, useSearchParams } from 'react-router-dom'

import { useAppStatus, useDesk, useModels, usePipelines, useReports } from '../api'
import { PageHeader } from '../components/Scope'
import { Flag, VerdictSummary, reportStates } from '../components/TheLine'
import { ProjectFeedFold } from '../components/Workbench'
import { ago } from '../components/map/states'
import { pipelineFor } from '../components/map/project'
import { dataPath, reportBelongsToModel } from '../nav'
import { Empty, SkeletonList } from '../components/Shared'
import MapView from './Map'

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

// When the model's data was last refreshed: its transform step's last run.
function refreshed(pipeline) {
  if (!pipeline) return { text: 'No refresh pipeline' }
  const layers = pipeline.layers || []
  const step = layers.find(l => l.name === 'transform') || layers[0]
  if (!step?.last_run) return { text: 'Not refreshed yet' }
  if (step.last_status === 'failed') {
    return { flag: { kind: 'bad', glyph: '✕', text: `Refresh failed ${ago(step.last_run)}` } }
  }
  return { text: `Refreshed ${ago(step.last_run)}` }
}

// One model, one row: what people call it (its identifier beside it), its
// shape, whether its built reports still reproduce, and when its data was
// last refreshed. The row opens the model's page.
function ModelRow({ model, reports, pipeline, desk }) {
  const mine = reports.filter(r => reportBelongsToModel(r, model.name))
  const when = refreshed(pipeline)
  const label = model.label || model.name
  return (
    <li>
      <Link to={dataPath(model.name)} className="dlist__row">
        <span className="dlist__main">
          <span className="dlist__name">
            {label}{label !== model.name && <span className="dlist__id">{model.name}</span>}
          </span>
          <span className="dlist__facts">
            {[plural(model.tables.length, 'table'), plural(model.measures.length, 'measure'), plural(mine.length, 'report')].join(' · ')}
          </span>
        </span>
        <span className="dlist__side">
          {desk && mine.length > 0 && <span className="dlist__verdicts"><VerdictSummary states={reportStates(mine, desk)} /></span>}
          <span className="dlist__when">{when.flag ? <Flag flag={when.flag} /> : when.text}</span>
        </span>
      </Link>
    </li>
  )
}

/**
 * Data: the models, one row each, or (?view=map) every model as one picture.
 * With one model there is nothing to pick, so the list opens it.
 */
export default function Data() {
  const [params, setParams] = useSearchParams()
  const map = params.get('view') === 'map'
  const { data, isLoading } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const { data: desk } = useDesk()
  const { data: appStatus } = useAppStatus()
  const dev = !!appStatus?.build_mode

  const models = data || []
  // Old links: /models?m=<model>, /data?model=<model>.
  const legacy = !map && (params.get('m') || params.get('model'))
  if (legacy) return <Navigate to={dataPath(legacy)} replace />
  if (!map && models.length === 1) return <Navigate to={dataPath(models[0].name)} replace />

  return (
    <>
      <PageHeader pageKey="data">
        <div className="seg" role="group" aria-label="Show the models as">
          <button type="button" aria-pressed={!map} onClick={() => setParams({}, { replace: true })}>List</button>
          <button type="button" aria-pressed={map} onClick={() => setParams({ view: 'map' }, { replace: true })}>Map</button>
        </div>
      </PageHeader>
      {map ? <MapView /> : isLoading ? <SkeletonList /> : models.length === 0 ? (
        <Empty icon="⬡" message="No models yet. Create one with tracebi new-model, in models/." />
      ) : (
        <ul className="dlist">
          {[...models].sort((a, b) => (a.label || a.name).localeCompare(b.label || b.name)).map(m => (
            <ModelRow key={m.name} model={m} reports={reports || []} desk={desk}
                      pipeline={pipelineFor(pipelines || [], m.name)} />
          ))}
        </ul>
      )}
      {/* In dev mode (`tracebi dev`) the agent's exhibits and your notes to it
          are here, folded, before any report exists. */}
      {dev && <ProjectFeedFold />}
    </>
  )
}
