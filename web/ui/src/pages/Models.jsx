import { useState, useMemo } from 'react'
import ReactFlow, { Background, Controls, MiniMap, Handle, Position, MarkerType } from 'reactflow'
import 'reactflow/dist/style.css'

import { useModels, useModel, useTablePreview } from '../api'
import {
  PageTitle, PageSub, Card, CardTitle, Badge, Spinner,
  Empty, Tabs, SplitLayout, ListItem, SearchInput, SkeletonList, SkeletonCard,
} from '../components/Shared'

// ── Table Preview ─────────────────────────────────────────────────────────────

function TablePreview({ modelName, tableName }) {
  const { data, isLoading, error } = useTablePreview(modelName, tableName)
  if (isLoading) return (
    <div style={{ padding: 20, display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
      <Spinner size={14} /> Loading preview…
    </div>
  )
  if (error) return <div style={{ padding: 16, color: '#fca5a5', fontSize: 13 }}>{error.message}</div>
  if (!data) return null
  return (
    <div className="fade-in">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Badge variant="gray">{data.rows} rows</Badge>
        <Badge variant="gray">{data.columns.length} cols</Badge>
      </div>
      <div style={{ overflowX: 'auto', borderRadius: 6, border: '1px solid var(--border)' }}>
        <table>
          <thead><tr>{data.columns.map(c => <th key={c}>{c}</th>)}</tr></thead>
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
  dimension: { header: 'linear-gradient(135deg,#0f2a52,#1a3f78)', accent: '#3b82f6', label: 'Dimension' },
  fact:      { header: 'linear-gradient(135deg,#1a0a42,#2a1668)', accent: '#a78bfa', label: 'Fact' },
  bridge:    { header: 'linear-gradient(135deg,#321c00,#4e2c00)', accent: '#fbbf24', label: 'Bridge' },
  isolated:  { header: 'linear-gradient(135deg,#131e34,#1c2a44)', accent: '#64748b', label: 'Table' },
}

function getTableKeys(tableName, relationships) {
  const pks = [...new Set(relationships.filter(r => r.right_table === tableName).map(r => r.right_key))]
  const fks = [...new Set(relationships.filter(r => r.left_table === tableName).map(r => r.left_key))]
  return { pks, fks }
}

function getTableRole(tableName, relationships) {
  const hasPK = relationships.some(r => r.right_table === tableName)
  const hasFK = relationships.some(r => r.left_table === tableName)
  if (hasPK && !hasFK) return 'dimension'
  if (hasFK && !hasPK) return 'fact'
  if (hasPK && hasFK) return 'bridge'
  return 'isolated'
}

function computeLayout(tables, relationships) {
  const buckets = { dimension: [], fact: [], bridge: [], isolated: [] }
  tables.forEach(t => buckets[getTableRole(t.name, relationships)].push(t.name))

  const COL_X = { dimension: 0, bridge: 380, fact: 760, isolated: 1140 }
  const ROW_GAP = 210
  const positions = {}
  Object.entries(buckets).forEach(([role, names]) => {
    names.forEach((name, i) => { positions[name] = { x: COL_X[role], y: i * ROW_GAP } })
  })
  return positions
}

function ERDTableNode({ data }) {
  const rs = ROLE_STYLES[data.role] || ROLE_STYLES.isolated
  const keyCount = data.pks.length + data.fks.length
  return (
    <div style={{
      background: '#0e1830',
      border: `1.5px solid ${rs.accent}3a`,
      borderRadius: 10,
      minWidth: 215,
      overflow: 'hidden',
      boxShadow: `0 8px 32px rgba(0,0,0,.6), 0 0 0 1px ${rs.accent}14`,
      fontSize: 12,
    }}>
      <Handle type="target" position={Position.Left}
        style={{ background: rs.accent, width: 10, height: 10, border: '2px solid #080f20', left: -6 }} />

      <div style={{ background: rs.header, padding: '10px 14px', borderBottom: `1px solid ${rs.accent}2a` }}>
        <div style={{ fontWeight: 700, fontSize: 12.5, color: '#e2e8f0', letterSpacing: .15, marginBottom: 4 }}>
          {data.label}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
            padding: '1px 7px', borderRadius: 20,
            background: `${rs.accent}20`, color: rs.accent, border: `1px solid ${rs.accent}3a`,
          }}>{rs.label}</span>
          {data.connector && (
            <span style={{ fontSize: 9.5, color: '#3d5278' }}>{data.connector}</span>
          )}
        </div>
      </div>

      <div style={{ padding: keyCount > 0 ? '6px 0 8px' : '0' }}>
        {data.pks.map(k => (
          <div key={k} style={{
            padding: '3px 14px', display: 'flex', alignItems: 'center', gap: 7,
            borderLeft: '2px solid #fbbf2450',
          }}>
            <span style={{ fontSize: 11, lineHeight: 1 }}>🔑</span>
            <span style={{ color: '#fcd34d', fontWeight: 500, fontFamily: 'Cascadia Code, Fira Code, monospace', fontSize: 11 }}>{k}</span>
            <span style={{ marginLeft: 'auto', fontSize: 8.5, color: '#475569', fontWeight: 700, letterSpacing: .4 }}>PK</span>
          </div>
        ))}
        {data.pks.length > 0 && data.fks.length > 0 && (
          <div style={{ height: 1, background: 'rgba(255,255,255,.04)', margin: '4px 14px' }} />
        )}
        {data.fks.map(k => (
          <div key={k} style={{
            padding: '3px 14px', display: 'flex', alignItems: 'center', gap: 7,
            borderLeft: `2px solid ${rs.accent}40`,
          }}>
            <span style={{ fontSize: 11, color: rs.accent, opacity: .7, lineHeight: 1 }}>⤷</span>
            <span style={{ color: '#93c5fd', fontWeight: 500, fontFamily: 'Cascadia Code, Fira Code, monospace', fontSize: 11 }}>{k}</span>
            <span style={{ marginLeft: 'auto', fontSize: 8.5, color: '#475569', fontWeight: 700, letterSpacing: .4 }}>FK</span>
          </div>
        ))}
        {keyCount === 0 && (
          <div style={{ padding: '6px 14px', color: '#334155', fontStyle: 'italic', fontSize: 11 }}>no key columns</div>
        )}
      </div>

      <Handle type="source" position={Position.Right}
        style={{ background: rs.accent, width: 10, height: 10, border: '2px solid #080f20', right: -6 }} />
    </div>
  )
}

const NODE_TYPES = { erdTable: ERDTableNode }

function ERDDiagram({ tables, relationships }) {
  const { nodes, edges } = useMemo(() => {
    const positions = computeLayout(tables, relationships)
    const nodes = tables.map(t => {
      const { pks, fks } = getTableKeys(t.name, relationships)
      return {
        id: t.name,
        type: 'erdTable',
        position: positions[t.name] || { x: 0, y: 0 },
        data: { label: t.name, connector: t.connector, role: getTableRole(t.name, relationships), pks, fks },
      }
    })
    const edges = relationships.map((r, i) => ({
      id: `e-${i}`,
      source: r.left_table,
      target: r.right_table,
      type: 'smoothstep',
      style: { stroke: '#3b82f660', strokeWidth: 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#3b82f6', width: 12, height: 12 },
      label: `${r.left_key} → ${r.right_key}`,
      labelStyle: { fontSize: 9, fill: '#4a6080', fontFamily: 'Cascadia Code, Fira Code, monospace' },
      labelBgStyle: { fill: '#040a14', fillOpacity: 0.9 },
    }))
    return { nodes, edges }
  }, [tables, relationships])

  return (
    <div className="erd-wrapper">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.28 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
      >
        <Background color="#1a2844" gap={30} size={1} />
        <Controls style={{
          background: 'rgba(8,15,32,.9)', border: '1px solid var(--border)',
          borderRadius: 8,
        }} />
        <MiniMap
          nodeColor={n => ROLE_STYLES[n.data?.role]?.accent || '#64748b'}
          style={{ background: '#040a14', border: '1px solid var(--border)', borderRadius: 8 }}
          maskColor="rgba(4,10,20,.75)"
        />
      </ReactFlow>
    </div>
  )
}

// ── ERD legend ────────────────────────────────────────────────────────────────

function ERDLegend() {
  const items = [
    { role: 'dimension', label: 'Dimension — referenced by others' },
    { role: 'bridge',    label: 'Bridge — references + is referenced' },
    { role: 'fact',      label: 'Fact — references others' },
    { role: 'isolated',  label: 'Isolated — no relationships' },
  ]
  return (
    <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginBottom: 14 }}>
      {items.map(({ role, label }) => {
        const rs = ROLE_STYLES[role]
        return (
          <span key={role} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--muted)' }}>
            <span style={{
              width: 10, height: 10, borderRadius: 3, display: 'inline-block',
              background: rs.accent, opacity: .8,
            }} />
            {label}
          </span>
        )
      })}
    </div>
  )
}

// ── Model Detail ──────────────────────────────────────────────────────────────

function ModelDetail({ name }) {
  const { data, isLoading } = useModel(name)
  const [tab, setTab] = useState('Tables')
  const [previewTable, setPreviewTable] = useState(null)

  if (!name) return (
    <Card>
      <Empty
        icon="⬡"
        message="Select a model to explore its tables, relationships, and schema diagram."
      />
    </Card>
  )
  if (isLoading) return <SkeletonCard />
  if (!data) return null

  const tabs = ['Tables', 'Relationships', ...(data.relationships.length > 0 ? ['ERD'] : [])]

  return (
    <Card className="fade-in">
      <CardTitle>{data.name}</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        {data.connectors.map(c => <Badge key={c} variant="blue">{c}</Badge>)}
        <Badge variant="gray">{data.tables.length} table{data.tables.length !== 1 ? 's' : ''}</Badge>
        {data.relationships.length > 0 && (
          <Badge variant="purple">{data.relationships.length} relationship{data.relationships.length !== 1 ? 's' : ''}</Badge>
        )}
      </div>

      <Tabs tabs={tabs} active={tab} onChange={t => { setTab(t); setPreviewTable(null) }} />

      {tab === 'Tables' && (
        <div>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead><tr><th>Table</th><th>Connector</th><th>Source</th><th></th></tr></thead>
              <tbody>
                {data.tables.map(t => (
                  <tr key={t.name}>
                    <td><code>{t.name}</code></td>
                    <td style={{ color: 'var(--text-2)' }}>{t.connector}</td>
                    <td style={{ color: 'var(--muted)' }}>{t.source}</td>
                    <td>
                      <button onClick={() => setPreviewTable(previewTable === t.name ? null : t.name)} style={{
                        padding: '3px 10px', fontSize: 11, fontWeight: 600, borderRadius: 4,
                        background: 'var(--blue-lt)', color: '#93c5fd',
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

      {tab === 'Relationships' && (
        data.relationships.length === 0
          ? <Empty message="No relationships defined on this model." />
          : (
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead><tr><th>Name</th><th>Left</th><th>Right</th><th>Keys</th><th>How</th></tr></thead>
                <tbody>
                  {data.relationships.map(r => (
                    <tr key={r.name}>
                      <td><code>{r.name}</code></td>
                      <td style={{ color: 'var(--text-2)' }}>{r.left_table}</td>
                      <td style={{ color: 'var(--text-2)' }}>{r.right_table}</td>
                      <td style={{ color: 'var(--muted)', fontSize: 12, fontFamily: 'Cascadia Code, Fira Code, monospace' }}>
                        {r.left_key} = {r.right_key}
                      </td>
                      <td><Badge variant="gray">{r.how}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
      )}

      {tab === 'ERD' && (
        <div className="fade-in">
          <ERDLegend />
          <ERDDiagram tables={data.tables} relationships={data.relationships} />
          <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
            Drag nodes to rearrange · scroll to zoom · edges show join keys
          </p>
        </div>
      )}
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Models() {
  const { data, isLoading } = useModels()
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')

  const models = data || []
  const filtered = models.filter(m => m.name.toLowerCase().includes(query.toLowerCase()))

  return (
    <>
      <PageTitle>Models</PageTitle>
      <PageSub>
        {isLoading
          ? 'Loading…'
          : `${models.length} data model${models.length !== 1 ? 's' : ''} registered. Select a model to explore its tables, relationships, and ERD schema diagram.`
        }
      </PageSub>

      {!isLoading && models.length === 0 ? (
        <Empty
          icon="⬡"
          message="No models registered. Add one with registry.add_model() in your app module."
        />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search models…" />
                {filtered.length === 0
                  ? <Empty message="No matches." />
                  : filtered.map(m => (
                    <ListItem
                      key={m.name}
                      selected={selected === m.name}
                      onClick={() => setSelected(m.name)}
                      name={m.name}
                      sub={`${m.tables.length} tables · ${m.relationships.length} rel`}
                    />
                  ))
                }
              </>
            )
          }
          right={<ModelDetail name={selected} />}
        />
      )}
    </>
  )
}
