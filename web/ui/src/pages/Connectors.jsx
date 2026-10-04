import { useState } from 'react'
import Chain from '../components/Chain'
import { Link } from 'react-router-dom'
import { useConnectors } from '../api'
import { StorageLine, KIND_LABEL } from '../components/Storage'
import {
  PageTitle, PageSub, Card, CardTitle, Badge,
  Empty, ListItem, SplitLayout, SearchInput, SkeletonList, SkeletonCard,
} from '../components/Shared'

const LABEL = { fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 6 }
function Section({ label, children }) {
  return <div style={{ marginBottom: 14 }}><div style={LABEL}>{label}</div>{children}</div>
}

function ConnectorDetail({ c }) {
  if (!c) return (
    <Card>
      <Empty message="Select a source to see where its data is kept." />
    </Card>
  )
  return (
    <Card className="fade-in">
      <CardTitle>{c.name}</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <Badge variant="blue">{c.type}</Badge>
        {c.storage?.kind && <Badge variant="gray">{KIND_LABEL[c.storage.kind]}</Badge>}
      </div>
      <Section label="Where the data lives"><StorageLine storage={c.storage} /></Section>
      <Section label="Used by">
        {(c.used_by || []).length === 0
          ? <span style={{ color: 'var(--muted)', fontSize: 12.5 }}>No model reads from this connector.</span>
          : (c.used_by || []).map(m => (
            <Link key={m} to={`/models/${encodeURIComponent(m)}`} style={{ marginRight: 12, fontSize: 13 }}>{m}</Link>
          ))}
      </Section>
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
      <Chain current="sources" />
      <PageTitle>Sources</PageTitle>
      <PageSub>
        {isLoading ? 'Loading…' : `${connectors.length} source${connectors.length !== 1 ? 's' : ''}: where each model's data is kept. A source is a connector: a file, folder or database. A model file declares meaning; the source says where the data is.`}
      </PageSub>

      {!isLoading && connectors.length === 0 ? (
        <Empty message="No sources yet. A model declares its own connector (add_connector); one can also be registered in an app module." />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search sources…" />
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
