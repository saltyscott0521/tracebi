import { useState, useMemo } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { ReactFlow, Background, Controls, MiniMap, Handle, Position, MarkerType } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { StorageLine, sourceKind } from '../components/Storage'
import { buildModelGraph, measureDefinition, MEASURE_KINDS } from '../components/modelGraph'
import { dimensionLabel, inSentence } from '../ask'
import {
  useModels, useModel, useTablePreview, useDesk, useReports, usePipelines, tableCsvUrl,
} from '../api'
import { PageHeader } from '../components/Scope'
import CodeView from '../components/CodeView'
import { askPath, dataPath, pipelineBelongsToModel, reportBelongsToModel } from '../nav'
import {
  Card, Badge, Spinner, Empty, ExportCsv, SkeletonList, SkeletonCard, useNarrow,
} from '../components/Shared'

// ── Table Preview ─────────────────────────────────────────────────────────────

function TablePreview({ modelName, tableName }) {
  const { data, isLoading, error } = useTablePreview(modelName, tableName)
  if (isLoading) return (
    <div style={{ padding: 20, display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
      <Spinner size={14} /> Loading preview…
    </div>
  )
  if (error) return <div style={{ padding: 16, color: 'var(--red-text)', fontSize: 13 }}>{error.message}</div>
  if (!data) return null
  const showingAll = data.total_rows == null || data.rows >= data.total_rows
  return (
    <div className="fade-in">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <Badge variant="gray">
          {showingAll
            ? `${data.rows} rows`
            : `first ${data.rows} of ${data.total_rows.toLocaleString()} rows`}
        </Badge>
        <Badge variant="gray">{data.columns.length} cols</Badge>
        <span style={{ flex: 1 }} />
        <ExportCsv href={tableCsvUrl(modelName, tableName)} title={showingAll ? undefined : 'Every row of the table, not only these'} />
      </div>
      <div style={{ overflowX: 'auto', borderRadius: 6, border: '1px solid var(--border)' }}>
        <table>
          <thead>
            <tr>
              {data.columns.map(c => (
                <th key={c}>
                  {c}
                  {data.dtypes?.[c] && (
                    <span style={{
                      display: 'block', fontSize: 9.5, fontWeight: 400,
                      color: 'var(--muted)', textTransform: 'none', letterSpacing: 0,
                      fontFamily: 'var(--font-mono)',
                    }}>{data.dtypes[c]}</span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.data.map((row, i) => (
              <tr key={i}>
                {data.columns.map(c => (
                  <td key={c}>
                    {row[c] === null
                      ? <span style={{ color: 'var(--muted)', fontStyle: 'italic' }}>null</span>
                      : String(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
              <span style={{ fontSize: 9.5, color: 'var(--muted)', fontFamily: MONO }}>{(c.dtype || '').toLowerCase()}</span>
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

// The model's named measures are its semantic contract: every report and
// query asks for them by name, so they are defined once, here.
function MeasuresTable({ measures }) {
  if (!measures.length) return <Empty message="This model declares no named measures." />
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="tb-list">
        <thead><tr><th>Measure</th><th>What it is</th><th>Defined as</th><th>Format</th></tr></thead>
        <tbody>
          {measures.map(m => (
            <tr key={m.name}>
              <td>
                <code>{m.name}</code>
                {m.description && <div style={{ fontSize: 11.5, color: 'var(--muted)', marginTop: 2 }}>{m.description}</div>}
              </td>
              <td><Badge variant="gray">{MEASURE_KINDS[m.kind] || m.kind}</Badge></td>
              <td style={{ fontFamily: MONO, fontSize: 11.5, color: 'var(--text-2)' }}>{measureDefinition(m)}</td>
              <td style={{ color: 'var(--muted)', fontSize: 12 }}>{m.format || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Model Detail ──────────────────────────────────────────────────────────────

// A model's tables point at connectors; a connector says where the data is.
// The model file (Python) only declares meaning: which table is a fact, what
// joins to what, what a measure is. Nothing is stored in it.
function ModelStorage({ details, tables }) {
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
    </div>
  )
}

// What the desk says of a warehouse table, in plain words.
const SINK_WORDS = { stale: 'changed since its checks last passed', no_contract: 'no checks declared' }

const VIEWS = ['Diagram', 'Tables', 'Measures', 'Relationships', 'Storage', 'Code']

/** *action*: what sits at the right of the views (the page's Edit as a draft). */
export function ModelDetail({ name, action }) {
  const { data, isLoading } = useModel(name)
  const { data: desk } = useDesk()
  const [tab, setTab] = useState(null)      // null: the model's own default tab
  const [previewTable, setPreviewTable] = useState(null)
  // A diagram fitted to a phone shrinks every table past reading; there the
  // Tables view (the diagram's list form) opens first.
  const phone = useNarrow('(max-width: 720px)')

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
  const storageOf = new Map((data.connector_details || []).map(c => [c.name, c.storage]))
  // A model with joins opens on its diagram; one with none has nothing to draw.
  const active = tab || (graph.edges.length && !phone ? 'Diagram' : 'Tables')
  // The grain in the words a report uses for each attribute; the identifiers in the title.
  const grainRefs = (data.dimensions || []).flatMap(d =>
    (d.attributes || []).map(attr => `${d.name}.${attr}`))
  const grain = grainRefs.map(ref => inSentence(dimensionLabel(data, ref))).join(' · ')
  const sinks = desk?.sinks || []

  return (
    <Card className="fade-in">
      <div className="mdetail__head">
        <div className="seg mdetail__views" role="group" aria-label="What to show of the model">
          {VIEWS.map(v => (
            <button key={v} type="button" aria-pressed={active === v}
                    onClick={() => { setTab(v); setPreviewTable(null) }}>{v}</button>
          ))}
        </div>
        {action && <div className="mdetail__action">{action}</div>}
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

      {active === 'Tables' && (
        <div>
          <div style={{ overflowX: 'auto' }}>
            <table className="tb-list">
              <thead><tr><th>Table</th><th>Stored in</th><th>Source table</th><th></th></tr></thead>
              <tbody>
                {data.tables.map(t => (
                  <tr key={t.name}>
                    <td><code>{t.name}</code></td>
                    <td style={{ color: 'var(--text-2)' }}>
                      {t.connector}
                      <div style={{ fontSize: 11, color: 'var(--muted)' }}>{storageOf.get(t.connector)?.where}</div>
                    </td>
                    <td style={{ color: 'var(--muted)' }}><code>{t.source}</code></td>
                    <td>
                      <button onClick={() => setPreviewTable(previewTable === t.name ? null : t.name)} style={{
                        padding: '3px 10px', fontSize: 11, fontWeight: 600, borderRadius: 4,
                        background: 'var(--blue-lt)', color: 'var(--accent-text)',
                        border: '1px solid var(--blue-br)', cursor: 'pointer',
                        transition: 'background var(--t)',
                      }}>
                        {previewTable === t.name ? 'Hide' : 'Preview'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {previewTable && (
            <div style={{ marginTop: 20, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
                Preview: <strong style={{ color: 'var(--text)' }}>{previewTable}</strong>
              </div>
              <TablePreview modelName={name} tableName={previewTable} />
            </div>
          )}
        </div>
      )}

      {active === 'Relationships' && (
        graph.edges.length === 0
          ? <Empty message="No joins declared. Give a fact its foreign_keys, or call add_relationship." />
          : (
            <div style={{ overflowX: 'auto' }}>
              <table className="tb-list">
                <thead><tr><th>From</th><th>To</th><th>Keys</th><th>Shape</th><th>Declared with</th></tr></thead>
                <tbody>
                  {graph.edges.map(e => (
                    <tr key={e.id}>
                      <td><code>{e.from}</code></td>
                      <td><code>{e.to}</code></td>
                      <td style={{ color: 'var(--muted)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>
                        {e.fromKey} = {e.toKey}
                      </td>
                      <td><Badge variant="gray">{e.cardinality === 'many-to-one' ? 'many to one' : (e.how || 'join')}</Badge></td>
                      <td style={{ color: 'var(--muted)', fontSize: 12 }}>{e.declared ? 'add_fact(foreign_keys=…)' : 'add_relationship'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
      )}

      {active === 'Measures' && <MeasuresTable measures={data.measures || []} />}

      {active === 'Storage' && <ModelStorage details={data.connector_details || []} tables={data.tables} />}
      {active === 'Code' && <CodeView kind="models" name={name} />}

      {active === 'Diagram' && (
        <div className="fade-in">
          <ERDLegend />
          <ERDDiagram data={data} selected={previewTable} onSelect={t => setPreviewTable(previewTable === t ? null : t)} />
          <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
            Click a table to preview its rows · drag to rearrange · scroll to zoom · each join runs from a fact to the dimension it references
          </p>
          {previewTable && (
            <div style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
                Preview: <strong style={{ color: 'var(--text)' }}>{previewTable}</strong>
              </div>
              <TablePreview modelName={name} tableName={previewTable} />
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
