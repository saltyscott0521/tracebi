import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ReactFlow, Background, Handle, Position, MarkerType } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { usePipelines, useStartPipelineRun, usePipelineRuns, useLayerHistory } from '../api'
import { PageHeader } from '../components/Scope'
import RunLog from '../components/RunLog'
import CodeView from '../components/CodeView'
import { pipelineModels, pipelineBelongsToModel } from '../nav'
import {
  Card, CardTitle, Badge, Spinner,
  Empty, Btn, Tabs, SkeletonCard, SkeletonList, SplitLayout, ListItem,
  SearchInput, useToast,
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
  landing: 'var(--op-landing-tx)', bronze: 'var(--op-landing-tx)',
  manipulation: 'var(--role-fact)', silver: 'var(--role-fact)',
  final: 'var(--op-final-tx)', gold: 'var(--op-final-tx)',
}
const STATUS_DOT = { success: 'var(--green)', failed: 'var(--red)', running: 'var(--amber)' }

function LayerNode({ data }) {
  const accent = TYPE_ACCENT[data.layer.type] || 'var(--role-table)'
  const status = data.layer.last_status
  const dot = STATUS_DOT[status] || 'var(--muted)'
  return (
    <div style={{
      background: 'var(--surface)',
      border: `1.5px solid color-mix(in srgb, ${accent} 22%, transparent)`,
      borderRadius: 10, minWidth: 200, overflow: 'hidden',
      boxShadow: 'var(--shadow-sm)',
      fontSize: 12,
    }}>
      <Handle type="target" position={Position.Left}
        style={{ background: accent, width: 9, height: 9, border: '2px solid #fff', left: -5 }} />
      <div style={{
        padding: '9px 13px 7px',
        background: `color-mix(in srgb, ${accent} 5%, transparent)`,
        borderBottom: `1px solid color-mix(in srgb, ${accent} 13%, transparent)`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span className={status === 'running' ? 'pulse-glow' : undefined} style={{
          width: 8, height: 8, borderRadius: '50%', background: dot, flexShrink: 0,
        }} />
        <span style={{ fontWeight: 700, fontSize: 12, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
          {data.layer.name}
        </span>
      </div>
      <div style={{ padding: '7px 13px 9px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
          <span style={{
            fontSize: 9, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .6,
            padding: '1px 7px', borderRadius: 20,
            background: `color-mix(in srgb, ${accent} 8%, transparent)`, color: accent, border: `1px solid color-mix(in srgb, ${accent} 23%, transparent)`,
          }}>{TYPE_LABEL[data.layer.type] || data.layer.type}</span>
          {data.layer.schedule && (
            <span style={{ fontSize: 9.5, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
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
              background: `color-mix(in srgb, ${accent} 7%, transparent)`, color: accent, border: `1px solid color-mix(in srgb, ${accent} 25%, transparent)`,
              opacity: data.running ? .5 : 1,
            }}
          >▶ run</button>
        </div>
      </div>
      <Handle type="source" position={Position.Right}
        style={{ background: accent, width: 9, height: 9, border: '2px solid #fff', right: -5 }} />
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
        style: { stroke: 'var(--muted)', strokeWidth: 1.4 },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#8a8a8a', width: 13, height: 13 },
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
        edgesFocusable={false}
        nodes={nodes}
        edges={edges}
        nodeTypes={DAG_NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.22 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
      >
        <Background color="var(--flow-dots)" gap={26} size={1} />
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

function pipelineSummary(layers) {
  const n = layers?.length || 0
  const failed = (layers || []).filter(l =>
    l.last_status === 'error' || l.last_status?.startsWith?.('error:')).length
  const running = (layers || []).some(l => l.last_status === 'running')
  if (running) return `${n} layer${n !== 1 ? 's' : ''} · running`
  if (failed) return `${n} layer${n !== 1 ? 's' : ''} · ${failed} failed`
  return `${n} layer${n !== 1 ? 's' : ''}`
}

export function PipelineDetail({ pipeline, layers }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: start, isPending: isStarting } = useStartPipelineRun()
  const { data: runs } = usePipelineRuns(pipeline)
  const [picked, setPicked] = useState(null)
  const [selected, setSelected] = useState(null)
  // A phone fits the flow into 350px and its run buttons shrink past tapping;
  // the list of steps keeps them full size.
  const [tab, setTab] = useState(() =>
    window.matchMedia?.('(max-width: 768px)').matches ? 'Steps' : 'Flow')

  if (!pipeline) {
    return (
      <Card>
        <Empty message="Select a pipeline to see its flow, layers, and run history." />
      </Card>
    )
  }

  // A run goes on in the background and its output is the Log tab: starting
  // one (or joining the one already going) opens it there.
  const latest = runs?.[0]
  const busy = isStarting || latest?.status === 'running'
  const shownRun = picked || latest?.run_id || null

  function begin(layer) {
    start({ pipeline, layer }, {
      onSuccess: res => {
        setPicked(res.run_id)
        setTab('Log')
        if (res.already_running) toast('Already running. Showing its log.', 'info')
      },
      onError: err => toast(`Could not start: ${err.message}`, 'error'),
    })
  }
  const handleRunAll = () => begin(undefined)
  const handleRunLayer = layer => begin(layer)
  // A run that ends changes what the page says about every step.
  const finished = () => {
    qc.invalidateQueries({ queryKey: ['pipelines'] })
    qc.invalidateQueries({ queryKey: ['pipeline-runs', pipeline] })
  }

  return (
    <Card className="fade-in">
      <CardTitle action={
        <Btn
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={handleRunAll}
        >
          {busy ? <><Spinner size={12} /> Running…</> : '▶ Run all'}
        </Btn>
      }>
        {pipeline}
      </CardTitle>

      <Tabs tabs={['Flow', 'Steps', 'Log', 'History', 'Code']} active={tab} onChange={t => setTab(t)} />

      {tab === 'Flow' && (
        <div className="fade-in">
          <PipelineDag layers={layers} onRun={handleRunLayer} running={busy} />
          <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
            Each step runs after the one it depends on. Status updates every 10 s; run any step from its node.
          </p>
        </div>
      )}

      {tab === 'Steps' && (
        <div style={{ overflowX: 'auto' }}>
          <table>
            <thead>
              <tr><th>Step</th><th>Type</th><th>Schedule</th><th>Runs after</th><th>Last status</th><th>Rows out</th><th>Last run</th><th><span className="sr-only">Run</span></th></tr>
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
                      disabled={busy}
                      onClick={() => handleRunLayer(l.name)}
                      aria-label={`Run ${l.name}`}
                    >
                      {busy ? <Spinner size={12} /> : '▶ Run'}
                    </Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'Log' && (
        <div className="fade-in">
          <RunLog pipeline={pipeline} runs={runs} runId={shownRun} onPick={setPicked} onDone={finished} />
        </div>
      )}

      {tab === 'Code' && <CodeView kind="pipelines" name={pipeline} />}

      {tab === 'History' && (
        <div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap: 'wrap' }}>
            {layers.map(l => (
              <button key={l.name} onClick={() => setSelected(l.name)} style={{
                padding: '4px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: selected === l.name ? 'var(--blue-lt)' : 'var(--surface-2)',
                color: selected === l.name ? 'var(--accent-text)' : 'var(--muted)',
                border: `1px solid ${selected === l.name ? 'var(--blue-br)' : 'var(--border)'}`,
                cursor: 'pointer',
                transition: 'background var(--t), color var(--t)',
              }}>{l.name}</button>
            ))}
          </div>
          {selected
            ? <LayerHistory pipeline={pipeline} layer={selected} />
            : <p style={{ fontSize: 13, color: 'var(--muted)' }}>Pick a step above to see its run history.</p>
          }
        </div>
      )}
    </Card>
  )
}

/**
 * Refresh: rebuild a model's data, then the reports that read it. One model
 * shows its pipeline; all models list every pipeline with the model it feeds.
 */
export default function Pipelines({ model = '' }) {
  const { data, isLoading } = usePipelines()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const pipelines = (data || []).filter(p => pipelineBelongsToModel(p, model))

  if (model) {
    return (
      <>
        <PageHeader pageKey="refresh" model={model} />
        {isLoading ? <SkeletonCard /> : pipelines.length
          ? pipelines.map(p => (
            <div key={p.pipeline} style={{ marginBottom: 16 }}>
              <PipelineDetail pipeline={p.pipeline} layers={p.layers || []} />
            </div>
          ))
          : (
            <Card>
              <Empty message={`Nothing refreshes ${model} yet. Add pipelines/${model}.py with runner = model_pipeline("${model}", transform="…") and its transform runs, then its reports rebuild.`} />
            </Card>
          )}
      </>
    )
  }

  const filtered = pipelines.filter(p =>
    `${p.pipeline} ${pipelineModels(p).join(' ')}`.toLowerCase().includes(query.toLowerCase()))
  // Open on the first pipeline rather than a blank "select one" pane.
  const current = filtered.find(p => p.pipeline === params.get('p')) || filtered[0]
  const select = name => setParams(name ? { p: name } : {}, { replace: true })

  return (
    <>
      <PageHeader pageKey="refresh" model="" />
      {!isLoading && pipelines.length === 0 ? (
        <Empty message="Nothing refreshes yet. Add pipelines/<model>.py with runner = model_pipeline(…) for each model." />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search pipelines…" />
                {filtered.length === 0
                  ? <Empty message="No matches." />
                  : filtered.map((p, i) => (
                    <div key={p.pipeline} className="rise" style={{ '--i': i }}>
                      <ListItem
                        selected={current?.pipeline === p.pipeline}
                        onClick={() => select(p.pipeline)}
                        name={p.pipeline}
                        sub={pipelineSummary(p.layers)}
                        meta={pipelineModels(p).filter(m => m !== p.pipeline).map(m => (
                          <Badge key={m} variant="gray" style={{ textTransform: 'none' }}>{m}</Badge>
                        ))}
                      />
                    </div>
                  ))
                }
              </>
            )
          }
          right={
            <PipelineDetail
              key={current?.pipeline || ''}
              pipeline={current?.pipeline}
              layers={current?.layers || []}
            />
          }
        />
      )}
    </>
  )
}
