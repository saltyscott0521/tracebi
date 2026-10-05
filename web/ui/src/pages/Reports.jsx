import { useState, useCallback, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import {
  useReports, useStartReportRun, useReportRun, useReportRunHistory,
  useReportLineage, useReportSelection, useKeepSelection, useBuiltReport,
  useReportSource, fetchBuiltReport, reportDownloadUrl, reportShareUrl, useDesk, usePipelines,
  useAppStatus, usePointing, useWorkbenchVersion, useWorkbenchState, useWorkbenchPreview,
} from '../api'
import { attachPointMode } from '../pointMode'
import Workbench from '../components/Workbench'
import { useBuildTimeline } from '../buildTimeline'
import { ReportLineage } from '../components/ReportLineage'
import { AttentionStrip, attentionItems, verdictOf, when } from '../components/Attention'
import { ReportArt } from '../components/Art'
import { PageHeader, useReportModels } from '../components/Scope'
import { reportBelongsToModel } from '../nav'
import {
  Card, CardTitle, Badge, Spinner,
  Empty, Btn, Tabs, SplitLayout, ListItem, ErrorDetail,
  SearchInput, SkeletonList, SkeletonCard, useToast, ReportFrame, pressable, useNarrow,
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
          {v2 ? 'Verifiable' : `manifest v${manifest.schema_version ?? '?'}`}
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
        The <strong>HTML</strong> download is one file that can be checked offline with{' '}
        <code>tracebi verify --file</code>. Excel is a plain spreadsheet. PDF is a
        print of this page and carries no receipt.
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

// Full screen lays the report over the app, with a close button (and Escape)
// to come back; Share hands the link to the phone's share sheet, or copies it
// where there is none.
function ShareLink({ name, html }) {
  const url = reportShareUrl(name)
  const [copied, setCopied] = useState(false)
  const [full, setFull] = useState(false)
  const share = async () => {
    try {
      if (navigator.share) { await navigator.share({ url }); return }
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* the reader closed the share sheet */ }
  }
  return (
    <>
      <Btn onClick={() => setFull(true)} variant="outline" size="sm">⤢ Full screen</Btn>
      <Btn onClick={share} variant="outline" size="sm">
        {copied ? '✓ Link copied' : '🔗 Share'}
      </Btn>
      {full && <FullScreen name={name} html={html} onClose={() => setFull(false)} />}
    </>
  )
}

function FullScreen({ name, html, onClose }) {
  const closeRef = useRef(null)
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])
  // At the document root: an animated ancestor (transform) would otherwise
  // make position:fixed relative to the report panel, not the screen.
  return createPortal(
    <div className="fullscreen" role="dialog" aria-modal="true" aria-label={`${name}, full screen`}>
      <div className="fullscreen-bar">
        <span className="fullscreen-title">{name}</span>
        <button ref={closeRef} type="button" className="fullscreen-close" onClick={onClose}>
          ✕ Close
        </button>
      </div>
      {/* The report's own document scrolls inside the frame. */}
      <iframe srcDoc={html} title={name} className="fullscreen-frame" />
    </div>,
    document.body,
  )
}

function ReportDetail({ report, onBack }) {
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
  const narrow = useNarrow()


  // The run executes in the background on the server; useReportRun polls
  // until it settles. Result/error derive from the polled record.
  const running = starting || run?.status === 'running'
  const result = run?.status === 'succeeded' ? run.result : null
  const shown = (runId && result) ? result : (disk || built.data || null)
  const runErr = run?.status === 'failed'
    ? { message: run.error?.message || 'Run failed', detail: run.error }
    : startErr

  // Build mode: the workbench beside the report. Point at a figure or area so
  // the agent knows what "this" means, leave it notes, and watch it work: the
  // preview is the working state, refreshed when the package, its model or the
  // feed changes. Local only (the server says so) and for packages, which are
  // what an agent edits.
  const { data: appStatus } = useAppStatus()
  const canPoint = !!appStatus?.build_mode && report?.form === 'package'
  // `tracebi dev <name> --app` opens the report with ?build=1: Build mode is on.
  const [searchParams] = useSearchParams()
  const [wantBuild, setWantBuild] = useState(() => searchParams.get('build') === '1')
  const pointOn = wantBuild && canPoint
  const [pointed, setPointed] = useState(null)
  const { mutate: sendPointing } = usePointing()
  const { data: wbVersion } = useWorkbenchVersion(report?.name, pointOn)
  const { data: wbState } = useWorkbenchState(report?.name, wbVersion, pointOn)
  const wbPreview = useWorkbenchPreview(report?.name, wbVersion, pointOn)
  // The last good render stays up while the package is broken mid-edit. The
  // timeline keeps each version, and can show an earlier one.
  const timeline = useBuildTimeline({
    html: wbPreview.data, frameRef, enabled: pointOn,
  })
  const frameHtml = pointOn && timeline.shownHtml ? timeline.shownHtml : shown?.html
  const clearPointing = () => { setPointed(null); sendPointing({ name: report.name, pointing: null }) }
  useEffect(() => {
    // Pointing is at the live report; an earlier version is only for looking.
    if (!pointOn || tab !== 'Output' || !timeline.isLatest) return undefined
    const frame = frameRef.current
    if (!frame) return undefined
    let detach = () => {}
    const attach = () => {
      detach()
      detach = attachPointMode(frame.contentDocument, {
        onPoint: p => { setPointed(p); sendPointing({ name: report.name, pointing: p }) },
        onClear: () => { setPointed(null); sendPointing({ name: report.name, pointing: null }) },
      })
    }
    frame.addEventListener('load', attach)
    if (frame.contentDocument?.readyState === 'complete') attach()
    return () => { frame.removeEventListener('load', attach); detach() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointOn, tab, frameHtml, report?.name, timeline.isLatest])
  // Leaving Point mode, or this report, stops pointing: the agent should not
  // act on something you are no longer looking at.
  useEffect(() => () => {
    if (pointOn) sendPointing({ name: report.name, pointing: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointOn, report?.name])
  const togglePoint = () => { setWantBuild(on => !on); setPointed(null); timeline.reset() }

  useEffect(() => {
    if (run?.status === 'succeeded') {
      toast('Report ran successfully', 'success')
      qc.invalidateQueries({ queryKey: ['desk'] })   // new build time + receipt check
    }
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

  if (!report) return null

  const parts = report.name.split('/')
  // On a phone the open report is the whole screen, and its name is the
  // page's heading; beside the list, it sits under the page's own h1.
  const Title = narrow ? 'h1' : 'h2'
  return (
    <Card>
      <nav className="crumbs mobile-only" aria-label="Breadcrumb">
        <button type="button" onClick={onBack}>‹ Reports</button>
        {parts.slice(0, -1).map(p => <span key={p}> / {p}</span>)}
      </nav>
      <CardTitle>
        <Title className="report-detail__title">{report.name}</Title>
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
        <div className="fade-in" style={{ display: 'flex', alignItems: 'center', gap: 14, color: 'var(--muted)', fontSize: 13 }}>
          <ReportArt mode="build" size={96} /> Opening the last build…
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
        <div className="fade-in" style={{ display: 'flex', alignItems: 'center', gap: 14, color: 'var(--muted)', fontSize: 13 }}>
          <ReportArt mode="build" size={96} />
          <span>Rebuilding: re-running every query. You can keep browsing; a toast will
          confirm when it finishes.</span>
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
            {canPoint && (
              <Btn onClick={togglePoint} variant={pointOn ? 'primary' : 'outline'} size="sm"
                   aria-pressed={pointOn}
                   title="Build mode: point at a figure or area, leave your agent notes, and watch it work.">
                ◎ Build
              </Btn>
            )}
            <span style={{ flex: 1 }} />
            <ShareLink name={report.name} html={shown.html} />
            <a
              href={reportDownloadUrl(report.name, 'html')}
              download
              className="dl-link"
              title="One self-contained file, checkable offline with tracebi verify --file"
              style={{
                background: 'var(--blue)', color: '#fff', borderColor: 'var(--blue)',
                fontWeight: 600,
              }}
            >
              ↓ HTML
            </a>
            <a
              href={reportDownloadUrl(report.name, 'xlsx')}
              download
              className="dl-link"
              title="A plain spreadsheet; it can't be checked the way the HTML file can"
            >
              ↓ Excel
            </a>
            <a
              href={reportDownloadUrl(report.name, 'pdf')}
              download
              className="dl-link"
              title="A print of this page. Charts render. It carries no receipt; the HTML file is what can be checked"
            >
              ↓ PDF
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
              {pointOn ? (
                <div className="build-layout">
                  <ReportFrame html={frameHtml} title={report.name} frameRef={frameRef} />
                  <Workbench pointed={pointed} onClearPointing={clearPointing}
                             state={wbState} previewError={wbPreview.error} timeline={timeline} />
                </div>
              ) : (
                <ReportFrame html={shown.html} title={report.name} frameRef={frameRef} />
              )}
            </>
          )}

          {tab === 'Lineage' && lineageData && <ReportLineage flow={lineageData.flow} />}

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

// The last build's receipt, re-checked by GET /api/desk. Nothing is shown
// for a report with no build on disk: an unchecked report makes no claim.
function ReceiptChip({ build }) {
  if (!build) return null
  const v = verdictOf(build.verdict)
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
      <Badge variant={v.variant} style={{ textTransform: 'none', fontSize: 10 }}>{v.label}</Badge>
      <span style={{ fontSize: 10.5, color: 'var(--muted)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
        built {when(build.built_at) || '—'}
      </span>
    </span>
  )
}

// Schedule, last schedule run, stored builds, and last edit. No owner:
// there are no accounts yet. Missing values are an em dash. The row opens
// the report, whose detail already lists recent runs.
function LibraryFacts({ report }) {
  const schedule = report.schedule
    ? [report.schedule.cron, report.schedule.timezone].filter(Boolean).join(' · ')
    : null
  const lastRun = report.last_run
    ? [report.last_run.status, when(report.last_run.time)].filter(Boolean).join(' · ')
    : null
  const builds = Number(report.past_builds) > 0 ? String(report.past_builds) : null
  const cells = [
    ['Schedule', schedule],
    ['Last run', lastRun],
    ['Builds', builds, 'Open to see run history'],
    ['Changed', when(report.last_change)],
  ]
  return cells.map(([label, value, title]) => (
    <span key={label} title={title} style={{ fontSize: 11, lineHeight: 1.35, maxWidth: '100%' }}>
      <span style={{ color: 'var(--muted)' }}>{label} </span>
      <span style={{ color: 'var(--text-2)', fontVariantNumeric: 'tabular-nums' }}>{value || '—'}</span>
    </span>
  ))
}

// What the list is, before you open anything: how many reports, whether their
// last builds still reproduce, what needs a look, and the latest builds.
function ReportsOverview({ reports, builds, onOpen }) {
  const names = new Set(reports.map(r => r.name))
  const built = builds.filter(b => names.has(b.report))
  const good = built.filter(b => verdictOf(b.verdict).variant === 'green').length
  const look = built.filter(b => !['green', 'gray'].includes(verdictOf(b.verdict).variant)).length
  const never = reports.length - built.length
  const latest = [...built].sort((a, b) => String(b.built_at).localeCompare(String(a.built_at))).slice(0, 6)
  const tiles = [
    ['Reports', reports.length, null],
    ['Reproduce', built.length ? `${good} of ${built.length}` : '—', good === built.length && built.length ? 'good' : null],
    ['Need a look', look, look ? 'bad' : null],
    ['Never built', never, null],
  ]
  return (
    <Card className="fade-in">
      <CardTitle>At a glance</CardTitle>
      <div className="glance-tiles">
        {tiles.map(([label, value, tone]) => (
          <div key={label} className={`glance-tile${tone ? ` glance-tile--${tone}` : ''}`}>
            <div className="glance-tile__value">{value}</div>
            <div className="glance-tile__label">{label}</div>
          </div>
        ))}
      </div>
      <div className="glance-heading">Latest builds</div>
      {latest.length === 0 ? (
        <p className="glance-empty">
          Nothing built yet. Open a report to build it, or run{' '}
          <code>tracebi report build &lt;name&gt;</code>.
        </p>
      ) : latest.map(b => {
        const v = verdictOf(b.verdict)
        return (
          <div key={b.report} className="glance-row" {...pressable(() => onOpen(b.report))}>
            <span className="glance-row__name">{b.report.slice(b.report.lastIndexOf('/') + 1)}</span>
            <span className="glance-row__when">{when(b.built_at) || '—'}</span>
            <Badge variant={v.variant} style={{ textTransform: 'none' }}>{v.label}</Badge>
          </div>
        )
      })}
    </Card>
  )
}

// Reports in folders are named by their path ("finance/weekly"). The list
// groups them under their folder; top-level reports come first, unheaded.
function groupByFolder(reports) {
  const groups = new Map()
  for (const r of reports) {
    const i = r.name.lastIndexOf('/')
    const folder = i === -1 ? '' : r.name.slice(0, i)
    if (!groups.has(folder)) groups.set(folder, [])
    groups.get(folder).push(r)
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a === '' ? -1 : b === '' ? 1 : a.localeCompare(b)))
    .map(([folder, items]) => ({ folder, items }))
}

function FolderHeading({ folder, count, open, onToggle }) {
  return (
    <button type="button" onClick={onToggle} aria-expanded={open} style={{
      display: 'flex', alignItems: 'center', gap: 8, width: '100%',
      padding: '8px 16px', border: 0, borderBottom: '1px solid var(--border)',
      background: 'var(--surface)', color: 'var(--text-2)', cursor: 'pointer',
      font: 'inherit', fontSize: 12, fontWeight: 600, textAlign: 'left',
    }}>
      <span aria-hidden="true" className={`folder-caret${open ? ' open' : ''}`}
            style={{ width: 10, color: 'var(--muted)' }}>▸</span>
      <svg aria-hidden="true" width="14" height="14" viewBox="0 0 20 20" fill="currentColor" style={{ color: 'var(--muted)', flexShrink: 0 }}>
        <path d="M2 6a2 2 0 012-2h4l2 2h6a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
      </svg>
      <span style={{ flex: 1, minWidth: 0, overflowWrap: 'anywhere' }}>{folder.split('/').join(' / ')}</span>
      <span style={{ color: 'var(--muted)', fontWeight: 400, fontVariantNumeric: 'tabular-nums' }}>{count}</span>
    </button>
  )
}

export default function Reports({ model = '' }) {
  const { data, isLoading } = useReports()
  const { data: desk } = useDesk()
  const { data: pipelines } = usePipelines()
  const [query, setQuery] = useState('')
  const builds = Object.fromEntries((desk?.builds || []).map(b => [b.report, b]))
  // Selection lives in the URL (?r=name), so an attention item can
  // deep-link straight to a report and the link is shareable.
  const [searchParams, setSearchParams] = useSearchParams()
  const selected = searchParams.get('r')
  const select = (name) => {
    const next = new URLSearchParams()
    if (name) next.set('r', name)
    setSearchParams(next)
    window.scrollTo(0, 0)
  }

  const reports = (data || []).filter(r => reportBelongsToModel(r, model))
  const modelsOf = useReportModels()
  const filtered = reports.filter(r =>
    r.name.toLowerCase().includes(query.toLowerCase()) ||
    (r.description || '').toLowerCase().includes(query.toLowerCase())
  )
  const current = reports.find(r => r.name === selected)
  const [closed, setClosed] = useState(() => new Set())
  const toggle = (folder) => setClosed(prev => {
    const next = new Set(prev)
    next.has(folder) ? next.delete(folder) : next.add(folder)
    return next
  })

  return (
    <div className={current ? 'reports-page reports-page--detail' : 'reports-page'}>
      <PageHeader pageKey="reports" model={model} />

      <AttentionStrip items={attentionItems(desk, pipelines, modelsOf)
        .filter(it => !model || it.models.includes(model))} />

      {!isLoading && reports.length === 0 ? (
        <Empty message={model
          ? `No reports for ${model} yet. Reports for it live in reports/${model}/: scaffold one with tracebi new-report.`
          : 'No reports yet. Scaffold one with tracebi new-report, or see Get Started.'} />
      ) : (
        <SplitLayout
          detail={!!current}
          left={
            isLoading ? <SkeletonList /> : (
              <>
                <SearchInput value={query} onChange={setQuery} placeholder="Search reports…" />
                {filtered.length === 0
                  ? <Empty message="No matches." />
                  // One model: its folder is the page, so no folder headings.
                  : (model ? [{ folder: '', items: filtered }] : groupByFolder(filtered)).map(({ folder, items }) => {
                    // A search always shows its matches, even in a closed folder.
                    const open = !folder || query || !closed.has(folder)
                    return (
                      <div key={folder || '(top)'}>
                        {folder && (
                          <FolderHeading folder={folder} count={items.length}
                                         open={open} onToggle={() => toggle(folder)} />
                        )}
                        {open && items.map((r, i) => (
                          <div key={r.name} className="rise" style={{ '--i': i }}>
                          <ListItem
                            selected={selected === r.name}
                            onClick={() => select(r.name)}
                            name={r.name.slice(r.name.lastIndexOf('/') + 1)}
                            sub={r.description}
                            meta={<LibraryFacts report={r} />}
                            right={
                              <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                                <FormChip form={r.form} />
                                <ReceiptChip build={builds[r.name]} />
                              </span>
                            }
                          />
                          </div>
                        ))}
                      </div>
                    )
                  })
                }
              </>
            )
          }
          right={isLoading ? <SkeletonCard /> : current
            ? <ReportDetail key={current.name} report={current} onBack={() => select(null)} />
            : <ReportsOverview reports={reports} builds={desk?.builds || []} onOpen={select} />}
        />
      )}
    </div>
  )
}
