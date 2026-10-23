import { useState, useCallback, useEffect, useRef, forwardRef } from 'react'
import { Link, Navigate, useLocation, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import {
  useReports, useStartReportRun, useReportRun, useRuns,
  useReportLineage, useBuiltReport,
  useReportSource, reportDownloadUrl, reportShareUrl, useDesk, useModels,
  useAppStatus, useMe, useRole, useFolders, usePointing, useWorkbenchVersion, useWorkbenchState, useWorkbenchPreview,
} from '../api'
import { FRAME_SANDBOX, followSelection, listenToFrame, setFrameSelection, tellFrame, tellVerdict } from '../frameBridge'
import Workbench from '../components/Workbench'
import ReceiptFrame from '../components/ReceiptFrame'
import { CodeFiles } from '../components/CodeView'
import { useBuildTimeline } from '../buildTimeline'
import { ReportLineage } from '../components/ReportLineage'
import { LOCAL_DETAIL, VERDICT_LABEL, checkedVerdict, needsAction, verdictOf } from '../verdict'
import { humanise } from '../ask'
import { useLineFacts } from '../components/TheLine'
import { stamp } from '../when'
import { count, plural } from '../format'
import { Older } from './Runs'
import EditAsDraft from '../components/EditAsDraft'
import { ReportArt } from '../components/Art'
import {
  Moved, useModelLabel, useOpenReport, useNavMenu,
} from '../components/Scope'
import {
  PAGES, dataPath, folderOf, libraryPath, movedTo, reportBelongsToModel, reportModels, reportPagePath,
} from '../nav'
import { scheduleWords } from '../schedule'
import {
  Spinner, Verdict, Empty, Btn, ErrorDetail, PageTitle, PageSub,
  SearchInput, Segmented, SkeletonList, SkeletonCard, Time, useToast, useNarrow,
} from '../components/Shared'

function runDuration(rec) {
  if (!rec.finished || !rec.started) return null
  const s = (new Date(rec.finished) - new Date(rec.started)) / 1000
  if (!Number.isFinite(s) || s < 0) return null
  return s < 10 ? `${s.toFixed(1)}s` : `${Math.round(s)}s`
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

// Start a report run, follow it, and say how it ended: what Rebuild on the
// page and "Build it now" both do. The new build shows on the page (desk,
// built-report) once it ends.
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
      qc.invalidateQueries({ queryKey: ['runs'] })   // the panel's History
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

// ── The report's own page ────────────────────────────────────────────────────
// The page is the report. The app's nav stays as a rail; above the report, a
// slim header (where it is, its name, the app's verdict on this build and, when
// that asks for a look, why, and when it was built) and one command bar: Open,
// Share and Export for everyone; Rebuild and Edit as a draft for an analyst or
// admin, Build in dev mode, and the "About this build" panel (Receipt, Lineage,
// History, Files). A command the person's role cannot use is not shown, nor
// one that needs a build (Open, Share, Export, About this build) before there
// is one. The
// report fills the rest of the screen and keeps its own receipt drawer
// (tracebi.js); the app tells the frame its verdict, so the report's masthead
// chip says what the app's check found rather than the file's "Not checked".

const ICON = {
  rebuild: <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />,
  export: <path d="M12 3v12M7 10l5 5 5-5M4 21h16" />,
  share: <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />,
  edit: <path d="M4 20h4L19 9l-4-4L4 16z" />,
  build: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2.5" /></>,
  details: <><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></>,
  open: <path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" />,
  more: <><circle cx="5" cy="12" r="1.2" /><circle cx="12" cy="12" r="1.2" /><circle cx="19" cy="12" r="1.2" /></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>,
  file: <><path d="M6 2h9l5 5v15H6z" /><path d="M15 2v5h5" /></>,
  close: <path d="M6 6l12 12M18 6L6 18" />,
}

function Icon({ name, size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{ICON[name]}</svg>
  )
}

// A flat command in the toolbar: icon and word. `on` marks a toggle that is on.
const Cmd = forwardRef(function Cmd({ icon, children, caret, on, className = '', ...rest }, ref) {
  return (
    <button ref={ref} type="button" className={`cmd ${className}`} aria-pressed={on}
            aria-label={typeof children === 'string' ? children : undefined} {...rest}>
      {icon && <Icon name={icon} />}
      {children && <span className="cmd__lab">{children}</span>}
      {caret && (
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
             strokeLinecap="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
      )}
    </button>
  )
})

// A menu or popover under a command: Escape, a click elsewhere, or tabbing out
// closes it and puts focus back on the command.
function usePopover() {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const away = e => { if (!rootRef.current?.contains(e.target)) setOpen(false) }
    const esc = e => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      setOpen(false)
      rootRef.current?.querySelector('button')?.focus()
    }
    document.addEventListener('pointerdown', away)
    document.addEventListener('keydown', esc, true)
    return () => {
      document.removeEventListener('pointerdown', away)
      document.removeEventListener('keydown', esc, true)
    }
  }, [open])
  const onBlur = e => { if (!rootRef.current?.contains(e.relatedTarget)) setOpen(false) }
  return { open, setOpen, rootRef, onBlur }
}

// The three files a report can be exported as. Only the HTML carries its trace.
const EXPORTS = [['pdf', 'PDF'], ['xlsx', 'Excel'], ['html', 'HTML', 'the file with its trace']]

function ExportItems({ name, onPick }) {
  return (
    <>
      {EXPORTS.map(([format, label, tag]) => (
        <a key={format} role="menuitem" href={reportDownloadUrl(name, format)} download
           className="rp__item" onClick={onPick}>
          <Icon name="file" />{label}{tag && <span className="rp__tag">{tag}</span>}
        </a>
      ))}
      <div className="rp__rule" role="separator" />
      <p className="rp__menu-note">
        Only the HTML file can be checked on its own: <code>tracebi verify --file</code>.
      </p>
    </>
  )
}

function ExportMenu({ name }) {
  const { open, setOpen, rootRef, onBlur } = usePopover()
  return (
    <div ref={rootRef} className="rp__pop" onBlur={onBlur}>
      <Cmd icon="export" caret on={open} aria-haspopup="menu" aria-expanded={open}
           onClick={() => setOpen(o => !o)}>Export</Cmd>
      {open && (
        <div className="rp__menu" role="menu">
          <ExportItems name={name} onPick={() => setOpen(false)} />
        </div>
      )}
    </div>
  )
}

// On a phone the bar is Open, Share and this: the rest of the commands, the
// person's role permitting, in one menu.
function MoreMenu({ name, shown, canBuild, rebuild, running, canPoint, pointOn, togglePoint, onAbout }) {
  const { open, setOpen, rootRef, onBlur } = usePopover()
  const pick = fn => () => { setOpen(false); fn() }
  return (
    <div ref={rootRef} className="rp__pop rp__pop--end" onBlur={onBlur}>
      <Cmd icon="more" on={open} aria-haspopup="menu" aria-expanded={open} aria-label="More"
           onClick={() => setOpen(o => !o)} />
      {open && (
        <div className="rp__menu" role="menu">
          {shown && (
            <>
              <div className="rp__menu-head">Export</div>
              <ExportItems name={name} onPick={() => setOpen(false)} />
              <div className="rp__rule" role="separator" />
            </>
          )}
          {canBuild && shown && (
            <button type="button" role="menuitem" className="rp__item" onClick={pick(rebuild)} disabled={running}>
              <Icon name="rebuild" />{running ? 'Rebuilding…' : 'Rebuild'}
            </button>
          )}
          <EditAsDraft kind="reports" path={name} bare className="rp__item" role="menuitem" />
          {canPoint && (
            <button type="button" role="menuitem" className="rp__item" onClick={pick(togglePoint)}>
              <Icon name="build" />{pointOn ? 'Leave Build mode' : 'Build'}
            </button>
          )}
          {!pointOn && shown && (
            <button type="button" role="menuitem" className="rp__item" onClick={pick(onAbout)}>
              <Icon name="details" />About this build
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function SharePopover({ name }) {
  const { open, setOpen, rootRef, onBlur } = usePopover()
  const [copied, setCopied] = useState(false)
  const url = reportShareUrl(name)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard refused: the link is selectable in the field */ }
  }
  return (
    <div ref={rootRef} className="rp__pop" onBlur={onBlur}>
      <Cmd icon="share" on={open} aria-haspopup="dialog" aria-expanded={open}
           onClick={() => setOpen(o => !o)}>Share</Cmd>
      {open && (
        <div className="rp__menu rp__menu--share" role="dialog" aria-label="Share">
          <div className="rp__menu-title">Share this report</div>
          <div className="rp__share">
            <input readOnly value={url} aria-label="Link to this report" onFocus={e => e.target.select()} />
            <Btn onClick={copy}>{copied ? 'Link copied' : 'Copy link'}</Btn>
          </div>
          <p className="rp__menu-note">Opens this build. Readers sign in the same way they sign in to the app.</p>
        </div>
      )}
    </div>
  )
}

const TABS = [['receipt', 'Trace'], ['lineage', 'Lineage'], ['history', 'History'], ['files', 'Files']]
const PANEL_KEY = 'tracebi-report-panel'
// Narrower than this, the command bar is Open, Share and a menu of the rest.
const BAR_QUERY = '(max-width: 720px)'

function readPanel() {
  try {
    const v = JSON.parse(localStorage.getItem(PANEL_KEY) || 'null')
    return v && TABS.some(([k]) => k === v.tab) ? { open: !!v.open, tab: v.tab } : { open: false, tab: 'receipt' }
  } catch { return { open: false, tab: 'receipt' } }
}

function Facts({ children }) { return <dl className="rpanel__kv">{children}</dl> }
function Fact({ k, children }) { return <><dt>{k}</dt><dd>{children}</dd></> }

// The Trace tab: a few facts the trace does not carry (whether the app's
// check still holds, the model, the figures, the schedule, the kind), then the
// build's own certificate, its chip in the app's verdict.
function ReceiptTab({ report, model, shown, lastBuild, checkedAt, verdict, onCheck, checking }) {
  const manifest = shown?.manifest
  const p = figureProvenance(manifest)
  const words = scheduleWords(report.schedule)
  const last = report.last_run
  const labelOf = useModelLabel()
  const queries = (manifest?.embedded_data || []).length
  const form = (FORMS[report.form] || FORMS.code).label
  return (
    <>
      <section className="rpanel__sec">
        {report.description && <p className="rpanel__lead rpanel__lead--facts">{report.description}</p>}
        <Facts>
          {lastBuild && (
            <Fact k="Checked">
              {!verdict ? 'Checking…' : checkedAt ? <Time iso={checkedAt} /> : 'Not yet'}
              {verdict && verdict.state !== 'reproduces' && <div className="rpanel__hint">{verdict.detail}</div>}
              <div><button type="button" className="rpanel__link" onClick={onCheck} disabled={checking}>Check again</button></div>
            </Fact>
          )}
          {manifest && manifest.schema_version !== 2 && (
            <Fact k="Trace">○ Manifest v{manifest.schema_version ?? '?'}: no per-figure queries to re-run</Fact>
          )}
          {model && <Fact k="Model"><Link to={dataPath(model, 'model')}>{labelOf(model)}</Link></Fact>}
          {manifest && (
            <Fact k="Figures">
              {count(p.total, 'figure')} from {count(queries, 'query', 'queries')}
              {p.derived > 0 && <div><span aria-hidden="true">○</span> {p.derived} from python, which cannot be re-run</div>}
              {p.unverified > 0 && <div><span aria-hidden="true">△</span> {p.unverified} unverified</div>}
            </Fact>
          )}
          <Fact k="Schedule">
            {words ? words.long : 'Not scheduled'}
            {!words && <div className="rpanel__hint">A <code>schedule</code> block in report.json builds it on a timetable.</div>}
          </Fact>
          {last && (
            <Fact k="Last run">
              <Time iso={last.time} />
              {SCHEDULE_ALERT[last.status] && (
                <> · <span className={`flag flag--${SCHEDULE_ALERT[last.status][0]}`}>
                  <span aria-hidden="true">{SCHEDULE_ALERT[last.status][1]}</span> {last.status}
                </span></>
              )}
            </Fact>
          )}
          <Fact k="Kind">{form}</Fact>
        </Facts>
      </section>
      {shown?.html
        ? <ReceiptFrame html={shown.html} verdict={verdict?.state} title={`How ${report.display_name || report.name} was made`}
                        file={`${report.name.slice(report.name.lastIndexOf('/') + 1)}.html`} />
        : <p className="rpanel__empty">Nothing to trace yet: this report has not been built.</p>}
    </>
  )
}

// What the run store records for a report, and what the History tab calls it.
const RUN_KIND = { report_build: 'Build', background_run: 'Build from the app', schedule: 'Scheduled run' }
const BUILD_KINDS = new Set(['report_build', 'background_run'])
const DONE = new Set(['succeeded', 'success', 'built', 'delivered'])
const FAILED = new Set(['failed', 'error', 'refused'])

// A report's runs, newest first: every build (from the app, the command line or
// a schedule), not only the ones started here. As on History: the newest
// successful build carries the page's verdict, a scheduled run the verdict its
// check recorded, and every older build a plain "Not checked".
function HistoryTab({ name, verdict }) {
  const { data, isLoading, error } = useRuns('', name)
  const [open, setOpen] = useState(false)
  if (isLoading) return <div className="rp__none"><Spinner /> Loading builds…</div>
  if (error) return <ErrorDetail error={error} />
  const runs = (Array.isArray(data) ? data : []).filter(r => RUN_KIND[r.kind])
  if (!runs.length) return <p className="rp__none">No builds recorded yet.</p>
  const newest = runs.find(r => BUILD_KINDS.has(r.kind) && r.status === 'succeeded')
  const said = r => {
    if (!DONE.has(r.status)) return null
    if (r.verdict) return checkedVerdict(r.verdict)
    if (r === newest) return verdict
    return { state: 'not-checked', detail: 'Only the latest build of a report is re-checked.' }
  }
  // As on History: the newest build (and anything since it) shows; older builds fold.
  const shown = runs.indexOf(newest) + 1 || 1
  const older = runs.slice(shown)
  const row = r => {
    const dur = runDuration(r)
    const v = said(r)
    return (
      <li key={r.id}>
        <span>{r.status === 'running' ? '… Running' : <Time iso={r.started} />}</span>
        <span>{RUN_KIND[r.kind]}{dur ? ` · ${dur}` : ''}{r.actor ? ` · ${r.actor}` : ''}</span>
        {v && <Verdict state={v.state} detail={v.detail} size="sm" />}
        {FAILED.has(r.status) && (
          <span className="flag flag--bad">
            <span aria-hidden="true">✕</span> {r.status === 'refused' ? 'Refused' : 'Failed'}
            {r.detail?.error ? `: ${r.detail.error}` : ''}
          </span>
        )}
      </li>
    )
  }
  return (
    <>
      <ul className="rp__runs">
        {runs.slice(0, shown).map(row)}
        {older.length > 0 && (
          <li className="rp__runs-fold">
            <Older older={older.map(run => ({ run }))} open={open} onToggle={() => setOpen(o => !o)} noun="build" />
          </li>
        )}
        {open && older.map(row)}
      </ul>
      <Link to={`/runs?target=${encodeURIComponent(name)}`} className="rpanel__link">Every run in History</Link>
    </>
  )
}

// A scheduled run that did not go out: failed, or built but refused or empty.
const SCHEDULE_ALERT = { failed: ['bad', '✕'], refused: ['warn', '△'], empty: ['warn', '△'] }

// The lineage, top to bottom: each stage and what is in it. The drawn flow is one click away.
function LineageTab({ name, manifest }) {
  const { mutate: fetchLineage, data, error } = useReportLineage()
  const [full, setFull] = useState(false)
  useEffect(() => { if (manifest) fetchLineage(name) }, [name, manifest, fetchLineage])
  if (!manifest) return <p className="rpanel__empty">Nothing to trace yet: this report has not been built.</p>
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${name.slice(name.lastIndexOf('/') + 1)}.manifest.json`
    a.click()
    URL.revokeObjectURL(url)
  }
  const flow = data?.flow
  const mark = status => (status === 'warn' ? '△ ' : status === 'derived' ? '○ python: ' : '')
  return (
    <div className="rpanel__sec rpanel__sec--last">
      <p className="rpanel__lead rpanel__lead--small">Where the numbers on this page came from, as this build recorded it.</p>
      {flow ? (
        <ol className="chain">
          {flow.columns.map(col => {
            const nodes = flow.nodes.filter(n => n.column === col.index)
            if (!nodes.length) return null
            return (
              <li key={col.index}>
                <span className="chain__dot" aria-hidden="true" />
                <div className="chain__kind">{col.label}</div>
                {nodes.map(n => (
                  <div key={n.id} className="chain__node">
                    <b className="mono">{n.label}</b>{n.sub ? <> · {n.sub}</> : null}
                    {n.status && n.status !== 'ok' && n.status !== 'muted' && <div className="chain__warn">{mark(n.status)}{n.status === 'warn' ? 'needs a look' : ''}</div>}
                    {n.detail?.contract?.status === 'satisfied' && <div className="chain__sub">The sink satisfied its contract.</div>}
                  </div>
                ))}
              </li>
            )
          })}
        </ol>
      ) : error ? <ErrorDetail error={error} />
        : <div className="rp__none"><Spinner /> Loading lineage…</div>}
      <div className="rpanel__buttons">
        <Btn variant="outline" size="sm" onClick={() => setFull(true)} disabled={!flow}>Full graph</Btn>
        <Btn variant="outline" size="sm" onClick={download}>Download manifest</Btn>
      </div>
      <p className="rpanel__hint">Lineage starts at the sink. The analysis inside a transform is not traced.</p>
      {full && flow && (
        <FullGraph onClose={() => setFull(false)}><ReportLineage flow={flow} /></FullGraph>
      )}
    </div>
  )
}

function FullGraph({ onClose, children }) {
  const close = useRef(null)
  useEffect(() => {
    const esc = e => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    document.addEventListener('keydown', esc, true)
    close.current?.focus()
    return () => document.removeEventListener('keydown', esc, true)
  }, [onClose])
  return (
    <>
      <div className="rp__scrim" onClick={onClose} aria-hidden="true" />
      <div className="rp__full" role="dialog" aria-modal="true" aria-label="Lineage graph">
        <div className="rp__full-head">
          <h2>Lineage graph</h2>
          <button ref={close} type="button" className="rp__close" onClick={onClose} aria-label="Close the graph">
            <Icon name="close" />
          </button>
        </div>
        {children}
      </div>
    </>
  )
}

// "About this build", beside the report (a sheet from the bottom on a phone):
// its tabs, a close, and the open tab's content.
function ReportPanel({ tab, setTab, onClose, ...props }) {
  const { report, shown, verdict } = props
  return (
    <aside className="rpanel" aria-label="About this build">
      <div className="rpanel__top">
        <h2 className="rpanel__title">About this build</h2>
        <button type="button" className="cmd" onClick={onClose} aria-label="Close the panel"><Icon name="close" /></button>
      </div>
      <div className="rpanel__tabs">
        <Segmented options={TABS} value={tab} onChange={setTab} label="About this build" panel="rp-tabpanel" />
      </div>
      <div className="rpanel__body" role="tabpanel" id="rp-tabpanel" aria-labelledby={`rp-tabpanel-${tab}`}>
        {tab === 'receipt' && <ReceiptTab {...props} />}
        {tab === 'lineage' && <LineageTab name={report.name} manifest={shown?.manifest} />}
        {tab === 'history' && <div className="rpanel__sec rpanel__sec--last"><HistoryTab name={report.name} verdict={verdict} /></div>}
        {tab === 'files' && <div className="rpanel__sec rpanel__sec--last"><ReportSource name={report.name} /></div>}
      </div>
    </aside>
  )
}

// A report with no build: nothing to show, and nothing is built by looking.
// A viewer cannot build, so is told who does instead of how.
function NeverBuilt({ build, canBuild }) {
  const busy = build.running || build.status === 'succeeded'
  const viewer = useRole() === 'viewer'
  return (
    <div className="rprev__never">
      <Verdict state="never-built" />
      <p>{viewer ? 'Not built yet. An analyst or admin builds it.'
        : 'There is no page to show yet. Build it once and the preview, its trace and the check appear here.'}</p>
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
  const [panel, setPanel] = useState(readPanel)
  const [disk, setDisk] = useState(null)
  const [checking, setChecking] = useState(false)
  const toast = useToast()
  const frameRef = useRef(null)
  const panelOpener = useRef(null)
  const qc = useQueryClient()
  const labelOf = useModelLabel()
  const navMenu = useNavMenu()
  const narrow = useNarrow(BAR_QUERY)
  const { data: me } = useMe()
  const canBuild = me?.role === 'analyst' || me?.role === 'admin'
  const { data: desk, dataUpdatedAt, isError: deskFailed, isFetching: checkingDesk } = useDesk()
  const lastBuild = (desk?.builds || []).find(b => b.report === name)
  const refreshed = useLineFacts(model).transform.goodAt
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
  // A live report recomputes its figures in the frame when its reader picks
  // a filter, and says so: the header shows Local and the selection, each
  // field a chip that clears it. A new page starts as authored.
  const [selection, setSelection] = useState(null)
  useEffect(() => {
    setSelection(null)
    const frame = frameRef.current
    return frame ? followSelection(frame, s => setSelection(s.local && !s.authored ? s.selection || {} : null))
      : undefined
  }, [frameHtml])
  const clearField = field => {
    const rest = { ...selection }
    delete rest[field]
    setFrameSelection(frameRef.current, rest)
  }
  useEffect(() => {
    // Pointing is at the live report; an earlier version is only for looking.
    if (!pointOn || !timeline.isLatest) return undefined
    const frame = frameRef.current
    if (!frame) return undefined
    // The report runtime does the pointing inside its sandboxed frame; it says
    // what was pointed at. Ask it to start now, and again whenever a new page
    // says it is up.
    const start = () => tellFrame(frame, { type: 'point', on: true })
    const stop = listenToFrame(frame, m => {
      if (m.type === 'ready') start()
      else if (m.type === 'pointed') { setPointed(m.point); sendPointing({ name, pointing: m.point }) }
      else if (m.type === 'point-cleared') { setPointed(null); sendPointing({ name, pointing: null }) }
    })
    start()
    return () => { stop(); tellFrame(frame, { type: 'point', on: false }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointOn, frameHtml, name, timeline.isLatest])
  // Leaving Point mode, or this report, stops pointing: the agent should not
  // act on something you are no longer looking at.
  useEffect(() => () => {
    if (pointOn) sendPointing({ name, pointing: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pointOn, name])
  // The workbench and the panel share the right edge: one at a time.
  const togglePoint = () => {
    setWantBuild(on => !on); setPointed(null); timeline.reset()
    setPanel(p => ({ ...p, open: false }))
  }


  // The panel's open/closed and its tab are remembered for next time.
  useEffect(() => {
    try { localStorage.setItem(PANEL_KEY, JSON.stringify(panel)) } catch { /* private window */ }
  }, [panel])
  const showPanel = panel.open && !pointOn
  const openPanel = (tab, e) => {
    panelOpener.current = e?.currentTarget || null
    setWantBuild(false)
    setPanel(p => (p.open && p.tab === tab ? { ...p, open: false } : { open: true, tab }))
  }
  // "About this build" opens the panel on the tab it was last left on.
  const togglePanel = e => {
    panelOpener.current = e?.currentTarget || null
    setPanel(p => ({ ...p, open: !p.open }))
  }
  const closePanel = useCallback(() => {
    setPanel(p => ({ ...p, open: false }))
    if (panelOpener.current?.isConnected) panelOpener.current.focus()
  }, [])
  // Escape closes the panel (a menu or dialog has already taken the key).
  useEffect(() => {
    if (!showPanel) return undefined
    const esc = e => { if (e.key === 'Escape' && !e.defaultPrevented) closePanel() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [showPanel, closePanel])

  // The desk re-runs every recorded query against the warehouse as it is now.
  const checkAgain = async () => {
    setChecking(true)
    try {
      await qc.refetchQueries({ queryKey: ['desk'] })
      const row = (qc.getQueryData(['desk'])?.builds || []).find(b => b.report === name)
      const v = row && verdictOf({ report, build: row })
      toast(row ? `Checked again: ${VERDICT_LABEL[v.state]}.` : 'There is no build to check.',
        v?.state === 'does-not-reproduce' ? 'error' : 'info')
    } catch (err) {
      toast(`The check failed: ${err.message}`, 'error')
    } finally {
      setChecking(false)
    }
  }

  // A check still running would show the verdict from before it.
  const verdict = desk && !checkingDesk ? verdictOf({
    report, build: lastBuild, contracts: shown?.manifest?.transform_contracts, checkedAt: dataUpdatedAt,
  }) : null
  const message = needsAction(verdict) ? verdict : null
  // The report's own chip says what the app's check found. Only the build is
  // told: Build mode's working preview is a draft, and says so itself.
  useEffect(() => (pointOn ? undefined : tellVerdict(frameRef.current, verdict)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [frameHtml, pointOn, verdict?.state, verdict?.detail])
  const builtAt = shown?.manifest?.rendered_at ? stamp(shown.manifest.rendered_at) : null
  const opening = !frameHtml && !running && ((!desk && !deskFailed) || built.isLoading)
  const label = report.display_name || name.slice(name.lastIndexOf('/') + 1)
  const words = scheduleWords(report.schedule)

  return (
    <div className={pointOn ? 'rp rp--build' : 'rp'}>
      <header className="rp__head">
        <nav aria-label="Where this report is" className="rp__crumb">
          {navMenu && (
            <button type="button" className="cmd rp__menu-btn" aria-label="Menu" onClick={navMenu.open}><Icon name="menu" size={18} /></button>
          )}
          <Link to="/">Reports</Link>
          {model && (
            <>
              <span aria-hidden="true">›</span>
              <Link to={libraryPath(model)}>{labelOf(model)}</Link>
            </>
          )}
        </nav>
        <div className="rp__titlerow">
          <h1 className="rp__name" title={name}>{label}</h1>
          {selection ? <Verdict state="local" detail={LOCAL_DETAIL} onClick={e => openPanel('receipt', e)} />
            : verdict && <Verdict state={verdict.state} detail={verdict.detail} onClick={e => openPanel('receipt', e)} />}
          {selection && (
            <ul className="rp__sel" aria-label="Selection">
              {Object.entries(selection).map(([field, values]) => (
                <li key={field}>
                  <button type="button" className="rp__selchip" onClick={() => clearField(field)}
                          title={`Clear ${humanise(field)}`}>
                    {humanise(field)}: {Array.isArray(values) ? values.join(', ') : JSON.stringify(values)}
                    <span aria-hidden="true"> ×</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="rp__meta">
            {builtAt && (
              <span title="Opening a report shows its last build. Rebuild or a schedule refreshes the data.">Built {builtAt}</span>
            )}
            {refreshed && <span className="rp__hide-sm">Data refreshed <Time iso={refreshed} /></span>}
            {words && <span className="rp__hide-sm"><Icon name="calendar" size={13} /> {words.short}</span>}
          </div>
        </div>
        {message && (
          <p role="status" className={`rp__why${message.state === 'does-not-reproduce' ? ' rp__why--bad' : ''}`}>
            {message.detail}
          </p>
        )}

      <div role="toolbar" aria-label="Report actions" className={narrow ? 'rp__bar rp__bar--narrow' : 'rp__bar'}>
        {shown && (
          <a className="cmd" href={reportShareUrl(name)} target="_blank" rel="noopener noreferrer"
             aria-label="Open" title="Open this build in a new tab, as readers receive it">
            <Icon name="open" /><span className="cmd__lab">Open</span>
          </a>
        )}
        {shown && <SharePopover name={name} />}
        {!narrow && shown && <ExportMenu name={name} />}
        <span className="rp__grow" />
        {narrow ? (
          // A viewer on a report nobody has built would open an empty menu.
          (shown || canBuild || canPoint) && (
            <MoreMenu name={name} shown={shown} canBuild={canBuild} rebuild={rebuild} running={running}
                      canPoint={canPoint} pointOn={pointOn} togglePoint={togglePoint}
                      onAbout={() => { setWantBuild(false); setPanel(p => ({ ...p, open: true })) }} />
          )
        ) : (
          <>
            {canBuild && shown && (
              <Cmd icon="rebuild" onClick={rebuild} disabled={running}
                   title="Re-run every query and build the report again">
                {running ? <><Spinner size={12} /> Rebuilding…</> : 'Rebuild'}
              </Cmd>
            )}
            <EditAsDraft kind="reports" path={name} bare />
            {canPoint && (
              <Cmd icon="build" on={pointOn} onClick={togglePoint}
                   title="Build mode: point at a figure or area, leave your agent notes, and watch it work.">
                Build
              </Cmd>
            )}
            {!pointOn && shown && (
              <>
                {(canBuild || canPoint) && <span className="rp__vr" aria-hidden="true" />}
                <Cmd icon="details" on={showPanel} onClick={togglePanel}>About this build</Cmd>
              </>
            )}
          </>
        )}
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
          {frameHtml ? (
            <iframe ref={frameRef} srcDoc={frameHtml} sandbox={FRAME_SANDBOX} title={name} className="rp__frame" />
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
        {showPanel && (
          <>
            <div className="rp__scrim rp__scrim--panel" onClick={closePanel} aria-hidden="true" />
            <ReportPanel tab={panel.tab} setTab={tab => setPanel({ open: true, tab })} onClose={closePanel}
                         report={report} model={model} shown={shown} lastBuild={lastBuild}
                         checkedAt={dataUpdatedAt} verdict={verdict} onCheck={checkAgain} checking={checking} />
          </>
        )}
      </div>
    </div>
  )
}

/** A report as a page of its own: the whole screen, a light bar of its own. */
export function ReportPage({ name }) {
  const { data: reports, isLoading } = useReports()
  const report = (reports || []).find(r => r.name === name)
  if (isLoading) return <div className="rp"><main className="rp__state"><SkeletonCard /></main></div>
  if (!report) {
    return (
      <div className="rp">
        <header className="rp__head">
          <nav aria-label="Where this report is" className="rp__crumb">
            <Link to="/">Reports</Link>
          </nav>
        </header>
        <main className="rp__state">
          <p className="rp__lead">No report named “{name}”.</p>
          <p className="rp__none">It may have been renamed or removed.</p>
        </main>
      </div>
    )
  }
  return <OpenReport key={name} report={report} model={reportModels(report)[0] || ''} />
}

// How a report is authored, from the reports API's `form` field: a JSON spec
// in the default style, or a custom package with its own template and style.
const FORMS = {
  spec: { label: 'JSON spec', title: 'A reports/<name>.json spec: sections in the default style' },
  package: { label: 'Custom', title: 'A reports/<name>/ package: its own template, style and scripts' },
  code: { label: 'Code', title: 'Registered from Python code' },
}

// The files that define the report, read-only. A spec is one JSON file; a
// package is report.json + template.html + style.css + script.js (+ assets).
function ReportSource({ name }) {
  const { data, isLoading, error } = useReportSource(name, true)
  if (isLoading) return <div style={{ color: 'var(--muted)', fontSize: 13 }}><Spinner /> Loading code…</div>
  if (error) return <ErrorDetail error={error} />
  return <CodeFiles files={data?.files || []} hint={data?.hint} other={data?.other_files} />
}

// ── The library: every report, by folder ────────────────────────────────────

// Reports in folders are named by their path ("finance/weekly"). The list
// groups them under their folder; top-level reports come first, unheaded.
function groupByFolder(reports, mine) {
  const groups = new Map()
  // Their own My published is always there, even before anything is in it.
  if (mine) groups.set(mine, [])
  for (const r of reports) {
    const folder = folderOf(r.name)
    if (!groups.has(folder)) groups.set(folder, [])
    groups.get(folder).push(r)
  }
  return [...groups.entries()]
    .sort(([a], [b]) => (a === '' ? -1 : b === '' ? 1 : a === mine ? -1 : b === mine ? 1 : a.localeCompare(b)))
    .map(([folder, items]) => ({ folder, items }))
}

const YOU_CAN = {
  publish: 'You can publish here',
  request: 'You can ask to publish here',
}

// What the person may do in a folder, and (to a manager, or the owner of a
// personal folder) who holds what there. Permissions are edited in the
// folder's _folder.yaml: the app only shows them.
function FolderNote({ info }) {
  const p = info.permissions
  const can = YOU_CAN[info.mode] || 'View only'
  return (
    <div className="lfolder__note">
      <div>
        {can}.
        {info.mine && ' Only you see this folder unless you share it by file.'}
        {info.personal && !info.mine && ' Shared with you by its owner.'}
        {info.accepts === 'checkable' && ' It accepts only reports whose every number a query can re-run.'}
      </div>
      {p && (
        <div style={{ marginTop: 6 }}>
          {p.malformed
            ? <div>The folder file cannot be read, so nobody but admins is granted anything.</div>
            : Object.keys(p.grants).length === 0
              ? <div>{info.mine
                ? 'Nobody else is granted anything.'
                : 'No folder file applies, so roles decide.'}</div>
              : (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {Object.entries(p.grants).map(([level, who]) => (
                    <li key={level}><span style={{ textTransform: 'capitalize' }}>{level}</span>: {who.join(', ')}</li>
                  ))}
                </ul>
              )}
          <div style={{ color: 'var(--muted)' }}>
            {p.file ? <>From <code>{p.file}</code>. </> : null}
            Permissions are changed in the folder&rsquo;s <code>_folder.yaml</code> file. Editing them here is not
            available yet.
          </div>
        </div>
      )}
    </div>
  )
}

// A folder's permissions are worth a line only where they differ from the
// rest of the library: a _folder.yaml applies, it is a personal folder, it
// accepts only checkable reports, or the person's level there is not their
// usual one.
function permissionsWorthSaying(info, usual) {
  if (!info) return false
  const p = info.permissions
  return !!(info.personal || p?.file || p?.malformed || info.accepts === 'checkable' || info.level !== usual)
}

// One report: its name, what it is, whether its numbers still hold, when it
// was built and when it is built again. The whole row opens it.
function LibraryRow({ report, verdict, built }) {
  const words = scheduleWords(report.schedule)
  const name = report.display_name || report.name.slice(report.name.lastIndexOf('/') + 1)
  return (
    <li>
      <Link to={reportPagePath(report.name)} className="lrow" data-report={report.name}>
        <span className="lrow__main">
          <span className="lrow__name">{name}</span>
          {report.description && <span className="lrow__desc" title={report.description}>{report.description}</span>}
        </span>
        <span className="lrow__side">
          {verdict && <Verdict state={verdict.state} detail={verdict.detail} size="sm" />}
          {built && <span className="lrow__built">Built <Time iso={built.built_at} /></span>}
          {words && (
            <span className="lrow__sched" title={words.long}><Icon name="calendar" size={12} /> {words.short}</span>
          )}
        </span>
      </Link>
    </li>
  )
}

function LibraryFolder({ folder, label, items, info, usual, open, onToggle, verdictFor, builds, searching }) {
  const [perm, setPerm] = useState(false)
  const worth = permissionsWorthSaying(info, usual)
  return (
    <section className="lfolder" aria-label={label}>
      {folder && (
        <div className="lfolder__head">
          <button type="button" className="lfolder__toggle" onClick={onToggle} aria-expanded={open}>
            <span aria-hidden="true" className={`folder-caret${open ? ' open' : ''}`}>▸</span>
            <span className="lfolder__label">{label}</span>
            <span className="lfolder__count">{items.length}</span>
          </button>
          {worth && (
            <button type="button" className="lfolder__perm" aria-expanded={perm} onClick={() => setPerm(o => !o)}>
              Permissions
            </button>
          )}
        </div>
      )}
      {worth && perm && <FolderNote info={info} />}
      {open && folder && !items.length && !searching && (
        <p className="lfolder__none">
          Nothing here yet. Publish a draft to My published from Review to put a report here.
        </p>
      )}
      {open && items.length > 0 && (
        <ul className="lfolder__rows">
          {items.map(r => (
            <LibraryRow key={r.name} report={r} verdict={verdictFor(r)} built={builds[r.name]} />
          ))}
        </ul>
      )}
    </section>
  )
}

// What the list holds before you open anything: how many reports, and how
// many of their last builds reproduce, need a look, or were never built, in
// the words of the chip each counts.
function Glance({ reports, verdictFor, known }) {
  const count = {}
  reports.forEach(r => { const v = verdictFor(r); if (v) count[v.state] = (count[v.state] || 0) + 1 })
  const parts = [
    ['reproduces', n => `${n} reproduce${n === 1 ? 's' : ''}`],
    ['needs-a-look', n => `${n} ${n === 1 ? 'needs' : 'need'} a look`],
    ['does-not-reproduce', n => `${n} ${n === 1 ? 'does' : 'do'} not reproduce`],
    ['not-checked', n => `${n} not checked`],
    ['never-built', n => `${n} never built`],
  ].filter(([state]) => count[state] || ['reproduces', 'needs-a-look', 'never-built'].includes(state))
  return (
    <div className="glance" role="group" aria-label="At a glance">
      <span className="glance__item"><b>{reports.length}</b> {plural(reports.length, 'report')}</span>
      {/* A count of nothing is not a signal: it reads muted, not in its chip's colour. */}
      {known && parts.map(([state, say]) => (
        <span key={state} className={`glance__item glance__item--${count[state] ? state : 'none'}`}>{say(count[state] || 0)}</span>
      ))}
    </div>
  )
}

/**
 * The library (`/`): every report the person may see, by folder, filtered by
 * model (?model=<name>) and a search. A row opens the report as a page of its
 * own. Nothing here builds or refreshes anything.
 */
export default function Library() {
  const { search: rawSearch } = useLocation()
  const moved = movedTo('/', rawSearch)   // an old ?r=<name> link opens the report
  const { data, isLoading } = useReports()
  const { data: modelList } = useModels()
  const { data: desk } = useDesk()
  const { data: folderData } = useFolders()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [closed, setClosed] = useState(() => new Set())
  const role = useRole()
  if (moved) return <Navigate to={moved} replace />

  const models = modelList || []
  const asked = params.get('model') || ''
  const model = models.some(m => m.name === asked) ? asked : ''
  const labelOf = name => models.find(m => m.name === name)?.label || name
  const all = data || []
  const reports = all.filter(r => reportBelongsToModel(r, model))
  const builds = Object.fromEntries((desk?.builds || []).map(b => [b.report, b]))
  // Before the desk has answered nothing is claimed about any build.
  const verdictFor = r => (desk ? verdictOf({ report: r, build: builds[r.name] }) : null)
  const needle = query.trim().toLowerCase()
  const listed = reports.filter(r => !needle || [r.display_name, r.name, r.description]
    .some(t => (t || '').toLowerCase().includes(needle)))
  const folders = folderData?.folders || []
  const folderInfo = Object.fromEntries(folders.map(f => [f.path, f]))
  // The level most folders give this person: a folder file is what moves one off it.
  const tally = {}
  folders.forEach(f => { tally[f.level] = (tally[f.level] || 0) + 1 })
  const usual = Object.keys(tally).sort((x, y) => tally[y] - tally[x])[0]
  // A viewer cannot publish, so has no My published to fill.
  const canPublish = role === 'analyst' || role === 'admin'
  const mine = needle || model || !canPublish ? null : folderData?.personal
  const pick = name => setParams(name ? new URLSearchParams({ model: name }) : new URLSearchParams())
  const toggle = folder => setClosed(prev => {
    const next = new Set(prev)
    next.has(folder) ? next.delete(folder) : next.add(folder)
    return next
  })
  const folderLabel = (folder, info) => (info?.mine ? 'My published'
    : models.some(m => m.name === folder) ? labelOf(folder) : folder.split('/').join(' / '))

  return (
    <div className="library">
      <header className="page-header">
        <PageTitle>Reports</PageTitle>
        <PageSub>{PAGES[0].sub}</PageSub>
      </header>
      {isLoading ? <SkeletonList /> : !all.length && !(canPublish && folderData?.personal) ? (
        <Empty message="No reports yet. Scaffold one with tracebi new-report, or see Get started." />
      ) : (
        <>
          <Glance reports={reports} verdictFor={verdictFor} known={!!desk} />
          <div className="library__find">
            {models.length > 1 && (
              <div className="library__chips" role="group" aria-label="Model">
                <button type="button" className="rsplit__chip" aria-pressed={!model} onClick={() => pick('')}>
                  All models <span className="library__n">{all.length}</span>
                </button>
                {models.map(m => (
                  <button key={m.name} type="button" className="rsplit__chip" aria-pressed={model === m.name}
                          onClick={() => pick(m.name)} title={m.name}>
                    {m.label || m.name}{' '}
                    <span className="library__n">{all.filter(r => reportBelongsToModel(r, m.name)).length}</span>
                  </button>
                ))}
              </div>
            )}
            <SearchInput value={query} onChange={setQuery} placeholder="Search reports…" label="Search reports"
                         style={{ padding: 0, borderBottom: 0 }} />
          </div>
          <div className="library__list">
            {!listed.length && !mine
              ? <p className="lfolder__none">No report matches. Clear the search or pick All models.</p>
              : groupByFolder(listed, mine).map(({ folder, items }) => (
                <LibraryFolder key={folder || '(top)'} folder={folder} label={folderLabel(folder, folderInfo[folder])}
                               items={items} info={folderInfo[folder]} usual={usual}
                               // A search always shows its matches, even in a closed folder.
                               open={!folder || !!needle || !closed.has(folder)} onToggle={() => toggle(folder)}
                               verdictFor={verdictFor} builds={builds} searching={!!needle} />
              ))}
          </div>
        </>
      )}
    </div>
  )
}

/** /reports/<name>: that report as a page of its own; /reports alone is the library. */
export function ReportRoute() {
  const open = useOpenReport()
  return open ? <ReportPage name={open.name} /> : <Moved />
}
