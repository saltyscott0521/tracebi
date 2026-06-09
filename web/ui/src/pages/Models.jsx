import { useState } from 'react'
import { useModels, useModel, useTablePreview } from '../api'
import {
  PageTitle, PageSub, Card, CardTitle, Badge, Spinner,
  Empty, Tabs, SplitLayout, ListItem, SearchInput, SkeletonList, SkeletonCard,
} from '../components/Shared'

function TablePreview({ modelName, tableName }) {
  const { data, isLoading, error } = useTablePreview(modelName, tableName)
  if (isLoading) return <div style={{ padding: 20, display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}><Spinner size={14} /> Loading preview…</div>
  if (error) return <div style={{ padding: 16, color: '#fca5a5', fontSize: 13 }}>{error.message}</div>
  if (!data) return null
  return (
    <div className="fade-in">
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Badge variant="gray">{data.rows} rows</Badge>
        <Badge variant="gray">{data.columns.length} cols</Badge>
      </div>
      <div style={{ overflowX: 'auto', borderRadius: 6, border: '1px solid var(--border)' }}>
        <table>
          <thead>
            <tr>{data.columns.map(c => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {data.data.map((row, i) => (
              <tr key={i}>
                {data.columns.map(c => (
                  <td key={c}>{row[c] === null ? <span style={{ color: 'var(--muted)', fontStyle: 'italic' }}>null</span> : String(row[c])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ModelDetail({ name }) {
  const { data, isLoading } = useModel(name)
  const [tab, setTab] = useState('Tables')
  const [previewTable, setPreviewTable] = useState(null)

  if (!name) return <Card><Empty message="Select a model to view its tables and relationships." /></Card>
  if (isLoading) return <SkeletonCard />
  if (!data) return null

  return (
    <Card className="fade-in">
      <CardTitle>{data.name}</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 18, flexWrap: 'wrap' }}>
        {data.connectors.map(c => <Badge key={c} variant="blue">{c}</Badge>)}
        <Badge variant="gray">{data.tables.length} tables</Badge>
        {data.relationships.length > 0 && <Badge variant="gray">{data.relationships.length} relationships</Badge>}
      </div>

      <Tabs tabs={['Tables', 'Relationships']} active={tab} onChange={t => { setTab(t); setPreviewTable(null) }} />

      {tab === 'Tables' && (
        <div>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead><tr><th>Table</th><th>Connector</th><th>Source</th><th></th></tr></thead>
              <tbody>
                {data.tables.map(t => (
                  <tr key={t.name}>
                    <td><code>{t.name}</code></td>
                    <td style={{ color: 'var(--text-2)' }}>{t.connector}</td>
                    <td style={{ color: 'var(--muted)' }}>{t.source}</td>
                    <td>
                      <button onClick={() => setPreviewTable(previewTable === t.name ? null : t.name)} style={{
                        padding: '3px 10px', fontSize: 11, fontWeight: 600, borderRadius: 4,
                        background: 'var(--blue-lt)', color: '#93c5fd',
                        border: '1px solid var(--blue-br)', cursor: 'pointer',
                        transition: 'background var(--t)',
                      }}>
                        {previewTable === t.name ? 'Hide' : 'Preview'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {previewTable && (
            <div style={{ marginTop: 20, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 12 }}>
                Preview: <strong style={{ color: 'var(--text)' }}>{previewTable}</strong>
              </div>
              <TablePreview modelName={name} tableName={previewTable} />
            </div>
          )}
        </div>
      )}

      {tab === 'Relationships' && (
        data.relationships.length === 0
          ? <Empty message="No relationships defined on this model." />
          : (
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead><tr><th>Name</th><th>Left</th><th>Right</th><th>Keys</th><th>How</th></tr></thead>
                <tbody>
                  {data.relationships.map(r => (
                    <tr key={r.name}>
                      <td><code>{r.name}</code></td>
                      <td>{r.left_table}</td>
                      <td>{r.right_table}</td>
                      <td style={{ color: 'var(--muted)', fontSize: 12 }}>{r.left_key} = {r.right_key}</td>
                      <td><Badge variant="gray">{r.how}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
      )}
    </Card>
  )
}

export default function Models() {
  const { data, isLoading } = useModels()
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')

  const models = data || []
  const filtered = models.filter(m =>
    m.name.toLowerCase().includes(query.toLowerCase())
  )

  return (
    <>
      <PageTitle>Models</PageTitle>
      <PageSub>
        {isLoading ? 'Loading…' : `${models.length} data model${models.length !== 1 ? 's' : ''} registered.`}
      </PageSub>

      {!isLoading && models.length === 0 ? (
        <Empty message="No models registered. Add one with registry.add_model() in your app module." />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search models…" />
                {filtered.length === 0
                  ? <Empty message="No matches." />
                  : filtered.map(m => (
                    <ListItem
                      key={m.name}
                      selected={selected === m.name}
                      onClick={() => setSelected(m.name)}
                      name={m.name}
                      sub={`${m.tables.length} tables · ${m.relationships.length} rel`}
                    />
                  ))
                }
              </>
            )
          }
          right={<ModelDetail name={selected} />}
        />
      )}
    </>
  )
}
