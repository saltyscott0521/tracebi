import { useState } from 'react'
import { useConnectors } from '../api'
import {
  PageTitle, PageSub, Card, CardTitle, Badge,
  Empty, ListItem, SplitLayout, SearchInput, SkeletonList, SkeletonCard,
} from '../components/Shared'

function ConnectorDetail({ c }) {
  if (!c) return (
    <Card>
      <Empty message="Select a connector to view details." />
    </Card>
  )
  return (
    <Card className="fade-in">
      <CardTitle>{c.name}</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <Badge variant="blue">{c.type}</Badge>
      </div>
      {c.url && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 6 }}>
            Connection URL
          </div>
          <code style={{ fontSize: 12 }}>{c.url}</code>
        </div>
      )}
      {c.directory && (
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 6 }}>
            Directory
          </div>
          <code style={{ fontSize: 12 }}>{c.directory}</code>
        </div>
      )}
      {c.tables && c.tables.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 8 }}>
            Tables ({c.tables.length})
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
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
  const [query, setQuery] = useState('')

  const connectors = data || []
  const filtered = connectors.filter(c =>
    c.name.toLowerCase().includes(query.toLowerCase()) ||
    c.type.toLowerCase().includes(query.toLowerCase())
  )
  const current = connectors.find(c => c.name === selected)

  return (
    <>
      <PageTitle>Connectors</PageTitle>
      <PageSub>
        {isLoading ? 'Loading…' : `${connectors.length} connector${connectors.length !== 1 ? 's' : ''} registered.`}
      </PageSub>

      {!isLoading && connectors.length === 0 ? (
        <Empty message="No connectors registered. Add one with registry.add_connector() in your app module." />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search connectors…" />
                {filtered.length === 0
                  ? <Empty message="No matches." />
                  : filtered.map(c => (
                    <ListItem
                      key={c.name}
                      selected={selected === c.name}
                      onClick={() => setSelected(c.name)}
                      name={c.name}
                      sub={c.type}
                    />
                  ))
                }
              </>
            )
          }
          right={isLoading ? <SkeletonCard /> : <ConnectorDetail c={current} />}
        />
      )}
    </>
  )
}
