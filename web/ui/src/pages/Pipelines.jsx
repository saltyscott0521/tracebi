import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useIsFetching, useQueryClient } from '@tanstack/react-query'
import { ReactFlow, Background, Handle, Position, MarkerType } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

import { useMe, usePipelines, useStartPipelineRun, usePipelineRuns, useLayerHistory } from '../api'
import RunLog from '../components/RunLog'
import CodeView from '../components/CodeView'
import { useModelLabel } from '../components/Scope'
import { ago } from '../when'
import { count } from '../format'
import { humanise } from '../ask'
import { dataPath, pipelineBelongsToModel } from '../nav'
import {
  Card, CardTitle, Badge, Chip, Spinner,
  Empty, Btn, Segmented, SkeletonCard, Time, useNarrow, useToast,
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
// A step's last status as a chip: the tone and the words. A step that raised
// records "error: <message>", which is its title.
const STATUS_CHIP = {
  success: ['', 'Succeeded'], succeeded: ['', 'Succeeded'],
  failed: ['bad', 'Failed'], error: ['bad', 'Failed'],
  running: ['warn', 'Running'],
}

function StepStatus({ status }) {
  if (!status) return <Chip tone="none">Not run yet</Chip>
  const [tone, words] = STATUS_CHIP[status.startsWith('error:') ? 'error' : status] || ['', status]
  return <Chip tone={tone} title={status.startsWith('error:') ? status : undefined}>{words}</Chip>
}

// The queries that read the warehouse's data. One answered while a transform is
// writing it can fail the run ("another process holds the warehouse open"), so
// a run starts only when the page is not in the middle of them.
const READS = ['warehouse', 'desk', 'models', 'model']

// ── Medallion DAG view ───────────────────────────────────────────────────────

const TYPE_ACCENT = {
  landing: 'var(--op-landing-tx)', bronze: 'var(--op-landing-tx)',
  manipulation: 'var(--role-fact)', silver: 'var(--role-fact)',
  final: 'var(--op-final-tx)', gold: 'var(--op-final-tx)',
}
const STATUS_DOT = { success: 'var(--muted)', failed: 'var(--red)', running: 'var(--amber)' }

// A model pipeline's two steps, in words: what the step is and what its last
// run left ("wrote 3 tables", "6 reports"), where a medallion layer counts rows.
const STEP_WORDS = {
  transform: { what: 'Transform', out: n => `wrote ${count(n, 'table')}` },
  build: { what: 'Build', out: n => count(n, 'report') },
}

// Which form of transform the last run ran (the run records it).
const FORM_LABEL = { sql: 'SQL', python: 'Python', notebook: 'Notebook' }

function stepLine(layer) {
  const words = STEP_WORDS[layer.name]
  const when = layer.last_status === 'running' ? 'running'
    : !layer.last_run ? 'not run yet'
      : `${layer.last_status === 'failed' ? 'failed' : 'ran'} ${ago(layer.last_run)}`
  const out = layer.last_rows_out != null && layer.last_status !== 'failed' ? words.out(layer.last_rows_out) : null
  return [words.what, FORM_LABEL[layer.last_detail?.form], when, out].filter(Boolean).join(' · ')
}

function LayerNode({ data }) {
  const accent = TYPE_ACCENT[data.layer.type] || 'var(--role-table)'
  const status = data.layer.last_status
  const dot = STATUS_DOT[status] || 'var(--muted)'
  const step = data.layer.type === 'step' && STEP_WORDS[data.layer.name]
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
        {step ? (
          <span style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
            <span style={{ fontWeight: 600, fontSize: 12.5, color: 'var(--text)' }}>{stepLine(data.layer)}</span>
            <span style={{ fontSize: 10.5, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>{data.layer.name}</span>
          </span>
        ) : (
          <span style={{ fontWeight: 700, fontSize: 12, color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
            {data.layer.name}
          </span>
        )}
      </div>
      <div style={{ padding: '7px 13px 9px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 5 }}>
          {TYPE_LABEL[data.layer.type] && <span style={{
            fontSize: 10, fontWeight: 600,
            padding: '1px 7px', borderRadius: 20,
            background: `color-mix(in srgb, ${accent} 8%, transparent)`, color: accent, border: `1px solid color-mix(in srgb, ${accent} 23%, transparent)`,
          }}>{TYPE_LABEL[data.layer.type]}</span>}
          {data.layer.schedule && (
            <span style={{ fontSize: 9.5, color: 'var(--muted)', fontFamily: 'var(--font-mono)' }}>
              {data.layer.schedule}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {!step && <span style={{ fontSize: 10.5, color: 'var(--muted)' }}>
            {data.layer.last_rows_out != null ? `${data.layer.last_rows_out} rows`
              : data.layer.last_status === 'failed' ? 'Failed'
                : data.layer.last_status ? 'Ran' : 'Not run yet'}
          </span>}
          {data.onRun && <button
            onClick={e => { e.stopPropagation(); data.onRun(data.layer.name) }}
            disabled={data.running}
            title={`Run ${data.layer.name}`}
            style={{
              marginLeft: 'auto', padding: '2px 10px', borderRadius: 5,
              fontSize: 10, fontWeight: 700, cursor: data.running ? 'default' : 'pointer',
              background: `color-mix(in srgb, ${accent} 7%, transparent)`, color: accent, border: `1px solid color-mix(in srgb, ${accent} 25%, transparent)`,
              opacity: data.running ? .5 : 1,
            }}
          >▶ run</button>}
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
        position: { x: depth * 340, y: row * 125 },
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
        // Two steps fitted to the card would be drawn at twice the app's type size.
        fitViewOptions={{ padding: 0.22, maxZoom: 1 }}
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
      <table className="tb-list">
        <thead>
          <tr><th>Run</th><th>Status</th><th>Rows in</th><th>Rows out</th><th>Completed</th></tr>
        </thead>
        <tbody>
          {runs.map(r => (
            <tr key={r.id}>
              <td style={{ color: 'var(--muted)', fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>{r.id}</td>
              <td><StepStatus status={r.last_status?.startsWith?.('error:') ? r.last_status : r.status} /></td>
              <td style={{ color: 'var(--text-2)' }}>{r.rows_in ?? '—'}</td>
              <td style={{ color: 'var(--text-2)' }}>{r.rows_out ?? '—'}</td>
              <td style={{ color: 'var(--muted)', fontSize: 12 }}>
                <Time iso={r.completed_at} fallback="—" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * One pipeline: its steps as a flow and as a list, its code, and its latest
 * run's output. Only an admin may run it (it writes the warehouse), so only an
 * admin sees a run button; with no sign-in everyone is admin. *primary*: this
 * is the pipeline that refreshes the model, and its run is the page's Refresh
 * data. Every run is on the page's own Runs tab (*model*'s), not a second one here.
 */
export function PipelineDetail({ pipeline, layers, primary, label, model }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: start, isPending: isStarting } = useStartPipelineRun()
  const { data: runs } = usePipelineRuns(pipeline)
  const { data: me } = useMe()
  const admin = !!me && (!me.role || me.role === 'admin')
  const reading = useIsFetching({ predicate: q => READS.includes(q.queryKey[0]) }) > 0
  const [picked, setPicked] = useState(null)
  const [logOpen, setLogOpen] = useState(false)
  const [openStep, setOpenStep] = useState(null)
  // A phone fits the flow into 350px and its run buttons shrink past tapping;
  // the list of steps keeps them full size.
  const [tab, setTab] = useState(() =>
    window.matchMedia?.('(max-width: 768px)').matches ? 'Steps' : 'Flow')
  // On a phone the Steps table drops Schedule and Runs after, so Status shows.
  const phone = useNarrow('(max-width: 640px)')

  if (!pipeline) {
    return (
      <Card>
        <Empty message="Select a pipeline to see its flow, layers, and runs." />
      </Card>
    )
  }

  // A run goes on in the background and its output is under the views, folded:
  // starting one (or joining the one already going) unfolds it.
  const latest = runs?.[0]
  const busy = isStarting || latest?.status === 'running'
  const shownRun = picked || latest?.run_id || null
  const shown = (runs || []).find(r => r.run_id === shownRun)

  function begin(layer) {
    start({ pipeline, layer }, {
      onSuccess: res => {
        setPicked(res.run_id)
        setLogOpen(true)
        if (res.already_running) toast('Already running. Showing its log.', 'info')
      },
      onError: err => toast(`Could not start: ${err.message}`, 'error'),
    })
  }
  const handleRunAll = () => begin(undefined)
  // The medallion layers have a type worth a column; a model pipeline's steps do not.
  const typed = layers.some(l => TYPE_LABEL[l.type] || /Layer$/.test(l.type || ''))
  const handleRunLayer = layer => begin(layer)
  // A run that ends changes what the page says about every step.
  const finished = () => {
    qc.invalidateQueries({ queryKey: ['pipelines'] })
    qc.invalidateQueries({ queryKey: ['pipeline-runs', pipeline] })
  }

  return (
    <Card className="fade-in">
      <CardTitle action={admin && (
        <Btn
          size="sm"
          variant={primary ? 'primary' : 'outline'}
          disabled={busy || reading}
          onClick={handleRunAll}
        >
          {busy ? <><Spinner size={12} /> Running…</> : primary ? 'Refresh data' : '▶ Run all'}
        </Btn>
      )}>
        <span title={pipeline}>{label || pipeline}</span>
      </CardTitle>

      <Segmented options={['Flow', 'Steps', 'Code']} value={tab} onChange={setTab} label="What to show of the pipeline" />

      {tab === 'Flow' && (
        <div className="fade-in">
          <PipelineDag layers={layers} onRun={admin ? handleRunLayer : undefined} running={busy} />
          <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 10 }}>
            Each step runs after the one it depends on. Status updates every 10 s{admin ? '; run any step from its node' : ''}.
          </p>
        </div>
      )}

      {tab === 'Steps' && (
        // relative: the sr-only "Actions" header is clipped by this scroller, not left to widen the page
        <div style={{ overflowX: 'auto', position: 'relative' }}>
          <table className="tb-list">
            <thead>
              <tr><th>Step</th>{typed && <th>Type</th>}{!phone && <><th>Schedule</th><th>Runs after</th></>}<th>Last status</th><th>Rows out</th><th>Last run</th><th><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {layers.map(l => (
                <tr key={l.name}>
                  <td>
                    <code style={{ fontSize: 12 }}>{l.name}</code>
                    {FORM_LABEL[l.last_detail?.form] && (
                      <span style={{ color: 'var(--muted)', fontSize: 12 }}> · {FORM_LABEL[l.last_detail.form]}</span>
                    )}
                  </td>
                  {typed && (
                    <td>
                      <Badge variant={TYPE_BADGE[l.type] || 'gray'}>
                        {TYPE_LABEL[l.type] || l.type?.replace('Layer', '') || l.type}
                      </Badge>
                    </td>
                  )}
                  {!phone && <td style={{ color: 'var(--muted)', fontSize: 12 }}>{l.schedule || '—'}</td>}
                  {!phone && <td style={{ color: 'var(--muted)', fontSize: 12 }}>{l.depends_on || '—'}</td>}
                  <td><StepStatus status={l.last_status} /></td>
                  <td style={{ color: 'var(--text-2)', fontVariantNumeric: 'tabular-nums' }}>
                    {l.last_rows_out ?? '—'}
                  </td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>
                    <Time iso={l.last_run} fallback="—" />
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    {admin && (
                      <>
                        <Btn
                          size="sm"
                          variant="outline"
                          disabled={busy || reading}
                          onClick={() => handleRunLayer(l.name)}
                          aria-label={`Run ${l.name}`}
                        >
                          {busy ? <Spinner size={12} /> : '▶ Run'}
                        </Btn>
                        {' '}
                      </>
                    )}
                    <Btn
                      size="sm"
                      variant="outline"
                      onClick={() => setOpenStep(openStep === l.name ? null : l.name)}
                      aria-expanded={openStep === l.name}
                      aria-label={`History of ${l.name}`}
                    >
                      History
                    </Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {openStep && (
            <div style={{ marginTop: 18 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>
                History of <code style={{ fontSize: 12 }}>{openStep}</code>
              </div>
              <LayerHistory pipeline={pipeline} layer={openStep} />
            </div>
          )}
        </div>
      )}

      {tab === 'Code' && <CodeView kind="pipelines" name={pipeline} />}

      {shownRun && (
        <details className="pipe-run" open={logOpen} onToggle={e => setLogOpen(e.currentTarget.open)}>
          <summary>
            {picked ? 'This run' : 'Latest run'}
            {shown && <span className="wb-meta"> · started <Time iso={shown.started_at} /></span>}
          </summary>
          <RunLog pipeline={pipeline} runs={runs} runId={shownRun} onDone={finished} />
          {model && <p className="wb-meta">Every run of this model is on its <Link to={dataPath(model, 'runs')}>Runs</Link> tab.</p>}
        </details>
      )}
    </Card>
  )
}

/**
 * The pipeline that rebuilds a model's data, then the reports that read it:
 * the Transform tab of its Data page. The one made for the model (else the
 * first) is its Refresh data.
 */
export default function Pipelines({ model }) {
  const { data, isLoading } = usePipelines()
  const labelOf = useModelLabel()
  const pipelines = (data || []).filter(p => pipelineBelongsToModel(p, model))

  if (isLoading) return <SkeletonCard />
  if (!pipelines.length) {
    return (
      <Card>
        <Empty message={<>No pipeline yet. <code>tracebi new-pipeline &quot;{model}&quot;</code> writes <code>pipelines/{model}.yaml</code>:
          it runs a transform, then rebuilds this model&apos;s reports.</>} />
      </Card>
    )
  }
  const own = pipelines.find(p => p.model === model) || pipelines[0]
  return pipelines.map(p => (
    <div key={p.pipeline} style={{ marginBottom: 16 }}>
      {/* A pipeline has no label of its own: the model's is its name when it is the model's. */}
      <PipelineDetail pipeline={p.pipeline} layers={p.layers || []} primary={p === own} model={model}
                      label={p.model ? labelOf(p.model) : humanise(p.pipeline)} />
    </div>
  ))
}
