import ReactFlow, { Background, Controls, Handle, Position } from 'reactflow'
import 'reactflow/dist/style.css'

export const OP_COLORS = {
  load: '#1e3a5f', filter: '#1a3d24', transform: '#4a3000',
  join: '#4a1500', sort: '#2d1060', select: '#1a2530',
  rename: '#003d38', bronze: '#4a2800', silver: '#2a3040', gold: '#3d3000',
}

export function LineageNode({ data }) {
  return (
    <div style={{
      background: data.color || '#1e2d4a',
      border: '1px solid rgba(255,255,255,.15)',
      borderRadius: 8, padding: '10px 14px', minWidth: 180, color: '#fff', fontSize: 12,
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

export function LineageGraph({ graph, height = 340 }) {
  if (!graph?.nodes?.length) return (
    <div style={{ padding: 24, color: 'var(--muted)', fontSize: 13 }}>No lineage data available.</div>
  )
  return (
    <div style={{ height, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)' }}>
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e2d4a" gap={20} />
        <Controls style={{ background: 'var(--card)', border: '1px solid var(--border)' }} />
      </ReactFlow>
    </div>
  )
}
