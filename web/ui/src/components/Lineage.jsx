import { useMemo, useState } from 'react'
import ReactFlow, { Background, Controls, MiniMap, Handle, Position } from 'reactflow'
import 'reactflow/dist/style.css'

// Operations with a dedicated tint in global.css (--op-{name}-bg/br/tx).
const KNOWN_OPS = new Set([
  'load', 'filter', 'transform', 'join', 'sort', 'select', 'rename',
  'landing', 'manipulation', 'final', 'bronze', 'silver', 'gold', 'warning',
])

export function opStyle(operation) {
  const key = KNOWN_OPS.has(String(operation).toLowerCase())
    ? String(operation).toLowerCase()
    : 'default'
  return {
    bg: `var(--op-${key}-bg)`,
    br: `var(--op-${key}-br)`,
    tx: `var(--op-${key}-tx)`,
  }
}

// One-line row-count summary from whatever counts the lineage step recorded.
export function rowSummary(meta) {
  const m = meta || {}
  const fmt = n => Number(n).toLocaleString()
  if (m.rows_left != null && m.rows_right != null && m.rows_after != null)
    return `${fmt(m.rows_left)} ⋈ ${fmt(m.rows_right)} → ${fmt(m.rows_after)} rows`
  if (m.rows_before != null && m.rows_after != null)
    return `${fmt(m.rows_before)} → ${fmt(m.rows_after)} rows`
  const rows = m.rows ?? m.rows_loaded ?? m.rows_out ?? m.rows_after
  if (rows != null) return `${fmt(rows)} rows`
  return null
}

export function LineageNode({ data, selected }) {
  const op = opStyle(data.operation)
  const rows = rowSummary(data.metadata)
  return (
    <div style={{
      background: op.bg,
      border: `1px solid ${selected ? 'var(--blue)' : op.br}`,
      boxShadow: selected ? '0 0 0 3px rgba(37,99,235,.18)' : 'var(--shadow-sm)',
      borderRadius: 8, padding: '10px 14px', minWidth: 180, color: 'var(--text)', fontSize: 12,
      cursor: 'pointer', transition: 'box-shadow .15s ease, border-color .15s ease',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: op.br }} />
      <div style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: 10, color: op.tx, marginBottom: 4, letterSpacing: .5 }}>
        {data.operation}
      </div>
      <div style={{ lineHeight: 1.4, color: 'var(--text-2)' }}>{data.description}</div>
      {rows && (
        <div style={{ marginTop: 6, fontSize: 10, color: 'var(--muted)' }}>
          {rows}
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ background: op.br }} />
    </div>
  )
}

const NODE_TYPES = { lineageNode: LineageNode }

function MetaRow({ k, v }) {
  return (
    <div style={{ display: 'flex', gap: 10, padding: '4px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', minWidth: 92, textTransform: 'capitalize' }}>
        {k.replaceAll('_', ' ')}
      </span>
      <span style={{ fontSize: 11.5, color: 'var(--text-2)', wordBreak: 'break-word', fontFamily: 'Cascadia Code, Fira Code, monospace' }}>
        {String(v)}
      </span>
    </div>
  )
}

function NodeInspector({ data, onClose }) {
  if (!data) return null
  const meta = data.metadata || {}
  const op = opStyle(data.operation)
  return (
    <div className="fade-in" style={{
      position: 'absolute', top: 10, right: 10, bottom: 10, width: 250, zIndex: 5,
      background: 'var(--surface)',
      border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px',
      overflowY: 'auto', boxShadow: 'var(--shadow)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
          padding: '2px 8px', borderRadius: 20,
          background: op.bg, color: op.tx, border: `1px solid ${op.br}`,
        }}>{data.operation}</span>
        <button onClick={onClose} style={{
          marginLeft: 'auto', background: 'none', border: 'none',
          color: 'var(--muted)', cursor: 'pointer', fontSize: 16, lineHeight: 1,
        }}>×</button>
      </div>
      <p style={{ fontSize: 12.5, color: 'var(--text)', lineHeight: 1.5, marginBottom: 10 }}>
        {data.description}
      </p>
      {data.connector && Object.entries(data.connector).map(([k, v]) => <MetaRow key={k} k={k} v={v} />)}
      {data.source && <MetaRow k="source" v={data.source} />}
      {Object.entries(meta).map(([k, v]) => <MetaRow key={k} k={k} v={v} />)}
      {data.timestamp && <MetaRow k="recorded" v={new Date(data.timestamp).toLocaleString()} />}
    </div>
  )
}

export function LineageGraph({ graph, height = 340 }) {
  const [inspected, setInspected] = useState(null)

  const edges = useMemo(
    () => (graph?.edges || []).map(e => ({
      ...e,
      animated: true,
      style: { stroke: 'rgba(37,99,235,.45)', strokeWidth: 1.5 },
    })),
    [graph],
  )

  if (!graph?.nodes?.length) return (
    <div style={{ padding: 24, color: 'var(--muted)', fontSize: 13 }}>No lineage data available.</div>
  )
  return (
    <div style={{ height, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', position: 'relative', background: 'var(--flow-bg)' }}>
      <ReactFlow
        nodes={graph.nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, node) => setInspected(node.data)}
        onPaneClick={() => setInspected(null)}
      >
        <Background color="var(--flow-dots)" gap={20} />
        <Controls style={{ background: 'var(--surface)', border: '1px solid var(--border)' }} />
        {graph.nodes.length > 4 && (
          <MiniMap
            nodeColor="#cbd9ea"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, width: 140, height: 90 }}
            maskColor="rgba(228,233,240,.6)"
          />
        )}
      </ReactFlow>
      <NodeInspector data={inspected} onClose={() => setInspected(null)} />
      <div style={{
        position: 'absolute', left: 52, bottom: 12, fontSize: 10.5,
        color: 'var(--muted)', pointerEvents: 'none',
      }}>click a step to inspect</div>
    </div>
  )
}
