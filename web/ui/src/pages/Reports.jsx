import { useState, useCallback, useEffect, useRef } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import {
  useReports, useStartReportRun, useReportRun, useReportRunHistory,
  useReportLineage, useReportSelection, useKeepSelection, useBuiltReport,
  useReportSource, fetchBuiltReport, reportDownloadUrl, reportShareUrl, useDesk, usePipelines,
  useAppStatus, useMe, usePointing, useWorkbenchVersion, useWorkbenchState, useWorkbenchPreview,
} from '../api'
import { attachPointMode } from '../pointMode'
import Workbench, { ProjectFeed } from '../components/Workbench'
import { CodeFiles } from '../components/CodeView'
import { useBuildTimeline } from '../buildTimeline'
import { ReportLineage } from '../components/ReportLineage'
import {
  AttentionStrip, attentionItems, reviewNotes, verdictOf, verdictFlag, isQuiet, when,
} from '../components/Attention'
import { Flag, stamp } from '../components/TheLine'
import EditAsDraft from '../components/EditAsDraft'
import { ReportArt } from '../components/Art'
import { PageHeader, useReportModels, useOpenReport, PREVIEW_QUERY } from '../components/Scope'
import { reportBelongsToModel, reportModels, pagePath, reportOpenPath } from '../nav'
import { scheduleWords } from '../schedule'
import {
  Card, CardTitle, Badge, Spinner,
  Empty, Btn, SplitLayout, ListItem, ErrorDetail,
  SearchInput, SkeletonList, SkeletonCard, useToast, pressable, useNarrow,
} from '../components/Shared'

// A report that has no build: marked, never coloured (it is not an error).
const NEVER_BUILT = { kind: 'none', glyph: '○', text: 'Never built' }

function runDuration(rec) {
  if (!rec.finished_at) return null
  const s = (new Date(rec.finished_at) - new Date(rec.started_at)) / 1000
  return s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`
}

// A report's recent builds, newest first. Only a failure is marked; the rest
// are plain facts.
function RunHistory({ name }) {
  const { data: runs, refetch } = useReportRunHistory(name)
  useEffect(() => { refetch() }, [refetch])
  if (!runs) return <div className="rp__none"><Spinner /> Loading builds…</div>
  if (!runs.length) return <p className="rp__none">No runs started from the app yet.</p>
  return (
    <ul className="rp__runs">
      {runs.map(r => {
        const dur = runDuration(r)
        return (
          <li key={r.run_id}>
            <span>{r.status === 'running' ? '… Running' : `${stamp(r.started_at)}${dur ? ` · ${dur}` : ''}`}</span>
            {r.status === 'failed' && (
              <span className="flag flag--bad">
                <span aria-hidden="true">✕</span> Failed{r.error?.message ? `: ${r.error.message}` : ''}
              </span>
            )}
          </li>
        )
      })}
    </ul>
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

// Plain facts; a glyph only where something is not fine (△ changed, ○ cannot be
// re-run or not declared).
function ReportReceipt({ manifest }) {
  if (!manifest) return null
  const p = figureProvenance(manifest)
  const v2 = manifest.schema_version === 2
  const contracts = Object.entries(manifest.transform_contracts || {})
  const sink = (table, status) => {
    if (status === 'satisfied') return <>{table}: the sink satisfied its contract</>
    if (status === 'stale') return <><span aria-hidden="true">△</span> {table}: changed since the sink last satisfied its contract</>
    return <><span aria-hidden="true">○</span> {table}: no contract declared</>
  }
  return (
    <ul className="rp__receipt">
      <li>{v2 ? 'Verifiable receipt (schema 2)' : `○ Manifest v${manifest.schema_version ?? '?'}: no per-figure receipts to re-run`}</li>
      {p.total > 0 && <li>{p.total} figures: {p.reproducible} re-run from their queries</li>}
      {p.derived > 0 && <li><span aria-hidden="true">○</span> {p.derived} from python, which cannot be re-run</li>}
      {p.unverified > 0 && <li><span aria-hidden="true">△</span> {p.unverified} unverified</li>}
      {contracts.map(([table, c]) => <li key={table}>{sink(table, c?.status)}</li>)}
    </ul>
  )
}

// Start a report run, follow it, and say how it ended: what Rebuild on the
// page and "Build it now" in the Reports stage both do. The new build shows
// on the page (desk) and in the preview (built-report) once it ends.
function useReportBuild(name) {
  const [runId, setRunId] = useState(null)
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: startRun, isPending: starting, error: startErr } = useStartReportRun()
  const { data: run } = useReportRun(name, runId)

  // The run executes in the background on the server; useReportRun polls
  // until it settles. Result/error derive from the polled record.
  const running = starting || run?.status === 'running'
  const result = run?.status === 'succeeded' ? run.result : null
  const error = run?.status === 'failed'
    ? { message: run.error?.message || 'Run failed', detail: run.error }
    : startErr

  useEffect(() => {
    if (run?.status === 'succeeded') {
      toast('Report ran successfully', 'info')
      qc.invalidateQueries({ queryKey: ['desk'] })   // new build time + receipt check
      qc.invalidateQueries({ queryKey: ['built-report', name] })
    }
    if (run?.status === 'failed') toast(`Run failed: ${run.error?.message || 'unknown error'}`, 'error')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status])

  const build = useCallback(() => {
    startRun(name, {
      onSuccess: data => setRunId(data.run_id),
      onError: err => toast(`Run failed to start: ${err.message}`, 'error'),
    })
  }, [name, startRun, toast])

  return { build, running, runId, result, error, status: run?.status }
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

// ── The report's own page ────────────────────────────────────────────────────
// One light bar (back to its model, its name, when it was built and what is not
// fine about that, then Rebuild, Share and More) and the report filling the
// rest of the screen. The report keeps its own receipt drawer on every figure
// (tracebi.js): the frame is as tall as the screen and scrolls inside, so that
// drawer opens at the edge of what you are looking at.

const BAR_BTN = { minHeight: 40, padding: '0 14px', borderRadius: 9, fontSize: 14 }

// Share hands the link to the phone's share sheet, or copies it where there is none.
function ShareButton({ name }) {
  const url = reportShareUrl(name)
  const [copied, setCopied] = useState(false)
  const share = async () => {
    try {
      if (navigator.share) { await navigator.share({ url }); return }
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* the reader closed the share sheet */ }
  }
  return <Btn onClick={share} variant="outline" style={BAR_BTN}>{copied ? 'Link copied' : 'Share'}</Btn>
}

// The three files a report can be downloaded as, each with what it is good for.
const DOWNLOADS = [
  ['html', 'HTML', 'One self-contained file, checkable offline with tracebi verify --file'],
  ['xlsx', 'Excel', "A plain spreadsheet; it can't be checked the way the HTML file can"],
  ['pdf', 'PDF', 'A print of this page. Charts render. It carries no receipt; the HTML file is what can be checked'],
]

// Everything a reader does not do every time: take a copy, trace a number back,
// read the code, check it again, see when it runs and what ran. Escape, a click
// elsewhere, or tabbing out closes it; choosing a file starts the download.
function MoreMenu({ name, rootRef, onPanel, onCheck, checking }) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return undefined
    const away = e => { if (!rootRef.current?.contains(e.target)) setOpen(false) }
    const esc = e => {
      if (e.key !== 'Escape') return
      setOpen(false)
      rootRef.current?.querySelector('button')?.focus()
    }
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open, rootRef])
  const then = fn => () => { setOpen(false); fn() }
  return (
    <div ref={rootRef} onBlur={e => { if (!rootRef.current.contains(e.relatedTarget)) setOpen(false) }}>
      <Btn onClick={() => setOpen(o => !o)} variant="outline" style={BAR_BTN}
           aria-expanded={open} aria-controls="report-more">
        More
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
             strokeLinecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      </Btn>
      {open && (
        <div id="report-more" className="rp__menu">
          {DOWNLOADS.map(([format, label, note]) => (
            <a key={format} href={reportDownloadUrl(name, format)} download
               className="rp__item" onClick={() => setOpen(false)}>
              <span className="rp__item-label">Download {label}</span>
              <span className="rp__item-note">{note}</span>
            </a>
          ))}
          <div className="rp__rule" role="separator" />
          <button type="button" className="rp__item" onClick={then(() => onPanel('lineage'))}>Lineage and manifest</button>
          <button type="button" className="rp__item" onClick={then(() => onPanel('code'))}>Code</button>
          <button type="button" className="rp__item" onClick={then(onCheck)} disabled={checking}>Check it again</button>
          <button type="button" className="rp__item" onClick={then(() => onPanel('schedule'))}>Schedule…</button>
          <button type="button" className="rp__item" onClick={then(() => onPanel('history'))}>Past builds</button>
        </div>
      )}
    </div>
  )
}

// A panel from the right edge over the report: Escape, its ✕ or a click on the
// report behind it closes it.
function Drawer({ title, onClose, children }) {
  const close = useRef(null)
  useEffect(() => {
    const esc = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', esc)
    close.current?.focus()
    return () => document.removeEventListener('keydown', esc)
  }, [onClose])
  return (
    <>
      <div className="rp__scrim" onClick={onClose} aria-hidden="true" />
      <aside className="rp__drawer" role="dialog" aria-modal="true" aria-label={title}>
        <div className="rp__drawer-head">
          <h2>{title}</h2>
          <button ref={close} type="button" className="rp__close" onClick={onClose} aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                 strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        {children}
      </aside>
    </>
  )
}

// What the last build's receipt says (plain facts), the lineage drawn from it,
// and the manifest it is read from.
function LineagePanel({ name, manifest }) {
  const { mutate: fetchLineage, data, error } = useReportLineage()
  useEffect(() => { if (manifest) fetchLineage(name) }, [name, manifest, fetchLineage])
  if (!manifest) return <p className="rp__none">Nothing to trace yet: this report has not been built.</p>
  return (
    <>
      <ReportReceipt manifest={manifest} />
      {data ? <ReportLineage flow={data.flow} />
        : error ? <ErrorDetail error={error} />
          : <div className="rp__none"><Spinner /> Loading lineage…</div>}
      <details className="rp__manifest">
        <summary>Manifest</summary>
        <pre className="code-block" style={{ maxHeight: 400, overflowY: 'auto' }}>
          {JSON.stringify(manifest, null, 2)}
        </pre>
      </details>
    </>
  )
}

// A scheduled run that did not go out: failed, or built but refused or empty.
const SCHEDULE_ALERT = { failed: ['bad', '✕'], refused: ['warn', '△'], empty: ['warn', '△'] }

// When it runs, in words, and how the last run went.
function SchedulePanel({ report }) {
  const words = scheduleWords(report.schedule)
  const last = report.last_run
  if (!words) {
    return (
      <>
        <p className="rp__lead">Not scheduled.</p>
        <p className="rp__none">A <code>schedule</code> block in report.json builds it on a timetable.</p>
      </>
    )
  }
  return (
    <>
      <p className="rp__lead">{words.long}</p>
      {words.long !== report.schedule.cron && (
        <p className="rp__none"><code>{report.schedule.cron}</code>{report.schedule.timezone ? ` · ${report.schedule.timezone}` : ''}</p>
      )}
      {last && (
        <p className="rp__none">
          Last scheduled run {stamp(last.time) || ''}
          {SCHEDULE_ALERT[last.status] && (
            <> · <span className={`flag flag--${SCHEDULE_ALERT[last.status][0]}`}>
              <span aria-hidden="true">{SCHEDULE_ALERT[last.status][1]}</span> {last.status}
            </span></>
          )}
        </p>
      )}
    </>
  )
}

// The files that define the report, read-only, and a way to change a copy.
function CodePanel({ name }) {
  return (
    <>
      <ReportSource name={name} />
      <div className="rp__foot"><EditAsDraft kind="reports" path={name} /></div>
    </>
  )
}

const PANELS = {
  lineage: 'Lineage and manifest', code: 'Code', schedule: 'Schedule', history: 'Past builds',
}

// "Source changed" on a build reads, beside its time, as "Source changed since".
function sinceFlag(verdict) {
  const flag = verdictFlag(verdict)
  return flag && verdict === 'source_drift' ? { ...flag, text: 'Source changed since' } : flag
}

// A report with no build: nothing to show, and nothing is built by looking.
function NeverBuilt({ build, canBuild }) {
  const busy = build.running || build.status === 'succeeded'
  return (
    <div className="rprev__never">
      <Flag flag={NEVER_BUILT} />
      <p>There is no page to show yet. Build it once and the preview, its receipt and the check appear here.</p>
      {canBuild && (
        <Btn onClick={build.build} disabled={busy}>
          {busy ? <><Spinner size={12} /> Building…</> : 'Build it now'}
        </Btn>
      )}
      {build.error && <ErrorDetail error={build.error} />}
    </div>
  )
}

function OpenReport({ report, model }) {
  const name = report.name
  const [panel, setPanel] = useState(null)
  const [disk, setDisk] = useState(null)
  const [checking, setChecking] = useState(false)
  const toast = useToast()
  const frameRef = useRef(null)
  const moreRef = useRef(null)
  const qc = useQueryClient()
  const narrow = useNarrow(PREVIEW_QUERY)
  const { data: me } = useMe()
  const canBuild = me?.role === 'analyst' || me?.role === 'admin'
  const { data: desk, isError: deskFailed, isFetching: checkingDesk } = useDesk()
  const lastBuild = (desk?.builds || []).find(b => b.report === name)
  const buildRun = useReportBuild(name)
  const { build: startBuild, running, result, error: runErr } = buildRun
  // The server builds a report it has no build of when asked for it, so ask
  // only once the desk has said it is built.
  const built = useBuiltReport(name, desk ? !!lastBuild : deskFailed)
  const shown = disk || result || built.data || null
  const rebuild = () => { setDisk(null); startBuild() }

  // Build mode: the workbench beside the report. Point at a figure or area so
  // the agent knows what "this" means, leave it notes, and watch it work: the
  // preview is the working state, refreshed when the package, its model or the
  // feed changes. Local only (the server says so) and for packages, which are
  // what an agent edits.
  const { data: appStatus } = useAppStatus()
  const canPoint = !!appStatus?.build_mode && report.form === 'package'
  // `tracebi dev <name>` opens the report with ?build=1: Build mode is on.
  const [searchParams] = useSearchParams()
  const [wantBuild, setWantBuild] = useState(() => searchParams.get('build') === '1')
  const pointOn = wantBuild && canPoint
  const [pointed, setPointed] = useState(null)
  const { mutate: sendPointing } = usePointing()
  const { data: wbVersion } = useWorkbenchVersion(name, pointOn)
  const { data: wbState } = useWorkbenchState(name, wbVersion, pointOn)
  const wbPreview = useWorkbenchPreview(name, wbVersion, pointOn)
  // The last good render stays up while the package is broken mid-edit. The
  // timeline keeps each version, and can show an earlier one.
  const timeline = useBuildTimeline({
    html: wbPreview.data, frameRef, enabled: pointOn,
  })
  const frameHtml = pointOn && timeline.shownHtml ? timeline.shownHtml : shown?.html
  const clearPointing = () => { setPointed(null); sendPointing({ name, pointing: null }) }
  useEffect(() => {
    // Pointing is at the live report; an earlier version is only for looking.
    if (!pointOn || !timeline.isLatest) return undefined
    const frame = frameRef.current
    if (!frame) return undefined
    let detach = () => {}
    const attach = () => {
      detach()
      detach = attachPointMode(frame.contentDocument, {
        onPoint: p => { setPointed(p); sendPointing({ name, pointing: p }) },
        onClear: () => { setPointed(null); sendPointing({ name, pointing: null }) },
      })
    }
    frame.addEventListener('load', attach)
    if (frame.contentDocument?.readyState === 'complete') attach()
    return () => { frame.removeEventListener('load', attach); detach() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointOn, frameHtml, name, timeline.isLatest])
  // Leaving Point mode, or this report, stops pointing: the agent should not
  // act on something you are no longer looking at.
  useEffect(() => () => {
    if (pointOn) sendPointing({ name, pointing: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointOn, name])
  const togglePoint = () => { setWantBuild(on => !on); setPointed(null); timeline.reset() }

  const refreshBuilt = useCallback(async () => {
    const fresh = await qc.fetchQuery({
      queryKey: ['built-report', name],
      queryFn: () => fetchBuiltReport(name),
    })
    setDisk(fresh || null)
  }, [qc, name])

  const closePanel = useCallback(() => {
    setPanel(null)
    moreRef.current?.querySelector('button')?.focus()
  }, [])

  // The desk re-runs every recorded query against the warehouse as it is now.
  const checkAgain = async () => {
    setChecking(true)
    try {
      await qc.refetchQueries({ queryKey: ['desk'] })
      const row = (qc.getQueryData(['desk'])?.builds || []).find(b => b.report === name)
      const v = row && verdictOf(row.verdict)
      toast(row ? `Checked again: ${v.label}.` : 'There is no build to check.', v?.variant === 'red' ? 'error' : 'info')
    } catch (err) {
      toast(`The check failed: ${err.message}`, 'error')
    } finally {
      setChecking(false)
    }
  }

  // A check still running would show the verdict from before it.
  const flag = !checkingDesk && lastBuild ? sinceFlag(lastBuild.verdict) : null
  const builtAt = shown?.manifest?.rendered_at ? stamp(shown.manifest.rendered_at) : null
  const opening = !frameHtml && !running && ((!desk && !deskFailed) || built.isLoading)
  const back = model
    ? `${pagePath('reports', model)}${narrow ? '' : `?${new URLSearchParams({ r: name })}`}`
    : pagePath('reports', '')
  const label = name.slice(name.lastIndexOf('/') + 1)

  return (
    <div className={pointOn ? 'rp rp--build' : 'rp'}>
      <header className="rp__bar">
        <Link to={back} className="rp__back">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
               strokeLinecap="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
          <span className={model ? 'rp__model' : undefined}>{model || 'All reports'}</span>
        </Link>
        <span className="rp__sep" aria-hidden="true">/</span>
        <h1 className="rp__name" title={name}>{label}</h1>
        {builtAt && (
          <span className="rp__built"
                title="Opening a report shows its last build. Rebuild or a schedule refreshes the data.">
            Built {builtAt}
          </span>
        )}
        {flag && <Flag flag={flag} />}
        <div className="rp__actions">
          {canBuild && shown && (
            <Btn onClick={rebuild} disabled={running} variant="outline" style={BAR_BTN}
                 title="Re-run every query and build the report again">
              {running ? <><Spinner size={12} /> Rebuilding…</> : 'Rebuild'}
            </Btn>
          )}
          {canPoint && (
            <Btn onClick={togglePoint} variant={pointOn ? 'primary' : 'outline'} style={BAR_BTN}
                 aria-pressed={pointOn}
                 title="Build mode: point at a figure or area, leave your agent notes, and watch it work.">
              ◎ Build
            </Btn>
          )}
          <ShareButton name={name} />
          <MoreMenu name={name} rootRef={moreRef} onPanel={setPanel} onCheck={checkAgain} checking={checking} />
        </div>
      </header>

      <div className="rp__body">
        <main className="rp__main">
          {running && shown && (
            <p className="rp__note" role="status">
              Rebuilding: re-running every query. You can keep browsing; a toast will
              confirm when it finishes.
            </p>
          )}
          {(runErr && shown) && <div className="rp__err"><ErrorDetail error={runErr} /></div>}
          {SHOW_ASK && shown && (
            <div className="rp__err">
              <AskCut reportName={name} frameRef={frameRef} onPackageChange={refreshBuilt} />
            </div>
          )}
          {frameHtml ? (
            <iframe ref={frameRef} srcDoc={frameHtml} title={name} className="rp__frame" />
          ) : opening ? (
            <div className="rp__state fade-in">
              <ReportArt mode="build" size={96} /> Opening the last build…
            </div>
          ) : (
            <div className="rp__state">
              {built.error && <ErrorDetail error={built.error} />}
              <NeverBuilt build={buildRun} canBuild={canBuild} />
            </div>
          )}
        </main>
        {pointOn && (
          <aside className="rp__wb" aria-label="Build mode">
            <Workbench pointed={pointed} onClearPointing={clearPointing} name={name}
                       state={wbState} previewError={wbPreview.error} timeline={timeline} />
          </aside>
        )}
      </div>

      {panel && (
        <Drawer title={PANELS[panel]} onClose={closePanel}>
          {panel === 'lineage' && <LineagePanel name={name} manifest={shown?.manifest} />}
          {panel === 'code' && <CodePanel name={name} />}
          {panel === 'schedule' && <SchedulePanel report={report} />}
          {panel === 'history' && <RunHistory name={name} />}
        </Drawer>
      )}
    </div>
  )
}

/** A report as a page of its own: the whole screen, a light bar of its own. */
export function ReportPage({ name, model }) {
  const { data: reports, isLoading } = useReports()
  const report = (reports || []).find(r => r.name === name)
  if (isLoading) return <div className="rp"><main className="rp__state"><SkeletonCard /></main></div>
  if (!report) {
    return (
      <div className="rp">
        <header className="rp__bar">
          <Link to={model ? pagePath('reports', model) : '/reports'} className="rp__back">
            <span aria-hidden="true">‹</span> {model || 'All reports'}
          </Link>
        </header>
        <main className="rp__state">
          <p className="rp__lead">No report named “{name}”.</p>
          <p className="rp__none">It may have been renamed or removed.</p>
        </main>
      </div>
    )
  }
  return <OpenReport key={name} report={report} model={model || reportModels(report)[0] || ''} />
}

// ── The Reports stage: the list, and the last build of the one picked ───────

// The width a report is laid out at in the preview; it is shrunk to the pane.
const PREVIEW_W = 1100
// The preview shows the top of the page at most this tall; Open reads the rest.
const PREVIEW_MAX = 520

// The last build as readers see it, scaled to fit and read-only.
function PreviewFrame({ html, title }) {
  const box = useRef(null)
  const frame = useRef(null)
  const [scale, setScale] = useState(0.6)
  const [height, setHeight] = useState(480)

  useEffect(() => {
    const el = box.current
    const fit = () => { if (el.clientWidth) setScale(el.clientWidth / PREVIEW_W) }
    fit()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(fit)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // The frame is as tall as the report, at the width it is laid out at.
  useEffect(() => {
    const el = frame.current
    let observer
    const measure = () => {
      const doc = el.contentDocument
      if (!doc?.body) return
      const h = Math.max(doc.documentElement?.scrollHeight || 0, doc.body.scrollHeight || 0)
      if (h) setHeight(h)
    }
    const onLoad = () => {
      measure()
      const doc = el.contentDocument
      if (doc?.body && typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(measure)
        observer.observe(doc.body)
      }
    }
    el.addEventListener('load', onLoad)
    if (el.contentDocument?.readyState === 'complete') onLoad()
    return () => { el.removeEventListener('load', onLoad); observer?.disconnect() }
  }, [html])

  const full = height * scale
  return (
    <div ref={box} className={`rprev__box${full > PREVIEW_MAX ? ' rprev__box--clipped' : ''}`}
         style={{ height: Math.min(full, PREVIEW_MAX) }}>
      <iframe ref={frame} srcDoc={html} title={title} tabIndex={-1} className="rprev__frame"
              style={{ width: PREVIEW_W, height, transform: `scale(${scale})` }} />
    </div>
  )
}

function BuiltPreview({ name }) {
  const built = useBuiltReport(name)
  if (built.isLoading) return <div className="rp__none"><Spinner /> Opening the last build…</div>
  if (built.error) return <ErrorDetail error={built.error} />
  if (!built.data) return null
  return (
    <>
      <PreviewFrame html={built.data.html} title={`Preview of ${name}`} />
      <p className="rprev__note">The last build, as readers see it. Open it to trace any number.</p>
    </>
  )
}

// The files that define the report, read-only; a copy of them to edit.
function ConfigView({ report }) {
  return (
    <div className="rconfig">
      <div className="rconfig__code"><ReportSource name={report.name} /></div>
      <div className="rconfig__foot"><EditAsDraft kind="reports" path={report.name} /></div>
    </div>
  )
}

// What a verdict that is not "reproduces" says of the builds that have it, said
// of *n* of them.
const NOT_HELD = {
  source_drift: n => `${n === 1 ? 'was' : 'were'} built before the source data changed`,
  not_reproduced: n => `${n === 1 ? "doesn't" : "don't"} reproduce`,
  unverifiable: n => `can't be re-run (${n === 1 ? 'its' : 'their'} numbers come from code)`,
  nothing_to_verify: () => 'recorded no numbers to check',
  refused_newer_schema: n => `${n === 1 ? 'was' : 'were'} built by a newer TraceBi`,
  error: () => 'could not be checked',
}

// The one sentence under the list that says whether the built reports still
// hold. The good news only when it is true; otherwise what is not.
function receiptLine(reports, builds, checkedAt) {
  const built = reports.filter(r => builds[r.name])
  if (!built.length) return 'No report here is built yet.'
  const when = checkedAt ? ` (checked ${stamp(new Date(checkedAt).toISOString())})` : ''
  const held = built.filter(r => builds[r.name].verdict === 'reproduces').length
  if (held === built.length) {
    return built.length === 1
      ? `The built report re-runs to the same numbers${when}.`
      : `All ${built.length} built reports re-run to the same numbers${when}.`
  }
  const rest = {}
  built.forEach(r => {
    const v = builds[r.name].verdict
    if (v !== 'reproduces') rest[v] = (rest[v] || 0) + 1
  })
  const said = Object.entries(rest).map(([v, n]) => `${n} ${(NOT_HELD[v] || (() => 'needs a look'))(n)}`)
  return `${held} of ${built.length} built reports re-run to the same numbers${when}. ${said.join('; ')}.`
}

function ReportRow({ report, flag, builtAt, selected, onPick }) {
  const words = scheduleWords(report.schedule)
  return (
    <li>
      <button type="button" className="rrow" aria-pressed={selected} onClick={onPick}>
        <span className="rrow__main">
          <span className="rrow__name" title={report.name}>{report.name.slice(report.name.lastIndexOf('/') + 1)}</span>
          {report.description && <span className="rrow__desc" title={report.description}>{report.description}</span>}
        </span>
        <span className="rrow__side">
          {flag && <Flag flag={flag} />}
          {builtAt && <span className="rrow__built">Built {builtAt}</span>}
          {words && <span className="rrow__sched">{words.short}</span>}
        </span>
      </button>
    </li>
  )
}

// The pane beside the list: the picked report's header, and its last build
// (Preview) or the files that define it (Config).
function ReportView({ report, model, desk, deskFailed, build, canBuild, view, onView }) {
  const buildRun = useReportBuild(report.name)
  const words = scheduleWords(report.schedule)
  const flag = build ? sinceFlag(build.verdict) : desk ? NEVER_BUILT : null
  const label = report.name.slice(report.name.lastIndexOf('/') + 1)
  return (
    <div className="rview">
      <div className="rview__head">
        <div className="rview__id">
          <div className="rview__name" title={report.name}>{label}</div>
          <div className="rview__built">
            {build && <span>Built {stamp(build.built_at)}</span>}
            {flag && <Flag flag={flag} />}
            {words && <span>{words.long}</span>}
          </div>
        </div>
        <div className="seg" role="group" aria-label="Show">
          {[['preview', 'Preview'], ['config', 'Config']].map(([key, text]) => (
            <button key={key} type="button" aria-pressed={view === key} onClick={() => onView(key)}>{text}</button>
          ))}
        </div>
        <Link to={reportOpenPath(report.name, model)} className="open-btn">
          Open
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
               strokeLinecap="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8" /></svg>
        </Link>
      </div>
      {view === 'config' ? <ConfigView report={report} /> : (
        <div className="rview__body">
          {desk && !build && <NeverBuilt build={buildRun} canBuild={canBuild} />}
          {(build || deskFailed) && <BuiltPreview name={report.name} />}
          {!desk && !deskFailed && <SkeletonCard />}
        </div>
      )}
    </div>
  )
}

const FILTERS = [['all', 'All'], ['look', 'Needs a look'], ['scheduled', 'Scheduled']]

// A model's reports on the Overview: the list on the left, and the one picked
// on the right (?r=<name>). Without room for a preview a row opens the report.
function ReportsStage({ model }) {
  const { data, isLoading } = useReports()
  const { data: desk, dataUpdatedAt, isError: deskFailed } = useDesk()
  // In dev mode (`tracebi dev`) the agent's exhibits and your notes to it are
  // here, even before a report exists.
  const { data: appStatus } = useAppStatus()
  const dev = !!appStatus?.build_mode
  const { data: me } = useMe()
  const canBuild = me?.role === 'analyst' || me?.role === 'admin'
  const narrow = useNarrow(PREVIEW_QUERY)
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [view, setView] = useState('preview')

  const reports = (data || []).filter(r => reportBelongsToModel(r, model))
  const modelsOf = useReportModels()
  const notes = reviewNotes(attentionItems(desk, [], modelsOf)).filter(it => it.models.includes(model))
  const builds = Object.fromEntries((desk?.builds || []).map(b => [b.report, b]))
  // Before the desk has answered nothing is claimed about any build.
  const flagOf = r => (!desk ? null : builds[r.name] ? verdictFlag(builds[r.name].verdict) : NEVER_BUILT)
  const needsLook = r => !!desk && (!builds[r.name] || !isQuiet(builds[r.name].verdict))
  // How many each filter would show (Needs a look is not known until the desk answers).
  const count = key => (key === 'look' ? (desk ? reports.filter(needsLook).length : null)
    : key === 'scheduled' ? reports.filter(r => r.schedule).length : null)
  const keep = { all: () => true, look: needsLook, scheduled: r => !!r.schedule }[filter]
  const needle = query.toLowerCase()
  const listed = reports.filter(r => keep(r) && (
    r.name.toLowerCase().includes(needle) || (r.description || '').toLowerCase().includes(needle)))

  // The URL says which is picked (?r=name), so a link can name one; none named,
  // the first.
  const picked = searchParams.get('r')
  const selected = narrow ? null : reports.find(r => r.name === picked) || reports[0]
  const pick = name => setSearchParams(new URLSearchParams({ r: name }), { replace: !narrow })

  if (isLoading) return <SkeletonCard />
  if (!reports.length) {
    return (
      <>
        <Empty message={`No reports for ${model} yet. Reports for it live in reports/${model}/: scaffold one with tracebi new-report.`} />
        {dev && <ProjectFeed />}
      </>
    )
  }
  return (
    <>
      <AttentionStrip items={notes} />
      <div className={narrow ? 'rsplit rsplit--list' : 'rsplit'}>
        <div className="rsplit__list">
          <div className="rsplit__find">
            <SearchInput value={query} onChange={setQuery} placeholder="Search reports…" label="Search reports"
                         style={{ padding: 0, borderBottom: 0 }} />
            <div className="rsplit__chips" role="group" aria-label="Show">
              {FILTERS.map(([key, text]) => (
                <button key={key} type="button" className="rsplit__chip" aria-pressed={filter === key}
                        onClick={() => setFilter(key)}>
                  {text}{count(key) != null && ` (${count(key)})`}
                </button>
              ))}
            </div>
          </div>
          <ul className="rsplit__rows">
            {listed.map(r => (
              <ReportRow key={r.name} report={r} flag={flagOf(r)}
                         builtAt={builds[r.name] ? stamp(builds[r.name].built_at) : null}
                         selected={narrow ? undefined : selected?.name === r.name}
                         onPick={() => pick(r.name)} />
            ))}
          </ul>
          {!listed.length && <p className="rsplit__none">No report matches. Clear the search or pick “All”.</p>}
          {desk && <p className="rsplit__receipt">{receiptLine(reports, builds, dataUpdatedAt)}</p>}
        </div>
        {selected && (
          <ReportView key={selected.name} report={selected} model={model} desk={desk} deskFailed={deskFailed}
                      build={builds[selected.name]} canBuild={canBuild} view={view} onView={setView} />
        )}
      </div>
      {dev && <ProjectFeed />}
    </>
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
  // How a report is authored is a fact, not a status: neutral (amber means "needs a look").
  return (
    <span
      title={f.title}
      style={{
        display: 'inline-flex', alignItems: 'center',
        fontSize: 10, fontWeight: 500,
        padding: '1px 7px', borderRadius: 'var(--radius-sm)', whiteSpace: 'nowrap',
        background: 'var(--surface-2)', color: 'var(--muted)', border: '1px solid var(--border)',
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
  if (isLoading) return <div style={{ color: 'var(--muted)', fontSize: 13 }}><Spinner /> Loading code…</div>
  if (error) return <ErrorDetail error={error} />
  return <CodeFiles files={data?.files || []} hint={data?.hint} other={data?.other_files} />
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
  // Only what exists: a row of "Schedule —  Last run —  Builds —" says nothing.
  const present = cells.filter(([, value]) => value)
  if (!present.length) {
    return <span style={{ fontSize: 11, color: 'var(--muted)' }}>No schedule, never built</span>
  }
  return present.map(([label, value, title]) => (
    <span key={label} title={title} style={{ fontSize: 11, lineHeight: 1.35, maxWidth: '100%' }}>
      <span style={{ color: 'var(--muted)' }}>{label} </span>
      <span style={{ color: 'var(--text-2)', fontVariantNumeric: 'tabular-nums' }}>{value}</span>
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
    ['Reproduce', built.length ? `${good} of ${built.length}` : '—', null],
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

// All models: every report in one list, with what the library knows of each. A
// report opens as a page of its own.
function AllReports({ model }) {
  const { data, isLoading } = useReports()
  const { data: desk } = useDesk()
  const { data: pipelines } = usePipelines()
  // In dev mode (`tracebi dev`) the agent's exhibits and your notes to it are
  // here, even before a report exists.
  const { data: appStatus } = useAppStatus()
  const dev = !!appStatus?.build_mode
  const [query, setQuery] = useState('')
  const builds = Object.fromEntries((desk?.builds || []).map(b => [b.report, b]))
  // Which report is open lives in the URL (?r=name), so an attention item can
  // deep-link straight to a report and the link is shareable.
  const [, setSearchParams] = useSearchParams()
  const select = (name) => {
    setSearchParams(new URLSearchParams({ r: name }))
    window.scrollTo(0, 0)
  }

  const reports = (data || []).filter(r => reportBelongsToModel(r, model))
  const modelsOf = useReportModels()
  const filtered = reports.filter(r =>
    r.name.toLowerCase().includes(query.toLowerCase()) ||
    (r.description || '').toLowerCase().includes(query.toLowerCase())
  )
  const [closed, setClosed] = useState(() => new Set())
  const toggle = (folder) => setClosed(prev => {
    const next = new Set(prev)
    next.has(folder) ? next.delete(folder) : next.add(folder)
    return next
  })

  return (
    <div className="reports-page">
      <PageHeader pageKey="reports" model={model} />

      <AttentionStrip items={attentionItems(desk, pipelines, modelsOf)
        .filter(it => !model || it.models.includes(model))} />

      {!isLoading && reports.length === 0 ? (
        <>
          <Empty message={model
            ? `No reports for ${model} yet. Reports for it live in reports/${model}/: scaffold one with tracebi new-report.`
            : 'No reports yet. Scaffold one with tracebi new-report, or see Get Started.'} />
          {dev && <ProjectFeed />}
        </>
      ) : (
        <SplitLayout
          detail={false}
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
                            onClick={() => select(r.name)}
                            name={r.name.slice(r.name.lastIndexOf('/') + 1)}
                            sub={r.description}
                            meta={<><FormChip form={r.form} /><LibraryFacts report={r} /></>}
                            right={<ReceiptChip build={builds[r.name]} />}
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
          right={isLoading ? <SkeletonCard /> : (
            <>
              <ReportsOverview reports={reports} builds={desk?.builds || []} onOpen={select} />
              {dev && <ProjectFeed />}
            </>
          )}
        />
      )}
    </div>
  )
}

export default function Reports({ model = '', embedded = false }) {
  const open = useOpenReport()
  if (open) return <ReportPage name={open.name} model={open.model} />
  return embedded ? <ReportsStage model={model} /> : <AllReports model={model} />
}
