import { Fragment } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'

import { useAppStatus, useConnectors, useDesk, useInputs, useModels, usePipelines, useReports } from '../api'
import { PageHeader } from '../components/Scope'
import { Flag, VerdictSummary, reportStates } from '../components/TheLine'
import { ProjectFeedFold } from '../components/Workbench'
import { ago } from '../components/map/states'
import { pipelineFor } from '../components/map/project'
import { upstreamOf } from '../chain'
import {
  DATA_TABS, DATA_TAB_LABEL, dataPath, dataTabPath, libraryPath, mapPath, reportBelongsToModel,
  sourcesPath, warehousePath,
} from '../nav'
import { Empty, SkeletonList } from '../components/Shared'

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

/**
 * Data's frame: its heading, then its four tabs in the order the data flows
 * (Models, Sources, Warehouse, Map), each at its own address, around the tab
 * you are on.
 */
export function DataFrame({ tab, children }) {
  const { data: appStatus } = useAppStatus()
  const dev = !!appStatus?.build_mode
  return (
    <div className="fade-in">
      <PageHeader pageKey="data" />
      <nav aria-label="Data: what to show">
        <ul className="dtabs review__tabs">
          {DATA_TABS.map(key => (
            <li key={key}>
              <Link to={dataTabPath(key)} aria-current={tab === key ? 'page' : undefined}>{DATA_TAB_LABEL[key]}</Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="stage">{children}</div>
      {/* In dev mode (`tracebi dev`) the agent's exhibits and your notes to it
          are here, folded, before any report exists. */}
      {dev && <ProjectFeedFold />}
    </div>
  )
}

// One link of a chain row: a count or a name, and where it leads.
function Seg({ to, children }) {
  return <li><Link to={to} className="chain__seg">{children}</Link></li>
}

// One model, one row: what people call it (its identifier beside it), then
// its chain left to right, each segment a link to where that part lives:
// the sources its transform reads, the transform, the warehouse tables, the
// model's measures, and its reports. On the right, whether its built reports
// still reproduce, and when its data was last refreshed.
function ChainRow({ model, reports, pipeline, desk, up }) {
  const mine = reports.filter(r => reportBelongsToModel(r, model.name))
  const when = refreshed(pipeline)
  const label = model.label || model.name
  const nSources = up.connections.length + up.files.length
  const segs = [
    <Seg key="s" to={sourcesPath(model.name)}>
      {plural(nSources, 'source')}
    </Seg>,
    up.transform
      ? <Seg key="t" to={dataPath(model.name, 'transform')}>
          <code>{up.transform}</code>
        </Seg>
      : <li key="t"><span className="chain__seg chain__seg--none">No transform</span></li>,
    <Seg key="w" to={warehousePath(model.name)}>
      {plural(model.tables.length, 'table')}
    </Seg>,
    <Seg key="m" to={dataPath(model.name)}>
      {plural(model.measures.length, 'measure')}
    </Seg>,
    <Seg key="r" to={libraryPath(model.name)}>
      {plural(mine.length, 'report')}
    </Seg>,
  ]
  return (
    <li className="chain" data-model={model.name}>
      <div className="chain__head">
        <Link to={dataPath(model.name)} className="chain__name">
          {label}{label !== model.name && <span className="dlist__id">{model.name}</span>}
        </Link>
        <span className="dlist__side">
          {desk && mine.length > 0 && <span className="dlist__verdicts"><VerdictSummary states={reportStates(mine, desk)} /></span>}
          <span className="dlist__when">{when.flag ? <Flag flag={when.flag} /> : when.text}</span>
        </span>
      </div>
      <ol className="chain__line" aria-label={`How ${label} is made`}>
        {segs.map((s, i) => (
          <Fragment key={i}>
            {i > 0 && <li className="chain__arrow" aria-hidden="true">→</li>}
            {s}
          </Fragment>
        ))}
      </ol>
    </li>
  )
}

/** Data's Models tab (/data): every model as a chain row. */
export default function Data() {
  const [params] = useSearchParams()
  const { data, isLoading } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const { data: connectors } = useConnectors()
  const { data: inputs } = useInputs()
  const { data: desk } = useDesk()

  // Old links: /data?view=map is the Map tab; /models?m=<model>, /data?model=<model> a model's page.
  if (params.get('view') === 'map') return <Navigate to={mapPath(params.get('model') || '')} replace />
  const legacy = params.get('m') || params.get('model')
  if (legacy) return <Navigate to={dataPath(legacy)} replace />

  const models = data || []
  return (
    <DataFrame tab="models">
      {isLoading ? <SkeletonList /> : models.length === 0 ? (
        <Empty icon="⬡" message="No models yet. Create one with tracebi new-model, in models/." />
      ) : (
        <ul className="dlist chains">
          {[...models].sort((a, b) => (a.label || a.name).localeCompare(b.label || b.name)).map(m => (
            <ChainRow key={m.name} model={m} reports={reports || []} desk={desk}
                      pipeline={pipelineFor(pipelines || [], m.name)}
                      up={upstreamOf({ model: m.name, pipelines, connectors, inputs })} />
          ))}
        </ul>
      )}
    </DataFrame>
  )
}
