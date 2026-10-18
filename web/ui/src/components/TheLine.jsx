import { Fragment, useMemo } from 'react'
import { Link } from 'react-router-dom'

import {
  usePipelines, usePipelineRuns, useLayerHistory, useModel, useConnectors,
  useConnectorWarehouse, useReports, useDesk,
} from '../api'
import { buildModelGraph } from './modelGraph'
import { Verdict } from './Shared'
import { verdictOf } from '../verdict'
import { dataPath, libraryPath, pipelineBelongsToModel, reportBelongsToModel } from '../nav'

// The line: how a model is made, as three stations and the two hand-offs
// between them. ① transforms/ writes tables into the warehouse; ② the model
// names the numbers over those tables; ③ reports show them. Each fact on it is
// read from what exists (the pipeline's runs, the warehouse's checks, the
// desk's re-checks); what is not known is left off rather than guessed.
// Colour and a glyph mark only an exception: "✕" failed, "△" changed or does
// not match, "○" never built or not declared. A fine thing is a plain fact.
// Reports say what they say everywhere else: the verdict chip, as counts.
//
// A station and a hand-off are drawn by LineNode, which the Map draws its
// nodes with too: one look for "something you write" (a card) and "what gets
// handed on" (a pill), wherever the project is drawn.

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
 * Everything a model's Data page says about *model*, from the queries the other pages
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
  const states = desk ? reportStates(listed, desk) : []
  const looks = states.filter(state => state === 'needs-a-look' || state === 'does-not-reproduce')

  // The tables of the model's warehouse, with the sink contract's word on each
  const read = new Set((detail?.tables || []).filter(t => t.connector === source?.name).map(t => t.source))
  const tables = (warehouse?.tables || []).filter(t => !read.size || read.has(t.name))

  const line = {
    transform: transformStation(pipelines, transform),
    model: modelStation(detail, graph),
    reports: reportsStation(reports, listed, desk, built, states),
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

/** The verdict on each report's last build (verdict.js), once the desk has answered. */
export function reportStates(reports, desk) {
  const builds = new Map((desk?.builds || []).map(b => [b.report, b]))
  return reports.map(r => verdictOf({ report: r, build: builds.get(r.name) }).state)
}

// Worst first; each count in the chip's own words.
const COUNTED = [
  ['does-not-reproduce', n => `${n} ${n === 1 ? 'does' : 'do'} not reproduce`],
  ['needs-a-look', n => `${n} ${n === 1 ? 'needs' : 'need'} a look`],
  ['never-built', n => `${n} never built`],
  ['not-checked', n => `${n} not checked`],
  ['reproduces', n => `${n} ${n === 1 ? 'reproduces' : 'reproduce'}`],
]

/** Verdict chips counting *states* ("6 reproduce", "1 needs a look"), worst first. */
export function VerdictSummary({ states }) {
  const count = {}
  states.forEach(st => { count[st] = (count[st] || 0) + 1 })
  return COUNTED.filter(([st]) => count[st]).map(([st, words]) => (
    <Verdict key={st} state={st} size="sm">{words(count[st])}</Verdict>
  ))
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
  else if (t.known) s.flags.push(mark('none', 'Not run yet'))
  return s
}

function modelStation(detail, graph) {
  const s = { name: detail?.label || detail?.name, sans: true, flags: [] }
  if (detail) s.fact = `${plural(detail.tables.length, 'table')} · ${plural(graph.edges.length, 'join')}`
  return s
}

function reportsStation(reports, listed, desk, built, states) {
  const s = { name: reports ? plural(listed.length, 'report') : null, sans: true, flags: [], states }
  if (!desk || !listed.length) return s
  const scheduled = listed.filter(r => r.schedule).length
  s.fact = [built.length && `${built.length} built`, scheduled && `${scheduled} scheduled`].filter(Boolean).join(' · ')
  return s
}

// The first hand-off: the warehouse file, and what its checks say of the
// tables in it. A failed check is the loudest word, then a table that no
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
  { key: 'transform', n: 1, title: 'Transform' },
  { key: 'model',     n: 2, title: 'Model' },
  { key: 'reports',   n: 3, title: 'Reports' },
]

export function Flag({ flag }) {
  return (
    <span className={`flag flag--${flag.kind}`}>
      <span aria-hidden="true">{flag.glyph}</span> {flag.text}
    </span>
  )
}

/**
 * One node, on the line and on the Map. A card (`shape="card"`) is something
 * you write: a transform, a model, a report. A pill is what gets handed on: a
 * file, its tables, a measure. It says what kind it is (*kind*, with the
 * phase's number *n*), its *name*, one plain *fact*, and *marks*: a verdict
 * chip or a flag, only when something is not fine. With *to* it is a link
 * (*current* when it is the page you are on), with *onClick* a button,
 * otherwise a labelled group. *tone* `hot` is a lit path; `unused` is quiet.
 * *title* is the name's hover text: the identifier, when the name is a label.
 */
export function LineNode({
  shape = 'card', kind, n, name, sans, fact, marks, note, to, onClick, pressed, current,
  tone, label, className, style, title = name,
}) {
  const cls = ['node', `node--${shape}`, tone && `node--${tone}`, note && 'node--noted', className]
    .filter(Boolean).join(' ')
  const body = (
    <>
      {kind && (
        <span className="node__kind">
          {n && <span className="node__n" aria-hidden="true">{n}</span>}{kind}
        </span>
      )}
      {name && (
        <span className={`node__name${sans ? ' node__name--sans' : ''}`} title={title}><Breakable name={name} /></span>
      )}
      {fact && <span className="node__fact">{fact}</span>}
      {marks?.length > 0 && <span className="node__marks">{marks}</span>}
      {note && <span className="node__note">{note}</span>}
    </>
  )
  if (to) {
    return <Link to={to} className={cls} style={style} aria-label={label} aria-current={current ? 'page' : undefined}>{body}</Link>
  }
  if (onClick) {
    return <button type="button" className={cls} style={style} aria-label={label} aria-pressed={pressed} onClick={onClick}>{body}</button>
  }
  return <div role="group" className={cls} style={style} aria-label={label}>{body}</div>
}

function Station({ model, tab, s, info }) {
  // Transform and Model are tabs of this page; Reports is the library, narrowed to the model.
  const to = s.key === 'reports' ? libraryPath(model) : dataPath(model, s.key === 'model' ? '' : s.key)
  const marks = [
    ...info.flags.map(f => <Flag key={f.text} flag={f} />),
    ...(info.states?.length ? [<VerdictSummary key="v" states={info.states} />] : []),
  ]
  return (
    <li>
      <LineNode to={to} current={tab === s.key} kind={s.title} n={s.n}
                name={info.name} sans={info.sans} fact={info.fact} marks={marks} />
    </li>
  )
}

// A hand-off: what passes from one station to the next, a pill on the track.
function Hand({ hand }) {
  const { pill } = hand
  const marks = pill?.kind ? [<Flag key="f" flag={{ kind: pill.kind, glyph: pill.glyph, text: pill.text }} />] : []
  return (
    <li className={`hand${hand.tone ? ` hand--${hand.tone}` : ''}`}>
      <span className="hand__seg" aria-hidden="true" />
      {pill && (
        <LineNode shape="pill" name={pill.name} sans={!pill.mono} fact={pill.sub} marks={marks}
                  label={`Hand-off: ${[pill.name, pill.sub || pill.text].filter(Boolean).join(', ')}`} />
      )}
      <span className="hand__seg" aria-hidden="true" />
      <span className="hand__head" aria-hidden="true" />
    </li>
  )
}

/**
 * The three stations as links (the tab you are on is the current page; Reports
 * opens the library, narrowed to the model), and the hand-offs between them.
 */
export default function TheLine({ model, tab, line }) {
  return (
    <nav aria-label={`How ${model} is made`}>
      <ol className="line">
        {STATIONS.map((s, i) => (
          <Fragment key={s.key}>
            <Station model={model} tab={tab} s={s} info={line[s.key]} />
            {i < 2 && <Hand hand={line.hands[i]} />}
          </Fragment>
        ))}
      </ol>
    </nav>
  )
}
