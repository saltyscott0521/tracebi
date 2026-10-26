import { Fragment } from 'react'
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'

import {
  useAppStatus, useConnectors, useDesk, useInputs, useModels, usePipelines, useReports, useTransforms, useWarehouses,
} from '../api'
import { Flag, VerdictSummary, reportStates, useModelFolder } from '../components/TheLine'
import { ProjectFeedFold } from '../components/Workbench'
import { ago } from '../when'
import { count } from '../format'
import { FORM_LABEL, pipelineFor, transformOf, upstreamOf } from '../chain'
import {
  dataFolder, modelPath, movedTo, reportBelongsToModel, sourcesPath, transformPath, warehousePath,
} from '../nav'
import { Badge, Empty, PageSub, PageTitle, SkeletonCard, SkeletonList } from '../components/Shared'

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
 * "Data › Warehouse › fact_holdings": where a thing's page sits under Data.
 * *trail* is [[path, label], …] after Data; *here* is the thing's own name,
 * set as code when *code* (a table, a transform) and as words otherwise (a
 * model's label).
 */
export function DataCrumbs({ trail = [], here, code = false }) {
  return (
    <nav aria-label="Breadcrumb" className="rp__crumb tpage__crumb">
      <Link to="/data">Data</Link>
      {trail.map(([to, text]) => (
        <Fragment key={to}><span aria-hidden="true">›</span><Link to={to}>{text}</Link></Fragment>
      ))}
      {here && <>
        <span aria-hidden="true">›</span>
        <span aria-current="page" className={code ? 'tpage__crumb-here' : 'rp__crumb-here'}>{here}</span>
      </>}
    </nav>
  )
}

/**
 * Data's one frame, around every page under /data. A folder's page (*folder*,
 * a DATA_FOLDERS key) is headed by the folder's name and one line of what it
 * holds; a thing's page by its breadcrumb (*trail*, *here*, *code*: see
 * DataCrumbs), and its own h1 is the page's. The sidebar marks the folder.
 * An older address that only its query told apart (?source=, ?file=,
 * ?model=) moves to the page that replaced it.
 */
export function DataFrame({ folder, trail, here, code, children }) {
  const { pathname, search, hash } = useLocation()
  const { data: appStatus } = useAppStatus()
  const dev = !!appStatus?.build_mode
  const moved = movedTo(pathname, search)
  if (moved) return <Navigate to={moved + hash} replace />
  const f = folder && dataFolder(folder)
  return (
    <div className="fade-in">
      {f ? (
        <header className="page-header">
          <PageTitle>{f.label}</PageTitle>
          <PageSub>{f.sub}</PageSub>
        </header>
      ) : <DataCrumbs trail={trail} here={here} code={code} />}
      {children}
      {/* In dev mode (`tracebi dev`) the agent's exhibits and your notes to it
          are here, folded, before any report exists. */}
      {dev && <ProjectFeedFold />}
    </div>
  )
}

/**
 * /data/models/<m>/transform is not a page: it lands on the transform the
 * model's pipeline runs, or on the model when it has none. The model page's
 * old Transform tab and the Refresh links that knew only the model go there.
 */
export function ModelTransform() {
  const { model } = useParams()
  const { data: pipelines, isLoading } = usePipelines()
  if (isLoading) return <SkeletonCard />
  const transform = transformOf(pipelines, model)
  return <Navigate to={transform ? transformPath(transform) : modelPath(model)} replace />
}

// One link of a chain row: a count or a name, and where it leads.
function Seg({ to, children }) {
  return <li><Link to={to} className="chain__seg">{children}</Link></li>
}

// One model, one row: what people call it (its identifier beside it), then
// its chain left to right, each segment a link to a different place: the
// sources, the transform's page, the warehouse group that transform wrote,
// the model's measures, and its folder in the library. On the right, whether
// its built reports still reproduce, and when its data was last refreshed.
// The transform goes by its file, its form a chip beside it; a pipeline that
// runs no transform file (a Python medallion runner) reads "pipeline" in the
// same slot, Python its chip, and has no page to link: the mechanism is the
// chip, never the name of the stage.
function ChainRow({ model, reports, pipeline, desk, up, written, form, group }) {
  const mine = reports.filter(r => reportBelongsToModel(r, model.name))
  const when = refreshed(pipeline, written)
  const label = model.label || model.name
  const nSources = up.connections.length + up.files.length
  const folder = useModelFolder(model.name)
  const segs = [
    <Seg key="s" to={sourcesPath()}>
      {count(nSources, 'source')}
    </Seg>,
    up.transform
      ? <Seg key="t" to={transformPath(up.transform)}>
          <code>{up.transform}</code>{form && <> <Badge>{FORM_LABEL[form] || form}</Badge></>}
        </Seg>
      : pipeline
        ? <li key="t"><span className="chain__seg chain__seg--none">
            <span title={pipeline.pipeline}>pipeline</span> <Badge>Python</Badge>
          </span></li>
        : <li key="t"><span className="chain__seg chain__seg--none">No transform</span></li>,
    <Seg key="w" to={group ? `${warehousePath()}?group=${encodeURIComponent(group)}` : warehousePath()}>
      {count(model.tables.length, 'table')}
    </Seg>,
    <Seg key="m" to={`${modelPath(model.name)}?view=measures`}>
      {count(model.measures.length, 'measure')}
    </Seg>,
    <Seg key="r" to={folder}>
      {count(mine.length, 'report')}
    </Seg>,
  ]
  return (
    <li className="chain" data-model={model.name}>
      <div className="chain__head">
        <Link to={modelPath(model.name)} className="chain__name">
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

// The warehouse browser's group for what *transform* wrote (its id in
// modelGraph.warehouseSchema: <warehouse>:<contract>), or null.
function groupFor(warehouses, transform) {
  for (const w of warehouses?.warehouses || []) {
    const wr = (w.writers || []).find(x => x.transform === transform)
    if (wr) return `${w.name}:${wr.contract}`
  }
  return null
}

/** Data's Models folder (/data/models): every model as a chain row. */
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
    <DataFrame folder="models">
      {isLoading ? <SkeletonList /> : models.length === 0 ? (
        <Empty message="No models yet. Create one with tracebi new-model, in models/." />
      ) : (
        <ul className="dlist chains">
          {[...models].sort((a, b) => (a.label || a.name).localeCompare(b.label || b.name)).map(m => {
            const up = upstreamOf({ model: m.name, pipelines, connectors, inputs })
            return (
              <ChainRow key={m.name} model={m} reports={reports || []} desk={desk}
                        pipeline={pipelineFor(pipelines || [], m.name)} written={writtenFor(warehouses, m.name)}
                        up={up} form={up.transform && formOf(up.transform)}
                        group={up.transform && groupFor(warehouses, up.transform)} />
            )
          })}
        </ul>
      )}
    </DataFrame>
  )
}
