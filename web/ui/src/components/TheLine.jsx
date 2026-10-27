import {
  usePipelines, usePipelineRuns, useLayerHistory, useModel, useConnectors,
  useConnectorWarehouse, useReports, useDesk, useInputs,
} from '../api'
import { verdictOf } from '../verdict'
import { count } from '../format'
import { upstreamOf } from '../chain'
import { checksWords, refreshWords } from '../words'
import { pipelineBelongsToModel, reportBelongsToModel } from '../nav'

// The line: how a model is made, as four stations and the hand-offs between
// them. ⓪ the sources the transform reads (connections and input files);
// ① transforms/ writes tables into the warehouse; ② the model names the
// numbers over those tables; ③ reports show them. Each fact on it is
// read from what exists (the pipeline's runs, the warehouse's checks, the
// desk's re-checks); what is not known is left off rather than guessed.
// Colour and a glyph mark only an exception: "✕" failed, "△" changed or does
// not match, "○" never built or not declared. A fine thing is a plain fact.
// Reports say what they say everywhere else: the verdict chip, as counts.
//
// The model page drew it as a strip; the console's pages read its facts
// (useLineFacts: the refresh, its failure, the builds) and the map draws the line.

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
  const { data: inputs } = useInputs()

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

  // ③ Reports: the model's, and what the desk found when it re-checked each last build
  const listed = (reports || []).filter(r => reportBelongsToModel(r, model))
  const builds = new Map((desk?.builds || []).map(b => [b.report, b]))
  const built = listed.filter(r => builds.has(r.name))
  const states = desk ? reportStates(listed, desk) : []
  const looks = states.filter(state => state === 'needs-a-look' || state === 'does-not-reproduce')

  // The tables of the model's warehouse, with the sink contract's word on each
  const read = new Set((detail?.tables || []).filter(t => t.connector === source?.name).map(t => t.source))
  const tables = (warehouse?.tables || []).filter(t => !read.size || read.has(t.name))

  // ⓪ Sources: what the transform reads, from the transform's own file
  const upstream = upstreamOf({ model, pipelines, connectors, inputs })

  const lastCheck = tables.map(t => t.contract?.checked_at).filter(Boolean).sort().pop()
  const line = {
    sources: sourcesStation(pipelines && connectors && inputs, upstream),
    transform: transformStation(pipelines, transform, lastCheck),
    model: modelStation(detail),
    reports: reportsStation(reports, listed, desk, built, states),
  }
  const pill1 = warehousePill(source, file, warehouse, tables, transform)
  // What the model hands its reports: its measures (how many is said once, in
  // the Semantic layer's line).
  const pill2 = detail ? { name: 'measures', sans: true } : null
  line.hands = [
    { pill: null, tone: '' },
    { pill: pill1, tone: pill1?.kind === 'bad' || pill1?.kind === 'warn' ? 'warn' : '' },
    { pill: pill2, tone: looks.length ? 'warn' : '' },
  ]

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

// Stage ⓪: the connections (by name) and the input files (by file name) the
// transform reads, as one card. Nothing is guessed: no transform, or one
// that names nothing, says so.
function sourcesStation(known, up) {
  const s = { name: null, sans: true, flags: [] }
  if (!known) return s
  const names = [...up.connections.map(c => c.name), ...up.files.map(f => f.path.split('/').pop())]
  if (!up.transform) return { ...s, flags: [mark('none', 'No transform')] }
  if (!names.length) return { ...s, flags: [mark('none', 'None named')] }
  s.name = names.join(', ')
  s.fact = [
    up.connections.length && count(up.connections.length, 'connection'),
    up.files.length && count(up.files.length, 'file'),
  ].filter(Boolean).join(' · ')
  return s
}

// The refresh, in the words every page uses (words.js refreshWords): the
// pipeline's runs, else the sink certificate's time (*written*), since a run
// outside the app (run_workflow.py, `tracebi run-transform`) records none
// here. A failed refresh is a flag, with the last good one as the fact.
function transformStation(pipelines, t, written) {
  const s = { name: t.name, file: t.pipeline?.transform || null, flags: [] }
  if (!t.pipeline) {
    if (pipelines) s.flags.push(mark('none', refreshWords({ pipeline: false }).text))
    return s
  }
  if (!t.known && !t.running) return s
  const w = refreshWords({
    running: t.running, failedAt: t.failed ? t.lastAt : null, ranAt: t.lastAt, writtenAt: written,
  })
  if (w.kind === 'failed') {
    if (t.goodAt) s.fact = refreshWords({ ranAt: t.goodAt }).text
    s.flags.push(mark('bad', w.text))
  } else if (w.kind === 'never') s.flags.push(mark('none', w.text))
  else s.fact = w.text
  return s
}

// The model's counts are said once, in the Semantic layer's line under it.
function modelStation(detail) {
  return { name: detail?.label || detail?.name, sans: true, flags: [] }
}

function reportsStation(reports, listed, desk, built, states) {
  const s = { name: reports ? count(listed.length, 'report') : null, sans: true, flags: [], states }
  if (!desk || !listed.length) return s
  const scheduled = listed.filter(r => r.schedule).length
  s.fact = [built.length && `${built.length} built`, scheduled && `${scheduled} scheduled`].filter(Boolean).join(' · ')
  return s
}

// The first hand-off: the warehouse file, by its name only (where it is kept
// is said once, in the Semantic layer's "Reads"), and what its checks say of
// the tables in it, in the chip's words (words.js checksWords). A failed check
// is the loudest word, then a table that no longer matches its last check,
// then tables with no checks; all fine says the checks passed.
function warehousePill(source, file, warehouse, tables, transform) {
  if (!source) return null
  const where = file?.storage?.where
  const pill = { name: where ? where.split('/').pop() : source.name, mono: true }
  if (warehouse && warehouse.exists === false) return { ...pill, ...mark('none', 'not built yet') }
  if (transform.failure) return { ...pill, ...mark('bad', checksWords({ failed: transform.failure.failed }).text) }
  if (tables.some(t => t.contract?.status === 'stale')) {
    return { ...pill, ...mark('warn', checksWords({ status: 'stale' }).text) }
  }
  const unchecked = tables.filter(t => (t.contract?.status || 'no_contract') === 'no_contract').length
  if (tables.length && unchecked) {
    const none = checksWords({ status: 'no_contract' }).text
    return { ...pill, ...mark('none', unchecked === tables.length ? none : `${none} on ${count(unchecked, 'table')}`) }
  }
  return tables.length ? { ...pill, sub: checksWords({ status: 'satisfied' }).text } : pill
}
