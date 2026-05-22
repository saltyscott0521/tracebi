import { useState } from 'react'
import { useConnectors } from '../api'
import { PageTitle, PageSub, Card, CardTitle, Badge, Spinner, Empty, ListItem, SplitLayout } from '../components/Shared'

function ConnectorDetail({ c }) {
  if (!c) return (
    <Card><Empty icon="⇌" message="Select a connector to view details." /></Card>
  )
  return (
    <Card>
      <CardTitle>{c.name}</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <Badge variant="blue">{c.type}</Badge>
      </div>
      {c.url && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Connection URL</div>
          <code style={{ fontSize: 12 }}>{c.url}</code>
        </div>
      )}
      {c.directory && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Directory</div>
          <code style={{ fontSize: 12 }}>{c.directory}</code>
        </div>
      )}
      {c.tables && c.tables.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 8 }}>
            Tables ({c.tables.length})
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {c.tables.map(t => <Badge key={t} variant="gray">{t}</Badge>)}
          </div>
        </div>
      )}
    </Card>
  )
}

export default function Connectors() {
  const { data, isLoading } = useConnectors()
  const [selected, setSelected] = useState(null)

  if (isLoading) return <div style={{ padding: 40 }}><Spinner /></div>

  const connectors = data || []
  const current = connectors.find(c => c.name === selected)

  return (
    <>
      <PageTitle>Connectors</PageTitle>
      <PageSub>{connectors.length} connector{connectors.length !== 1 ? 's' : ''} registered.</PageSub>

      {connectors.length === 0
        ? <Empty icon="⇌" message="No connectors registered. Add one in your app module." />
        : (
          <SplitLayout
            left={connectors.map(c => (
              <ListItem
                key={c.name}
                selected={selected === c.name}
                onClick={() => setSelected(c.name)}
                name={c.name}
                sub={c.type}
              />
            ))}
            right={<ConnectorDetail c={current} />}
          />
        )
      }
    </>
  )
}
