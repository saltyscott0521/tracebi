import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useGraph, useRunningRuns } from '../api'
import { DataFrame } from './Data'
import { NodePassport, ProjectPassport } from '../components/Passport'
import DependsOn, { DEPENDS_KINDS } from '../components/DependsOn'
import { contractFailure } from '../components/TheLine'
import { count } from '../format'
import { checksWords, refreshWords } from '../words'
import { modelsPath, sourcesPath, transformsPath, warehousePath } from '../nav'
import { Empty, ErrorDetail, Segmented, SkeletonCard } from '../components/Shared'

// Lineage (/data/lineage), and every page's Lineage tab: the map. The workspace as one graph (GET /api/graph,
// tracebi/graph.py, which the gateway serves agents as describe_project), one
// lane per stage, read left to right in the order the data moves:
//
//   ⓪ Sources  →  ① Transforms  →  Warehouse  →  ② Models  →  ③ Reports
//
// A source card holds its tables, a warehouse group (one per transform that
// wrote it) its tables. The wires are the graph's edges, facts the API already
// holds: what a transform's text reads, the certificate's writers, a model's
// tables and a report's bindings; never a guess. A piece wired on one side
// only is a gap: dashed, amber, its reason under its name.
//
// A lens repaints the same map for one question (?lens=): Coverage (the
// default), Flow, Freshness, Trust, What agents see, each with its one-line
// legend above the lanes (and what it says when it has nothing to show).
// Clicking a piece selects it (?node=<id>) and the passport answers the same
// rows for it: on a wide map it floats over the lanes, on the side away from
// the piece, so the lanes keep their width (Escape or × closes it); with nothing
// selected, the passport is the workspace's, under the map. ?lane= focuses one
// lane. Hovering or focusing a piece lights its whole path. When the map
// is narrower than its five lanes fit, they stack and no wire is drawn. A name
// breaks only after _ . / and ends in an ellipsis; hover or focus says it whole.
//
// The graph's edge_facts are the edges DuckDB's parse proved: a SQL
// transform's certificate says which source tables, files and warehouse
// tables each column of its tables comes from. They are not the board's
// wires. On Flow, a selected warehouse table lights the source tables and
// files it takes columns from (through any warehouse table between) and draws
// those wires solid green.
//
// A pipeline run going now moves on it (useRunningRuns; observation only, a
// graph edge is a dependency, never a trigger): the transform pulses while its
// step runs; when the step is done its warehouse group, the group's tables and
// the models that read them light; while the build step runs those models
// pulse and each report lights as the run's log says it was rendered. A failed
// step stops the pulse on the node that failed, which then says why in its
// Trust row. When no run is going nothing moves.
//
// Selecting a warehouse table, a source table or a model (then one of its
// measures, ?measure=<model>:<measure>) adds Depends on this under the
// passport: every report figure downstream of it, from the builds' manifests.

export const LENSES = [
  ['coverage', 'Coverage'], ['flow', 'Flow'], ['freshness', 'Freshness'], ['trust', 'Trust'], ['access', 'What agents see'],
]

// The lanes, and the list each one's count opens (the folder's page).
const LANES = [
  { key: 'sources', n: '⓪', title: 'Sources', list: sourcesPath(), word: 'source' },
  { key: 'transforms', n: '①', title: 'Transforms', list: transformsPath(), word: 'transform' },
  { key: 'warehouse', n: '', title: 'Warehouse', list: warehousePath(), word: 'table' },
  { key: 'models', n: '②', title: 'Models', list: modelsPath(), word: 'model' },
  { key: 'reports', n: '③', title: 'Reports', list: '/', word: 'report' },
]
export const LANE_KEYS = LANES.map(l => l.key)

// What each lens says above the map, in one line.
const LEGEND = {
  coverage: [['ok', 'wired on both sides'], ['warn', 'a gap: read by nobody, run by nothing, or built from nothing']],
  freshness: [['ok', 'moved after everything upstream'], ['warn', 'older than what feeds it'], ['off', 'not moved here yet']],
  trust: [['ok', 'checks passed · reproduces'], ['warn', 'changed since checked · snapshot · drifted'], ['bad', 'checks failed · error'], ['off', 'nothing to check']],
  access: [['ok', 'the gateway can read it'], ['off', 'dark: on no allowlist (a transform is only ever proposed)']],
}

// What a lens says when it has nothing to show, from the graph's own counts.
function emptyOf(lens, graph) {
  const s = graph.summary || {}
  if (lens === 'freshness' && !graph.nodes.some(n => n.passport?.moved?.at)) {
    return 'Nothing has moved yet: run a transform (Refresh data) and every piece it feeds dates from it.'
  }
  if (lens === 'trust' && !s.checks?.of) {
    return 'No sink declares a contract yet: a transform\'s .contract.yaml gives the tables it writes checks to satisfy.'
  }
  if (lens === 'access' && !s.agents?.source_tables && !s.agents?.models && !s.agents?.reports) {
    return 'Agents see nothing yet: tick the tables they may read on a source\'s Tables tab.'
  }
  return null
}

// Where a name may break: after an underscore, a dot or a slash, never inside a word.
function breakable(text) {
  if (typeof text !== 'string') return text
  return text.split(/(?<=[_./])/).flatMap((part, i) => (i ? [<wbr key={i} />, part] : [part]))
}

const JUDGED = new Set(['written', 'built', 'snapshot'])

/** Everything the map draws, from the graph: lanes of cards, their children, and the paths between them. */
function mapOf(graph) {
  const byId = Object.fromEntries(graph.nodes.map(n => [n.id, n]))
  // An input file a connection already stands for (a SQLite file under
  // inputs/) is that connection's card, not a second one.
  const stored = new Map(graph.nodes.filter(n => n.kind === 'source').map(n => [n.passport?.origin, n.id]))
  const standIn = {}
  graph.nodes.forEach(n => { if (n.kind === 'file' && stored.has(n.name)) standIn[n.id] = stored.get(n.name) })
  const kids = {}
  graph.nodes.forEach(n => { if (n.parent && byId[n.parent]) (kids[n.parent] ||= []).push(n) })
  const top = graph.nodes.filter(n => !(n.parent && byId[n.parent]) && !standIn[n.id])
  const lanes = LANES.map((_, i) => top.filter(n => n.lane === i))
  // Files no transform reads are one dashed card in Sources, each a chip.
  const unread = lanes[0].filter(n => n.kind === 'file' && n.gap)
  lanes[0] = lanes[0].filter(n => !(n.kind === 'file' && n.gap))

  const at = id => standIn[id] || id
  const edges = graph.edges.map(([a, z]) => [at(a), at(z)]).filter(([a, z]) => byId[a] && byId[z] && a !== z)
  const up = {}
  const down = {}
  edges.forEach(([a, z]) => { (down[a] ||= []).push(z); (up[z] ||= []).push(a) })
  // A table's path is its group's, a source table's its source's: the walk
  // steps to the parent in both directions.
  const walk = (id, dir) => {
    const seen = new Set([id])
    const queue = [id]
    while (queue.length) {
      const x = queue.shift()
      const next = [...(dir[x] || []), byId[x]?.parent].filter(Boolean)
      next.forEach(y => { if (!seen.has(y)) { seen.add(y); queue.push(y) } })
    }
    return seen
  }
  const pathOf = id => { const s = walk(id, up); walk(id, down).forEach(x => s.add(x)); return s }

  // What a warehouse table takes columns from, transitively: the proven
  // edges, followed upstream through the warehouse tables between.
  const proven = (graph.edge_facts || []).map(e => [at(e.from), at(e.to)])
    .filter(([a, z]) => byId[a] && byId[z] && a !== z)
  const takes = {}
  proven.forEach(([a, z]) => { (takes[z] ||= []).push(a) })
  const takesFrom = id => {
    const seen = new Set()
    const queue = [id]
    while (queue.length) {
      (takes[queue.shift()] || []).forEach(y => { if (!seen.has(y) && y !== id) { seen.add(y); queue.push(y) } })
    }
    return seen
  }

  // Freshness: a piece that is made (written, built, read) is older than what
  // feeds it when anything upstream moved after it. A definition is not judged.
  const time = n => (n?.passport?.moved?.at ? Date.parse(n.passport.moved.at) : NaN)
  const fresh = {}
  graph.nodes.forEach(n => {
    const m = n.passport?.moved
    if (!m?.at || !JUDGED.has(m.how)) { fresh[n.id] = m?.at ? 'ok' : 'off'; return }
    const mine = time(n)
    const older = [...walk(n.id, up)].some(id => id !== n.id && id !== n.parent && time(byId[id]) > mine)
    fresh[n.id] = older ? 'warn' : 'ok'
  })
  return { byId, kids, lanes, unread, edges, pathOf, fresh, proven, takesFrom }
}

// The dot's tone under a lens.
function toneOf(n, lens, map) {
  if (n.gap) return 'warn'
  if (lens === 'coverage') return 'ok'
  if (lens === 'freshness') return map.fresh[n.id]
  if (lens === 'trust') return { ok: 'ok', warn: 'warn', bad: 'bad' }[n.passport?.trust?.state] || 'off'
  if (lens === 'access') return n.passport?.agents?.state === 'ok' ? 'ok' : 'off'
  return 'off'
}
const dark = (n, lens) => lens === 'access' && n.passport?.agents?.state !== 'ok'

/**
 * What the runs going now (and each pipeline's last run when it failed) say
 * of each piece: `{state, trust}`, *state* an id → running · moved · failed,
 * *trust* an id → the Trust row a failed step gives that piece. A failed run
 * moves nothing: only the piece whose step failed is marked.
 */
function runStates(runs, map) {
  const state = {}
  const trust = {}
  for (const r of runs || []) {
    const tid = `transform:${r.transform}`
    const t = map.byId[tid]
    if (!t) continue
    const step = r.steps.find(s => s.name === 'transform') || r.steps[0]
    const rest = r.steps.filter(s => s !== step)
    const groups = (t.passport?.readers || []).filter(id => map.byId[id])
    const tables = groups.flatMap(g => (map.kids[g] || []).map(k => k.id))
    const models = [...new Set(groups.flatMap(g => map.byId[g].passport?.readers || []))].filter(id => map.byId[id])
    const failure = contractFailure(r.error?.message)
    const said = failure ? checksWords({ failed: failure.failed }).text
      : refreshWords({ failedAt: r.finished_at || r.started_at }).text
    if (step?.state === 'failed') {
      state[tid] = 'failed'
      trust[tid] = { state: 'bad', text: said }
      continue
    }
    if (rest.some(s => s.state === 'failed')) {
      models.forEach(id => { state[id] = 'failed'; trust[id] = { state: 'bad', text: said } })
      continue
    }
    if (r.status !== 'running') continue
    if (step && step.state !== 'done') { state[tid] = 'running'; continue }
    ;[tid, ...groups, ...tables].forEach(id => { state[id] = 'moved' })
    const building = rest.some(s => s.state === 'running')
    models.forEach(id => { state[id] = building ? 'running' : 'moved' })
    r.reports.forEach(name => { if (map.byId[`report:${name}`]) state[`report:${name}`] = 'moved' })
  }
  return { state, trust }
}
const runClass = (id, run) => run?.state[id] && `is-run-${run.state[id]}`
// Under Trust, a piece whose step failed is dotted as its Trust row says.
const runTone = (n, lens, map, run) => (lens === 'trust' && run?.trust[n.id] ? 'bad' : toneOf(n, lens, map))

// ── The cards ────────────────────────────────────────────────────────────────

function Chips({ list, lens, map, sel, from, run, refOf, select, light, label }) {
  return (
    <ul className="mcard__kids" aria-label={label}>
      {list.map(k => (
        <li key={k.id}>
          <button type="button" ref={refOf(k.id)} data-node={k.id} data-tone={runTone(k, lens, map, run)}
                  className={['mchip', k.gap && 'mchip--gap', sel === k.id && 'is-sel', from?.has(k.id) && 'is-from', dark(k, lens) && 'is-dark', runClass(k.id, run)].filter(Boolean).join(' ')}
                  data-run={run?.state[k.id]}
                  aria-pressed={sel === k.id} title={[k.label, k.gap ? k.gap.reason : k.sub].filter(Boolean).join(' · ')}
                  onClick={() => select(k.id)} onMouseEnter={() => light(k.id)} onMouseLeave={() => light('')}>
            <i className="mdot" aria-hidden="true" />{k.chip === 'view' && <span className="mchip__view">view</span>}<span className="mchip__nm">{k.label}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function Card({ n, kids, state, refOf, select, light }) {
  const { lens, map, sel, lit, from, run } = state
  const cls = ['mcard', n.gap && 'mcard--gap', sel === n.id && 'is-sel', lit && (lit.has(n.id) ? 'is-lit' : 'is-dim'), from?.has(n.id) && 'is-from', dark(n, lens) && 'is-dark', runClass(n.id, run)]
  return (
    <li>
      <div ref={refOf(n.id)} className={cls.filter(Boolean).join(' ')} data-node={n.id} data-tone={runTone(n, lens, map, run)}
           data-run={run?.state[n.id]}
           onMouseEnter={() => light(n.id)} onMouseLeave={() => light('')}
           onFocus={() => light(n.id)} onBlur={() => light('')}>
        <button type="button" className="mcard__main" aria-pressed={sel === n.id} onClick={() => select(n.id)} title={n.label}>
          <span className="mcard__t">
            <i className="mdot" aria-hidden="true" />
            <span className="mcard__nm">{breakable(n.label)}</span>
          </span>
          <span className="mcard__s">
            {n.chip && !n.gap && <span className="mcard__chip">{n.chip}</span>}{breakable(n.gap ? n.gap.reason : n.sub)}
          </span>
        </button>
        {kids?.length > 0 && (
          <Chips list={kids} lens={lens} map={map} sel={sel} from={from} run={run} refOf={refOf} select={select} light={light}
                 label={`Tables of ${n.label}`} />
        )}
      </div>
    </li>
  )
}

// The files no transform reads: one dashed card, a chip each.
function Unread({ files, state, refOf, select, light }) {
  if (!files.length) return null
  const { lens, map, sel, from } = state
  return (
    <li>
      <div className={`mcard mcard--gap${lens === 'access' ? ' is-dark' : ''}`} data-node="files:unread" data-tone="warn">
        <p className="mcard__main mcard__main--static">
          <span className="mcard__t"><i className="mdot" aria-hidden="true" /><span className="mcard__nm">{count(files.length, 'file')}</span></span>
          <span className="mcard__s">{files[0].gap.reason}</span>
        </p>
        <Chips list={files} lens={lens} map={map} sel={sel} from={from} refOf={refOf} select={select} light={light} label="Files no transform reads" />
      </div>
    </li>
  )
}

// ── The map ──────────────────────────────────────────────────────────────────

function Board({ graph, map, lens, sel, lane, run, select, light, hover }) {
  const boardRef = useRef(null)
  const svgRef = useRef(null)
  const nodes = useRef({})
  const [paths, setPaths] = useState([])

  // The lit path: the piece under the pointer, else (on Flow) the selected one.
  const focus = hover || (lens === 'flow' ? sel : '')
  // On Flow, a selected warehouse table: what it takes columns from.
  const from = useMemo(() => (lens === 'flow' && map.byId[sel]?.kind === 'table' ? map.takesFrom(sel) : null),
    [map, lens, sel])
  const lit = useMemo(() => {
    if (!focus || !map.byId[focus]) return null
    const path = map.pathOf(focus)
    if (from && focus === sel) from.forEach(id => path.add(id))
    return path
  }, [map, focus, from, sel])
  const state = { lens, map, sel, lit, from, run }

  const refOf = useCallback(id => el => { if (el) nodes.current[id] = el; else delete nodes.current[id] }, [])

  // Wires, from where each card or chip is now: the right edge of one's card
  // to the left edge of the next's, at the chip's height, as a gentle S across
  // the gutter between the lanes, so no wire runs under a card. None when the
  // lanes stack (the svg is hidden), and none inside a lane.
  const draw = useCallback(() => {
    const host = boardRef.current
    const svg = svgRef.current
    if (!host || !svg) return
    if (getComputedStyle(svg).display === 'none') { setPaths(p => (p.length ? [] : p)); return }
    const b = host.getBoundingClientRect()
    const el = id => nodes.current[id] || nodes.current[map.byId[id]?.parent]
    const card = e => (e.closest('.mcard') || e).getBoundingClientRect()
    const next = []
    for (const [a, z] of map.edges) {
      const A = el(a)
      const Z = el(z)
      if (!A || !Z || map.byId[a].lane >= map.byId[z].lane) continue
      const ra = A.getBoundingClientRect()
      const rz = Z.getBoundingClientRect()
      const x1 = card(A).right - b.left
      const y1 = ra.top + ra.height / 2 - b.top
      const x2 = card(Z).left - b.left
      const y2 = rz.top + rz.height / 2 - b.top
      const dx = Math.max(24, (x2 - x1) / 2)
      next.push({ key: `${a}>${z}`, a, z, d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}` })
    }
    // The proven edges into the selected table, and into the tables it takes from.
    for (const [a, z] of from ? map.proven : []) {
      if (!from.has(a) || !(z === sel || from.has(z))) continue
      const A = el(a)
      const Z = el(z)
      if (!A || !Z || map.byId[a].lane >= map.byId[z].lane) continue
      const ra = A.getBoundingClientRect()
      const rz = Z.getBoundingClientRect()
      const x1 = card(A).right - b.left
      const y1 = ra.top + ra.height / 2 - b.top
      const x2 = card(Z).left - b.left
      const y2 = rz.top + rz.height / 2 - b.top
      const dx = Math.max(24, (x2 - x1) / 2)
      next.push({ key: `proven:${a}>${z}`, a, z, proven: true, d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}` })
    }
    setPaths(prev => (prev.map(p => p.key + p.d).join() === next.map(p => p.key + p.d).join() ? prev : next))
  }, [map, from, sel])

  useLayoutEffect(() => { draw() }, [draw])
  useEffect(() => {
    const host = boardRef.current
    if (!host) return undefined
    const ro = new ResizeObserver(() => draw())
    ro.observe(host)
    host.querySelectorAll('.map-lane__cards').forEach(el => ro.observe(el))
    window.addEventListener('resize', draw)
    document.fonts?.ready.then(draw)
    return () => { ro.disconnect(); window.removeEventListener('resize', draw) }
  }, [draw])

  const wireClass = p => {
    if (p.proven) return 'is-proven'
    const a = map.byId[p.a]
    const z = map.byId[p.z]
    if (lit) return lit.has(p.a) && lit.has(p.z) ? 'is-lit' : 'is-dim'
    if (lens === 'access' && (dark(a, lens) || dark(z, lens))) return 'is-dim'
    if (lane && (LANE_KEYS[a.lane] !== lane && LANE_KEYS[z.lane] !== lane)) return 'is-dim'
    return undefined
  }

  return (
    <div className="map-board" ref={boardRef}>
      <svg className="map-wires" ref={svgRef} aria-hidden="true">
        {paths.map(p => <path key={p.key} d={p.d} className={wireClass(p)} />)}
      </svg>
      {LANES.map((l, i) => {
        const cards = map.lanes[i]
        const total = graph.summary?.[l.key === 'warehouse' ? 'tables' : l.key] ?? cards.length
        return (
          <section key={l.key} className={`map-lane map-lane--${l.key}${lane && lane !== l.key ? ' is-away' : ''}${lane === l.key ? ' is-focus' : ''}`}
                   aria-labelledby={`lane-${l.key}`} data-lane={l.key}>
            <h2 id={`lane-${l.key}`} className="map-lane__head">
              <span className="map-lane__stage">{l.n && <span aria-hidden="true">{l.n} </span>}{l.title}</span>
              <Link to={l.list} className="map-lane__n" title={`Every ${l.word}, as a list`} aria-label={`All ${count(total, l.word)}`}>{total}</Link>
            </h2>
            <ul className="map-lane__cards">
              {cards.map(n => (
                <Card key={n.id} n={n} kids={map.kids[n.id]} state={state} refOf={refOf} select={select} light={light} />
              ))}
              {i === 0 && <Unread files={map.unread} state={state} refOf={refOf} select={select} light={light} />}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

// The summary at the right of the lens bar: the counts, then the lens's own clause.
function Summary({ summary, lens, stale }) {
  const s = summary || {}
  const clause = {
    coverage: <> · <span className="map-sum__warn">{count(s.gaps || 0, 'gap')}</span></>,
    freshness: stale ? <> · <span className="map-sum__warn">{stale} older than what feeds {stale === 1 ? 'it' : 'them'}</span></> : <> · nothing older than what feeds it</>,
    trust: s.checks ? <> · <b>{s.checks.satisfied} of {s.checks.of}</b> sinks satisfied their contracts</> : null,
    access: s.agents ? <> · agents see <b>{count(s.agents.source_tables, 'source table')}</b>, {count(s.agents.models, 'model')}, {count(s.agents.reports, 'published report')}</> : null,
  }[lens]
  return (
    <p className="map-sum" aria-live="polite">
      <b>{s.sources}</b> sources · <b>{s.transforms}</b> transforms · <b>{s.tables}</b> tables · <b>{s.models}</b> models · <b>{s.reports}</b> reports{clause}
    </p>
  )
}

// The lens's one line above the lanes: its dots, or (Flow) what is lit and how
// to light it, or what it says when it has nothing to show.
function Legend({ lens, graph, map, sel, hover }) {
  const empty = emptyOf(lens, graph)
  if (empty) return <p className="map-legend map-legend--empty" data-legend={lens}>{empty}</p>
  if (lens === 'flow') {
    const focus = map.byId[hover || sel]
    const proven = focus?.kind === 'table' && focus.id === sel && map.takesFrom(sel).size > 0
    return (
      <p className="map-legend" data-legend="flow" aria-live="polite">
        {focus
          ? <><span>Lit: everything that feeds <b>{focus.label}</b> and everything it feeds.</span>{proven && <span className="map-legend__item" data-tone="ok"><i className="mdot" aria-hidden="true" />green: the sources its columns come from, as the parser read them</span>}</>
          : <span>Flow shows what feeds what. Hover, focus or select a piece to light its whole path; a table a SQL transform wrote also lights its sources in green.</span>}
      </p>
    )
  }
  return (
    <p className="map-legend" data-legend={lens}>
      {LEGEND[lens].map(([tone, text]) => (
        <span key={tone} className="map-legend__item" data-tone={tone}><i className="mdot" aria-hidden="true" />{text}</span>
      ))}
    </p>
  )
}

// The map's own lenses inside a page's Lineage tab: the questions a single
// piece is asked about (what feeds it, what its checks say, what agents see).
const TAB_LENSES = LENSES.filter(([k]) => ['flow', 'trust', 'access'].includes(k))

/**
 * The map. On /data/lineage its lens, selection and lane are the address's;
 * *focus* (a node id) embeds it in a page's Lineage tab instead, that node
 * selected under Flow, the lens and selection its own, and no passport beside
 * it: the page around it is that node's.
 */
export function TheMap({ graph, focus }) {
  const embedded = !!focus
  const [params, setParams] = useSearchParams()
  const map = useMemo(() => mapOf(graph), [graph])
  const { data: runs } = useRunningRuns()
  const run = useMemo(() => runStates(runs, map), [runs, map])
  const [local, setLocal] = useState({ lens: 'flow', node: focus || '', measure: '' })
  const asked = embedded ? local
    : { lens: params.get('lens'), node: params.get('node'), lane: params.get('lane'), measure: params.get('measure') }
  const lenses = embedded ? TAB_LENSES : LENSES
  const lens = lenses.some(([k]) => k === asked.lens) ? asked.lens : embedded ? 'flow' : 'coverage'
  // A measure (<model>:<measure>) selects its model; Depends on this answers for the measure.
  const [ofModel, measureName] = (asked.measure || '').split(/:(.*)/s)
  const byMeasure = measureName && map.byId[`model:${ofModel}`] ? `model:${ofModel}` : ''
  const sel = map.byId[asked.node] ? asked.node : byMeasure
  const measure = byMeasure && sel === byMeasure ? measureName : ''
  const lane = LANE_KEYS.includes(asked.lane) ? asked.lane : ''
  const [hover, setHover] = useState('')
  const passRef = useRef(null)

  const go = useCallback(patch => {
    if (embedded) { setLocal(s => ({ ...s, ...patch })); return }
    setParams(p => {
      const next = new URLSearchParams(p)
      Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)))
      return next
    })
  }, [setParams, embedded])

  // Selecting a piece shows its rows. Where they sit under the map (a narrow
  // column), they are brought into view, or the click seems to do nothing; a
  // link in them brings the piece it names into view instead.
  const select = useCallback(id => {
    go({ node: id === sel ? '' : id, lane: '', measure: '' })
    const pass = passRef.current
    if (id !== sel && pass && pass.getBoundingClientRect().top > window.innerHeight) pass.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [go, sel])
  // Escape closes the passport (the selection), as its × does.
  useEffect(() => {
    if (embedded || !sel) return undefined
    const esc = e => { if (e.key === 'Escape' && !e.defaultPrevented) go({ node: '', measure: '' }) }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [embedded, sel, go])
  const goTo = useCallback(id => {
    go({ node: id, lane: '', measure: '' })
    requestAnimationFrame(() => document.querySelector(`[data-node="${CSS.escape(id)}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
  }, [go])

  const stale = Object.entries(map.fresh).filter(([id, t]) => t === 'warn' && !map.byId[id]?.gap).length
  const node = sel && map.byId[sel]
  // A step that failed says so in its piece's Trust row.
  const shown = node && run.trust[node.id] ? { ...node, passport: { ...node.passport, trust: run.trust[node.id] } } : node
  // On a page's Lineage tab, the panel answers for the selection, else the page's own piece.
  const about = node || (embedded ? map.byId[focus] : null)
  // Picking a measure of that model, or none (back to the model).
  const pickMeasure = useCallback(name => {
    go(name ? { node: '', lane: '', measure: `${about.name}:${name}` } : { node: about.id, measure: '' })
  }, [go, about])
  return (
    <>
      <div className="map-bar">
        <Segmented options={lenses} value={lens} onChange={v => go({ lens: !embedded && v === 'coverage' ? '' : v })} label="Lens" className="map-lenses" />
        <Summary summary={graph.summary} lens={lens} stale={stale} />
      </div>
      <div className="map-frame"><div className={`map-wrap${embedded ? ' map-wrap--tab' : ''}`}>
        <div className="map">
          <Legend lens={lens} graph={graph} map={map} sel={sel} hover={hover} />
          <Board graph={graph} map={map} lens={lens} sel={sel} lane={lane} run={run} select={select} light={setHover} hover={hover} />
        </div>
        {embedded ? (
          <>
            {node && node.id !== focus && node.open && (
              <p className="map-picked">
                <span>{node.label}</span> <Link to={node.open}>Open its page</Link>
              </p>
            )}
            {about && DEPENDS_KINDS.has(about.kind) && (
              <div className="pass pass--deps"><DependsOn node={about} measure={measure} onMeasure={pickMeasure} /></div>
            )}
          </>
        ) : (
          <aside className={['pass', node && 'pass--float', node && node.lane >= 3 && 'pass--left'].filter(Boolean).join(' ')}
                 aria-label="Passport" ref={passRef}>
            {node && <button type="button" className="dbx-close pass__close" onClick={() => go({ node: '', measure: '' })} aria-label="Close the passport">×</button>}
            {shown
              ? <NodePassport n={shown} byId={map.byId} onGo={goTo}
                              from={node.kind === 'table' ? [...map.takesFrom(node.id)].filter(id => map.byId[id].lane === 0) : null} />
              : <ProjectPassport summary={graph.summary || {}} focus={l => go({ lane: l, node: '' })} coverage={() => go({ lens: '', lane: '', node: '' })} />}
            {node && <DependsOn node={node} measure={measure} onMeasure={pickMeasure} />}
          </aside>
        )}
      </div></div>
    </>
  )
}

/** A page's Lineage tab: the map focused on *node* (a graph id). */
export function LineageTab({ node }) {
  const { data: graph, error, isLoading } = useGraph()
  if (error) return <ErrorDetail error={error} />
  if (isLoading || !graph) return <SkeletonCard />
  return <TheMap graph={graph} focus={node} />
}

/** Lineage (/data/lineage): the map, the workspace as one graph. */
export default function DataMap() {
  const { data: graph, error, isLoading } = useGraph()
  return (
    <DataFrame folder="lineage">
      {error ? <ErrorDetail error={error} />
        : isLoading || !graph ? <SkeletonCard />
        : !graph.nodes.length
          ? <Empty message="Nothing to draw yet. Put files under inputs/, write a transform with tracebi new-transform, and a model over the warehouse with tracebi new-model." />
          : <TheMap graph={graph} />}
    </DataFrame>
  )
}
