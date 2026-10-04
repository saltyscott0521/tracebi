import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useConnectors } from '../api'
import { StorageLine, KIND_LABEL } from '../components/Storage'
import { PageHeader } from '../components/Scope'
import { pagePath } from '../nav'
import {
  Card, CardTitle, Badge,
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
            <Link key={m} to={pagePath('model', m)} style={{ marginRight: 12, fontSize: 13 }}>{m}</Link>
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

export default function Connectors({ model = '' }) {
  const { data, isLoading } = useConnectors()
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')

  // A source can feed several models; with one picked, show the ones it reads.
  const connectors = (data || []).filter(c => !model || (c.used_by || []).includes(model))
  const filtered = connectors.filter(c =>
    c.name.toLowerCase().includes(query.toLowerCase()) ||
    c.type.toLowerCase().includes(query.toLowerCase())
  )
  // Open on the first source rather than a blank "select one" pane.
  const current = connectors.find(c => c.name === selected) || filtered[0]

  return (
    <>
      <PageHeader pageKey="sources" model={model} />

      {!isLoading && connectors.length === 0 ? (
        <Empty message={model
          ? `${model} names no source. A model declares where its data is with add_connector(…).`
          : 'No sources yet. A model declares its own (add_connector); one can also be registered in an app module.'} />
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
                      selected={current?.name === c.name}
                      onClick={() => setSelected(c.name)}
                      name={c.name}
                      sub={KIND_LABEL[c.storage?.kind] || c.type}
                      meta={!model && (c.used_by || []).length > 0
                        ? (c.used_by || []).map(m => <Badge key={m} variant="gray" style={{ textTransform: 'none' }}>{m}</Badge>)
                        : null}
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
