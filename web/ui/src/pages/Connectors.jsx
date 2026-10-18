import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useConnectors } from '../api'
import { StorageLine, sourceKind } from '../components/Storage'
import { PageHeader, useModelLabel } from '../components/Scope'
import CodeView from '../components/CodeView'
import Warehouse from '../components/Warehouse'
import { dataPath } from '../nav'
import {
  Card, CardTitle, Badge, Btn,
  Empty, ListItem, SplitLayout, SearchInput, SkeletonList, SkeletonCard,
} from '../components/Shared'

const LABEL = { fontSize: 11, fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 6 }
function Section({ label, children }) {
  return <div style={{ marginBottom: 14 }}><div style={LABEL}>{label}</div>{children}</div>
}

function ConnectorDetail({ c }) {
  const labelOf = useModelLabel()
  const [code, setCode] = useState(false)
  const [warehouse, setWarehouse] = useState(false)
  if (!c) return (
    <Card>
      <Empty message="Select a source to see where its data is kept." />
    </Card>
  )
  const isWarehouse = c.type === 'DuckDBConnector' && c.storage?.kind === 'file'
  return (
    <Card className="fade-in">
      <CardTitle action={(
        <span style={{ display: 'inline-flex', gap: 6 }}>
          {isWarehouse && <Btn size="sm" variant="outline" onClick={() => setWarehouse(v => !v)}>{warehouse ? 'Hide warehouse' : 'Warehouse'}</Btn>}
          <Btn size="sm" variant="outline" onClick={() => setCode(v => !v)}>{code ? 'Hide code' : '</> View code'}</Btn>
        </span>
      )}>{c.name}</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        <Badge variant="gray" style={{ textTransform: 'none' }} title={c.type}>{sourceKind(c)}</Badge>
      </div>
      <Section label="Where the data lives"><StorageLine storage={c.storage} /></Section>
      <Section label="Used by">
        {(c.used_by || []).length === 0
          ? <span style={{ color: 'var(--muted)', fontSize: 12.5 }}>No model reads from this connector.</span>
          : (c.used_by || []).map(m => (
            <Link key={m} to={dataPath(m)} style={{ marginRight: 12, fontSize: 13 }}>{labelOf(m)}</Link>
          ))}
      </Section>
      {warehouse && <Section label="Warehouse"><Warehouse connector={c} /></Section>}
      {code && <div style={{ marginBottom: 18 }}><CodeView kind="connectors" name={c.name} /></div>}
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

/**
 * Where the data is kept: every source (/data/sources), or with *model* only
 * the ones that model reads (its Sources tab).
 */
export default function Connectors({ model }) {
  const { data, isLoading } = useConnectors()
  const labelOf = useModelLabel()
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')

  const connectors = (data || []).filter(c => !model || (c.used_by || []).includes(model))
  const filtered = connectors.filter(c =>
    c.name.toLowerCase().includes(query.toLowerCase()) ||
    sourceKind(c).toLowerCase().includes(query.toLowerCase())
  )
  // Open on the first source rather than a blank "select one" pane.
  const current = connectors.find(c => c.name === selected) || filtered[0]

  return (
    <>
      {!model && <PageHeader pageKey="sources" model="" />}

      {!isLoading && connectors.length === 0 ? (
        <Empty message={model
          ? 'This model reads no source, so its tables have no data behind them. Its file names one under connectors.'
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
                    <div key={c.name} data-source={c.name}>
                      <ListItem
                        selected={current?.name === c.name}
                        onClick={() => setSelected(c.name)}
                        name={c.name}
                        sub={sourceKind(c)}
                        meta={(c.used_by || []).length > 0
                          ? (c.used_by || []).map(m => <Badge key={m} variant="gray" style={{ textTransform: 'none' }}>{labelOf(m)}</Badge>)
                          : null}
                      />
                    </div>
                  ))
                }
              </>
            )
          }
          right={isLoading ? <SkeletonCard /> : <ConnectorDetail key={current?.name} c={current} />}
        />
      )}
    </>
  )
}
