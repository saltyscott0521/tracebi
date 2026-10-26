import { Fragment, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ReactFlow, ReactFlowProvider, Background, BackgroundVariant, BaseEdge, Controls, ControlButton, MiniMap,
  Handle, Position, getSmoothStepPath, useNodesState, useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { useTable, useTables } from '../api'
import { CONTRACT } from './Warehouse'
import { useModelLabel } from './Scope'
import { MAX_COLUMNS, NODE_W, layoutSchema, nodeHeight, typeKind } from './modelGraph'
import { count } from '../format'
import { modelPath, reportPagePath, tablePath, transformPath, warehouseTablePath } from '../nav'
import { Btn, BtnLink, Chip, ErrorDetail, Time } from './Shared'

// The data browser: a tree of tables, the schema drawn as a diagram, and an
// inspector for what is selected, side by side, as a database tool lays them
// out. One component for two scopes: a model's page (its tables, joins and
// measures) and the Warehouse folder (every table, grouped by the transform
// that wrote it, with every model's joins over them).
//
// It draws what the API states and counts nothing itself: a table's rows and
// checks come from the table API (or the warehouse listing), read only when
// that table is selected; its columns, rows and profile are on its own page.
// The selection is the address's (?table=, ?group=), so a link opens on it and
// Back steps back.

// ── Glyphs ────────────────────────────────────────────────────────────────────

const KIND = {
  fact: 'Fact: the rows a measure adds up',
  dimension: 'Dimension: what a fact is broken down by',
  bridge: 'Both a fact and a dimension',
  table: 'A table with no joins',
}
const KIND_WORD = { fact: 'Fact', dimension: 'Dimension', bridge: 'Fact and dimension', table: 'Table' }

const KeyIcon = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
    <circle cx="4" cy="6" r="2.4" /><path d="M6.4 6H11M9.2 6v2.2M11 6v1.6" strokeLinecap="round" />
  </svg>
)

// A view: one square laid over another, the rows a definition shows of the
// tables under it.
const ViewIcon = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.3"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="1.5" y="3.5" width="7" height="7" rx="1" /><path d="M3.5 1.5h6a1 1 0 0 1 1 1v6" />
  </svg>
)
const VIEW_TITLE = 'View: a definition over warehouse tables, its rows computed when read'

/**
 * A table's kind as a small square: Σ for a fact, a key for a dimension. A
 * sink view (*view*) has its own square, whatever role a model gives it.
 */
export function KindGlyph({ role, view }) {
  if (view) {
    return <span className="dbx-kind dbx-kind--view" role="img" aria-label="View" title={VIEW_TITLE}><ViewIcon /></span>
  }
  return (
    <span className={`dbx-kind dbx-kind--${role}`} role="img" aria-label={KIND_WORD[role]} title={KIND[role]}>
      {role === 'dimension' ? <KeyIcon /> : role === 'table' ? '' : 'Σ'}
    </span>
  )
}

const TYPE_PATH = {
  number: 'M4.6 1.5 3.6 10.5M8.4 1.5l-1 9M1.5 4.2h9M1.2 7.8h9',
  text: 'M2 2.5h8M6 2.5v8',
  date: 'M2 3h8a.5.5 0 0 1 .5.5v6.5a.5.5 0 0 1-.5.5H2a.5.5 0 0 1-.5-.5V3.5A.5.5 0 0 1 2 3ZM1.5 5.5h9M4 1.5v2.5M8 1.5v2.5',
  bool: 'M2.5 1.5h7a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1ZM3.8 6.1l1.6 1.6 3-3.3',
  other: 'M4.5 1.5C3.2 1.5 3.4 3 3.4 4.3 3.4 5.4 2.6 6 1.6 6c1 0 1.8.6 1.8 1.7 0 1.3-.2 2.8 1.1 2.8M7.5 1.5c1.3 0 1.1 1.5 1.1 2.8 0 1.1.8 1.7 1.8 1.7-1 0-1.8.6-1.8 1.7 0 1.3.2 2.8-1.1 2.8',
}
const TYPE_WORD = { number: 'Number', text: 'Text', date: 'Date or time', bool: 'True or false', other: 'Other type' }

/** A column's type as one of five 12 px glyphs, its engine type in the title. */
export function TypeGlyph({ type }) {
  const k = typeKind(type)
  return (
    <span className="dbx-ty" title={type ? `${TYPE_WORD[k]} (${type})` : TYPE_WORD[k]}>
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.2"
           strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={TYPE_PATH[k]} /></svg>
    </span>
  )
}

const FLAG_TITLE = {
  PK: 'Key: the column a fact joins this table on',
  FK: 'Foreign key: joins a dimension',
  'Σ': 'A measure column on the fact',
}

/** Before a column's name: its key or foreign-key mark, Σ for a measure, else its type. */
function ColMark({ c }) {
  if (c.flag === 'PK') return <span className="dbx-mark dbx-mark--pk" title={FLAG_TITLE.PK}><KeyIcon /></span>
  if (c.flag === 'FK') return <span className="dbx-mark dbx-mark--fk" title={FLAG_TITLE.FK} aria-hidden="true">→</span>
  if (c.flag === 'Σ') return <span className="dbx-mark dbx-mark--m" title={FLAG_TITLE['Σ']} aria-hidden="true">Σ</span>
  return <TypeGlyph type={c.type} />
}

const rowsWords = (info, short) => {
  if (!info || info.rows == null) return ''
  const n = `${info.exact === false ? '~' : ''}${Number(info.rows).toLocaleString('en-US')}`
  return short ? n : `${n} ${Number(info.rows) === 1 ? 'row' : 'rows'}`
}

// The part of *text* that matches *q*, marked.
function Hit({ text, q }) {
  const i = q ? text.toLowerCase().indexOf(q) : -1
  if (i < 0) return text
  return <>{text.slice(0, i)}<mark>{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>
}

// ── The tree ──────────────────────────────────────────────────────────────────

/**
 * Groups, their tables, and each table's columns, as one flat ARIA tree (each
 * item says its level), so arrows move through what is visible. Typing in the
 * filter keeps the tables whose name or a column's matches.
 */
function Tree({ schema, infoOf, selected, onTable, onColumn, onGroup, query, setQuery, filterRef }) {
  const q = query.trim().toLowerCase()
  const [closedGroups, setClosedGroups] = useState(() => new Set())
  const [open, setOpen] = useState(() => new Set(selected.table ? [selected.table] : []))
  const [focus, setFocus] = useState(null)
  const listRef = useRef(null)
  useEffect(() => { if (selected.table) setOpen(s => (s.has(selected.table) ? s : new Set(s).add(selected.table))) }, [selected.table])

  const byId = useMemo(() => Object.fromEntries(schema.tables.map(t => [t.id, t])), [schema])
  const items = useMemo(() => {
    const out = []
    schema.groups.forEach(g => {
      const shown = g.tables.map(id => byId[id]).filter(Boolean).map(t => {
        const named = !q || t.name.toLowerCase().includes(q)
        const cols = q ? t.columns.filter(c => c.name.toLowerCase().includes(q)) : t.columns
        return { t, named, cols: named ? t.columns : cols }
      }).filter(x => x.named || x.cols.length)
      if (q && !shown.length) return
      const gOpen = !closedGroups.has(g.id) || !!q
      out.push({ key: `g:${g.id}`, kind: 'group', g, n: shown.length, level: 1, expanded: gOpen })
      if (!gOpen) return
      shown.forEach(({ t, named, cols }) => {
        const tOpen = open.has(t.id) || (!!q && !named)
        out.push({ key: `t:${t.id}`, kind: 'table', t, level: 2, expanded: tOpen, parent: `g:${g.id}` })
        if (tOpen) cols.forEach(c => out.push({ key: `c:${t.id}:${c.name}`, kind: 'column', t, c, level: 3, parent: `t:${t.id}` }))
      })
    })
    return out
  }, [schema, byId, q, closedGroups, open])

  const at = Math.max(0, items.findIndex(i => i.key === (focus || `t:${selected.table}`)))
  const move = i => {
    const it = items[Math.max(0, Math.min(items.length - 1, i))]
    if (!it) return
    setFocus(it.key)
    listRef.current?.querySelector(`[data-key="${CSS.escape(it.key)}"]`)?.focus()
  }
  const toggle = it => {
    if (it.kind === 'group') setClosedGroups(s => { const n = new Set(s); n.has(it.g.id) ? n.delete(it.g.id) : n.add(it.g.id); return n })
    if (it.kind === 'table') setOpen(s => { const n = new Set(s); n.has(it.t.id) ? n.delete(it.t.id) : n.add(it.t.id); return n })
  }
  const activate = it => {
    setFocus(it.key)
    if (it.kind === 'group') { if (onGroup) onGroup(it.g.id); else toggle(it) }
    if (it.kind === 'table') { onTable(it.t.id); setOpen(s => new Set(s).add(it.t.id)) }
    if (it.kind === 'column') onColumn(it.t.id, it.c.name)
  }
  const onKey = e => {
    const it = items[at]
    if (!it) return
    const k = e.key
    if (k === 'ArrowDown') { e.preventDefault(); move(at + 1) }
    else if (k === 'ArrowUp') { e.preventDefault(); move(at - 1) }
    else if (k === 'Home') { e.preventDefault(); move(0) }
    else if (k === 'End') { e.preventDefault(); move(items.length - 1) }
    else if (k === 'ArrowRight') {
      e.preventDefault()
      if (it.expanded === false) toggle(it)
      else if (it.expanded) move(at + 1)
    } else if (k === 'ArrowLeft') {
      e.preventDefault()
      if (it.expanded && !q) toggle(it)
      else if (it.parent) move(items.findIndex(x => x.key === it.parent))
    } else if (k === 'Enter' || k === ' ') { e.preventDefault(); activate(it) }
  }

  return (
    <div className="dbx-tree">
      <div className="dbx-tree__find">
        <input ref={filterRef} type="search" value={query} onChange={e => setQuery(e.target.value)}
               placeholder="Find a table or column" aria-label="Find a table or column" />
        <kbd aria-hidden="true" title="Press / to find">/</kbd>
      </div>
      {items.length === 0 && <p className="dbx-tree__none">Nothing matches “{query}”.</p>}
      <ul ref={listRef} className="dbx-tree__list" role="tree" aria-label="Tables" onKeyDown={onKey}>
        {items.map((it, i) => {
          const common = {
            key: it.key, 'data-key': it.key, role: 'treeitem', 'aria-level': it.level,
            tabIndex: i === at ? 0 : -1, onFocus: () => setFocus(it.key),
            onClick: () => activate(it),
          }
          const chev = it.expanded !== undefined && (
            <span className="dbx-tree__chev" aria-hidden="true" data-open={it.expanded || undefined}
                  onClick={e => { e.stopPropagation(); setFocus(it.key); toggle(it) }}>›</span>
          )
          if (it.kind === 'group') {
            const on = selected.group === it.g.id
            return (
              <li {...common} aria-expanded={it.expanded} aria-selected={onGroup ? on : undefined}
                  className={`dbx-tree__group${it.g.writer ? ' dbx-tree__group--writer' : ''}${on ? ' is-on' : ''}`} data-writer={it.g.writer?.transform || it.g.writer?.contract}>
                {chev}<span className="dbx-tree__glabel">{it.g.label}</span><span className="dbx-tree__n">{it.n}</span>
              </li>
            )
          }
          if (it.kind === 'table') {
            const info = infoOf(it.t)
            const c = info?.contract && (CONTRACT[info.contract.status] || CONTRACT.no_contract)
            const on = selected.table === it.t.id
            return (
              <li {...common} aria-expanded={it.expanded} aria-selected={on} data-table={it.t.id}
                  className={`dbx-tree__table${on ? ' is-on' : ''}`}>
                {chev}<KindGlyph role={it.t.role} view={info?.view} />
                <span className="dbx-tree__name" title={it.t.name}><Hit text={it.t.name} q={q} /></span>
                <span className="dbx-tree__n">{rowsWords(info, true)}</span>
                {c
                  ? <span className={`dbx-dot dbx-dot--${info.contract.status}`} role="img" aria-label={c.label} title={c.title} />
                  : <span className="dbx-dot dbx-dot--blank" aria-hidden="true" />}
              </li>
            )
          }
          return (
            <li {...common} className="dbx-tree__col" data-column={it.c.name}>
              <ColMark c={it.c} />
              <span className="dbx-tree__name" title={it.c.name}><Hit text={it.c.name} q={q} /></span>
              <span className="dbx-tree__ty">{it.c.flag === 'PK' ? 'PK' : it.c.flag === 'FK' ? 'FK' : it.c.type}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ── The canvas ────────────────────────────────────────────────────────────────

const H = { opacity: 0, width: 6, height: 6, minWidth: 0, minHeight: 0, border: 0, background: 'transparent' }

// One column's join points: where a join leaves (a foreign key) or lands (a key).
function Ports({ name, ports }) {
  return (
    <>
      {ports.src.has(name) && <>
        <Handle type="source" id={`s-l-${name}`} position={Position.Left} isConnectable={false} style={H} />
        <Handle type="source" id={`s-r-${name}`} position={Position.Right} isConnectable={false} style={H} />
      </>}
      {ports.tgt.has(name) && <>
        <Handle type="target" id={`t-l-${name}`} position={Position.Left} isConnectable={false} style={H} />
        <Handle type="target" id={`t-r-${name}`} position={Position.Right} isConnectable={false} style={H} />
      </>}
    </>
  )
}

const TableNode = memo(function TableNode({ data }) {
  const { t, info, on, faded, open, onMore, ports } = data
  const cols = open ? t.columns : t.columns.slice(0, MAX_COLUMNS)
  const more = t.columns.length - cols.length
  return (
    <div className={`dbx-node dbx-node--${t.role}${on ? ' is-on' : ''}${faded ? ' is-faded' : ''}`} style={{ width: NODE_W }}
         data-table={t.id}>
      {['l', 'r'].map(s => (
        <Fragment key={s}>
          <Handle type="source" id={`s-${s}-`} position={s === 'l' ? Position.Left : Position.Right} isConnectable={false} style={H} />
          <Handle type="target" id={`t-${s}-`} position={s === 'l' ? Position.Left : Position.Right} isConnectable={false} style={H} />
        </Fragment>
      ))}
      <div className="dbx-node__band">
        <KindGlyph role={t.role} view={info?.view} />
        <span className="dbx-node__name" title={t.name}>{t.name}</span>
        <span className="dbx-node__rows">{rowsWords(info)}</span>
      </div>
      <ul className="dbx-node__cols">
        {cols.map(c => (
          <li key={c.name} className={`dbx-node__col${c.flag === 'PK' || c.flag === 'FK' ? ' is-key' : ''}`}>
            <Ports name={c.name} ports={ports} />
            <ColMark c={c} />
            <span className="dbx-node__cname" title={c.name}>{c.name}</span>
            <span className="dbx-node__type">{c.type}</span>
          </li>
        ))}
        {cols.length === 0 && <li className="dbx-node__col dbx-node__none">Columns not read</li>}
      </ul>
      {(more > 0 || (open && t.columns.length > MAX_COLUMNS)) && (
        <button type="button" className="dbx-node__more nodrag" onClick={e => { e.stopPropagation(); onMore(t.id) }}>
          {open ? 'Show fewer' : `+${more} more`}
        </button>
      )}
    </div>
  )
})

// A join, drawn in steps from the fact's foreign key to the dimension's key,
// a crow's foot on the many side and a bar on the one. Its words are its
// title (a tooltip) and the inspector's, never text on the line.
function JoinEdge({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data }) {
  const [path] = getSmoothStepPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition, borderRadius: 8, offset: 20 })
  const s = data.on ? '-on' : data.faded ? '-off' : ''
  return (
    <g>
      <title>{data.tip}</title>
      <BaseEdge id={id} path={path} interactionWidth={14}
                markerStart={data.many ? `url(#dbx-many${s})` : undefined} markerEnd={data.many ? `url(#dbx-one${s})` : undefined} />
    </g>
  )
}

const NODE_TYPES = { table: TableNode }
const EDGE_TYPES = { join: JoinEdge }

/** "N : 1 · fund_id", the words of a join, from the edge. */
export const joinWords = e => {
  const keys = e.fromKey === e.toKey ? e.fromKey : `${e.fromKey} = ${e.toKey}`
  return e.cardinality === 'many-to-one' ? `N : 1 · ${keys}` : `${e.how ? `${e.how} join` : 'join'} · ${keys}`
}

function Markers() {
  return (
    <svg className="dbx-markers" width="0" height="0" aria-hidden="true" focusable="false">
      <defs>
        {['', '-on', '-off'].map(s => (
          <Fragment key={s}>
            <marker id={`dbx-many${s}`} viewBox="0 0 10 10" markerWidth="10" markerHeight="10" refX="10" refY="5"
                    orient="auto-start-reverse" markerUnits="userSpaceOnUse">
              <path className={`dbx-mk${s}`} d="M2 5 10 1.5M2 5h8M2 5l8 3.5" fill="none" />
            </marker>
            <marker id={`dbx-one${s}`} viewBox="0 0 10 10" markerWidth="10" markerHeight="10" refX="10" refY="5"
                    orient="auto" markerUnits="userSpaceOnUse">
              <path className={`dbx-mk${s}`} d="M6 1.5v7" fill="none" />
            </marker>
          </Fragment>
        ))}
      </defs>
    </svg>
  )
}

const readSaved = key => {
  try { return JSON.parse(localStorage.getItem(key) || '{}') || {} } catch { return {} }
}
const writeSaved = (key, value) => {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* a private window: it is not kept */ }
}

function Canvas({ schema, infoOf, selected, onSelect, storeKey, emptyNote }) {
  const flow = useReactFlow()
  const wrap = useRef(null)
  const key = `tracebi-diagram-${storeKey}`
  const laid = useMemo(() => layoutSchema(schema.tables, schema.edges), [schema])
  const [opened, setOpened] = useState(() => new Set())
  const onMore = useCallback(id => setOpened(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n }), [])
  const base = useCallback(saved => schema.tables.map(t => ({
    id: t.id, type: 'table', position: saved[t.id] || laid[t.id] || { x: 0, y: 0 }, data: {},
    ariaLabel: `${KIND_WORD[t.role]} ${t.name}`,
  })), [schema, laid])
  const [nodes, setNodes, onNodesChange] = useNodesState(base(readSaved(key)))
  useEffect(() => { setNodes(base(readSaved(key))) }, [base, key, setNodes])

  const ports = useMemo(() => {
    const p = Object.fromEntries(schema.tables.map(t => [t.id, { src: new Set(), tgt: new Set() }]))
    schema.edges.forEach(e => { p[e.from]?.src.add(e.fromKey); p[e.to]?.tgt.add(e.toKey) })
    return p
  }, [schema])
  const byId = useMemo(() => Object.fromEntries(schema.tables.map(t => [t.id, t])), [schema])
  const near = useMemo(() => new Set(selected ? schema.edges.filter(e => e.from === selected || e.to === selected)
    .flatMap(e => [e.from, e.to]) : []), [schema, selected])

  const shown = useMemo(() => nodes.map(n => ({
    ...n,
    data: {
      t: byId[n.id], info: infoOf(byId[n.id]), on: n.id === selected, faded: !!selected && !near.has(n.id) && n.id !== selected,
      open: opened.has(n.id), onMore, ports: ports[n.id],
    },
  })), [nodes, byId, infoOf, selected, near, opened, onMore, ports])

  const xOf = useMemo(() => Object.fromEntries(nodes.map(n => [n.id, n.position.x])), [nodes])
  const edges = useMemo(() => schema.edges.map(e => {
    const visible = (id, col) => {
      const t = byId[id]
      return opened.has(id) || t.columns.findIndex(c => c.name === col) < MAX_COLUMNS
    }
    // Leave on the side that faces the other table, so a join runs across. A
    // table above or below (the ring's top and bottom) is reached round the
    // outer side of both, so the join never runs behind a card or across the
    // join of the fact beside it.
    const dx = xOf[e.to] - xOf[e.from]
    const [out, into] = Math.abs(dx) < NODE_W ? (dx >= 0 ? ['l', 'l'] : ['r', 'r']) : dx < 0 ? ['l', 'r'] : ['r', 'l']
    const on = !!selected && (e.from === selected || e.to === selected)
    return {
      id: e.id, source: e.from, target: e.to, type: 'join',
      sourceHandle: `s-${out}-${visible(e.from, e.fromKey) ? e.fromKey : ''}`,
      targetHandle: `t-${into}-${visible(e.to, e.toKey) ? e.toKey : ''}`,
      className: on ? 'is-on' : selected ? 'is-faded' : undefined,
      focusable: false,
      data: { on, faded: !!selected && !on, many: e.cardinality === 'many-to-one', tip: `${e.from}.${e.fromKey} → ${e.to}.${e.toKey} · ${joinWords(e)}` },
    }
  }), [schema, byId, opened, xOf, selected])

  // Open at 100 %, the top left of the drawing in view: the tables read at
  // their own size, and the minimap and Fit show the rest.
  const start = useCallback(() => {
    const all = nodes.map(n => n.position)
    if (!all.length) return
    // With a table selected, open on it and the tables it joins, at a size
    // the columns can be read; else the whole schema (never larger than life).
    if (selected && byId[selected]) {
      const ids = [selected, ...near].map(id => ({ id }))
      flow.fitView({ nodes: ids, padding: 0.12, maxZoom: 1, duration: 0 })
      return
    }
    flow.fitView({ padding: 0.08, maxZoom: 1, duration: 0 })
  }, [nodes, selected, byId, near]) // eslint-disable-line react-hooks/exhaustive-deps

  // A table selected from the tree comes into view if it is not already.
  const reveal = (id, animate = true) => {
    const n = flow.getNode(id)
    const el = wrap.current
    if (!n || !el) return
    const { x, y, zoom } = flow.getViewport()
    const h = nodeHeight(byId[id])
    const sx = n.position.x * zoom + x
    const sy = n.position.y * zoom + y
    const W = el.clientWidth
    const Hh = el.clientHeight
    if (sx >= 0 && sy >= 0 && sx + NODE_W * zoom <= W && sy + Math.min(h, Hh) * zoom <= Hh) return
    const z = Math.max(zoom, 0.85)
    flow.setCenter(n.position.x + NODE_W / 2, n.position.y + Math.min(h, Hh / z - 64) / 2, { zoom: z, duration: animate ? 250 : 0 })
  }
  const first = useRef(true)
  useEffect(() => {
    if (first.current) { first.current = false; return }
    if (selected) reveal(selected)
  }, [selected]) // eslint-disable-line react-hooks/exhaustive-deps

  // Back to the ring, the whole of it in view, as it opens.
  const reset = () => {
    writeSaved(key, {})
    setNodes(base({}))
    setTimeout(() => flow.fitView({ padding: 0.08, maxZoom: 1, duration: 0 }), 0)
  }

  return (
    <div ref={wrap} className="dbx-canvas__flow">
      <ReactFlow
        nodes={shown} edges={edges} nodeTypes={NODE_TYPES} edgeTypes={EDGE_TYPES}
        onNodesChange={onNodesChange}
        onNodeDragStop={(_, __, dragged) => {
          const saved = { ...readSaved(key) }
          dragged.forEach(n => { saved[n.id] = n.position })
          nodes.forEach(n => { saved[n.id] ||= n.position })
          writeSaved(key, saved)
        }}
        onNodeClick={(_, n) => onSelect(n.id === selected ? null : n.id)}
        onPaneClick={() => selected && onSelect(null)}
        onInit={start}
        minZoom={0.2} maxZoom={1.6}
        nodesConnectable={false} edgesFocusable={false} elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1.2} color="var(--dbx-dots)" />
        <Controls position="bottom-left" showInteractive={false} fitViewOptions={{ padding: 0.08, maxZoom: 1 }}>
          <ControlButton onClick={reset} title="Reset layout" aria-label="Reset layout" className="dbx-reset">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" aria-hidden="true">
              <path d="M2.2 6a3.8 3.8 0 1 0 1.1-2.7M2 1.6v2.2h2.2" />
            </svg>
          </ControlButton>
        </Controls>
        <MiniMap position="bottom-right" pannable zoomable ariaLabel="Overview of the diagram" style={{ width: 150, height: 96 }}
                 nodeClassName={n => `dbx-mini dbx-mini--${byId[n.id]?.role || 'table'}${n.id === selected ? ' is-on' : ''}`} />
      </ReactFlow>
      {emptyNote && schema.edges.length === 0 && <div className="dbx-canvas__note">{emptyNote}</div>}
    </div>
  )
}

// ── The inspector ─────────────────────────────────────────────────────────────

/** One section of the inspector: a sticky heading, open until folded. */
function Section({ id, title, aside, children, open = true, onToggle }) {
  return (
    <section className="dbx-sec" aria-labelledby={`dbx-${id}`} data-section={id}>
      <h3 id={`dbx-${id}`} className="dbx-sec__h">
        {onToggle
          ? <button type="button" aria-expanded={open} onClick={onToggle}><span className="dbx-tree__chev" aria-hidden="true" data-open={open || undefined}>›</span>{title}</button>
          : title}
        {aside && <span className="dbx-sec__aside">{aside}</span>}
      </h3>
      {open && <div className="dbx-sec__body">{children}</div>}
    </section>
  )
}

/** The joins *id* is in, as sentences; a click selects the table at the other end. */
function JoinsSection({ id, edges, onSelect }) {
  const mine = edges.filter(e => e.from === id || e.to === id)
  return (
    <Section id="joins" title="Joins" aside={mine.length ? count(mine.length, 'join') : null}>
      {mine.length === 0 ? <p className="dbx-quiet">No join names this table.</p> : (
        <ul className="dbx-joins">
          {mine.map(e => {
            const other = e.from === id ? e.to : e.from
            const how = e.cardinality === 'many-to-one' ? 'many to one' : e.how ? `${e.how} join` : 'join'
            return (
              <li key={e.id}>
                <button type="button" onClick={() => onSelect(other)} title={`Select ${other}`}
                        aria-label={`${e.from}.${e.fromKey} → ${e.to}.${e.toKey} · ${how}`}>
                  <code>{e.from}.{e.fromKey}</code><span aria-hidden="true">→</span><code>{e.to}.{e.toKey}</code>
                  <span className="dbx-joins__how">· {how}</span>
                </button>
                {e.models?.length > 0 && <span className="dbx-quiet"> declared by {e.models.join(', ')}</span>}
              </li>
            )
          })}
        </ul>
      )}
    </Section>
  )
}

function UsedBy({ info }) {
  const labelOf = useModelLabel()
  if (!info) return null
  return (
    <Section id="used" title="Used by">
      <p className="dbx-quiet">
        Read by {(info.read_by || []).length
          ? info.read_by.map((m, i) => <Fragment key={m}>{i > 0 && ', '}<Link to={modelPath(m)}>{labelOf(m)}</Link></Fragment>)
          : 'no model'}
      </p>
      {(info.used_by || []).length > 0
        ? <ul className="dbx-used">{info.used_by.map(r => <li key={r.report}><Link to={reportPagePath(r.report)}>{r.display_name || r.report}</Link></li>)}</ul>
        : <p className="dbx-quiet">No report reads a model over this table.</p>}
    </Section>
  )
}

// A table, selected: a short card. What it is, its checks, its shape, who
// wrote it, its joins and who uses it; its columns, rows and profile are on
// its own page, which Open table opens.
function TableInspector({ t, edges, measures, onSelect, onClose }) {
  const { data: info, error } = useTable(t.connector, t.source)
  const c = info?.contract && (CONTRACT[info.contract.status] || CONTRACT.no_contract)
  const connected = info && info.connected !== false
  const view = connected && info.table_kind === 'view'
  // A warehouse table's page is under Warehouse; it names its warehouse only
  // when the browser does (two warehouses: ids are <warehouse>.<table>).
  const page = info?.kind === 'warehouse'
    ? warehouseTablePath(t.source, t.id === `${t.connector}.${t.source}` ? t.connector : '')
    : tablePath(t.connector, t.source)
  return (
    <div className="dbx-insp__table" data-inspecting={t.id}>
      <header className="dbx-insp__head">
        <div className="dbx-insp__title">
          <KindGlyph role={t.role} view={view} />
          <h2 className="dbx-insp__name" title={t.name}>{t.name}</h2>
          {c && <Chip tone={c.tone} title={c.title}>{c.label}</Chip>}
          <button type="button" className="dbx-close" onClick={onClose} aria-label="Close the table" title="Back to the summary">×</button>
        </div>
        <p className="dbx-insp__sub">
          {view ? 'View' : KIND_WORD[t.role]}
          {connected && <> · {info.rows == null ? 'rows not counted' : `${info.rows_exact === false ? '~' : ''}${count(info.rows, 'row')}`} × {count(info.columns.length, 'column')}</>}
          {view && (info.view?.transform || info.view?.bases?.length > 0) && <>
            {' · '}defined by {info.view.transform ? <code>{info.view.transform}</code> : 'a transform'}
            {info.view.bases?.length > 0 && <> over {info.view.bases.map((b, i) => <Fragment key={b}>{i > 0 && ', '}<code>{b}</code></Fragment>)}</>}
          </>}
          {t.source !== t.name && <> · stored as <code>{t.source}</code></>}
        </p>
        {connected && info.kind === 'warehouse' && (
          <p className="dbx-insp__sub">
            Written by {info.written_by?.transform
              ? <Link to={transformPath(info.written_by.transform)}><code>{info.written_by.transform}</code></Link>
              : 'no recorded transform'}
            {info.written_by?.at && <> · <Time iso={info.written_by.at} /></>}
          </p>
        )}
        {info?.connected === false && <p className="dbx-quiet">Not connected here · {info.variable ? <>set <code>{info.variable}</code></> : info.reason}</p>}
        {error && <ErrorDetail error={error} />}
        <div className="dbx-insp__acts">
          <BtnLink size="sm" to={page}>Open table</BtnLink>
        </div>
      </header>
      <JoinsSection id={t.id} edges={edges} onSelect={onSelect} />
      {measures}
      <UsedBy info={connected ? info : null} />
    </div>
  )
}

// ── The browser ───────────────────────────────────────────────────────────────

const modeOf = w => (w >= 1040 ? 'wide' : w >= 640 ? 'mid' : 'phone')

/**
 * The browser over *schema* (`modelSchema` / `warehouseSchema` in
 * modelGraph.js).
 *
 * - *storeKey*: where a rearranged diagram is kept (`tracebi-diagram-<key>`).
 * - *infoOf*(table): `{rows, exact, contract, view}` when the page already has it
 *   (the warehouse listing); otherwise each table is read from the table API.
 * - *summary*: the inspector when nothing is selected.
 * - *groupView*(group): the inspector when a tree group is selected (only
 *   when given; a group heading otherwise folds).
 * - *measuresOf*(table): the inspector's Measures section for a table, or null.
 * - *emptyNote*: said on the canvas when there are no joins.
 * - *summaryOpen*: the address names a part of the summary (?view=), so it
 *   shows even where the inspector is a sheet.
 */
export default function DataBrowser({ schema, storeKey, infoOf: given, summary, groupView, measuresOf, emptyNote, label, summaryOpen }) {
  const [params, setParams] = useSearchParams()
  const table = schema.tables.some(t => t.id === params.get('table')) ? params.get('table') : null
  const groupId = groupView && schema.groups.some(g => g.id === params.get('group')) ? params.get('group') : null
  const group = schema.groups.find(g => g.id === groupId) || null
  const [query, setQuery] = useState('')
  const filterRef = useRef(null)
  const root = useRef(null)
  const [mode, setMode] = useState('wide')
  const [top, setTop] = useState(0)
  const [sheet, setSheet] = useState(false)

  // One read per table for the tree's counts when the page has none of its own
  // (a model's tables): the same cache the inspector reads.
  const reads = useTables(schema.tables.map(t => [t.connector, t.source]), !given)
  const infoOf = useCallback(t => {
    if (!t) return null
    if (given) return given(t)
    const d = reads[schema.tables.indexOf(t)]?.data
    return d && d.connected !== false ? { rows: d.rows, exact: d.rows_exact, contract: d.contract, view: d.table_kind === 'view' } : null
  }, [given, reads, schema]) // eslint-disable-line react-hooks/exhaustive-deps

  const go = useCallback(patch => setParams(p => {
    const next = new URLSearchParams(p)
    Object.entries(patch).forEach(([k, v]) => (v == null ? next.delete(k) : next.set(k, v)))
    return next
  }), [setParams])
  const selectTable = useCallback(id => { go({ table: id, group: null }) }, [go])
  // A column, picked in the tree, selects its table (its profile is on the table's page).
  const selectColumn = id => selectTable(id)
  const selectGroup = id => { go({ group: id, table: null }) }
  const close = () => { setSheet(false); go({ table: null, group: null }) }

  // The panes take what is left of the screen under the page's header; each
  // scrolls on its own. On a phone the page scrolls instead.
  useLayoutEffect(() => {
    const el = root.current
    if (!el) return undefined
    const measure = () => {
      setMode(modeOf(el.clientWidth))
      setTop(el.getBoundingClientRect().top + window.scrollY)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  // "/" finds a table, from anywhere on the page but a field.
  useEffect(() => {
    const onKey = e => {
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return
      const tag = e.target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) return
      e.preventDefault()
      filterRef.current?.focus()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const t = schema.tables.find(x => x.id === table)
  const inspecting = !!(t || group)
  const body = t
    ? <TableInspector key={t.id} t={t} edges={schema.edges} measures={measuresOf?.(t)}
                      onSelect={selectTable} onClose={close} />
    : group ? (
      <div className="dbx-insp__group">
        <button type="button" className="dbx-close dbx-close--float" onClick={close} aria-label="Close the group" title="Back to the summary">×</button>
        {groupView(group, selectTable)}
      </div>
    ) : summary
  const tree = (
    <Tree schema={schema} infoOf={infoOf} selected={{ table, group: groupId }}
          onTable={id => selectTable(id === table ? null : id)} onColumn={selectColumn}
          onGroup={groupView ? id => selectGroup(id === groupId ? null : id) : null}
          query={query} setQuery={setQuery} filterRef={filterRef} />
  )
  const shown = mode === 'wide' || mode === 'phone' || inspecting || sheet || !!summaryOpen

  return (
    <div ref={root} className={`dbx dbx--${mode}`} aria-label={label}
         style={mode === 'phone' ? undefined : { height: `max(560px, calc(100dvh - ${Math.round(top)}px - 24px))` }}>
      <Markers />
      {mode === 'phone' ? (
        <details className="dbx__drop">
          <summary>{t ? <><KindGlyph role={t.role} view={infoOf(t)?.view} /> <code>{t.name}</code></> : `Tables (${schema.tables.length})`}</summary>
          {tree}
        </details>
      ) : <div className="dbx__tree">{tree}</div>}
      <div className="dbx__canvas">
        <ReactFlowProvider>
          <Canvas schema={schema} infoOf={infoOf} selected={table} onSelect={selectTable} storeKey={storeKey} emptyNote={emptyNote} />
        </ReactFlowProvider>
        {mode === 'mid' && !shown && (
          <div className="dbx__details"><Btn size="sm" variant="outline" onClick={() => setSheet(true)}>Details</Btn></div>
        )}
      </div>
      {shown && (
        <aside className={`dbx__insp${mode === 'mid' ? ' dbx__insp--sheet' : ''}`} aria-label="Inspector">
          {mode === 'mid' && !inspecting && (
            <button type="button" className="dbx-close dbx-close--float" onClick={() => { setSheet(false); if (summaryOpen) go({ view: null }) }} aria-label="Close the details">×</button>
          )}
          {body}
        </aside>
      )}
    </div>
  )
}

export { Section as InspectorSection }
