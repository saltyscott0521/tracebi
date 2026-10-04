import { useState, useMemo } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { ReactFlow, Background, Controls, MiniMap, Handle, Position, MarkerType } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { StorageLine, KIND_LABEL } from '../components/Storage'
import { buildModelGraph, measureDefinition, MEASURE_KINDS, summary } from '../components/modelGraph'
import {
  useModels, useModel, useTablePreview, useDesk, useReports, usePipelines, tableCsvUrl,
} from '../api'
import { PageHeader } from '../components/Scope'
import { pagePath, pipelineBelongsToModel, reportBelongsToModel } from '../nav'
import {
  Card, Badge, Spinner, Empty, Tabs, SkeletonList, SkeletonCard,
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
        <a href={tableCsvUrl(modelName, tableName)} download className="dl-link">
          ↓ CSV {showingAll ? '' : '(all rows)'}
        </a>
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
                      fontFamily: 'Cascadia Code, Fira Code, monospace',
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
  dimension: { header: 'var(--op-landing-bg)',      accent: '#2563eb', label: 'Dimension' },
  fact:      { header: 'var(--op-manipulation-bg)', accent: '#6d28d9', label: 'Fact' },
  bridge:    { header: 'var(--op-transform-bg)',    accent: '#b45309', label: 'Bridge' },
  table:     { header: 'var(--op-default-bg)',      accent: '#64748b', label: 'Table' },
}

// PK / FK / Σ: a text badge, not an icon, so it reads in any theme and print.
const FLAG_STYLES = {
  PK:  { color: 'var(--op-gold-tx)', border: 'var(--op-gold-br)', title: 'Primary key: the dimension\'s join key' },
  FK:  { color: 'var(--accent-text)', border: 'var(--blue-br)',   title: 'Foreign key: joins to a dimension' },
  'Σ': { color: '#6d28d9',            border: '#6d28d940',        title: 'A measure column on the fact' },
}

const MONO = 'Cascadia Code, Fira Code, monospace'
const HANDLE = { width: 10, height: 10, border: '2px solid #fff' }

function ERDTableNode({ data }) {
  const rs = ROLE_STYLES[data.role] || ROLE_STYLES.table
  return (
    <div style={{
      background: 'var(--surface)', border: `1.5px solid ${rs.accent}38`,
      borderRadius: 10, width: 300, overflow: 'hidden',
      boxShadow: data.selected ? `0 0 0 2px ${rs.accent}` : 'var(--shadow-sm)',
      fontSize: 12, cursor: 'pointer',
    }}>
      <Handle id="in-l" type="target" position={Position.Left} style={{ ...HANDLE, background: rs.accent, left: -6 }} />
      <Handle id="out-l" type="source" position={Position.Left} style={{ ...HANDLE, background: rs.accent, left: -6 }} />

      <div style={{ background: rs.header, padding: '10px 14px', borderBottom: `1px solid ${rs.accent}26`, height: 62, boxSizing: 'border-box' }}>
        <div style={{ fontWeight: 700, fontSize: 12.5, color: 'var(--text)', letterSpacing: .15, marginBottom: 4 }}>
          {data.label}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
            padding: '1px 7px', borderRadius: 20,
            background: 'var(--surface)', color: rs.accent, border: `1px solid ${rs.accent}3a`,
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
        style: { stroke: '#3b82f680', strokeWidth: 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#3b82f6', width: 12, height: 12 },
        label: edgeLabel(e),
        labelStyle: { fontSize: 9, fill: '#55657a', fontFamily: MONO },
        labelBgStyle: { fill: '#ffffff', fillOpacity: 0.92 },
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
        <Controls style={{ background: 'rgba(8,15,32,.9)', border: '1px solid var(--border)', borderRadius: 8 }} />
        {nodes.length > 10 && (
          <MiniMap
            nodeColor={n => ROLE_STYLES[n.data?.role]?.accent || '#64748b'}
            style={{ background: '#ffffff', border: '1px solid var(--border)', borderRadius: 8 }}
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
      <table>
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
                <Badge variant="blue">{c.type}</Badge>
                <Badge variant="gray">{KIND_LABEL[c.storage?.kind] || 'Unknown'}</Badge>
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

export function ModelDetail({ name }) {
  const { data, isLoading } = useModel(name)
  const { data: desk } = useDesk()
  const [tab, setTab] = useState(null)      // null: the model's own default tab
  const [previewTable, setPreviewTable] = useState(null)

  if (!name) return (
    <Card>
      <Empty
        icon="⬡"
        message="Select a model to read its file, grain, measures, tables, and connectors."
      />
    </Card>
  )
  if (isLoading) return <SkeletonCard />
  if (!data) return null

  const graph = buildModelGraph(data)
  const storageOf = new Map((data.connector_details || []).map(c => [c.name, c.storage]))
  const tabs = ['Diagram', 'Tables', 'Measures', 'Relationships', 'Storage']
  // A model with joins opens on its diagram; one with none has nothing to draw.
  const active = tab || (graph.edges.length ? 'Diagram' : 'Tables')
  const grain = (data.dimensions || []).flatMap(d =>
    (d.attributes || []).map(attr => `${d.name}.${attr}`)
  ).join(', ')
  const sinks = desk?.sinks || []

  return (
    <Card className="fade-in">
      <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12, lineHeight: 1.6 }}>
        {data.source_file && <div>Defined in <code>{data.source_file}</code></div>}
        {(data.connector_details || []).map(c => (
          <div key={c.name}>Data in <StorageLine storage={c.storage} /></div>
        ))}
        {grain && <div>Grain: {grain}</div>}
        {desk?.warehouse && sinks.length === 0 && <div>Its tables satisfied their checks when they were last written.</div>}
        {sinks.length > 0 && (
          <div>
            {sinks.map(s => `${s.table} ${s.status}`).join(' · ')}
          </div>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        {data.connectors.map(c => <Badge key={c} variant="blue">{c}</Badge>)}
        <Badge variant="purple">{summary(data)}</Badge>
        <Badge variant="gray">{data.tables.length} table{data.tables.length !== 1 ? 's' : ''}</Badge>
      </div>

      <Tabs tabs={tabs} active={active} onChange={t => { setTab(t); setPreviewTable(null) }} />

      {active === 'Tables' && (
        <div>
          <div style={{ overflowX: 'auto' }}>
            <table>
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
              <table>
                <thead><tr><th>From</th><th>To</th><th>Keys</th><th>Shape</th><th>Declared with</th></tr></thead>
                <tbody>
                  {graph.edges.map(e => (
                    <tr key={e.id}>
                      <td><code>{e.from}</code></td>
                      <td><code>{e.to}</code></td>
                      <td style={{ color: 'var(--muted)', fontSize: 12, fontFamily: 'Cascadia Code, Fira Code, monospace' }}>
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
 * The all-models view of a page that is always about one model (Data model,
 * Explore): the models, each opening that page for itself.
 */
export default function Models({ pageKey = 'model' }) {
  const { data, isLoading } = useModels()
  const { data: reports } = useReports()
  const { data: pipelines } = usePipelines()
  const [params] = useSearchParams()
  // Old links: /models?m=<model>, /explore?model=<model>.
  const legacy = params.get('m') || params.get('model')
  if (legacy) return <Navigate to={pagePath(pageKey, legacy)} replace />

  const models = data || []
  const reportCount = name => (reports || []).filter(r => reportBelongsToModel(r.name, name)).length
  const refreshes = name => (pipelines || []).some(p => pipelineBelongsToModel(p, name))

  return (
    <>
      <PageHeader pageKey={pageKey} model=""
        sub={pageKey === 'explore'
          ? 'Explore asks one model at a time. Pick one.'
          : 'Each model is a star schema over stored tables: its grain, joins and measures. Pick one.'} />
      {isLoading ? <SkeletonList /> : models.length === 0 ? (
        <Empty icon="⬡" message="No models yet. Create one with tracebi new-model, in models/." />
      ) : (
        <div className="model-cards">
          {models.map((m, i) => {
            const n = reportCount(m.name)
            return (
              <Link key={m.name} to={pagePath(pageKey, m.name)} className="model-card rise" style={{ '--i': i }}>
                <span className="model-card__name">{m.name}</span>
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
