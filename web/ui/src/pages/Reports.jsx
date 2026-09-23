import { useState, useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import {
  useReports, useStartReportRun, useReportRun, useReportRunHistory,
  useReportLineage, useReportSelection, useKeepSelection, useBuiltReport,
  useReportSource, fetchBuiltReport, reportDownloadUrl,
} from '../api'
import { LineageGraph } from '../components/Lineage'
import {
  PageTitle, PageSub, Card, CardTitle, Badge, Spinner,
  Empty, Btn, Tabs, SplitLayout, ListItem, ErrorDetail,
  SearchInput, SkeletonList, SkeletonCard, useToast, ReportFrame,
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

// The receipt, at a glance — derived from the schema-2 manifest the run
// returns. Provenance is not a stored field: a figure is query-reproducible
// when it names a binding and is not marked unverified and that binding was
// embedded verifiable; python-derived when its binding embedded verifiable:false.
function figureProvenance(manifest) {
  const figures = manifest?.figures || []
  const verifiable = {}
  ;(manifest?.embedded_data || []).forEach(e => { verifiable[e.name] = e.verifiable !== false })
  let reproducible = 0, unverified = 0, derived = 0
  figures.forEach(f => {
    if (f.unverified) unverified++
    else if (f.binding && verifiable[f.binding] === false) derived++
    else if (f.binding) reproducible++
  })
  return { total: figures.length, reproducible, unverified, derived }
}

function ReportReceipt({ manifest }) {
  if (!manifest) return null
  const p = figureProvenance(manifest)
  const v2 = manifest.schema_version === 2
  const contracts = Object.entries(manifest.transform_contracts || {})
  const contractVariant = s => (s === 'satisfied' ? 'green' : s === 'stale' ? 'amber' : 'gray')
  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 12, padding: '12px 14px',
      marginBottom: 16, background: 'var(--surface-2, var(--surface))',
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <Badge variant={v2 ? 'green' : 'gray'} style={{ textTransform: 'none' }}>
          {v2 ? '🧾 Verifiable artifact' : `manifest v${manifest.schema_version ?? '?'}`}
        </Badge>
        {p.total > 0 && (
          <>
            <Badge variant="green" style={{ textTransform: 'none' }}>{p.reproducible} reproducible</Badge>
            {p.derived > 0 && <Badge variant="gray" style={{ textTransform: 'none' }}>{p.derived} python-derived</Badge>}
            {p.unverified > 0 && <Badge variant="amber" style={{ textTransform: 'none' }}>{p.unverified} unverified</Badge>}
          </>
        )}
        {contracts.map(([table, c]) => (
          <Badge key={table} variant={contractVariant(c?.status)} title={table} style={{ textTransform: 'none' }}>
            {table}: {(c?.status || 'no_contract').replace(/_/g, ' ')}
          </Badge>
        ))}
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 8, lineHeight: 1.5 }}>
        The <strong>HTML</strong> download carries this receipt — every figure’s data is embedded and
        fingerprinted, so it re-checks offline with <code>tracebi verify --file</code>. Excel is a plain
        spreadsheet with no receipt.
      </div>
    </div>
  )
}

function parseCut(text) {
  const filters = {}
  String(text || '').split('\n').forEach(line => {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) return
    const eq = trimmed.indexOf('=')
    if (eq < 1) return
    const key = trimmed.slice(0, eq).trim()
    let val = trimmed.slice(eq + 1).trim()
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) val = val.slice(1, -1)
    if (Object.prototype.hasOwnProperty.call(filters, key)) {
      const prev = filters[key]
      filters[key] = Array.isArray(prev) ? prev.concat([val]) : [prev, val]
    } else {
      filters[key] = val
    }
  })
  return filters
}

// Ask is off for now: when it returns it answers only from what is on the
// report or in its model's data.
const SHOW_ASK = false

function AskCut({ reportName, frameRef, onPackageChange }) {
  const [text, setText] = useState('')
  const [reply, setReply] = useState(null)
  const [kept, setKept] = useState(null)
  const select = useReportSelection()
  const keep = useKeepSelection()
  const quoted = (reply?.figures || []).filter(fig =>
    fig.kind === 'value' && fig.fingerprint &&
    (fig.formatted != null || typeof fig.value === 'number'))
  const added = reply?.added_binding
    ? (reply.figures || []).find(fig => fig.binding === reply.added_binding)
    : null

  const apply = () => {
    const trimmed = text.trim()
    const request = (!trimmed || trimmed.includes('='))
      ? { name: reportName, filters: parseCut(text) }
      : { name: reportName, question: trimmed }
    setKept(null)
    select.mutate(request, {
      onSuccess: (payload) => {
        setReply(payload)
        if (payload?.added_binding) {
          onPackageChange?.()
          return
        }
        const filters = payload?.filters || {}
        const tb = frameRef.current?.contentWindow?.tracebi
        if (tb && typeof tb.setSelection === 'function') tb.setSelection(filters)
      },
    })
  }

  const cutLine = reply
    ? Object.entries(reply.filters || {}).map(([key, value]) => (
      `${key} = ${Array.isArray(value) ? value.join(', ') : value}`
    )).join('; ')
    : ''

  return (
    <div style={{
      border: '1px solid var(--border)', borderRadius: 12, padding: '12px 14px',
      marginBottom: 14,
    }}>
      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Ask</div>
      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder={'what about Software'}
        rows={2}
        style={{
          width: '100%', boxSizing: 'border-box', font: '12px/1.4 ui-monospace, monospace',
          marginBottom: 8,
        }}
      />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Btn onClick={apply} disabled={select.isPending}>Apply cut</Btn>
        {reply && !reply.added_binding && (
          <Btn onClick={() => keep.mutate(
            { name: reportName, filters: reply.filters || {} },
            { onSuccess: (payload) => { setKept(payload); onPackageChange?.() } },
          )} disabled={keep.isPending}>
            Keep this cut
          </Btn>
        )}
      </div>
      {select.error && (
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--red-text, #9b2c2c)' }}>
          {select.error.message}
        </div>
      )}
      {(reply?.pins || []).length > 0 && (
        <div style={{ marginTop: 10, fontSize: 12, lineHeight: 1.5 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>Pins first</div>
          {reply.pins.map(pin => (
            <div key={`${pin.report}-${pin.id}`}>
              {pin.report}{pin.note ? ` · ${pin.note}` : ''}
            </div>
          ))}
        </div>
      )}
      {reply?.added_binding && (
        <div style={{ marginTop: 10, fontSize: 12 }}>
          added binding {reply.added_binding}
          {added?.fingerprint && (
            <>
              {' · '}
              <code title={added.fingerprint}>{String(added.fingerprint).slice(0, 12)}</code>
            </>
          )}
          {reply.verdict && <> · {reply.verdict}</>}
        </div>
      )}
      {reply && (
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--muted)' }}>
          {cutLine ? `cut: ${cutLine}` : 'cut: none'}
        </div>
      )}
      {quoted.length > 0 && (
        <div style={{ marginTop: 10, fontSize: 12, lineHeight: 1.6 }}>
          {quoted.map(fig => (
            <div key={fig.id || fig.binding}>
              <span>{fig.formatted ?? fig.value}</span>
              {' · '}
              <code title={fig.fingerprint}>{String(fig.fingerprint).slice(0, 12)}</code>
            </div>
          ))}
        </div>
      )}
      {kept && (
        <div style={{ marginTop: 8, fontSize: 12 }}>
          verdict: {kept.verdict}
        </div>
      )}
      {keep.error && (
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--red-text, #9b2c2c)' }}>
          {keep.error.message}
        </div>
      )}
    </div>
  )
}

function ReportDetail({ report }) {
  const [tab, setTab] = useState('Output')
  const [runId, setRunId] = useState(null)
  const [disk, setDisk] = useState(null)
  const [lineageData, setLineageData] = useState(null)
  const toast = useToast()
  const frameRef = useRef(null)
  const qc = useQueryClient()
  const { mutate: startRun, isPending: starting, error: startErr } = useStartReportRun()
  const { data: run } = useReportRun(report?.name, runId)
  const built = useBuiltReport(report?.name)
  const { mutate: fetchLineage, isPending: loadingLineage } = useReportLineage()

  // The run executes in the background on the server; useReportRun polls
  // until it settles. Result/error derive from the polled record.
  const running = starting || run?.status === 'running'
  const result = run?.status === 'succeeded' ? run.result : null
  const shown = (runId && result) ? result : (disk || built.data || null)
  const runErr = run?.status === 'failed'
    ? { message: run.error?.message || 'Run failed', detail: run.error }
    : startErr

  useEffect(() => {
    if (run?.status === 'succeeded') toast('Report ran successfully', 'success')
    if (run?.status === 'failed') toast(`Run failed: ${run.error?.message || 'unknown error'}`, 'error')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status])

  const refreshBuilt = useCallback(async () => {
    if (!report?.name) return
    setRunId(null)
    const fresh = await qc.fetchQuery({
      queryKey: ['built-report', report.name],
      queryFn: () => fetchBuiltReport(report.name),
    })
    setDisk(fresh || null)
  }, [qc, report?.name])

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

  if (!report) return <Card><Empty message="Select a report from the list to open its last build." /></Card>

  return (
    <Card>
      <CardTitle>
        {report.name}
        <FormChip form={report.form} style={{ marginLeft: 8, verticalAlign: 'middle' }} />
        {report.description && (
          <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--muted)', marginLeft: 8 }}>
            {report.description}
          </span>
        )}
      </CardTitle>

      <RunHistory name={report.name} refreshKey={run?.status} />

      {runErr && <ErrorDetail error={runErr} />}

      {!shown && !running && built.isLoading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
          <Spinner /> Opening the last build…
        </div>
      )}
      {!shown && !running && !built.isLoading && (
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn onClick={handleRun}>▶ Run Report</Btn>
          <Btn onClick={() => setTab('Source')} variant="outline">{'</>'} View source</Btn>
        </div>
      )}
      {!shown && tab === 'Source' && (
        <div style={{ marginTop: 18 }}><ReportSource name={report.name} /></div>
      )}
      {running && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--muted)', fontSize: 13 }}>
          <Spinner /> Rebuilding… you can keep browsing; a toast will confirm when it finishes.
        </div>
      )}

      {shown && (
        <>
          {shown.manifest?.rendered_at && (
            <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}
                 title="Opening a report shows its last build. Rebuild or a schedule refreshes the data.">
              Built {new Date(shown.manifest.rendered_at).toLocaleString()}
            </div>
          )}
          <ReportReceipt manifest={shown.manifest} />
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
            <Btn onClick={handleRun} disabled={running} variant="outline" size="sm">
              {running ? <><Spinner size={12} /> Rebuilding…</> : '↺ Rebuild'}
            </Btn>
            {!lineageData && (
              <Btn onClick={handleLineage} disabled={loadingLineage} variant="outline" size="sm">
                {loadingLineage ? <><Spinner size={12} /> Loading…</> : '⊶ View Lineage'}
              </Btn>
            )}
            <span style={{ flex: 1 }} />
            <a
              href={reportDownloadUrl(report.name, 'html')}
              download
              className="dl-link"
              title="The self-contained artifact with the embedded receipt"
              style={{
                background: 'var(--blue)', color: '#fff', borderColor: 'var(--blue)',
                fontWeight: 600,
              }}
            >
              ↓ HTML (with receipt)
            </a>
            <a
              href={reportDownloadUrl(report.name, 'xlsx')}
              download
              className="dl-link"
              title="A plain spreadsheet — no receipt, not verifiable"
            >
              ↓ Excel
            </a>
          </div>

          <Tabs
            tabs={lineageData ? ['Output', 'Lineage', 'Manifest', 'Source'] : ['Output', 'Manifest', 'Source']}
            active={tab}
            onChange={setTab}
          />

          {tab === 'Output' && (
            <>
              {SHOW_ASK && (
                <AskCut reportName={report.name} frameRef={frameRef} onPackageChange={refreshBuilt} />
              )}
              <ReportFrame html={shown.html} title={report.name} frameRef={frameRef} />
            </>
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

          {tab === 'Source' && <ReportSource name={report.name} />}

          {tab === 'Manifest' && (
            <pre className="code-block" style={{ maxHeight: 400, overflowY: 'auto' }}>
              {JSON.stringify(shown.manifest, null, 2)}
            </pre>
          )}
        </>
      )}
    </Card>
  )
}

// How a report is authored, from the reports API's `form` field: a JSON spec
// in the default style, or a custom package with its own template and style.
const FORMS = {
  spec: { label: 'JSON spec', title: 'A reports/<name>.json spec: sections in the default style' },
  package: { label: 'Custom', title: 'A reports/<name>/ package: its own template, style and scripts' },
  code: { label: 'Code', title: 'Registered from Python code' },
}

function FormChip({ form, style }) {
  const f = FORMS[form] || FORMS.code
  const custom = form === 'package'
  return (
    <span
      title={f.title}
      style={{
        display: 'inline-flex', alignItems: 'center',
        fontSize: 10, fontWeight: 700, letterSpacing: 0.2,
        padding: '2px 7px', borderRadius: 20, whiteSpace: 'nowrap',
        background: custom ? 'var(--amber-lt)' : 'var(--blue-lt)',
        color: custom ? 'var(--amber-text)' : 'var(--accent-text)',
        border: `1px solid ${custom ? 'var(--amber-br)' : 'var(--border)'}`,
        ...style,
      }}
    >
      {f.label}
    </span>
  )
}

// The files that define the report, read-only. A spec is one JSON file; a
// package is report.json + template.html + style.css + script.js (+ assets).
function ReportSource({ name }) {
  const { data, isLoading, error } = useReportSource(name, true)
  const [active, setActive] = useState(0)
  if (isLoading) return <div style={{ color: 'var(--muted)', fontSize: 13 }}><Spinner /> Loading source…</div>
  if (error) return <ErrorDetail error={error} />
  const files = data?.files || []
  const file = files[Math.min(active, files.length - 1)]
  return (
    <div className="fade-in">
      <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 12 }}>{data?.hint}</div>
      {files.length > 1 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          {files.map((f, i) => (
            <Btn key={f.path} size="sm" variant={i === active ? undefined : 'outline'} onClick={() => setActive(i)}>
              {f.path.split('/').pop()}
            </Btn>
          ))}
        </div>
      )}
      {file && (
        <>
          <div style={{ fontFamily: 'var(--mono, monospace)', fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>
            {file.path}{file.truncated ? ' (first 256 KB)' : ''}
          </div>
          <pre className="code-block" style={{ maxHeight: 480, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{file.content}</pre>
        </>
      )}
      {data?.other_files?.length > 0 && (
        <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 10 }}>
          Also in the package: {data.other_files.join(', ')}
        </div>
      )}
    </div>
  )
}

// The at-rest trust signal, from the reports API's `kind` field: an artifact
// report renders a self-contained, fingerprinted, verifiable page; a carrier
// (code-factory) report is rendered but not a byte-verifiable artifact.
function TrustChip({ kind }) {
  const verifiable = kind === 'artifact'
  return (
    <span
      title={verifiable
        ? 'Renders a verifiable artifact — re-checkable offline with verify --file'
        : 'A code-factory report — rendered, but not a byte-verifiable artifact'}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        fontSize: 10, fontWeight: 700, letterSpacing: 0.2,
        padding: '2px 7px', borderRadius: 20, whiteSpace: 'nowrap',
        background: verifiable ? 'var(--green-lt)' : 'var(--surface-2)',
        color: verifiable ? 'var(--green-text)' : 'var(--muted)',
        border: `1px solid ${verifiable ? 'var(--green-br)' : 'var(--border)'}`,
      }}
    >
      {verifiable ? '✓ verifiable' : 'python-derived'}
    </span>
  )
}

export default function Reports() {
  const { data, isLoading } = useReports()
  const [query, setQuery] = useState('')
  // Selection lives in the URL (?r=name), so the Home trust ledger can
  // deep-link straight to a report and the link is shareable.
  const [searchParams, setSearchParams] = useSearchParams()
  const selected = searchParams.get('r')
  const select = (name) => setSearchParams(name ? { r: name } : {}, { replace: true })

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
        {isLoading ? 'Loading…' : `${reports.length} report${reports.length !== 1 ? 's' : ''} registered. Select one to open its last build. Rebuild is the second action.`}
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
                      onClick={() => select(r.name)}
                      name={r.name}
                      sub={r.description}
                      right={
                        <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                          <FormChip form={r.form} />
                          <TrustChip kind={r.kind} />
                        </span>
                      }
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
