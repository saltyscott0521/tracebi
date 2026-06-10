import { useMemo, useState } from 'react'
import ReactFlow, { Background, Handle, Position, MarkerType } from 'reactflow'
import 'reactflow/dist/style.css'

import { usePipelines, useRunLayer, useRunPipeline, useLayerHistory } from '../api'
import {
  PageTitle, PageSub, Card, CardTitle, Badge, Spinner,
  Empty, Btn, Tabs, SkeletonCard, useToast,
} from '../components/Shared'

const TYPE_BADGE = {
  bronze: 'bronze',  silver: 'silver',       gold: 'gold',
  landing: 'landing', manipulation: 'manipulation', final: 'final',
  BronzeLayer: 'bronze', SilverLayer: 'silver', GoldLayer: 'gold',
}
const TYPE_LABEL = {
  bronze: 'Landing', silver: 'Manipulation', gold: 'Final',
  landing: 'Landing', manipulation: 'Manipulation', final: 'Final',
}
const STATUS_BADGE = { success: 'green', error: 'red', running: 'amber' }

// ── Medallion DAG view ───────────────────────────────────────────────────────

const TYPE_ACCENT = {
  landing: '#4A90E2', bronze: '#4A90E2',
  manipulation: '#7B68EE', silver: '#7B68EE',
  final: '#10B981', gold: '#10B981',
}
const STATUS_DOT = { success: '#22c55e', failed: '#ef4444', running: '#fbbf24' }

function LayerNode({ data }) {
  const accent = TYPE_ACCENT[data.layer.type] || '#64748b'
  const status = data.layer.last_status
  const dot = STATUS_DOT[status] || '#475569'
  return (
    <div style={{
      background: '#0e1830',
      border: `1.5px solid ${accent}45`,
      borderRadius: 10, minWidth: 200, overflow: 'hidden',
      boxShadow: `0 8px 28px rgba(0,0,0,.55), 0 0 0 1px ${accent}12`,
      fontSize: 12,
    }}>
      <Handle type="target" position={Position.Left}
        style={{ background: accent, width: 9, height: 9, border: '2px solid #080f20', left: -5 }} />
      <div style={{
        padding: '9px 13px 7px',
        background: `linear-gradient(135deg, ${accent}1c, transparent)`,
        borderBottom: `1px solid ${accent}22`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span className={status === 'running' ? 'pulse-glow' : undefined} style={{
          width: 8, height: 8, borderRadius: '50%', background: dot, flexShrink: 0,
        }} />
        <span style={{ fontWeight: 700, fontSize: 12, color: '#e2e8f0', fontFamily: 'Cascadia Code, Fira Code, monospace' }}>
          {data.layer.name}
        </span>
      </div>
      <div style={{ padding: '7px 13px 9px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
          <span style={{
            fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
            padding: '1px 7px', borderRadius: 20,
            background: `${accent}20`, color: accent, border: `1px solid ${accent}3a`,
          }}>{TYPE_LABEL[data.layer.type] || data.layer.type}</span>
          {data.layer.schedule && (
            <span style={{ fontSize: 9.5, color: '#3d5278', fontFamily: 'Cascadia Code, Fira Code, monospace' }}>
              {data.layer.schedule}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>
            {data.layer.last_rows_out != null ? `${data.layer.last_rows_out} rows` : 'never run'}
          </span>
          <button
            onClick={e => { e.stopPropagation(); data.onRun(data.layer.name) }}
            disabled={data.running}
            title={`Run ${data.layer.name}`}
            style={{
              marginLeft: 'auto', padding: '2px 10px', borderRadius: 5,
              fontSize: 10, fontWeight: 700, cursor: data.running ? 'default' : 'pointer',
              background: `${accent}1f`, color: accent, border: `1px solid ${accent}40`,
              opacity: data.running ? .5 : 1,
            }}
          >▶ run</button>
        </div>
      </div>
      <Handle type="source" position={Position.Right}
        style={{ background: accent, width: 9, height: 9, border: '2px solid #080f20', right: -5 }} />
    </div>
  )
}

const DAG_NODE_TYPES = { layerNode: LayerNode }

function layerDepth(name, byName, seen = new Set()) {
  const layer = byName[name]
  if (!layer?.depends_on || seen.has(name)) return 0
  seen.add(name)
  return 1 + layerDepth(layer.depends_on, byName, seen)
}

function PipelineDag({ layers, onRun, running }) {
  const { nodes, edges } = useMemo(() => {
    const byName = Object.fromEntries(layers.map(l => [l.name, l]))
    const depthCount = {}
    const nodes = layers.map(l => {
      const depth = layerDepth(l.name, byName)
      const row = depthCount[depth] ?? 0
      depthCount[depth] = row + 1
      return {
        id: l.name,
        type: 'layerNode',
        position: { x: depth * 280, y: row * 125 },
        data: { layer: l, onRun, running },
      }
    })
    const edges = layers
      .filter(l => l.depends_on && byName[l.depends_on])
      .map(l => ({
        id: `e-${l.depends_on}-${l.name}`,
        source: l.depends_on,
        target: l.name,
        animated: true,
        style: { stroke: `${TYPE_ACCENT[l.type] || '#64748b'}70`, strokeWidth: 1.6 },
        markerEnd: { type: MarkerType.ArrowClosed, color: TYPE_ACCENT[l.type] || '#64748b', width: 13, height: 13 },
      }))
    return { nodes, edges }
  }, [layers, onRun, running])

  const maxRows = Math.max(...Object.values(
    nodes.reduce((acc, n) => { acc[n.position.x] = (acc[n.position.x] || 0) + 1; return acc }, {})
  ), 1)

  return (
    <div style={{
      height: Math.max(190, maxRows * 125 + 70),
      borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)',
    }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={DAG_NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.22 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
      >
        <Background color="#1a2844" gap={26} size={1} />
      </ReactFlow>
    </div>
  )
}

function LayerHistory({ pipeline, layer }) {
  const { data, isLoading } = useLayerHistory(pipeline, layer)
  if (isLoading) return <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', fontSize: 13, padding: '12px 0' }}><Spinner size={14} /> Loading history…</div>
  const runs = data?.runs || []
  if (runs.length === 0) return <p style={{ fontSize: 13, color: 'var(--muted)', padding: '12px 0' }}>No runs yet for this layer.</p>
  return (
    <div style={{ overflowX: 'auto' }} className="fade-in">
      <table>
        <thead>
          <tr><th>Run ID</th><th>Status</th><th>Rows In</th><th>Rows Out</th><th>Completed</th></tr>
        </thead>
        <tbody>
          {runs.map(r => (
            <tr key={r.id}>
              <td style={{ color: 'var(--muted)', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>{r.id}</td>
              <td>
                {r.last_status?.startsWith?.('error:')
                  ? <Badge variant="red" style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', textTransform: 'none', fontWeight: 400 }} title={r.last_status}>{r.last_status}</Badge>
                  : <Badge variant={STATUS_BADGE[r.status] || 'gray'}>{r.status || '—'}</Badge>
                }
              </td>
              <td style={{ color: 'var(--text-2)' }}>{r.rows_in ?? '—'}</td>
              <td style={{ color: 'var(--text-2)' }}>{r.rows_out ?? '—'}</td>
              <td style={{ color: 'var(--muted)', fontSize: 12 }}>
                {r.completed_at ? new Date(r.completed_at).toLocaleString() : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PipelineCard({ pipeline, layers }) {
  const toast = useToast()
  const { mutate: run, isPending } = useRunLayer()
  const { mutate: runAll, isPending: isRunningAll } = useRunPipeline()
  const [selected, setSelected] = useState(null)
  const [tab, setTab] = useState('Flow')

  function handleRunAll() {
    runAll({ pipeline }, {
      onSuccess: res => toast(`Pipeline ran ${res.ran?.length ?? 0} layer(s)`, 'success'),
      onError: err => toast(`Pipeline failed: ${err.message}`, 'error'),
    })
  }

  function handleRunLayer(layer) {
    run({ pipeline, layer }, {
      onSuccess: () => toast(`Layer "${layer}" triggered`, 'success'),
      onError: err => toast(`Failed: ${err.message}`, 'error'),
    })
  }

  return (
    <Card>
      <CardTitle action={
        <Btn
          size="sm"
          variant="outline"
          disabled={isRunningAll}
          onClick={handleRunAll}
        >
          {isRunningAll ? <><Spinner size={12} /> Running…</> : '▶ Run all'}
        </Btn>
      }>
        {pipeline}
      </CardTitle>

      <Tabs tabs={['Flow', 'Layers', 'History']} active={tab} onChange={t => setTab(t)} />

      {tab === 'Flow' && (
        <div className="fade-in">
          <PipelineDag layers={layers} onRun={handleRunLayer} running={isPending || isRunningAll} />
          <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
            Live medallion flow — Landing → Manipulation → Final. Status updates every 10 s; run any layer from its node.
          </p>
        </div>
      )}

      {tab === 'Layers' && (
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr><th>Layer</th><th>Type</th><th>Schedule</th><th>Depends On</th><th>Last Status</th><th>Rows Out</th><th>Last Run</th><th></th></tr>
            </thead>
            <tbody>
              {layers.map(l => (
                <tr key={l.name}>
                  <td><code style={{ fontSize: 12 }}>{l.name}</code></td>
                  <td>
                    <Badge variant={TYPE_BADGE[l.type] || 'gray'}>
                      {TYPE_LABEL[l.type] || l.type?.replace('Layer', '') || l.type}
                    </Badge>
                  </td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>{l.schedule || '—'}</td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>{l.depends_on || '—'}</td>
                  <td>
                    {l.last_status
                      ? l.last_status.startsWith('error:')
                        ? <Badge variant="red" title={l.last_status}>error</Badge>
                        : <Badge variant={STATUS_BADGE[l.last_status] || 'gray'}>{l.last_status}</Badge>
                      : <Badge variant="gray">—</Badge>
                    }
                  </td>
                  <td style={{ color: 'var(--text-2)', fontVariantNumeric: 'tabular-nums' }}>
                    {l.last_rows_out ?? '—'}
                  </td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>
                    {l.last_run ? new Date(l.last_run).toLocaleString() : '—'}
                  </td>
                  <td>
                    <Btn
                      size="sm"
                      variant="outline"
                      disabled={isPending}
                      onClick={() => handleRunLayer(l.name)}
                    >
                      {isPending ? <Spinner size={12} /> : '▶'}
                    </Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'History' && (
        <div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
            {layers.map(l => (
              <button key={l.name} onClick={() => setSelected(l.name)} style={{
                padding: '4px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: selected === l.name ? 'var(--blue-lt)' : 'rgba(255,255,255,.04)',
                color: selected === l.name ? '#93c5fd' : 'var(--muted)',
                border: `1px solid ${selected === l.name ? 'var(--blue-br)' : 'var(--border)'}`,
                cursor: 'pointer',
                transition: 'background var(--t), color var(--t)',
              }}>{l.name}</button>
            ))}
          </div>
          {selected
            ? <LayerHistory pipeline={pipeline} layer={selected} />
            : <p style={{ fontSize: 13, color: 'var(--muted)' }}>Select a layer above to view its run history.</p>
          }
        </div>
      )}
    </Card>
  )
}

export default function Pipelines() {
  const { data, isLoading } = usePipelines()
  const pipelines = data || []

  return (
    <>
      <PageTitle>Pipelines</PageTitle>
      <PageSub>
        {isLoading
          ? 'Loading…'
          : `${pipelines.length} pipeline${pipelines.length !== 1 ? 's' : ''} registered — Landing → Manipulation → Final layers. Run history auto-refreshes every 10 s.`
        }
      </PageSub>

      {isLoading ? (
        <><SkeletonCard /><SkeletonCard /></>
      ) : pipelines.length === 0 ? (
        <Empty message="No pipelines registered. Add one with registry.add_pipeline() in your app module." />
      ) : (
        pipelines.map(p => (
          <PipelineCard key={p.pipeline} pipeline={p.pipeline} layers={p.layers} />
        ))
      )}
    </>
  )
}
