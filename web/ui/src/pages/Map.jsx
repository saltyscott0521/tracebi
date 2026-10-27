import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'

import { useConnectors, useGraph } from '../api'
import { DataFrame } from './Data'
import { SetupSheet } from './Connectors'
import { NodePassport, ProjectPassport } from '../components/Passport'
import { count } from '../format'
import { modelPath, modelsPath, sourcesPath, transformsPath, warehousePath } from '../nav'
import { Empty, ErrorDetail, Segmented, SkeletonCard } from '../components/Shared'

// Data's Overview (/data): the map. The project as one graph (GET /api/graph,
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
// default), Flow, Freshness, Trust, What agents see. Clicking a piece selects
// it (?node=<id>) and the passport beside the map answers the same rows for
// it; with nothing selected, the passport is the project's. ?lane= focuses one
// lane (the sidebar's Sources · Transforms · Warehouse · Models open the map
// that way). Hovering or focusing a piece lights its whole path. When the map
// is narrower than its five lanes fit, they stack and no wire is drawn.
//
// The graph's edge_facts are the edges DuckDB's parse proved: a SQL
// transform's certificate says which source tables, files and warehouse
// tables each column of its tables comes from. They are not the board's
// wires. On Flow, a selected warehouse table lights the source tables and
// files it takes columns from (through any warehouse table between) and draws
// those wires solid green.

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

// What each lens says under the map.
const LEGEND = {
  coverage: [['ok', 'wired on both sides'], ['warn', 'a gap: read by nobody, run by nothing, or built from nothing']],
  flow: 'Hover or focus any piece to light its whole path. The selected piece stays lit. Select a warehouse table a SQL transform wrote: green wires are the source tables and files its columns come from, as the parser read them.',
  freshness: [['ok', 'moved after everything upstream'], ['warn', 'older than what feeds it'], ['off', 'not moved here yet']],
  trust: [['ok', 'checks passed · reproduces'], ['warn', 'changed since checked · snapshot · drifted'], ['bad', 'checks failed · error'], ['off', 'not a sink, nothing to check']],
  access: 'Lit: what the gateway can read. Dark: not on any allowlist. Transforms are never read, only proposed.',
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

// ── The cards ────────────────────────────────────────────────────────────────

function Chips({ list, lens, map, sel, from, refOf, select, light, label }) {
  return (
    <ul className="mcard__kids" aria-label={label}>
      {list.map(k => (
        <li key={k.id}>
          <button type="button" ref={refOf(k.id)} data-node={k.id} data-tone={toneOf(k, lens, map)}
                  className={['mchip', k.gap && 'mchip--gap', sel === k.id && 'is-sel', from?.has(k.id) && 'is-from', dark(k, lens) && 'is-dark'].filter(Boolean).join(' ')}
                  aria-pressed={sel === k.id} title={k.gap ? k.gap.reason : k.sub || k.name}
                  onClick={() => select(k.id)} onMouseEnter={() => light(k.id)} onMouseLeave={() => light('')}>
            <i className="mdot" aria-hidden="true" />{k.chip === 'view' && <span className="mchip__view">view</span>}<span className="mchip__nm">{k.label}</span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function Card({ n, kids, state, refOf, select, light }) {
  const { lens, map, sel, lit, from } = state
  const cls = ['mcard', n.gap && 'mcard--gap', sel === n.id && 'is-sel', lit && (lit.has(n.id) ? 'is-lit' : 'is-dim'), from?.has(n.id) && 'is-from', dark(n, lens) && 'is-dark']
  return (
    <li>
      <div ref={refOf(n.id)} className={cls.filter(Boolean).join(' ')} data-node={n.id} data-tone={toneOf(n, lens, map)}
           onMouseEnter={() => light(n.id)} onMouseLeave={() => light('')}
           onFocus={() => light(n.id)} onBlur={() => light('')}>
        <button type="button" className="mcard__main" aria-pressed={sel === n.id} onClick={() => select(n.id)}>
          <span className="mcard__t">
            <i className="mdot" aria-hidden="true" />
            <span className="mcard__nm" title={n.label}>{n.label}</span>
          </span>
          <span className="mcard__s">
            {n.chip && !n.gap && <span className="mcard__chip">{n.chip}</span>}{n.gap ? n.gap.reason : n.sub}
          </span>
        </button>
        {kids?.length > 0 && (
          <Chips list={kids} lens={lens} map={map} sel={sel} from={from} refOf={refOf} select={select} light={light}
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

function Board({ graph, map, lens, sel, lane, select, light, hover }) {
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
  const state = { lens, map, sel, lit, from }

  const refOf = useCallback(id => el => { if (el) nodes.current[id] = el; else delete nodes.current[id] }, [])

  // Wires, from where each card or chip is now: right edge of one to the left
  // edge of the next, as a gentle S. None when the lanes stack (the svg is
  // hidden), and none inside a lane.
  const draw = useCallback(() => {
    const host = boardRef.current
    const svg = svgRef.current
    if (!host || !svg) return
    if (getComputedStyle(svg).display === 'none') { setPaths(p => (p.length ? [] : p)); return }
    const b = host.getBoundingClientRect()
    const el = id => nodes.current[id] || nodes.current[map.byId[id]?.parent]
    const next = []
    for (const [a, z] of map.edges) {
      const A = el(a)
      const Z = el(z)
      if (!A || !Z || map.byId[a].lane >= map.byId[z].lane) continue
      const ra = A.getBoundingClientRect()
      const rz = Z.getBoundingClientRect()
      const x1 = ra.right - b.left
      const y1 = ra.top + ra.height / 2 - b.top
      const x2 = rz.left - b.left
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
      const x1 = ra.right - b.left
      const y1 = ra.top + ra.height / 2 - b.top
      const x2 = rz.left - b.left
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

function Legend({ lens }) {
  const l = LEGEND[lens]
  return (
    <p className="map-legend">
      {typeof l === 'string' ? l : l.map(([tone, text]) => (
        <span key={tone} className="map-legend__item" data-tone={tone}><i className="mdot" aria-hidden="true" />{text}</span>
      ))}
    </p>
  )
}

function TheMap({ graph }) {
  const [params, setParams] = useSearchParams()
  const map = useMemo(() => mapOf(graph), [graph])
  const lens = LENSES.some(([k]) => k === params.get('lens')) ? params.get('lens') : 'coverage'
  const sel = map.byId[params.get('node')] ? params.get('node') : ''
  const lane = LANE_KEYS.includes(params.get('lane')) ? params.get('lane') : ''
  const [hover, setHover] = useState('')
  const [setup, setSetup] = useState(null)
  const { data: connectors } = useConnectors()
  const passRef = useRef(null)

  const go = useCallback(patch => setParams(p => {
    const next = new URLSearchParams(p)
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)))
    return next
  }), [setParams])

  // Selecting a piece shows its passport. Where the passport sits under the
  // map (a narrow column), it is brought into view, or the click seems to do
  // nothing; a link in a passport brings the piece it names into view instead.
  const select = useCallback(id => {
    go({ node: id === sel ? '' : id, lane: '' })
    const pass = passRef.current
    if (id !== sel && pass && pass.getBoundingClientRect().top > window.innerHeight) pass.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [go, sel])
  const goTo = useCallback(id => {
    go({ node: id, lane: '' })
    requestAnimationFrame(() => document.querySelector(`[data-node="${CSS.escape(id)}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
  }, [go])

  const stale = Object.entries(map.fresh).filter(([id, t]) => t === 'warn' && !map.byId[id]?.gap).length
  const node = sel && map.byId[sel]
  return (
    <>
      <div className="map-bar">
        <Segmented options={LENSES} value={lens} onChange={v => go({ lens: v === 'coverage' ? '' : v })} label="Lens" className="map-lenses" />
        <Summary summary={graph.summary} lens={lens} stale={stale} />
      </div>
      <div className="map-frame"><div className="map-wrap">
        <div className="map">
          <Board graph={graph} map={map} lens={lens} sel={sel} lane={lane} select={select} light={setHover} hover={hover} />
          <Legend lens={lens} />
        </div>
        <aside className="pass" aria-label="Passport" ref={passRef}>
          {node
            ? <NodePassport n={node} byId={map.byId} onGo={goTo} onSetup={name => setSetup(name)}
                            from={node.kind === 'table' ? [...map.takesFrom(node.id)].filter(id => map.byId[id].lane === 0) : null} />
            : <ProjectPassport summary={graph.summary || {}} focus={l => go({ lane: l, node: '' })} coverage={() => go({ lens: '', lane: '', node: '' })} />}
        </aside>
      </div></div>
      {setup && (connectors || []).find(c => c.name === setup) && (
        <SetupSheet c={connectors.find(c => c.name === setup)} onClose={() => setSetup(null)} />
      )}
    </>
  )
}

/** Data's Overview (/data): the map. */
export default function DataMap() {
  const [params] = useSearchParams()
  const { data: graph, error, isLoading } = useGraph()

  // Old links: /data?view=map was the Map (a model's map is its own page's
  // line now); /data?m=<model> was a model's page; /data?model=<m> lit that
  // model's path, which is its node selected on Flow now.
  if (params.get('view') === 'map') {
    return <Navigate to={params.get('model') ? modelPath(params.get('model')) : '/data'} replace />
  }
  if (params.get('m')) return <Navigate to={modelPath(params.get('m'))} replace />
  if (params.get('model')) {
    return <Navigate to={`/data?lens=flow&node=${encodeURIComponent(`model:${params.get('model')}`)}`} replace />
  }

  return (
    <DataFrame folder="overview">
      {error ? <ErrorDetail error={error} />
        : isLoading || !graph ? <SkeletonCard />
        : !graph.nodes.length
          ? <Empty message="Nothing to draw yet. Put files under inputs/, write a transform with tracebi new-transform, and a model over the warehouse with tracebi new-model." />
          : <TheMap graph={graph} />}
    </DataFrame>
  )
}
