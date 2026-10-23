import { cloneElement, Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { ReactFlow, Background, Controls, MiniMap, Handle, Position, MarkerType } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { StorageLine, sourceKind } from '../components/Storage'
import { buildModelGraph, measureDefinition } from '../components/modelGraph'
import { dimensionLabel, encodeQuery, humanise, inSentence } from '../ask'
import {
  useModels, useModel, useTable, useDesk, useReports, usePipelines,
} from '../api'
import { PageHeader } from '../components/Scope'
import CodeView from '../components/CodeView'
import DataGrid from '../components/DataGrid'
import { askPath, dataPath, pipelineBelongsToModel, reportBelongsToModel, tablePath } from '../nav'
import {
  Card, Badge, Chip, Empty, Segmented, SkeletonList, SkeletonCard, useNarrow,
} from '../components/Shared'

// ── One table's rows, inline ──────────────────────────────────────────────────

// A model table's rows, opened in place under its row (or under the diagram):
// the one grid, read through the table API by the table's SOURCE name (a model
// may call a stored table something else), keeping its cut to itself so the
// page's own address stays the model's view. Its page has the rest.
function InlineTable({ t }) {
  const columns = (t.columns || []).map(c => ({ name: c.name, type: c.dtype }))
  return (
    <div className="mtables__grid fade-in">
      <DataGrid source={t.connector} table={t.source} columns={columns.length ? columns : undefined}
                label={`Rows of ${t.name}`} />
      <p className="mtables__page"><Link to={tablePath(t.connector, t.source)}>Open table page →</Link></p>
    </div>
  )
}

// ── ERD Diagram ──────────────────────────────────────────────────────────────

const ROLE_STYLES = {
  dimension: { header: 'var(--surface-2)',      accent: 'var(--role-dimension)', label: 'Dimension' },
  fact:      { header: 'var(--surface-2)', accent: 'var(--role-fact)', label: 'Fact' },
  bridge:    { header: 'var(--surface-2)',    accent: 'var(--role-bridge)', label: 'Bridge' },
  table:     { header: 'var(--surface-2)',      accent: 'var(--role-table)', label: 'Table' },
}

// PK / FK / Σ: a text badge, not an icon, so it reads in any theme and print.
const FLAG_STYLES = {
  PK:  { color: 'var(--op-gold-tx)', border: 'var(--op-gold-br)', title: 'Primary key: the dimension\'s join key' },
  FK:  { color: 'var(--accent-text)', border: 'var(--blue-br)',   title: 'Foreign key: joins to a dimension' },
  'Σ': { color: 'var(--role-fact)',   border: 'color-mix(in srgb, var(--role-fact) 25%, transparent)', title: 'A measure column on the fact' },
}

const MONO = 'var(--font-mono)'
const HANDLE = { width: 10, height: 10, border: '2px solid #fff' }

function ERDTableNode({ data }) {
  const rs = ROLE_STYLES[data.role] || ROLE_STYLES.table
  return (
    <div style={{
      background: 'var(--surface)', border: `1.5px solid color-mix(in srgb, ${rs.accent} 22%, transparent)`,
      borderRadius: 10, width: 300, overflow: 'hidden',
      boxShadow: data.selected ? `0 0 0 2px ${rs.accent}` : 'var(--shadow-sm)',
      fontSize: 12, cursor: 'pointer',
    }}>
      <Handle id="in-l" type="target" position={Position.Left} style={{ ...HANDLE, background: rs.accent, left: -6 }} />
      <Handle id="out-l" type="source" position={Position.Left} style={{ ...HANDLE, background: rs.accent, left: -6 }} />

      <div style={{ background: rs.header, padding: '10px 14px', borderBottom: `1px solid color-mix(in srgb, ${rs.accent} 15%, transparent)`, height: 62, boxSizing: 'border-box' }}>
        <div style={{ fontWeight: 700, fontSize: 12.5, color: 'var(--text)', letterSpacing: .15, marginBottom: 4 }}>
          {data.label}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontSize: 10, fontWeight: 600,
            padding: '1px 7px', borderRadius: 20,
            background: 'var(--surface)', color: rs.accent, border: `1px solid color-mix(in srgb, ${rs.accent} 23%, transparent)`,
          }}>{rs.label}</span>
          {data.connector && <span style={{ fontSize: 9.5, color: 'var(--muted)' }}>{data.connector}</span>}
        </div>
      </div>

      <div style={{ padding: '0 0 12px' }}>
        {data.columns.length === 0 && (
          <div style={{ padding: '3px 14px', height: 22, color: 'var(--muted)', fontStyle: 'italic', fontSize: 11 }}>columns not available</div>
        )}
        {data.columns.map(c => {
          const fs = FLAG_STYLES[c.flag]
          return (
            <div key={c.name} style={{ height: 22, boxSizing: 'border-box', padding: '0 14px', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span title={fs?.title} style={{
                width: 22, textAlign: 'center', fontSize: 8.5, fontWeight: 700, letterSpacing: .3,
                color: fs?.color, border: fs ? `1px solid ${fs.border}` : '1px solid transparent',
                borderRadius: 4, lineHeight: '14px',
              }}>{c.flag}</span>
              <span style={{
                fontFamily: MONO, fontSize: 11, flex: 1, minWidth: 0,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                color: c.flag ? 'var(--text)' : 'var(--text-2)', fontWeight: c.flag ? 600 : 400,
              }}>{c.name}</span>
              <span style={{ fontSize: 9.5, color: 'var(--muted)', fontFamily: MONO }}>{c.dtype || ''}</span>
            </div>
          )
        })}
        {data.hidden > 0 && (
          <div style={{ height: 22, padding: '0 14px 0 44px', display: 'flex', alignItems: 'center', fontSize: 10.5, color: 'var(--muted)' }}>
            + {data.hidden} more column{data.hidden !== 1 ? 's' : ''}
          </div>
        )}
      </div>

      <Handle id="in-r" type="target" position={Position.Right} style={{ ...HANDLE, background: rs.accent, right: -6 }} />
      <Handle id="out-r" type="source" position={Position.Right} style={{ ...HANDLE, background: rs.accent, right: -6 }} />
    </div>
  )
}

const NODE_TYPES = { erdTable: ERDTableNode }

function edgeLabel(e) {
  const keys = e.fromKey === e.toKey ? e.fromKey : `${e.fromKey} → ${e.toKey}`
  return e.cardinality === 'many-to-one' ? `N : 1  ·  ${keys}` : keys
}

function ERDDiagram({ data, selected, onSelect }) {
  const { nodes, edges, height } = useMemo(() => {
    const g = buildModelGraph(data)
    const x = Object.fromEntries(g.nodes.map(n => [n.name, n.position.x]))
    return {
      height: g.height,
      nodes: g.nodes.map(n => ({
        id: n.name, type: 'erdTable', position: n.position,
        data: { label: n.name, connector: n.connector, role: n.role, columns: n.columns, hidden: n.hidden },
      })),
      edges: g.edges.map(e => ({
        id: e.id, source: e.from, target: e.to, type: 'smoothstep',
        // Leave on the side that faces the other table, so a join runs straight
        // across instead of looping round the outside.
        sourceHandle: x[e.from] > x[e.to] ? 'out-l' : 'out-r',
        targetHandle: x[e.from] > x[e.to] ? 'in-r' : 'in-l',
        style: { stroke: 'var(--muted)', strokeWidth: 1.25 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#8a8a8a', width: 12, height: 12 },
        label: edgeLabel(e),
        labelStyle: { fontSize: 9, fill: 'var(--muted)', fontFamily: MONO },
        labelBgStyle: { fill: 'var(--surface)', fillOpacity: 0.92 },
      })),
    }
  }, [data])
  const shown = useMemo(
    () => nodes.map(n => ({ ...n, data: { ...n.data, selected: n.id === selected } })),
    [nodes, selected])

  return (
    // Tall enough to read a stack of facts, capped so the page still scrolls.
    <div className="erd-wrapper" style={{ height: Math.min(760, Math.max(320, height * 0.8)) }}>
      <ReactFlow
        edgesFocusable={false}
        nodes={shown}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, n) => onSelect(n.id)}
        // fitView on the first frame frames a panel that is still animating in
        // (zero size); frame it again once it has settled.
        onInit={flow => setTimeout(() => flow.fitView({ padding: 0.12 }), 350)}
      >
        <Background color="var(--flow-dots)" gap={30} size={1} />
        <Controls style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6 }} />
        {nodes.length > 10 && (
          <MiniMap
            nodeColor={n => ROLE_STYLES[n.data?.role]?.accent || '#64748b'}
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6 }}
            maskColor="rgba(228,233,240,.6)"
          />
        )}
      </ReactFlow>
    </div>
  )
}

// ── ERD legend ────────────────────────────────────────────────────────────────

function ERDLegend() {
  const roles = [
    { role: 'dimension', label: 'Dimension' },
    { role: 'fact',      label: 'Fact' },
    { role: 'bridge',    label: 'Both a fact and a dimension' },
    { role: 'table',     label: 'Table with no joins' },
  ]
  const flags = [
    ['PK', 'join key on a dimension'], ['FK', 'foreign key on a fact'], ['Σ', 'measure column'],
  ]
  return (
    <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 14, alignItems: 'center' }}>
      {roles.map(({ role, label }) => (
        <span key={role} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--muted)' }}>
          <span style={{ width: 10, height: 10, borderRadius: 3, display: 'inline-block', background: ROLE_STYLES[role].accent, opacity: .8 }} />
          {label}
        </span>
      ))}
      <span style={{ width: 1, height: 14, background: 'var(--border)' }} />
      {flags.map(([f, label]) => (
        <span key={f} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--muted)' }}>
          <span style={{
            fontSize: 8.5, fontWeight: 700, padding: '0 4px', borderRadius: 4, lineHeight: '14px',
            color: FLAG_STYLES[f].color, border: `1px solid ${FLAG_STYLES[f].border}`,
          }}>{f}</span>
          {label}
        </span>
      ))}
    </div>
  )
}

// ── Measures ──────────────────────────────────────────────────────────────────

// A format as what it does to a number (the artifact's own named formats,
// tracebi.js applyNamedFormat), its token in the title. Anything else is shown
// as written.
const FORMAT_SAMPLES = {
  currency: '$1,234.00', currency0: '$1,234', currency_compact: '$1.2K', compact: '1.2K',
  comma: '1,234', decimal: '1,234.00', percent: '12.3%',
}

const askMeasure = (model, name) =>
  `${askPath(model)}&q=${encodeURIComponent(encodeQuery({ measures: [name], dimensions: [], filters: {} }))}`

// The model's named measures are its semantic contract: every report and
// query asks for them by name, so they are defined once, here. A row the
// address names (?measure=, as ⌘K links one) is scrolled to and marked.
function MeasuresTable({ model, measures, target }) {
  const targetRow = useRef(null)
  useEffect(() => { targetRow.current?.scrollIntoView({ block: 'center' }) }, [target])
  if (!measures.length) return <Empty message="This model declares no named measures." />
  return (
    <table className="tb-list mlist">
      <thead><tr><th>Measure</th><th>Defined as</th><th>Shown as</th><th><span className="sr-only">Ask</span></th></tr></thead>
      <tbody>
        {measures.map(m => {
          const label = m.label || m.description || humanise(m.name)
          const here = m.name === target
          return (
            <tr key={m.name} ref={here ? targetRow : undefined} className={here ? 'mlist__target' : undefined}
                data-measure={m.name}>
              <td>
                <span className="mlist__label">{label}</span>
                <code className="mlist__id">{m.name}</code>
                <span className="mlist__def-inline">{measureDefinition(m)}</span>
              </td>
              <td className="mlist__def">{measureDefinition(m)}</td>
              <td className="mlist__fmt" title={m.format || undefined}>
                {m.format && (FORMAT_SAMPLES[m.format] || <code>{m.format}</code>)}
              </td>
              <td><Link to={askMeasure(model, m.name)} aria-label={`Ask about ${label}`}>Ask</Link></td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// ── Model Detail ──────────────────────────────────────────────────────────────

// A model's tables point at connectors; a connector says where the data is.
// The model file (Python) only declares meaning: which table is a fact, what
// joins to what, what a measure is. Nothing is stored in it.
// TraceBi's own tables (the state store's) are never listed as data, even
// when a model names one; the server leaves them out and counts them.
function FrameworkHidden({ n }) {
  if (!(n > 0)) return null
  return (
    <p className="wb-meta" title="TraceBi's own tables (tracebi_*, alembic_version) are not shown as data.">
      {n} framework {n === 1 ? 'table' : 'tables'} hidden
    </p>
  )
}

function ModelStorage({ details, tables, hidden }) {
  if (!details.length) return <Empty message="This model declares no connector, so its tables have no data behind them." />
  return (
    <div>
      <p style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.6, margin: '0 0 14px', maxWidth: '72ch' }}>
        The model file only says what the data <em>means</em>. Each table below reads from a
        connector, and the connector says where the data is kept.
      </p>
      <div style={{ display: 'grid', gap: 12 }}>
        {details.map(c => {
          const served = tables.filter(t => t.connector === c.name)
          return (
            <div key={c.name} style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '12px 14px', background: 'var(--surface)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                <strong style={{ fontSize: 13 }}>{c.name}</strong>
                <Badge variant="gray" style={{ textTransform: 'none' }} title={c.type}>{sourceKind(c)}</Badge>
              </div>
              <div style={{ marginBottom: 10 }}><StorageLine storage={c.storage} /></div>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 6 }}>
                Tables it serves ({served.length})
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {served.map(t => (
                  <Badge key={t.name} variant="gray" title={t.source !== t.name ? `reads ${t.source}` : undefined}>
                    {t.name}{t.source !== t.name ? ` ← ${t.source}` : ''}
                  </Badge>
                ))}
              </div>
            </div>
          )
        })}
      </div>
      <FrameworkHidden n={hidden} />
    </div>
  )
}

// What the desk says of a warehouse table, in plain words.
const SINK_WORDS = { stale: 'changed since its checks last passed', no_contract: 'no checks declared' }

// The views, in the address as ?view= (lower case), so a reload keeps the one
// you are on and Back steps back through them.
const VIEWS = [
  ['diagram', 'Diagram'], ['tables', 'Tables'], ['measures', 'Measures'],
  ['relationships', 'Relationships'], ['storage', 'Storage'], ['code', 'Code'],
]

// A table's role in the star, as the diagram's legend says it.
const ROLE_WORDS = { fact: 'Fact', dimension: 'Dimension', bridge: 'Fact and dimension', table: 'No joins' }

/**
 * The Tables view: where the tables are stored, said once, then one row per
 * table (its role, rows, columns, joins). A row opens its rows in place, below
 * that row; the address keeps which (?table=).
 */
function TablesView({ data, graph, open, onOpen }) {
  const storageOf = new Map((data.connector_details || []).map(c => [c.name, c.storage]))
  const connectors = [...new Set(data.tables.map(t => t.connector))]
  const roleOf = Object.fromEntries(graph.nodes.map(n => [n.name, n.role]))
  const joins = name => graph.edges.filter(e => e.from === name || e.to === name).length
  return (
    <div>
      {connectors.length > 0 && (
        <p className="mtables__where">
          Stored in {connectors.map((c, i) => (
            <Fragment key={c}>
              {i > 0 && ', '}<strong>{c}</strong>
              {storageOf.get(c)?.where && <> · <code>{storageOf.get(c).where}</code></>}
            </Fragment>
          ))}
        </p>
      )}
      <table className="tb-list mtables">
        <colgroup><col /><col className="mtables__n" /><col className="mtables__n mtables__cols" /><col className="mtables__n" /></colgroup>
        <thead><tr><th>Table</th><th>Rows</th><th className="mtables__cols">Columns</th><th>Joins</th></tr></thead>
        <tbody>
          {data.tables.map(t => (
            <TableRow key={t.name} t={t} role={roleOf[t.name]} joins={joins(t.name)}
                      many={connectors.length > 1} open={open === t.name}
                      onOpen={() => onOpen(open === t.name ? null : t.name)} />
          ))}
        </tbody>
      </table>
      <FrameworkHidden n={data.hidden_framework_tables} />
    </div>
  )
}

// One table's row. Its row count is the table API's (exact for the warehouse;
// "≈" marks a catalog estimate; "—" when the source cannot be reached).
function TableRow({ t, role, joins, many, open, onOpen }) {
  const { data: info } = useTable(t.connector, t.source)
  const rows = info && info.connected !== false ? info.rows : null
  const opened = useRef(null)
  // Opened from the address (a link, a reload): bring it into view once.
  useEffect(() => { if (open) opened.current?.scrollIntoView({ block: 'nearest' }) }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <>
      <tr ref={opened} className={`mtables__row${open ? ' mtables__row--open' : ''}`} data-table={t.name}>
        <td>
          <button type="button" className="mtables__name" aria-expanded={open} onClick={onOpen}>
            <span className="mtables__chev" aria-hidden="true">›</span>
            <code>{t.name}</code>
          </button>
          <span className="mtables__sub">
            <Chip>{ROLE_WORDS[role] || ROLE_WORDS.table}</Chip>
            {t.source !== t.name && <span>stored as <code>{t.source}</code></span>}
            {many && <span>in {t.connector}</span>}
          </span>
        </td>
        <td className="mtables__num">
          {!info ? '' : rows == null ? '—' : `${info.rows_exact === false ? '≈' : ''}${Number(rows).toLocaleString('en-US')}`}
        </td>
        <td className="mtables__num mtables__cols">{(t.columns || []).length || '—'}</td>
        <td className="mtables__num">{joins}</td>
      </tr>
      {open && (
        <tr className="mtables__open"><td colSpan={4}><InlineTable t={t} /></td></tr>
      )}
    </>
  )
}

// Whether a row that scrolls sideways has more past its right edge: the cue
// (a chevron at that edge) that it scrolls at all. *ready* re-measures once the row exists.
function useMoreToTheRight(ref, ready) {
  const [more, setMore] = useState(false)
  useEffect(() => {
    const el = ref.current?.firstElementChild   // the views' row, inside its wrap
    if (!el) return undefined
    const check = () => setMore(el.scrollLeft + el.clientWidth < el.scrollWidth - 1)
    check()
    el.addEventListener('scroll', check, { passive: true })
    const resized = new ResizeObserver(check)
    resized.observe(el)
    return () => { el.removeEventListener('scroll', check); resized.disconnect() }
  }, [ref, ready])
  return more
}

// On a phone the views take the row, and the page's action (Edit as a draft)
// goes into a "…" menu, where it keeps its words.
function MoreMenu({ children }) {
  const [open, setOpen] = useState(false)
  const root = useRef(null)
  const onBlur = e => { if (!root.current?.contains(e.relatedTarget)) setOpen(false) }
  return (
    <div ref={root} className="mdetail__action rp__pop rp__pop--end" onBlur={onBlur}
         onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }}>
      <button type="button" className="cmd" aria-label="More" aria-haspopup="menu" aria-expanded={open}
              onClick={() => setOpen(o => !o)}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          <circle cx="5" cy="12" r="1.2" /><circle cx="12" cy="12" r="1.2" /><circle cx="19" cy="12" r="1.2" />
        </svg>
      </button>
      {open && (
        <div className="rp__menu mdetail__menu" role="menu">
          {cloneElement(children, { className: 'rp__item', role: 'menuitem' })}
        </div>
      )}
    </div>
  )
}

/** *action*: what sits at the right of the views (the page's Edit as a draft). */
export function ModelDetail({ name, action }) {
  const { data, isLoading } = useModel(name)
  const { data: desk } = useDesk()
  // The view, the opened table and the named measure are the address's
  // (?view=, ?table=, ?measure=): each change is a step Back undoes.
  const [params, setParams] = useSearchParams()
  const asked = params.get('view')
  const view = VIEWS.some(([v]) => v === asked) ? asked : null
  const measure = params.get('measure')
  const go = patch => setParams(p => {
    const next = new URLSearchParams(p)
    Object.entries(patch).forEach(([k, v]) => (v == null ? next.delete(k) : next.set(k, v)))
    return next
  })
  // A diagram fitted to a phone shrinks every table past reading; there the
  // Tables view (the diagram's list form) opens first.
  const phone = useNarrow('(max-width: 720px)')
  const viewsRef = useRef(null)
  const more = useMoreToTheRight(viewsRef, !!data)

  if (!name) return (
    <Card>
      <Empty
        message="Select a model to read its file, grain, measures, tables, and connectors."
      />
    </Card>
  )
  if (isLoading) return <SkeletonCard />
  if (!data) return null

  const graph = buildModelGraph(data)
  // A model with joins opens on its diagram; one with none has nothing to draw.
  const active = view || (graph.edges.length && !phone ? 'diagram' : 'tables')
  const openTable = data.tables.find(t => t.name === params.get('table')) || null
  const openOn = table => go({ view: active, table, measure: null })
  // The grain in the words a report uses for each attribute; the identifiers in the title.
  const grainRefs = (data.dimensions || []).flatMap(d =>
    (d.attributes || []).map(attr => `${d.name}.${attr}`))
  const grain = grainRefs.map(ref => inSentence(dimensionLabel(data, ref))).join(' · ')
  const sinks = desk?.sinks || []

  return (
    <Card className="fade-in">
      <div className="mdetail__head">
        <div ref={viewsRef} className="mdetail__viewwrap">
          <Segmented className="mdetail__views" options={VIEWS} value={active} label="What to show of the model"
                     onChange={v => go({ view: v, table: null, measure: null })} />
          {more && <span className="mdetail__more" aria-hidden="true">›</span>}
        </div>
        {action && (phone ? <MoreMenu>{action}</MoreMenu> : <div className="mdetail__action">{action}</div>)}
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 16, lineHeight: 1.6 }}>
        {grain && <div title={grainRefs.join(', ')}>Grain: {grain}</div>}
        {(data.owners || []).length > 0 && (
          <div>Owners: {data.owners.join(', ')} (only they or an admin publish changes to it)</div>
        )}
        {desk?.warehouse && sinks.length === 0 && <div>Its tables satisfied their checks when they were last written.</div>}
        {sinks.length > 0 && (
          <div>
            {sinks.map(s => `${s.table}: ${SINK_WORDS[s.status] || s.status}`).join(' · ')}
          </div>
        )}
      </div>

      {active === 'tables' && (
        <TablesView data={data} graph={graph} open={openTable?.name} onOpen={openOn} />
      )}

      {active === 'relationships' && (
        graph.edges.length === 0
          ? <Empty message="No joins declared. Give a fact its foreign_keys:, or list one under relationships:." />
          : (
            <div style={{ overflowX: 'auto' }}>
              <table className="tb-list">
                <thead><tr><th>From</th><th>To</th><th>Keys</th><th>Shape</th><th>Declared under</th></tr></thead>
                <tbody>
                  {graph.edges.map(e => (
                    <tr key={e.id}>
                      <td><code>{e.from}</code></td>
                      <td><code>{e.to}</code></td>
                      <td style={{ color: 'var(--muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                        {e.fromKey} = {e.toKey}
                      </td>
                      <td><Chip>{e.cardinality === 'many-to-one' ? 'Many to one' : e.how ? `${e.how[0].toUpperCase()}${e.how.slice(1)} join` : 'Join'}</Chip></td>
                      <td style={{ color: 'var(--muted)', fontSize: 12 }}>
                        {e.declared ? <><code>foreign_keys:</code> on the fact</> : <code>relationships:</code>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
      )}

      {active === 'measures' && <MeasuresTable model={name} measures={data.measures || []} target={measure} />}

      {active === 'storage' && <ModelStorage details={data.connector_details || []} tables={data.tables} hidden={data.hidden_framework_tables} />}
      {active === 'code' && <CodeView kind="models" name={name} />}

      {active === 'diagram' && (
        <div className="fade-in">
          <ERDLegend />
          <ERDDiagram data={data} selected={openTable?.name}
                      onSelect={t => openOn(openTable?.name === t ? null : t)} />
          <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
            Click a table to see its rows · drag to rearrange · scroll to zoom · each join runs from a fact to the dimension it references
          </p>
          {openTable && (
            <div className="mdetail__open">
              <h3 className="mdetail__open-name"><code>{openTable.name}</code></h3>
              <InlineTable t={openTable} />
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

// ── All models: pick one ─────────────────────────────────────────────────────

/**
 * The models, each opening *pageKey* for itself: Ask with it picked ('ask'),
 * or its page on Data ('data'; Data's own list is pages/Data.jsx).
 */
export default function Models({ pageKey = 'data' }) {
  const { data, isLoading } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const [params] = useSearchParams()
  const open = pageKey === 'ask' ? askPath : dataPath
  // Old links: /models?m=<model>, /explore?model=<model>.
  const legacy = params.get('m') || params.get('model')
  if (legacy) return <Navigate to={open(legacy)} replace />

  const models = data || []
  const reportCount = name => (reports || []).filter(r => reportBelongsToModel(r, name)).length
  const refreshes = name => (pipelines || []).some(p => pipelineBelongsToModel(p, name))

  return (
    <>
      <PageHeader pageKey={pageKey} model=""
        sub={pageKey === 'ask' ? 'Ask asks one model at a time. Pick one.' : undefined} />
      {isLoading ? <SkeletonList /> : models.length === 0 ? (
        <Empty message="No models yet. Create one with tracebi new-model, in models/." />
      ) : (
        <div className="model-cards">
          {models.map((m, i) => {
            const n = reportCount(m.name)
            return (
              <Link key={m.name} to={open(m.name)} className="model-card rise" style={{ '--i': i }}>
                <span className="model-card__name">{m.label || m.name}</span>
                <span className="model-card__shape">
                  {m.facts
                    ? `${m.facts.length} fact${m.facts.length !== 1 ? 's' : ''} · ${m.dimensions.length} dimension${m.dimensions.length !== 1 ? 's' : ''} · ${m.measures.length} measures`
                    : `${m.tables.length} tables`}
                </span>
                <span className="model-card__facts">
                  <span>{n} report{n !== 1 ? 's' : ''}</span>
                  <span>{refreshes(m.name) ? 'Has a refresh pipeline' : 'No refresh pipeline'}</span>
                </span>
              </Link>
            )
          })}
        </div>
      )}
    </>
  )
}
