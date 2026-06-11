import { useState, useCallback, useEffect } from 'react'

import { useRequests, useRequestParams, useRunRequest, useRequestLineage } from '../api'
import { LineageGraph } from '../components/Lineage'
import {
  PageTitle, PageSub, Card, CardTitle, Badge, Spinner,
  Empty, Btn, Tabs, SplitLayout, ListItem, ErrorDetail,
  SearchInput, SkeletonList, SkeletonCard, useToast,
} from '../components/Shared'

function timeAgo(iso) {
  if (!iso) return ''
  const secs = (Date.now() - new Date(iso).getTime()) / 1000
  if (secs < 60) return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

// Form for a script's declared request_params() — type-aware inputs.
function ParamsForm({ schema, values, onChange, disabled }) {
  if (!schema?.length) return null
  return (
    <div style={{
      display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-end',
      marginBottom: 14, padding: '12px 14px',
      background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 8,
    }}>
      <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: .6, alignSelf: 'center' }}>
        Parameters
      </span>
      {schema.map(p => (
        <label key={p.name} style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>
          {p.name}
          {p.type === 'bool' ? (
            <input
              type="checkbox"
              checked={!!values[p.name]}
              disabled={disabled}
              onChange={e => onChange(p.name, e.target.checked)}
              style={{ width: 16, height: 16, accentColor: 'var(--blue)' }}
            />
          ) : (
            <input
              type={p.type === 'int' || p.type === 'float' ? 'number' : 'text'}
              step={p.type === 'float' ? 'any' : undefined}
              value={values[p.name] ?? ''}
              disabled={disabled}
              onChange={e => onChange(p.name, e.target.value)}
              className="search-input"
              style={{ padding: '6px 10px', width: 170 }}
            />
          )}
        </label>
      ))}
    </div>
  )
}

function RequestDetail({ request }) {
  const [tab, setTab] = useState('Output')
  const [result, setResult] = useState(null)
  const [lineageData, setLineageData] = useState(null)
  const [paramValues, setParamValues] = useState(null)
  const toast = useToast()
  const { data: paramData } = useRequestParams(request?.name)
  const { mutate: run, isPending: running, error: runErr } = useRunRequest()
  const { mutate: fetchLineage, isPending: loadingLineage } = useRequestLineage()

  const schema = paramData?.params || []

  // Seed the form with the script's declared defaults once they load.
  useEffect(() => {
    if (schema.length && paramValues === null) {
      setParamValues(Object.fromEntries(schema.map(p => [p.name, p.default])))
    }
  }, [schema, paramValues])

  const effectiveParams = paramValues || {}
  const setParam = useCallback(
    (k, v) => setParamValues(prev => ({ ...(prev || {}), [k]: v })),
    [],
  )

  const handleRun = useCallback(() => {
    run({ name: request.name, params: effectiveParams }, {
      onSuccess: data => {
        setResult(data)
        setLineageData(null)
        toast('Request ran successfully', 'success')
      },
      onError: err => toast(`Run failed: ${err.message}`, 'error'),
    })
  }, [request?.name, run, toast, effectiveParams])

  const handleLineage = useCallback(() => {
    fetchLineage({ name: request.name, params: effectiveParams }, {
      onSuccess: data => {
        setLineageData(data)
        setTab('Lineage')
      },
      onError: err => toast(`Lineage failed: ${err.message}`, 'error'),
    })
  }, [request?.name, fetchLineage, toast, effectiveParams])

  if (!request) return <Card><Empty message="Select a request script to run it and preview the output." /></Card>

  return (
    <Card>
      <CardTitle>
        {request.name}
        <Badge style={{ marginLeft: 8 }}>{request.type}</Badge>
        <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--muted)', marginLeft: 8 }}>
          {request.file} · modified {timeAgo(request.modified)}
        </span>
      </CardTitle>

      <ParamsForm schema={schema} values={effectiveParams} onChange={setParam} disabled={running} />

      {runErr && <ErrorDetail error={runErr} />}

      {!result && !running && (
        <Btn onClick={handleRun}>▶ Run Request</Btn>
      )}
      {running && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
          <Spinner /> Running script…
        </div>
      )}

      {result && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <Btn onClick={handleRun} disabled={running} variant="outline" size="sm">
              {running ? <><Spinner size={12} /> Running…</> : '↺ Re-run'}
            </Btn>
            {!lineageData && (
              <Btn onClick={handleLineage} disabled={loadingLineage} variant="outline" size="sm">
                {loadingLineage ? <><Spinner size={12} /> Loading…</> : '⊶ View Lineage'}
              </Btn>
            )}
          </div>

          <Tabs
            tabs={lineageData ? ['Output', 'Lineage', 'Manifest'] : ['Output', 'Manifest']}
            active={tab}
            onChange={setTab}
          />

          {tab === 'Output' && (
            <iframe
              srcDoc={result.html}
              style={{ width: '100%', height: 640, border: 'none', borderRadius: 6, background: '#fff' }}
              title={request.name}
            />
          )}

          {tab === 'Lineage' && lineageData && (
            <div className="fade-in">
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>Combined lineage graph</div>
                <LineageGraph graph={lineageData.combined_graph} />
              </div>
              {lineageData.sections?.map(s => (
                <div key={s.section_title} style={{ marginTop: 20 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--muted)', marginBottom: 8 }}>
                    {s.section_title} · <span style={{ fontWeight: 400 }}>{s.dataset_name}</span>
                  </div>
                  <LineageGraph graph={s.graph} />
                </div>
              ))}
            </div>
          )}

          {tab === 'Manifest' && (
            <pre className="code-block" style={{ maxHeight: 400, overflowY: 'auto' }}>
              {JSON.stringify(result.manifest, null, 2)}
            </pre>
          )}
        </>
      )}
    </Card>
  )
}

export default function Requests() {
  const { data, isLoading, refetch } = useRequests()
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')

  const requests = data || []
  const filtered = requests.filter(r =>
    r.name.toLowerCase().includes(query.toLowerCase())
  )
  const current = requests.find(r => r.file === selected)

  return (
    <>
      <PageTitle>Requests</PageTitle>
      <PageSub>
        {isLoading
          ? 'Loading…'
          : `${requests.length} script${requests.length !== 1 ? 's' : ''} in requests/. Scripts run fresh on every click — edits on disk are picked up immediately.`}
      </PageSub>

      {!isLoading && requests.length === 0 ? (
        <Empty message="No request scripts found. Scaffold one with: tracebi new-request &quot;My report&quot;" />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search requests…" />
                {filtered.length === 0
                  ? <Empty message="No matches." />
                  : filtered.map(r => (
                    <ListItem
                      key={r.file}
                      selected={selected === r.file}
                      onClick={() => { setSelected(r.file); refetch() }}
                      name={r.name}
                      sub={`${r.type} · ${timeAgo(r.modified)}`}
                    />
                  ))
                }
              </>
            )
          }
          right={isLoading ? <SkeletonCard /> : <RequestDetail key={current?.file} request={current} />}
        />
      )}
    </>
  )
}
