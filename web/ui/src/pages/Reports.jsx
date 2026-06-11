import { useState, useCallback, useEffect } from 'react'

import {
  useReports, useStartReportRun, useReportRun, useReportRunHistory,
  useReportLineage, reportDownloadUrl,
} from '../api'
import { LineageGraph } from '../components/Lineage'
import {
  PageTitle, PageSub, Card, CardTitle, Badge, Spinner,
  Empty, Btn, Tabs, SplitLayout, ListItem, ErrorDetail,
  SearchInput, SkeletonList, SkeletonCard, useToast,
} from '../components/Shared'

function runDuration(rec) {
  if (!rec.finished_at) return null
  const s = (new Date(rec.finished_at) - new Date(rec.started_at)) / 1000
  return s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`
}

function RunHistory({ name, refreshKey }) {
  const { data: runs, refetch } = useReportRunHistory(name)
  useEffect(() => { refetch() }, [refreshKey, refetch])
  if (!runs?.length) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap', marginBottom: 14 }}>
      <span style={{ fontSize: 11, color: 'var(--muted)' }}>Recent runs:</span>
      {runs.map(r => {
        const dur = runDuration(r)
        return (
          <Badge
            key={r.run_id}
            variant={r.status === 'succeeded' ? 'green' : r.status === 'failed' ? 'red' : 'amber'}
            title={r.status === 'failed' ? r.error?.message : undefined}
            style={{ textTransform: 'none' }}
          >
            {r.status === 'running'
              ? '… running'
              : `${r.status === 'succeeded' ? '✓' : '✕'} ${new Date(r.started_at).toLocaleTimeString()}${dur ? ` · ${dur}` : ''}`}
          </Badge>
        )
      })}
    </div>
  )
}

function ReportDetail({ report }) {
  const [tab, setTab] = useState('Output')
  const [runId, setRunId] = useState(null)
  const [lineageData, setLineageData] = useState(null)
  const toast = useToast()
  const { mutate: startRun, isPending: starting, error: startErr } = useStartReportRun()
  const { data: run } = useReportRun(report?.name, runId)
  const { mutate: fetchLineage, isPending: loadingLineage } = useReportLineage()

  // The run executes in the background on the server; useReportRun polls
  // until it settles. Result/error derive from the polled record.
  const running = starting || run?.status === 'running'
  const result = run?.status === 'succeeded' ? run.result : null
  const runErr = run?.status === 'failed'
    ? { message: run.error?.message || 'Run failed', detail: run.error }
    : startErr

  useEffect(() => {
    if (run?.status === 'succeeded') toast('Report ran successfully', 'success')
    if (run?.status === 'failed') toast(`Run failed: ${run.error?.message || 'unknown error'}`, 'error')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status])

  const handleRun = useCallback(() => {
    startRun(report.name, {
      onSuccess: data => setRunId(data.run_id),
      onError: err => toast(`Run failed to start: ${err.message}`, 'error'),
    })
  }, [report?.name, startRun, toast])

  const handleLineage = useCallback(() => {
    fetchLineage(report.name, {
      onSuccess: data => {
        setLineageData(data)
        setTab('Lineage')
      },
      onError: err => toast(`Lineage failed: ${err.message}`, 'error'),
    })
  }, [report?.name, fetchLineage, toast])

  if (!report) return <Card><Empty message="Select a report from the list to run it and view its output." /></Card>

  return (
    <Card>
      <CardTitle>
        {report.name}
        {report.description && (
          <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--muted)', marginLeft: 8 }}>
            {report.description}
          </span>
        )}
      </CardTitle>

      <RunHistory name={report.name} refreshKey={run?.status} />

      {runErr && <ErrorDetail error={runErr} />}

      {!result && !running && (
        <Btn onClick={handleRun}>▶ Run Report</Btn>
      )}
      {running && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
          <Spinner /> Running in background… you can keep browsing; a toast will confirm when it finishes.
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
            <span style={{ flex: 1 }} />
            <a href={reportDownloadUrl(report.name, 'xlsx')} download className="dl-link">
              ↓ Excel
            </a>
            <a href={reportDownloadUrl(report.name, 'html')} download className="dl-link">
              ↓ HTML
            </a>
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
              title={report.name}
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

export default function Reports() {
  const { data, isLoading } = useReports()
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')

  const reports = data || []
  const filtered = reports.filter(r =>
    r.name.toLowerCase().includes(query.toLowerCase()) ||
    (r.description || '').toLowerCase().includes(query.toLowerCase())
  )
  const current = reports.find(r => r.name === selected)

  return (
    <>
      <PageTitle>Reports</PageTitle>
      <PageSub>
        {isLoading ? 'Loading…' : `${reports.length} report${reports.length !== 1 ? 's' : ''} registered. Select one to run it.`}
      </PageSub>

      {!isLoading && reports.length === 0 ? (
        <Empty message="No reports registered. Add one with @registry.report() in your app module." />
      ) : (
        <SplitLayout
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search reports…" />
                {filtered.length === 0
                  ? <Empty message="No matches." />
                  : filtered.map(r => (
                    <ListItem
                      key={r.name}
                      selected={selected === r.name}
                      onClick={() => setSelected(r.name)}
                      name={r.name}
                      sub={r.description}
                    />
                  ))
                }
              </>
            )
          }
          right={isLoading ? <SkeletonCard /> : <ReportDetail key={current?.name} report={current} />}
        />
      )}
    </>
  )
}
