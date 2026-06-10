import { useEffect, useState } from 'react'
import { useDashboards, useDashboardLineage } from '../api'
import { opStyle } from '../components/Lineage'
import { PageTitle, PageSub, Card, Badge, Spinner, Empty, Btn } from '../components/Shared'

function LineageModal({ name, onClose }) {
  const { mutate, data, isPending, error } = useDashboardLineage()

  useEffect(() => {
    mutate(name)
  }, [name])

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(22,35,60,.4)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 100, padding: 24,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--card)', border: '1px solid var(--border)',
          borderRadius: 10, padding: '20px 24px', maxWidth: 1000, width: '100%',
          maxHeight: '85vh', overflow: 'auto',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)' }}>
            Dashboard lineage — <code>{name}</code>
          </div>
          <Btn size="sm" variant="outline" onClick={onClose}>Close</Btn>
        </div>

        {isPending && <Spinner />}
        {error && <p style={{ color: 'var(--red-text)', fontSize: 13 }}>{String(error)}</p>}

        {data && (
          <>
            <p style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 14 }}>
              {data.combined_graph.nodes.length} unique lineage node(s) across {data.panels.length} panel(s).
            </p>
            {data.panels.map((p, i) => (
              <div key={i} style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 6 }}>
                  {p.panel_title || p.panel_id || 'panel'} <span style={{ color: 'var(--muted)', fontWeight: 400 }}>· dataset {p.dataset_name}</span>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {p.graph.nodes.map(n => {
                    const op = opStyle(n.data.operation)
                    return (
                      <span
                        key={n.id}
                        title={n.data.description}
                        style={{
                          display: 'inline-block', padding: '3px 9px', borderRadius: 4,
                          fontSize: 11, fontWeight: 600,
                          background: op.bg, color: op.tx, border: `1px solid ${op.br}`,
                        }}
                      >
                        {n.data.operation}
                      </span>
                    )
                  })}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}

export default function Dashboards() {
  const { data, isLoading } = useDashboards()
  const dashboards = data || []
  const [lineageFor, setLineageFor] = useState(null)

  if (isLoading) return <div style={{ padding: 40 }}><Spinner /></div>

  return (
    <>
      <PageTitle>Dashboards</PageTitle>
      <PageSub>{dashboards.length} dashboard{dashboards.length !== 1 ? 's' : ''} registered.</PageSub>

      {dashboards.length === 0
        ? <Empty icon="◫" message="No dashboards registered. Add one in your app module." />
        : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))', gap: 16 }}>
            {dashboards.map(d => (
              <Card key={d.name} style={{ marginBottom: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)' }}>{d.name}</div>
                  <Badge variant="blue">Dash</Badge>
                </div>
                {d.description && (
                  <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 16 }}>
                    {d.description}
                  </p>
                )}
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <a
                    href={`/dashboards/${d.name}/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      padding: '7px 14px', borderRadius: 6, fontSize: 13, fontWeight: 600,
                      background: 'linear-gradient(135deg,var(--blue),var(--blue-md))',
                      color: '#fff', textDecoration: 'none',
                      boxShadow: '0 2px 12px rgba(59,130,246,.3)',
                    }}
                  >
                    ↗ Open Dashboard
                  </a>
                  <Btn size="sm" variant="outline" onClick={() => setLineageFor(d.name)}>
                    ⊶ Lineage
                  </Btn>
                </div>
              </Card>
            ))}
          </div>
        )
      }

      {lineageFor && (
        <LineageModal name={lineageFor} onClose={() => setLineageFor(null)} />
      )}
    </>
  )
}
