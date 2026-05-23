import { useState } from 'react'
import { usePipelines, useRunLayer, useRunPipeline, useLayerHistory } from '../api'
import { PageTitle, PageSub, Card, CardTitle, Badge, Spinner, Empty, Btn, Tabs } from '../components/Shared'

// PipelineRunner stamps layer_type with either the legacy medallion name
// ("bronze" / "silver" / "gold") or the new TraceBi vocabulary
// ("landing" / "manipulation" / "final"). Map both to badge variants.
const TYPE_BADGE = {
  bronze:       'bronze',  silver:       'silver',       gold:  'gold',
  landing:      'landing', manipulation: 'manipulation', final: 'final',
  BronzeLayer:  'bronze',  SilverLayer:  'silver',       GoldLayer: 'gold',
}
const TYPE_LABEL = {
  bronze: 'Landing',     silver: 'Manipulation',  gold: 'Final',
  landing: 'Landing',    manipulation: 'Manipulation', final: 'Final',
}
const STATUS_BADGE = { success: 'green', error: 'red', running: 'amber' }

function LayerHistory({ pipeline, layer }) {
  const { data, isLoading } = useLayerHistory(pipeline, layer)
  if (isLoading) return <Spinner />
  const runs = data?.runs || []
  if (runs.length === 0) return <p style={{ fontSize: 13, color: 'var(--muted)' }}>No runs yet.</p>
  return (
    <div style={{ overflowX: 'auto' }}>
      <table>
        <thead>
          <tr><th>Run ID</th><th>Status</th><th>Rows In</th><th>Rows Out</th><th>Completed</th></tr>
        </thead>
        <tbody>
          {runs.map(r => (
            <tr key={r.id}>
              <td style={{ color: 'var(--muted)', fontSize: 12 }}>{r.id}</td>
              <td><Badge variant={STATUS_BADGE[r.status] || 'gray'}>{r.status || '—'}</Badge></td>
              <td>{r.rows_in ?? '—'}</td>
              <td>{r.rows_out ?? '—'}</td>
              <td style={{ color: 'var(--muted)', fontSize: 12 }}>{r.completed_at ? new Date(r.completed_at).toLocaleString() : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PipelineCard({ pipeline, layers }) {
  const { mutate: run, isPending } = useRunLayer()
  const { mutate: runAll, isPending: isRunningAll } = useRunPipeline()
  const [selected, setSelected] = useState(null)
  const [tab, setTab] = useState('Layers')

  return (
    <Card>
      <CardTitle>
        <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span><span style={{ marginRight: 8 }}>⧖</span>{pipeline}</span>
          <Btn
            size="sm"
            variant="outline"
            disabled={isRunningAll}
            onClick={() => runAll({ pipeline })}
          >
            {isRunningAll ? <Spinner size={12} /> : '▶ Run all'}
          </Btn>
        </span>
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
                  <td><Badge variant={TYPE_BADGE[l.type] || 'gray'}>{TYPE_LABEL[l.type] || l.type?.replace('Layer','') || l.type}</Badge></td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>{l.schedule || '—'}</td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>{l.depends_on || '—'}</td>
                  <td>
                    {l.last_status
                      ? <Badge variant={STATUS_BADGE[l.last_status] || 'gray'}>{l.last_status}</Badge>
                      : <Badge variant="gray">never run</Badge>
                    }
                  </td>
                  <td style={{ color: 'var(--muted)' }}>{l.last_rows_out ?? '—'}</td>
                  <td style={{ color: 'var(--muted)', fontSize: 12 }}>
                    {l.last_run ? new Date(l.last_run).toLocaleString() : '—'}
                  </td>
                  <td>
                    <Btn
                      size="sm"
                      variant="outline"
                      disabled={isPending}
                      onClick={() => run({ pipeline, layer: l.name })}
                    >
                      {isPending ? <Spinner size={12} /> : '▶ Run'}
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
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            {layers.map(l => (
              <button key={l.name} onClick={() => setSelected(l.name)} style={{
                padding: '4px 12px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                background: selected === l.name ? 'var(--blue-lt)' : 'rgba(255,255,255,.04)',
                color: selected === l.name ? '#93c5fd' : 'var(--muted)',
                border: `1px solid ${selected === l.name ? 'var(--blue-br)' : 'var(--border)'}`,
                cursor: 'pointer',
              }}>{l.name}</button>
            ))}
          </div>
          {selected
            ? <LayerHistory pipeline={pipeline} layer={selected} />
            : <p style={{ fontSize: 13, color: 'var(--muted)' }}>Select a layer to view its run history.</p>
          }
        </div>
      )}
    </Card>
  )
}

export default function Pipelines() {
  const { data, isLoading } = usePipelines()
  const pipelines = data || []

  if (isLoading) return <div style={{ padding: 40 }}><Spinner /></div>

  return (
    <>
      <PageTitle>Pipelines</PageTitle>
      <PageSub>
        {pipelines.length} pipeline{pipelines.length !== 1 ? 's' : ''} registered —
        {' '}Landing → Manipulation → Final layers (medallion-compatible).
        {' '}Run history auto-refreshes every 10 seconds.
      </PageSub>

      {pipelines.length === 0
        ? <Empty icon="⧖" message="No pipelines registered. Add one in your app module." />
        : pipelines.map(p => (
          <PipelineCard key={p.pipeline} pipeline={p.pipeline} layers={p.layers} />
        ))
      }
    </>
  )
}
