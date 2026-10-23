import { Fragment } from 'react'
import { Link } from 'react-router-dom'

import {
  useAppStatus, useConnectors, useDesk, useInputs, useModels, usePipelines, useReports, useTransforms, useWarehouses,
} from '../api'
import { PageHeader } from '../components/Scope'
import { Flag, VerdictSummary, reportStates } from '../components/TheLine'
import { ProjectFeedFold } from '../components/Workbench'
import { ago } from '../when'
import { count } from '../format'
import { FORM_LABEL, pipelineFor, upstreamOf } from '../chain'
import {
  DATA_TABS, DATA_TAB_LABEL, dataPath, dataTabPath, libraryPath, reportBelongsToModel,
  sourcesPath, warehousePath,
} from '../nav'
import { Badge, Empty, SkeletonList } from '../components/Shared'

// When the model's data was last refreshed: its transform step's last run.
// A transform run outside the app (run_workflow.py, `tracebi run-transform`)
// leaves no run here, but its sink certificate records when it wrote the
// tables (*written*), so that is said instead of "not refreshed".
function refreshed(pipeline, written) {
  if (!pipeline) return { text: 'No refresh pipeline' }
  const layers = pipeline.layers || []
  const step = layers.find(l => l.name === 'transform') || layers[0]
  if (!step?.last_run) return { text: written ? `Written ${ago(written)} · outside the app` : 'Not refreshed yet' }
  if (step.last_status === 'failed') {
    return { flag: { kind: 'bad', glyph: '✕', text: `Refresh failed ${ago(step.last_run)}` } }
  }
  return { text: `Refreshed ${ago(step.last_run)}` }
}

/**
 * Data's frame: its heading, then its five tabs (Flow, the board, then
 * Sources, Transforms, Warehouse and Models, the lists behind it in the order
 * the data flows), each at its own address, around the tab you are on.
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
// still reproduce, and when its data was last refreshed. The transform goes
// by its file, its form a chip beside it; a pipeline that runs no transform
// file (a Python medallion runner) reads "pipeline" in the same slot, Python
// its chip: the mechanism is the chip, never the name of the stage.
function ChainRow({ model, reports, pipeline, desk, up, written, form }) {
  const mine = reports.filter(r => reportBelongsToModel(r, model.name))
  const when = refreshed(pipeline, written)
  const label = model.label || model.name
  const nSources = up.connections.length + up.files.length
  const segs = [
    <Seg key="s" to={sourcesPath(model.name)}>
      {count(nSources, 'source')}
    </Seg>,
    up.transform
      ? <Seg key="t" to={dataPath(model.name, 'transform')}>
          <code>{up.transform}</code>{form && <> <Badge>{FORM_LABEL[form] || form}</Badge></>}
        </Seg>
      : pipeline
        ? <Seg key="t" to={dataPath(model.name, 'transform')}>
            <span title={pipeline.pipeline}>pipeline</span> <Badge>Python</Badge>
          </Seg>
        : <li key="t"><span className="chain__seg chain__seg--none">No transform</span></li>,
    <Seg key="w" to={warehousePath(model.name)}>
      {count(model.tables.length, 'table')}
    </Seg>,
    <Seg key="m" to={dataPath(model.name)}>
      {count(model.measures.length, 'measure')}
    </Seg>,
    <Seg key="r" to={libraryPath(model.name)}>
      {count(mine.length, 'report')}
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

// When the newest table *model* reads was written, by its certificate.
function writtenFor(warehouses, model) {
  return (warehouses?.warehouses || []).flatMap(w => w.tables)
    .filter(t => t.read_by.includes(model) && t.written_by?.at)
    .map(t => t.written_by.at).sort().pop()
}

/** Data's Models tab (/data/models): every model as a chain row. */
export default function ModelList() {
  const { data, isLoading } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const { data: connectors } = useConnectors()
  const { data: inputs } = useInputs()
  const { data: desk } = useDesk()
  const { data: warehouses } = useWarehouses()
  const { data: transforms } = useTransforms()
  const formOf = name => (transforms || []).find(t => t.name === name)?.form

  const models = data || []
  return (
    <DataFrame tab="models">
      {isLoading ? <SkeletonList /> : models.length === 0 ? (
        <Empty message="No models yet. Create one with tracebi new-model, in models/." />
      ) : (
        <ul className="dlist chains">
          {[...models].sort((a, b) => (a.label || a.name).localeCompare(b.label || b.name)).map(m => {
            const up = upstreamOf({ model: m.name, pipelines, connectors, inputs })
            return (
              <ChainRow key={m.name} model={m} reports={reports || []} desk={desk}
                        pipeline={pipelineFor(pipelines || [], m.name)} written={writtenFor(warehouses, m.name)}
                        up={up} form={up.transform && formOf(up.transform)} />
            )
          })}
        </ul>
      )}
    </DataFrame>
  )
}
