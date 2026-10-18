import { Fragment, useMemo } from 'react'
import { Link } from 'react-router-dom'

import {
  usePipelines, usePipelineRuns, useLayerHistory, useModel, useConnectors,
  useConnectorWarehouse, useReports, useDesk,
} from '../api'
import { buildModelGraph } from './modelGraph'
import { verdictOf } from '../verdict'
import { dataPath, pipelineBelongsToModel, reportBelongsToModel } from '../nav'

// The line: how a model is made, as three stations and the two hand-offs
// between them. ① transforms/ writes tables into the warehouse; ② the model
// names the numbers over those tables; ③ reports show them. Each fact on it is
// read from what exists (the pipeline's runs, the warehouse's sink contract,
// the desk's re-checks); what is not known is left off rather than guessed.
// Colour and a glyph mark only an exception: "✕" failed, "△" changed or does
// not match, "○" never built or not declared. A fine thing is a plain fact.

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`
const pad = n => String(n).padStart(2, '0')

/** "Oct 8 · 23:19" */
export function stamp(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  return `${d.toLocaleString('en-US', { month: 'short', day: 'numeric' })} · ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** "2 min ago", "3 h ago", else the stamp. */
export function since(iso) {
  const ms = Date.now() - Date.parse(iso)
  if (!(ms >= 0)) return stamp(iso)
  const min = Math.round(ms / 60000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min} min ago`
  if (min < 24 * 60) return `${Math.round(min / 60)} h ago`
  return stamp(iso)
}

/**
 * A name that may break after its underscores (and dots) when the screen is
 * narrow, so a long one wraps between its words, not inside one. The text
 * itself is unchanged.
 */
export function Breakable({ name }) {
  return ((name || '').match(/[^_.]+[_.]?|[_.]/g) || []).map((part, i) => (
    <Fragment key={i}>{i > 0 && <wbr />}{part}</Fragment>
  ))
}

/**
 * What a failed transform said when its sink contract failed: how many checks
 * failed, and each as the contract wrote it ("rows(fact, {...})", observed 4).
 * The sink raises after the tables are written and records no certificate.
 * Null for any other failure.
 */
export function contractFailure(message) {
  const m = /did not satisfy contract '[^']*' — (\d+) of (\d+) check\(s\) failed/.exec(message || '')
  if (!m) return null
  const checks = (message.match(/^\s*✗ .+$/gm) || []).map(line => {
    const [check, observed] = line.replace(/^\s*✗\s*/, '').split(' — observed ')
    return { check, observed }
  })
  return { failed: Number(m[1]), total: Number(m[2]), checks }
}

const GLYPH = { bad: '✕', warn: '△', none: '○' }
const mark = (kind, text) => ({ kind, glyph: GLYPH[kind], text })

// ── The facts ────────────────────────────────────────────────────────────────

/**
 * Everything the Overview says about *model*, from the queries the other pages
 * already use (they share the cache), as the line and the header read it.
 */
export function useLineFacts(model) {
  const { data: pipelines } = usePipelines()
  const { data: detail } = useModel(model)
  const { data: connectors } = useConnectors()
  const { data: reports } = useReports()
  const { data: desk } = useDesk()

  const mine = (pipelines || []).filter(p => pipelineBelongsToModel(p, model))
  const pipeline = mine.find(p => p.model === model) || mine[0]
  const layers = pipeline?.layers || []
  // The transform is a model pipeline's own step; any other pipeline has no
  // such step, so its first stands in for it.
  const step = layers.find(l => l.name === 'transform') || layers[0]
  const { data: runs } = usePipelineRuns(pipeline?.pipeline)
  const { data: history } = useLayerHistory(pipeline?.pipeline, step?.name)

  // The file the model's tables are read from, when it is a warehouse file.
  const modelConnectors = (connectors || []).filter(c => (c.used_by || []).includes(model))
  const file = modelConnectors.find(c => c.type === 'DuckDBConnector' && c.storage?.kind === 'file')
  const source = file || modelConnectors[0]
  const { data: warehouse } = useConnectorWarehouse(file?.name)

  // ① Transform
  const finished = (history?.runs || []).filter(r => r.status === 'success' || r.status === 'failed')
  const last = finished[0]
  const good = finished.find(r => r.status === 'success')
  const at = r => r && (r.completed_at || r.started_at)
  const running = (runs || []).some(r => r.status === 'running')
  const failed = !running && last?.status === 'failed'
  const failure = failed ? contractFailure(last.error_message) : null
  const transform = {
    pipeline,
    name: pipeline ? (pipeline.transform || pipeline.pipeline) : null,
    running, failed, failure,
    // not known until the step's history has come back (a pipeline with no step has none to wait for)
    known: history !== undefined || !step,
    message: failed ? last.error_message : null,
    lastAt: at(last), goodAt: at(good), actor: last?.actor,
  }

  // ② Model
  const graph = useMemo(() => (detail ? buildModelGraph(detail) : null), [detail])

  // ③ Reports: the model's, and what the desk found when it re-checked each last build
  const listed = (reports || []).filter(r => reportBelongsToModel(r, model))
  const builds = new Map((desk?.builds || []).map(b => [b.report, b]))
  const built = listed.filter(r => builds.has(r.name))
  const looks = built.map(r => verdictOf({ report: r, build: builds.get(r.name) }).state)
    .filter(state => state === 'needs-a-look' || state === 'does-not-reproduce')

  // The tables of the model's warehouse, with the sink contract's word on each
  const read = new Set((detail?.tables || []).filter(t => t.connector === source?.name).map(t => t.source))
  const tables = (warehouse?.tables || []).filter(t => !read.size || read.has(t.name))

  const line = {
    transform: transformStation(pipelines, transform),
    model: modelStation(model, detail, graph),
    reports: reportsStation(reports, listed, desk, built, looks),
  }
  const pill1 = warehousePill(source, file, detail, warehouse, tables, transform)
  const pill2 = detail ? { name: plural(detail.measures?.length || 0, 'measure'), sans: true } : null
  line.hands = [
    { pill: pill1, tone: pill1?.kind === 'bad' || pill1?.kind === 'warn' ? 'warn' : '' },
    { pill: pill2, tone: looks.length ? 'warn' : '' },
  ]

  const lastCheck = tables.map(t => t.contract?.checked_at).filter(Boolean).sort().pop()
  return {
    line, transform, source: file, read, tables, lastCheck, builtCount: built.length,
    description: pipeline?.description,
  }
}

function transformStation(pipelines, t) {
  const s = { name: t.name, flags: [] }
  if (!t.pipeline) {
    if (pipelines) s.flags.push(mark('none', 'No pipeline'))
    return s
  }
  if (t.running) s.fact = 'Running now'
  else if (t.failed) {
    if (t.goodAt) s.fact = `Last good run ${stamp(t.goodAt)}`
    s.flags.push(mark('bad', `Failed ${since(t.lastAt)}`))
  } else if (t.lastAt) s.fact = `Ran ${stamp(t.lastAt)}`
  else if (t.known) s.flags.push(mark('none', 'Never run'))
  return s
}

function modelStation(model, detail, graph) {
  const s = { name: model, flags: [] }
  if (detail) s.fact = `${plural(detail.tables.length, 'table')} · ${plural(graph.edges.length, 'join')}`
  return s
}

function reportsStation(reports, listed, desk, built, looks) {
  const s = { name: reports ? plural(listed.length, 'report') : null, sans: true, flags: [] }
  if (!desk || !listed.length) return s
  const scheduled = listed.filter(r => r.schedule).length
  s.fact = [built.length && `${built.length} built`, scheduled && `${scheduled} scheduled`].filter(Boolean).join(' · ')
  const never = listed.length - built.length
  if (never) s.flags.push(mark('none', `${never} never built`))
  // The chip's words, on a count.
  const broken = looks.filter(state => state === 'does-not-reproduce').length
  const look = looks.length - broken
  if (broken) s.flags.push(mark('bad', `${broken} ${broken === 1 ? 'does' : 'do'} not reproduce`))
  if (look) s.flags.push(mark('warn', `${look} ${look === 1 ? 'needs' : 'need'} a look`))
  return s
}

// The first hand-off: the warehouse file, and what the sink contract says of
// the tables in it. A failed check is the loudest word, then a table that no
// longer matches its last check, then tables with no checks; all fine says
// only how many tables.
function warehousePill(source, file, detail, warehouse, tables, transform) {
  if (!source) return null
  const where = file?.storage?.where
  const pill = { name: where ? where.split('/').pop() : source.name, mono: true }
  if (warehouse && warehouse.exists === false) return { ...pill, ...mark('none', 'not built yet') }
  if (transform.failure) return { ...pill, ...mark('bad', `${plural(transform.failure.failed, 'check')} failed`) }
  if (tables.some(t => t.contract?.status === 'stale')) {
    return { ...pill, ...mark('warn', "doesn't match its last check") }
  }
  const unchecked = tables.filter(t => (t.contract?.status || 'no_contract') === 'no_contract').length
  if (tables.length && unchecked) {
    return { ...pill, ...mark('none', unchecked === tables.length ? 'no checks declared' : `${plural(unchecked, 'table')} without checks`) }
  }
  const n = detail ? detail.tables.filter(t => t.connector === source.name).length : 0
  return n ? { ...pill, sub: plural(n, 'table') } : pill
}

// ── The line ─────────────────────────────────────────────────────────────────

const STATIONS = [
  { key: 'transform', n: 1, title: 'Transform', role: 'writes the tables' },
  { key: 'model',     n: 2, title: 'Model',     role: 'names the numbers' },
  { key: 'reports',   n: 3, title: 'Reports',   role: 'show them' },
]

// A hand-off's track runs, and shows it, beside the stage you are looking at.
const HOT = [['transform', 'model'], ['model', 'reports']]

export function Flag({ flag }) {
  return (
    <span className={`flag flag--${flag.kind}`}>
      <span aria-hidden="true">{flag.glyph}</span> {flag.text}
    </span>
  )
}

function Station({ model, stage, s, info }) {
  const current = stage === s.key
  return (
    <li>
      <Link to={dataPath(model, s.key)} className="station" aria-current={current ? 'page' : undefined}>
        <span className="station__head">
          <span className="station__n" aria-hidden="true">{s.n}</span>
          <span className="station__title">{s.title}</span>
          <span className="station__role">{s.role}</span>
        </span>
        {info.name && (
          <span className={`station__name${info.sans ? ' station__name--sans' : ''}`} title={info.name}>
            <Breakable name={info.name} />
          </span>
        )}
        {info.fact && <span className="station__fact">{info.fact}</span>}
        {info.flags.map(f => <Flag key={f.text} flag={f} />)}
        <span className="station__notch" aria-hidden="true" />
      </Link>
    </li>
  )
}

function Hand({ stage, i, hand }) {
  const hot = HOT[i].includes(stage)
  const { pill } = hand
  return (
    <li className={`hand${hand.tone ? ` hand--${hand.tone}` : ''}${hot ? ' hand--hot' : ''}`}>
      <span className="hand__seg" aria-hidden="true" />
      {pill && (
        <span className="hand__pill">
          <span className="sr-only">Hand-off: </span>
          <span className={`hand__name${pill.mono ? ' hand__name--mono' : ''}`}><Breakable name={pill.name} /></span>
          {(pill.sub || pill.kind) && (
            <span className={`hand__sub${pill.kind ? ` flag--${pill.kind}` : ''}`}>
              {pill.kind && <><span aria-hidden="true">{pill.glyph}</span> </>}{pill.sub || pill.text}
            </span>
          )}
        </span>
      )}
      <span className="hand__seg" aria-hidden="true" />
      <span className="hand__head" aria-hidden="true" />
    </li>
  )
}

/** The three stations as links (the one you are on is the current page), and the hand-offs between them. */
export default function TheLine({ model, stage, line }) {
  return (
    <nav aria-label={`How ${model} is made`}>
      <ol className="line">
        {STATIONS.map((s, i) => (
          <Fragment key={s.key}>
            <Station model={model} stage={stage} s={s} info={line[s.key]} />
            {i < 2 && <Hand stage={stage} i={i} hand={line.hands[i]} />}
          </Fragment>
        ))}
      </ol>
    </nav>
  )
}
