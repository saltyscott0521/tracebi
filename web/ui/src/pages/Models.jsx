import { useState } from 'react'
import { useModels, useModel, useTablePreview } from '../api'
import { PageTitle, PageSub, Card, CardTitle, Badge, Spinner, Empty, Tabs, SplitLayout, ListItem } from '../components/Shared'

function TablePreview({ modelName, tableName }) {
  const { data, isLoading, error } = useTablePreview(modelName, tableName)
  if (isLoading) return <div style={{ padding: 20 }}><Spinner /></div>
  if (error) return <div style={{ padding: 16, color: '#fca5a5', fontSize: 13 }}>{error.message}</div>
  if (!data) return null
  return (
    <div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
        <Badge variant="gray">{data.rows} rows</Badge>
        <Badge variant="gray">{data.columns.length} columns</Badge>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>{data.columns.map(c => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {data.data.map((row, i) => (
              <tr key={i}>
                {data.columns.map(c => (
                  <td key={c}>{row[c] === null ? <span style={{ color: 'var(--muted)' }}>null</span> : String(row[c])}</td>
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

  if (!name) return <Card><Empty icon="⊞" message="Select a model to view details." /></Card>
  if (isLoading) return <Card><Spinner /></Card>
  if (!data) return null

  return (
    <Card>
      <CardTitle>{data.name}</CardTitle>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {data.connectors.map(c => <Badge key={c} variant="blue">{c}</Badge>)}
        <Badge variant="gray">{data.tables.length} tables</Badge>
        <Badge variant="gray">{data.relationships.length} relationships</Badge>
      </div>

      <Tabs tabs={['Tables', 'Relationships']} active={tab} onChange={t => { setTab(t); setPreviewTable(null) }} />

      {tab === 'Tables' && (
        <div>
          <table style={{ marginBottom: previewTable ? 20 : 0 }}>
            <thead><tr><th>Table</th><th>Connector</th><th>Source</th><th></th></tr></thead>
            <tbody>
              {data.tables.map(t => (
                <tr key={t.name}>
                  <td><code>{t.name}</code></td>
                  <td>{t.connector}</td>
                  <td style={{ color: 'var(--muted)' }}>{t.source}</td>
                  <td>
                    <button onClick={() => setPreviewTable(previewTable === t.name ? null : t.name)} style={{
                      padding: '3px 10px', fontSize: 11, fontWeight: 600, borderRadius: 4,
                      background: 'var(--blue-lt)', color: '#93c5fd',
                      border: '1px solid var(--blue-br)', cursor: 'pointer',
                    }}>
                      {previewTable === t.name ? 'Hide' : 'Preview'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {previewTable && (
            <div style={{ marginTop: 20, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
                Preview: <strong style={{ color: 'var(--text)' }}>{previewTable}</strong>
              </div>
              <TablePreview modelName={name} tableName={previewTable} />
            </div>
          )}
        </div>
      )}

      {tab === 'Relationships' && (
        data.relationships.length === 0
          ? <Empty icon="⊹" message="No relationships defined on this model." />
          : (
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
          )
      )}
    </Card>
  )
}

export default function Models() {
  const { data, isLoading } = useModels()
  const [selected, setSelected] = useState(null)
  const models = data || []

  if (isLoading) return <div style={{ padding: 40 }}><Spinner /></div>

  return (
    <>
      <PageTitle>Models</PageTitle>
      <PageSub>{models.length} data model{models.length !== 1 ? 's' : ''} registered.</PageSub>

      {models.length === 0
        ? <Empty icon="⊞" message="No models registered. Add one in your app module." />
        : (
          <SplitLayout
            left={models.map(m => (
              <ListItem
                key={m.name}
                selected={selected === m.name}
                onClick={() => setSelected(m.name)}
                name={m.name}
                sub={`${m.tables.length} tables · ${m.relationships.length} relationships`}
              />
            ))}
            right={<ModelDetail name={selected} />}
          />
        )
      }
    </>
  )
}
