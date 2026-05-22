import { useDashboards } from '../api'
import { PageTitle, PageSub, Card, Badge, Spinner, Empty, Btn } from '../components/Shared'

export default function Dashboards() {
  const { data, isLoading } = useDashboards()
  const dashboards = data || []

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
              </Card>
            ))}
          </div>
        )
      }
    </>
  )
}
