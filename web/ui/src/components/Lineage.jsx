import { useMemo, useState } from 'react'
import ReactFlow, { Background, Controls, MiniMap, Handle, Position } from 'reactflow'
import 'reactflow/dist/style.css'

export const OP_COLORS = {
  load: '#1e3a5f', filter: '#1a3d24', transform: '#4a3000',
  join: '#4a1500', sort: '#2d1060', select: '#1a2530',
  rename: '#003d38', bronze: '#4a2800', silver: '#2a3040', gold: '#3d3000',
}

export function LineageNode({ data, selected }) {
  return (
    <div style={{
      background: data.color || '#1e2d4a',
      border: `1px solid ${selected ? 'rgba(96,165,250,.9)' : 'rgba(255,255,255,.15)'}`,
      boxShadow: selected ? '0 0 0 3px rgba(96,165,250,.25)' : 'none',
      borderRadius: 8, padding: '10px 14px', minWidth: 180, color: '#fff', fontSize: 12,
      cursor: 'pointer', transition: 'box-shadow .15s ease, border-color .15s ease',
    }}>
      <Handle type="target" position={Position.Left} style={{ background: 'rgba(255,255,255,.3)' }} />
      <div style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: 10, opacity: .65, marginBottom: 4, letterSpacing: .5 }}>
        {data.operation}
      </div>
      <div style={{ lineHeight: 1.4 }}>{data.description}</div>
      {data.metadata?.rows_before != null && (
        <div style={{ marginTop: 6, fontSize: 10, opacity: .55 }}>
          {data.metadata.rows_before} → {data.metadata.rows_after} rows
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ background: 'rgba(255,255,255,.3)' }} />
    </div>
  )
}

const NODE_TYPES = { lineageNode: LineageNode }

function MetaRow({ k, v }) {
  return (
    <div style={{ display: 'flex', gap: 10, padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
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
  return (
    <div className="fade-in" style={{
      position: 'absolute', top: 10, right: 10, bottom: 10, width: 250, zIndex: 5,
      background: 'rgba(6,12,26,.96)', backdropFilter: 'blur(8px)',
      border: '1px solid var(--border)', borderRadius: 10, padding: '14px 16px',
      overflowY: 'auto',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
          padding: '2px 8px', borderRadius: 20, background: data.color || '#1e2d4a', color: '#fff',
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
      style: { stroke: 'rgba(96,165,250,.5)', strokeWidth: 1.5 },
    })),
    [graph],
  )

  if (!graph?.nodes?.length) return (
    <div style={{ padding: 24, color: 'var(--muted)', fontSize: 13 }}>No lineage data available.</div>
  )
  return (
    <div style={{ height, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)', position: 'relative' }}>
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
        <Background color="#1e2d4a" gap={20} />
        <Controls style={{ background: 'var(--card)', border: '1px solid var(--border)' }} />
        {graph.nodes.length > 4 && (
          <MiniMap
            nodeColor={n => n.data?.color || '#1e2d4a'}
            style={{ background: '#040a14', border: '1px solid var(--border)', borderRadius: 8, width: 140, height: 90 }}
            maskColor="rgba(4,10,20,.75)"
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
