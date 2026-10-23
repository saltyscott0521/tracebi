import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'

import {
  useConnectorTables, useConnectors, useInputs, useModels, usePipelines, useReports, useTransforms, useWarehouses,
} from '../api'
import { DataFrame } from './Data'
import { FORM_LABEL } from '../chain'
import { fmtBytes, sourceKind } from '../components/Storage'
import { count } from '../format'
import {
  dataPath, pipelineModels, reportModels, reportPagePath, sourcesPath, tablePath, transformsPath, warehousePath,
} from '../nav'
import { Badge, Chip, Empty, ErrorDetail, SkeletonCard } from '../components/Shared'

// Data's Flow tab (/data): the board. One lane per stage, read left to right
// in the order the data moves:
//
//   ⓪ Sources  →  ① Transforms  →  Warehouse  →  ② Models  →  ③ Reports
//
// A lane holds only its own kind of thing (a source is something a transform
// reads; a warehouse table is something a transform wrote), and how a thing is
// built is a chip on its card, never a lane. Every card opens the page that
// already exists for it; the wires between cards are drawn from their live
// positions, from facts the API already gives: a connection's or an input
// file's read_by (source → transform), the certificate's writers (transform →
// its group in the warehouse), the models that read a group's tables (group →
// model) and the models a report's bindings read (model → report).
//
// Hovering or focusing a model lights its whole path and fades the rest; with
// ?model=<m> the board opens with that path lit until the pointer moves. The
// lighting is presentation only: every card is a link either way. When the
// board is narrower than its five lanes fit, the lanes stack, no wire is
// drawn and nothing fades.

// The mark beside a source's name: two or three letters for its kind.
const DIALECT_MARK = {
  postgresql: 'PG', sqlite: 'SQ', mysql: 'MY', mariadb: 'MA', mssql: 'MS', oracle: 'OR',
  snowflake: 'SF', bigquery: 'BQ', duckdb: 'DD',
}
const TYPE_MARK = {
  BigQueryConnector: 'BQ', SnowflakeConnector: 'SF', DuckDBConnector: 'DD', CSVConnector: 'CSV', MemoryConnector: 'PY',
}
function connectionMark(c) {
  if (c.type === 'SQLConnector') return DIALECT_MARK[c.dialect] || 'DB'
  return TYPE_MARK[c.type] || (c.type || '?').slice(0, 2).toUpperCase()
}
const extOf = path => (path.match(/\.([^./]+)$/)?.[1] || '').toLowerCase()
const FILE_KIND = { csv: 'CSV file', tsv: 'TSV file', parquet: 'Parquet file', json: 'JSON file', xlsx: 'Excel file', sqlite: 'SQLite file' }
const FILE_MARK = { parquet: 'PQ', sqlite: 'SQ', xlsx: 'XLS' }

// A warehouse's tier, in the words of its chip.
const TIER = { file: 'DuckDB file', object: 'Parquet', remote: 'Remote' }

const byName = (a, b) => a.name.localeCompare(b.name)
const LOOSE = '(none)'

/** Everything the board draws: its five lanes and the edges between them, from the API's answers. */
function boardOf({ connectors, inputs, transforms, warehouses, models, reports, pipelines }) {
  const stored = new Set(connectors.map(c => c.storage?.where).filter(Boolean))
  const sources = [
    ...connectors.filter(c => !c.warehouse).sort(byName).map(c => ({
      id: `src:${c.name}`, kind: 'connection', name: c.name, c,
      reads: (c.read_by?.transforms || []).map(t => t.name),
    })),
    // An input file a connection already stands for (a SQLite file under
    // inputs/) is that connection's card, not a second one.
    ...(inputs?.files || []).filter(f => (f.read_by || []).length && !stored.has(f.path)).map(f => ({
      id: `src:${f.path}`, kind: 'file', name: f.path, f, reads: f.read_by,
    })),
  ]

  // A transform is on the board when it is in the flow: a pipeline runs it,
  // or a certificate says it wrote tables. Any other file is counted, not drawn.
  const inFlow = t => t.pipelines.length || t.tables.length
  const shown = transforms.filter(inFlow).sort(byName)
  const pipelineOf = name => pipelines.find(p => p.pipeline === name)
  const trans = shown.map(t => {
    const p = t.pipelines.map(pipelineOf).find(Boolean)
    return { id: `tr:${t.name}`, t, model: (p && pipelineModels(p)[0]) || t.models[0] || '' }
  })

  // The warehouse: one card per warehouse, a group per writer (in the order of
  // the transforms lane), then any tables no certificate covers.
  const whs = warehouses.map(w => {
    const groups = [...(w.writers || [])]
      .sort((a, b) => (a.transform || a.contract).localeCompare(b.transform || b.contract))
      .map(wr => ({ key: wr.transform || wr.contract, transform: wr.transform, tables: w.tables.filter(t => t.written_by?.contract === wr.contract) }))
    const loose = w.tables.filter(t => !t.written_by?.contract)
    if (loose.length) groups.push({ key: LOOSE, transform: null, tables: loose })
    return {
      w,
      groups: groups.filter(g => g.tables.length).map(g => ({
        ...g, id: `grp:${w.name}:${g.key}`,
        models: [...new Set(g.tables.flatMap(t => t.read_by))],
      })),
    }
  })

  const modelList = [...models].sort(byName)
  const order = modelList.map(m => m.name)
  const rank = r => {
    const i = Math.min(...reportModels(r).map(m => order.indexOf(m)).filter(i => i >= 0))
    return Number.isFinite(i) ? i : order.length
  }
  const reportList = [...reports].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name))

  const edges = []
  const onBoard = new Set(trans.map(x => x.t.name))
  for (const s of sources) for (const t of s.reads) if (onBoard.has(t)) edges.push([s.id, `tr:${t}`])
  for (const { groups } of whs) {
    for (const g of groups) {
      if (g.transform && onBoard.has(g.transform)) edges.push([`tr:${g.transform}`, g.id])
      for (const m of g.models) if (order.includes(m)) edges.push([g.id, `m:${m}`])
    }
  }
  for (const r of reportList) for (const m of reportModels(r)) if (order.includes(m)) edges.push([`m:${m}`, `rp:${r.name}`])

  return { sources, trans, others: transforms.length - shown.length, whs, models: modelList, reports: reportList, edges }
}

/**
 * Every card and group on *model*'s path: its reports, the warehouse groups
 * holding its tables, the transforms that wrote them (and the one its
 * pipeline runs), and the sources those transforms read.
 */
function pathOf(board, model) {
  const lit = new Set([`m:${model}`])
  board.reports.forEach(r => { if (reportModels(r).includes(model)) lit.add(`rp:${r.name}`) })
  const writers = new Set(board.trans.filter(x => x.model === model).map(x => x.t.name))
  for (const { w, groups } of board.whs) {
    for (const g of groups) {
      if (!g.models.includes(model)) continue
      lit.add(g.id)
      lit.add(`wh:${w.name}`)
      if (g.transform) writers.add(g.transform)
    }
  }
  writers.forEach(t => lit.add(`tr:${t}`))
  board.sources.forEach(s => { if (s.reads.some(t => writers.has(t))) lit.add(s.id) })
  return lit
}

// ── The cards ────────────────────────────────────────────────────────────────

function Lane({ n, title, total, tone, children, foot }) {
  return (
    <section className={`flow-lane flow-lane--${tone}`} aria-labelledby={`lane-${tone}`}>
      <h2 id={`lane-${tone}`} className="flow-lane__head">
        <span className="flow-lane__stage">{n && <span aria-hidden="true">{n} </span>}{title}</span>
        <span className="flow-lane__n">{total}</span>
      </h2>
      <ul className="flow-lane__cards">{children}</ul>
      {foot}
    </section>
  )
}

// A connection's state here: what the Sources tab says when it opens it.
function Reach({ name }) {
  const { data } = useConnectorTables(name)
  if (!data) return null
  return data.connected
    ? <Chip>Connected</Chip>
    : <Chip tone="warn" title={data.variable ? `Set ${data.variable} to connect.` : data.reason}>Not connected here</Chip>
}

function SourceCard({ s, cardProps }) {
  if (s.kind === 'connection') {
    const { c } = s
    const mark = connectionMark(c)
    const where = c.storage?.where
    return (
      <li>
        <Link {...cardProps(s.id)} to={`${sourcesPath()}?source=${encodeURIComponent(c.name)}`}>
          <span className="fcard__t">
            <span className={`fcard__mark fcard__mark--${mark.toLowerCase()}`} aria-hidden="true">{mark}</span>
            <span className="fcard__nm" title={c.name}>{c.label || c.name}</span>
          </span>
          <span className="fcard__s">
            <Badge>{sourceKind(c)}</Badge><Reach name={c.name} />
            {where && <code className="fcard__where" title={where}>{where}</code>}
          </span>
        </Link>
      </li>
    )
  }
  const { f } = s
  const ext = extOf(f.path)
  const mark = FILE_MARK[ext] || ext.toUpperCase().slice(0, 3) || 'FILE'
  const to = f.table ? tablePath('inputs', f.path.replace(/^inputs\//, '')) : `${sourcesPath()}?source=inputs`
  return (
    <li>
      <Link {...cardProps(s.id)} to={to}>
        <span className="fcard__t">
          <span className={`fcard__mark fcard__mark--${mark.toLowerCase()}`} aria-hidden="true">{mark}</span>
          <span className="fcard__nm" title={f.path}>{f.path.split('/').pop()}</span>
        </span>
        <span className="fcard__s">
          <Badge>{FILE_KIND[ext] || 'File'}</Badge>
          <code className="fcard__where" title={f.path}>{f.path}</code>
        </span>
      </Link>
    </li>
  )
}

function TransformCard({ x, cardProps }) {
  const { t } = x
  return (
    <li>
      <Link {...cardProps(x.id)} to={x.model ? dataPath(x.model, 'transform') : transformsPath()}>
        <span className="fcard__t"><code className="fcard__nm" title={t.file}>{t.name}</code></span>
        <span className="fcard__s">
          <Badge>{FORM_LABEL[t.form] || t.form}</Badge>
          <span>writes {count(t.tables.length, 'table')}</span>
          {t.pipelines[0] && <span>pipeline <code>{t.pipelines[0]}</code></span>}
        </span>
      </Link>
    </li>
  )
}

function WarehouseCard({ w, groups, lit, focus, cardProps, groupRef }) {
  const n = w.tables.length
  const facts = [count(n, 'table'), w.size != null && fmtBytes(w.size)].filter(Boolean).join(' · ')
  const modelFor = g => g.models[0] || ''
  return (
    <li>
      <div {...cardProps(`wh:${w.name}`, 'fcard--wh')} role="group" aria-label={`Warehouse ${w.name}`}>
        <div className="fcard__head">
          <span className="fcard__t">
            <Link to={`${warehousePath()}#wh-${w.name}`} className="fcard__nm fcard__nm--link"><code>{w.name}</code></Link>
          </span>
          <span className="fcard__s">
            <Badge>{TIER[w.tier] || w.tier}</Badge>
            {w.where && <code className="fcard__where" title={w.where}>{w.where}</code>}
            <span>{facts}</span>
          </span>
        </div>
        {!w.exists && <p className="fcard__grp fcard__quiet">Nothing is built here yet.</p>}
        {groups.map(g => (
          <div key={g.id} ref={groupRef(g.id)} data-writer={g.key}
               className={`fcard__grp${focus ? (lit.has(g.id) ? ' is-lit' : ' is-dim') : ''}`}>
            <p className="fcard__who">
              {g.transform
                ? <Link to={warehousePath(modelFor(g))}>written by <code>{g.transform}</code></Link>
                : <span>written outside a transform</span>}
              <span>{g.tables.length}</span>
            </p>
            <ul className="fcard__tbls" aria-label={g.transform ? `Tables ${g.transform} wrote` : 'Tables no transform wrote'}>
              {g.tables.map(t => {
                const ok = t.contract?.status === 'satisfied'
                return (
                  <li key={t.name}>
                    <Link to={tablePath(w.name, t.name)} className={`fcard__tbl${ok ? ' fcard__tbl--ok' : ''}`}
                          title={ok ? 'The sink satisfied its contract on the run that wrote it' : undefined}>
                      {t.name}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </div>
    </li>
  )
}

function ModelCard({ m, cardProps, onLight }) {
  return (
    <li>
      <Link {...cardProps(`m:${m.name}`)} to={dataPath(m.name)} data-model={m.name}
            onMouseEnter={() => onLight(m.name)} onMouseLeave={() => onLight('')}
            onFocus={() => onLight(m.name)} onBlur={() => onLight('')}>
        <span className="fcard__t"><span className="fcard__nm">{m.label || m.name}</span></span>
        <span className="fcard__s">
          <code>{m.name}</code>
          <span>{count(m.tables.length, 'table')}</span>
          <span>{count(m.measures.length, 'measure')}</span>
        </span>
      </Link>
    </li>
  )
}

function ReportCard({ r, cardProps }) {
  const made = r.made_from === 'app.jsx' ? 'dashboard' : r.made_from === 'template.html' ? 'page' : null
  return (
    <li>
      <Link {...cardProps(`rp:${r.name}`)} to={reportPagePath(r.name)} data-report={r.name}>
        <span className="fcard__t"><span className="fcard__nm" title={r.name}>{r.display_name || r.name}</span></span>
        <span className="fcard__s">
          {made && <Badge>{made}</Badge>}
          {reportModels(r).map(m => <code key={m}>{m}</code>)}
        </span>
      </Link>
    </li>
  )
}

// ── The board ────────────────────────────────────────────────────────────────

function Board({ board, pinned }) {
  const boardRef = useRef(null)
  const svgRef = useRef(null)
  const nodes = useRef({})
  const [paths, setPaths] = useState([])
  const [hover, setHover] = useState('')
  const [pin, setPin] = useState(pinned)

  // ?model=<m> lights its path until the pointer moves.
  useEffect(() => {
    setPin(pinned)
    if (!pinned) return undefined
    const off = () => setPin('')
    window.addEventListener('pointermove', off, { once: true })
    return () => window.removeEventListener('pointermove', off)
  }, [pinned])

  const active = hover || pin
  const lit = useMemo(() => (active ? pathOf(board, active) : new Set()), [board, active])
  const focus = lit.size > 0

  const ref = useCallback(id => el => { if (el) nodes.current[id] = el; else delete nodes.current[id] }, [])
  const cardProps = (id, extra) => ({
    ref: ref(id),
    className: ['fcard', extra, focus && (lit.has(id) ? 'is-lit' : 'is-dim')].filter(Boolean).join(' '),
  })

  // Wires, from where each card is now: right edge of one to the left edge of
  // the next, as a gentle S. None when the lanes stack (the svg is hidden).
  const draw = useCallback(() => {
    const host = boardRef.current
    const svg = svgRef.current
    if (!host || !svg) return
    if (getComputedStyle(svg).display === 'none') { setPaths(p => (p.length ? [] : p)); return }
    const b = host.getBoundingClientRect()
    const next = []
    for (const [a, z] of board.edges) {
      const A = nodes.current[a]
      const Z = nodes.current[z]
      if (!A || !Z) continue
      const ra = A.getBoundingClientRect()
      const rz = Z.getBoundingClientRect()
      const x1 = ra.right - b.left
      const y1 = ra.top + ra.height / 2 - b.top
      const x2 = rz.left - b.left
      const y2 = rz.top + rz.height / 2 - b.top
      const dx = Math.max(24, (x2 - x1) / 2)
      next.push({ key: `${a}>${z}`, a, z, d: `M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}` })
    }
    setPaths(prev => (prev.map(p => p.key + p.d).join() === next.map(p => p.key + p.d).join() ? prev : next))
  }, [board])

  useLayoutEffect(() => { draw() }, [draw])
  useEffect(() => {
    const host = boardRef.current
    if (!host) return undefined
    // A card that grows (a connection's state arriving) moves the cards
    // under it: each lane's list is watched, not only the board.
    const ro = new ResizeObserver(() => draw())
    ro.observe(host)
    host.querySelectorAll('.flow-lane__cards').forEach(el => ro.observe(el))
    window.addEventListener('resize', draw)
    document.fonts?.ready.then(draw)
    return () => { ro.disconnect(); window.removeEventListener('resize', draw) }
  }, [draw])

  const light = model => setHover(model)
  const groupRef = id => ref(id)

  return (
    <>
      <p className="flow-hint">
        Read left to right, in the order the data moves. Hover or focus a model to light its whole path.
      </p>
      <div className="flow">
        <div className={`flow-board${focus ? ' flow-board--focus' : ''}`} ref={boardRef}>
          <svg className="flow-wires" ref={svgRef} aria-hidden="true">
            {paths.map(p => (
              <path key={p.key} d={p.d} className={focus && lit.has(p.a) && lit.has(p.z) ? 'is-lit' : undefined} />
            ))}
          </svg>
          <Lane n="⓪" title="Sources" total={board.sources.length} tone="sources">
            {board.sources.map(s => <SourceCard key={s.id} s={s} cardProps={cardProps} />)}
          </Lane>
          <Lane n="①" title="Transforms" total={board.trans.length} tone="transforms"
                foot={board.others > 0 && (
                  <p className="flow-lane__foot">
                    <Link to={transformsPath()}>{count(board.others, 'other transform file')}</Link>: no pipeline runs it and no certificate names it.
                  </p>
                )}>
            {board.trans.map(x => <TransformCard key={x.id} x={x} cardProps={cardProps} />)}
          </Lane>
          <Lane title="Warehouse" total={board.whs.reduce((n, { w }) => n + w.tables.length, 0)} tone="warehouse">
            {board.whs.map(({ w, groups }) => (
              <WarehouseCard key={w.name} w={w} groups={groups} lit={lit} focus={focus}
                             cardProps={cardProps} groupRef={groupRef} />
            ))}
          </Lane>
          <Lane n="②" title="Models" total={board.models.length} tone="models">
            {board.models.map(m => <ModelCard key={m.name} m={m} cardProps={cardProps} onLight={light} />)}
          </Lane>
          <Lane n="③" title="Reports" total={board.reports.length} tone="reports">
            {board.reports.map(r => <ReportCard key={r.name} r={r} cardProps={cardProps} />)}
          </Lane>
        </div>
      </div>
      <p className="flow-legend">
        <span><b>Lanes</b> are stages and never mix: a source is a thing you read, a warehouse table is a thing a transform wrote.</span>
        <span><b>Chips</b> say the mechanism: SQL, Python, Postgres, SQLite file, CSV.</span>
        <span><b>Green dots</b> are tables where the sink satisfied its contract on the run that wrote them.</span>
      </p>
    </>
  )
}

/** Data's Flow tab (/data): the board. */
export default function Flow() {
  const [params] = useSearchParams()
  const queries = [useConnectors(), useInputs(), useTransforms(), useWarehouses(), useModels(), useReports(), usePipelines()]
  const [connectors, inputs, transforms, warehouses, models, reports, pipelines] = queries.map(q => q.data)
  const board = useMemo(() => (
    [connectors, inputs, transforms, warehouses, models, reports, pipelines].every(Boolean)
      ? boardOf({ connectors, inputs, transforms, warehouses: warehouses.warehouses || [], models, reports, pipelines })
      : null
  ), [connectors, inputs, transforms, warehouses, models, reports, pipelines])

  // Old links: /data?view=map was the Map (a model's map is its own page's
  // line now); /data?m=<model> was a model's page.
  if (params.get('view') === 'map') {
    return <Navigate to={params.get('model') ? dataPath(params.get('model')) : '/data'} replace />
  }
  if (params.get('m')) return <Navigate to={dataPath(params.get('m'))} replace />

  const failed = queries.find(q => q.error)
  return (
    <DataFrame tab="flow">
      {failed ? <ErrorDetail error={failed.error} />
        : !board ? <SkeletonCard />
        : !board.models.length && !board.sources.length && !board.trans.length
          ? <Empty message="Nothing to draw yet. Put files under inputs/, write a transform with tracebi new-transform, and a model over the warehouse with tracebi new-model." />
          : <Board board={board} pinned={params.get('model') || ''} />}
    </DataFrame>
  )
}
