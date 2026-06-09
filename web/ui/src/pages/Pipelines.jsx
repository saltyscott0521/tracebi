import { useState } from 'react'
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
  const [tab, setTab] = useState('Layers')

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

      <Tabs tabs={['Layers', 'History']} active={tab} onChange={t => setTab(t)} />

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
