import { useState, useCallback, useEffect, useLayoutEffect, useRef, forwardRef } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import {
  useReports, useStartReportRun, useReportRun, useRuns,
  useReportLineage, useBuiltReport,
  useReportSource, reportDownloadUrl, reportShareUrl, reportCoverUrl, useDesk, useModels,
  useAppStatus, useMe, useRole, useFolders, usePointing, useWorkbenchVersion, useWorkbenchState, useWorkbenchPreview, fetchDeskFresh,
  usePipelines, useStartPipelineRun,
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
import { count } from '../format'
import { Older } from './Runs'
import EditAsDraft from '../components/EditAsDraft'
import { ReportArt } from '../components/Art'
import { CoverRow, CoverTile, FolderTile, Health, builtLine, tagOf } from '../components/Directory'
import { useDocumentTitle } from '../components/Layout'
import FolderPage, { FolderNote } from './Folder'
import { folderPath, hueStyle, newestBuild, useBuilds, useLibrary } from '../folders'
import {
  Moved, useModelLabel, useOpenReport, useNavMenu,
} from '../components/Scope'
import {
  folderOf, mayUse, modelPath, movedTo, pipelineBelongsToModel, reportBelongsToModel, reportModels,
  reportPagePath,
} from '../nav'
import { scheduleWords } from '../schedule'
import {
  Spinner, Verdict, Empty, Btn, BtnLink, CopyCommand, ErrorDetail,
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
// The page is the report. The app's nav stays as a rail; above the report, the
// breadcrumb (Library, its folder, the report) and one command bar: its name,
// the app's verdict on this build (and, when that asks for a look, why), when
// it was built and how many figures and queries it holds, then Open, Share and
// Export for everyone as quiet commands; Rebuild and Edit as a draft (the
// primary) for an analyst or admin, Build in dev mode, and "About this build"
// (the trace, Lineage, History, Files). A command the person's role cannot use
// is not shown, nor one that needs a build (Open, Share, Export, About this
// build) before there is one. On a wide window the trace sits beside the page
// as a card, open until it is closed; narrower, it is a panel that slides in.
// The report keeps its own receipt drawer (tracebi.js); the app tells the
// frame its verdict, so the report's masthead chip says what the app's check
// found rather than the file's "Not checked".

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
// From this width of the report's own column, the trace sits beside the page.
const WIDE = 1240

// The panel's state as last left. `open` is null until the person opens or
// closes it: then the trace is open beside a wide page and closed over a
// narrow one, where it would cover the report.
function readPanel() {
  try {
    const v = JSON.parse(localStorage.getItem(PANEL_KEY) || 'null')
    return v && TABS.some(([k]) => k === v.tab)
      ? { open: typeof v.open === 'boolean' ? v.open : null, tab: v.tab } : { open: null, tab: 'receipt' }
  } catch { return { open: null, tab: 'receipt' } }
}

// How wide *ref*'s element is, as it changes.
function useWidth(ref) {
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    setWidth(el.getBoundingClientRect().width)
    if (typeof ResizeObserver === 'undefined') return undefined
    const watch = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    watch.observe(el)
    return () => watch.disconnect()
  }, [ref])
  return width
}

function Facts({ children }) { return <dl className="rpanel__kv rpanel__kv--tight">{children}</dl> }
function Fact({ k, children }) { return <><dt>{k}</dt><dd>{children}</dd></> }

/**
 * The figure the trace is about: the one the reader last clicked in the page
 * (*id*), else the build's first value figure, else its first. Its label is
 * the one the page printed for it (the desk's `values`), else its cell's name.
 */
function focusOf(manifest, id, values) {
  const figures = manifest?.figures || []
  const figure = figures.find(f => f.id === id) || figures.find(f => f.kind === 'value') || figures[0]
  if (!figure) return null
  const printed = (values || []).find(v => v.id === figure.id)
  return { figure, printed, label: printed?.label || humanise(figure.cell || figure.binding || figure.id) }
}

// The query a binding recorded, in one line: its measures, what it is cut
// by, its filters and its limit. It is the closed query the build stamped,
// not SQL: the manifest records no SQL to show.
function queryLine(spec) {
  if (!spec) return null
  const measures = Array.isArray(spec.measures) ? spec.measures : Object.keys(spec.measures || {})
  const where = Object.entries(spec.filters || {})
    .map(([k, v]) => `${k} = ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : v}`)
  return [
    measures.join(', ') || '(rows)',
    spec.dimensions?.length ? `by ${spec.dimensions.join(', ')}` : '',
    where.length ? `where ${where.join('; ')}` : '',
    spec.limit ? `limit ${spec.limit}` : '',
  ].filter(Boolean).join(' ')
}

const shortSha = sha => (sha && sha.length > 12 ? `${sha.slice(0, 4)}…${sha.slice(-4)}` : sha)

// What a sink certificate says of the table a figure's query read, in the
// locked words: the sink satisfied its contract, never "verified".
const SINK_WORDS = {
  satisfied: n => `the sink satisfied its contract${n ? ` (${count(n, 'check')})` : ''}`,
  stale: () => 'the table changed since the sink last satisfied its contract',
  no_contract: () => 'no contract declared',
}

function Step({ n, k, children }) {
  return (
    <li className="rtrace__step">
      <span className="rtrace__n" aria-hidden="true">{n}</span>
      <div><div className="rtrace__k">{k}</div><div className="rtrace__v">{children}</div></div>
    </li>
  )
}

/**
 * The trace of the figure in focus, in five steps (where its table came from,
 * the model and the join it read, the query, the fingerprint the build
 * recorded, and what re-running it said), then the verdict on the page. Every
 * value is read from the build's manifest and the desk's last re-check;
 * nothing is computed here.
 */
function TraceSteps({ manifest, focus, verdict, checkedAt, selection }) {
  const labelOf = useModelLabel()
  const role = useRole()
  if (!manifest) return null
  if (!focus) return <p className="rpanel__empty">This build records no figures to trace.</p>
  const { figure, printed } = focus
  const binding = (manifest.embedded_data || []).find(e => e.name === figure.binding)
  const spec = binding?.query_spec
  const model = binding?.model
  const slice = manifest.semantic_contract?.[model]?.slice
  const table = slice?.tables?.find(t => t.name === spec?.fact)?.source || spec?.fact
  const cert = table ? (manifest.transform_contracts || {})[table] : null
  const sources = Object.keys(cert?.sources || {})
  // The dimensions the query reached through its joins: what it is cut and filtered by.
  const joined = [...new Set([...(spec?.dimensions || []), ...Object.keys(spec?.filters || {})]
    .filter(c => c.includes('.')).map(c => c.split('.')[0]))]
  const derived = binding?.verifiable === false
  const rerun = !figure.binding || figure.unverified ? 'Typed in by its author: there is no query to re-run.'
    : derived ? 'Computed in report.py, so it cannot be re-run.'
      : !verdict ? 'Checking…'
        : verdict.state === 'reproduces'
          ? <>{printed && <><code>{printed.text}</code> · </>}same fingerprint{checkedAt && <>, <Time iso={checkedAt} /></>}</>
          : verdict.detail
  const band = verdict && VERDICT_LABEL[verdict.state] ? verdict : null
  return (
    <section className="rtrace" aria-label="How this figure was made">
      <ol className="rtrace__steps">
        <Step n={1} k="Source">
          {cert ? (
            <>
              {sources.length > 0 && <>{sources.join(' + ')} → </>}
              {cert.transform ? <code>{cert.transform}</code> : 'a transform'} wrote <code>{table}</code>
              {' · '}{(SINK_WORDS[cert.status] || SINK_WORDS.no_contract)(cert.checks)}
            </>
          ) : table ? <><code>{table}</code> · no sink certificate recorded</> : 'Not recorded'}
        </Step>
        <Step n={2} k="Model">
          {model ? (
            <>
              {/* The model is a link to its page for whoever sees Data. */}
              {mayUse(role, 'data') ? <Link to={modelPath(model)}><code>{model}</code></Link> : <code>{model}</code>}
              {labelOf(model) !== model && <> ({labelOf(model)})</>}
              {spec?.fact && <> · {spec.fact}{joined.length > 0 && <> ⋈ {joined.join(', ')}</>}</>}
            </>
          ) : 'Not recorded'}
        </Step>
        <Step n={3} k="Query">
          {spec ? <code title={JSON.stringify(spec)}>{queryLine(spec)}</code> : 'No query: typed in by its author'}
        </Step>
        <Step n={4} k="Fingerprint">
          {binding?.embedded_sha256
            ? <><code title={binding.embedded_sha256}>sha256 · {shortSha(binding.embedded_sha256)}</code>
              {manifest.rendered_at && <> · recorded <Time iso={manifest.rendered_at} /></>}</>
            : 'None recorded'}
        </Step>
        <Step n={5} k="Re-run now">{rerun}</Step>
      </ol>
      {selection && (
        <p className="rpanel__hint rtrace__hint">The page shows your selection, recomputed in it; this is the trace of the build as authored.</p>
      )}
      {band && (
        <p className={`rtrace__verdict rtrace__verdict--${band.state}`}>
          <span className="rtrace__dot" aria-hidden="true" />
          {VERDICT_LABEL[band.state]}{band.state === 'reproduces' ? ' · every figure on this page' : ''}
        </p>
      )}
    </section>
  )
}

// The Trace tab: a few facts the trace does not carry (whether the app's
// check still holds, the schedule, the kind), the trace of the figure in
// focus, then the build's own certificate, its chip in the app's verdict.
function ReceiptTab({ report, shown, lastBuild, checkedAt, verdict, onCheck, checking, focus, selection, beside }) {
  const manifest = shown?.manifest
  const p = figureProvenance(manifest)
  const words = scheduleWords(report.schedule)
  const last = report.last_run
  const form = (FORMS[report.form === 'package' ? report.made_from : report.form] || FORMS.code).label
  return (
    <>
      <section className="rpanel__sec">
        {report.description && (
          <p className={`rpanel__lead rpanel__lead--facts${beside ? ' rpanel__lead--clamp' : ''}`} title={beside ? report.description : undefined}>
            {report.description}
          </p>
        )}
        <Facts>
          {lastBuild && (
            <Fact k="Checked">
              {!verdict ? 'Checking…' : checkedAt ? <Time iso={checkedAt} /> : 'Not yet'}
              {' · '}<button type="button" className="rpanel__link" onClick={onCheck} disabled={checking}>Check again</button>
              {verdict && verdict.state !== 'reproduces' && <div className="rpanel__hint">{verdict.detail}</div>}
            </Fact>
          )}
          {manifest && manifest.schema_version !== 2 && (
            <Fact k="Trace">○ Manifest v{manifest.schema_version ?? '?'}: no per-figure queries to re-run</Fact>
          )}
          {(p.derived > 0 || p.unverified > 0) && (
            <Fact k="Figures">
              {p.derived > 0 && <div><span aria-hidden="true">○</span> {p.derived} from python, which cannot be re-run</div>}
              {p.unverified > 0 && <div><span aria-hidden="true">△</span> {p.unverified} unverified</div>}
            </Fact>
          )}
          <Fact k="Schedule">
            {words ? words.long : 'Not scheduled'}
            {!words && !beside && <div className="rpanel__hint">A <code>schedule</code> block in report.json builds it on a timetable.</div>}
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
      <TraceSteps manifest={manifest} focus={focus} verdict={verdict} checkedAt={checkedAt} selection={selection} />
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
// check recorded, and every older build a plain "Not checked". The newest
// build shows its cover when it took one: each build writes over the last
// one's picture, so an older build has none left to show.
function HistoryTab({ name, verdict }) {
  const role = useRole()
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
        {r === newest && r.detail?.cover && (
          <img className="rp__thumb" src={reportCoverUrl(name, r.finished || r.started)} alt="" />
        )}
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
      {mayUse(role, 'runs') && (
        <Link to={`/runs?target=${encodeURIComponent(name)}`} className="rpanel__link">Every run in History</Link>
      )}
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

// "About this build": the trace, a card beside a wide page, a panel that
// slides in over a narrower one (a sheet from the bottom on a phone). Its
// title and the figure in focus, a close, its tabs (the trace, then Lineage,
// History and Files), and the open tab's content.
function ReportPanel({ tab, setTab, onClose, beside, ...props }) {
  const { report, shown, verdict, focus } = props
  return (
    <aside className={beside ? 'rpanel rpanel--beside' : 'rpanel'} aria-label="About this build">
      <div className="rpanel__top">
        <h2 className="rpanel__title">The trace</h2>
        {focus && tab === 'receipt' && (
          <span className="rpanel__focus" title={`The figure this trace follows: ${focus.label}. Click a figure in the page to follow it.`}>
            figure: {focus.label}
          </span>
        )}
        <button type="button" className="cmd" onClick={onClose} aria-label="Close the panel"><Icon name="close" /></button>
      </div>
      <div className="rpanel__tabs">
        <Segmented options={TABS} value={tab} onChange={setTab} label="About this build" panel="rp-tabpanel" />
      </div>
      <div className="rpanel__body" role="tabpanel" id="rp-tabpanel" aria-labelledby={`rp-tabpanel-${tab}`}>
        {tab === 'receipt' && <ReceiptTab {...props} beside={beside} />}
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
  // The figure the trace follows: the one the reader last clicked in the page
  // (the frame says which, by its id), else the build's first value figure.
  const [clicked, setClicked] = useState(null)
  // A build is deterministic, so a rebuild on unchanged data gives the same
  // HTML string; the frame is keyed on the build's time as well, so a new
  // build is a new page (and starts as authored) even when its bytes match.
  const buildKey = shown?.manifest?.rendered_at || null
  // A layout effect: the listeners are on before the browser can load the
  // frame, so nothing the page says is missed.
  useLayoutEffect(() => {
    setSelection(null)
    setClicked(null)
    const frame = frameRef.current
    if (!frame) return undefined
    // A new build starts as authored, so when the page says it is up it is
    // told the authored state (a no-op on a page that has none), before any
    // gesture. (A page in a srcdoc frame keeps no selection in its address
    // either, tracebi.js writeHash, so a re-created frame has none to inherit.)
    const stopReady = listenToFrame(frame, m => {
      if (m.type === 'ready') setFrameSelection(frame, {})
      else if (m.type === 'figure' && typeof m.id === 'string') setClicked(m.id)
    })
    const stopFollow = followSelection(frame, s => setSelection(s.local && !s.authored ? s.selection || {} : null))
    return () => { stopReady(); stopFollow() }
  }, [frameHtml, buildKey])
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
  // On a wide window the trace is a card beside the page; narrower, the panel
  // and the workbench share the right edge, one at a time.
  const rootRef = useRef(null)
  const wide = useWidth(rootRef) >= WIDE
  const togglePoint = () => {
    setWantBuild(on => !on); setPointed(null); timeline.reset()
    if (!wide) setPanel(p => ({ ...p, open: false }))
  }

  // The panel's open/closed and its tab are remembered for next time, once
  // the person has opened or closed it.
  useEffect(() => {
    if (panel.open === null) return
    try { localStorage.setItem(PANEL_KEY, JSON.stringify(panel)) } catch { /* private window */ }
  }, [panel])
  const isOpen = p => p.open ?? wide
  const showPanel = isOpen(panel) && !pointOn
  const openPanel = (tab, e) => {
    panelOpener.current = e?.currentTarget || null
    setWantBuild(false)
    setPanel(p => (isOpen(p) && p.tab === tab ? { ...p, open: false } : { open: true, tab }))
  }
  // "About this build" opens the panel on the tab it was last left on.
  const togglePanel = e => {
    panelOpener.current = e?.currentTarget || null
    setPanel(p => ({ ...p, open: !isOpen(p) }))
  }
  const closePanel = useCallback(() => {
    setPanel(p => ({ ...p, open: false }))
    if (panelOpener.current?.isConnected) panelOpener.current.focus()
  }, [])
  // Escape closes the panel that lies over the report (a menu or dialog has
  // already taken the key); the card beside a wide page covers nothing.
  useEffect(() => {
    if (!showPanel || wide) return undefined
    const esc = e => { if (e.key === 'Escape' && !e.defaultPrevented) closePanel() }
    document.addEventListener('keydown', esc)
    return () => document.removeEventListener('keydown', esc)
  }, [showPanel, wide, closePanel])

  // The desk keeps a verdict while its inputs are unchanged, so a plain refetch
  // would hand back the kept one; Check again asks it to re-run every recorded
  // query against the warehouse as it is now, and that answer replaces the kept.
  const checkAgain = async () => {
    setChecking(true)
    try {
      const fresh = await fetchDeskFresh()
      qc.setQueryData(['desk'], fresh)
      const row = (fresh?.builds || []).find(b => b.report === name)
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
    report, build: lastBuild, contracts: shown?.manifest?.transform_contracts, checkedAt: lastBuild?.computed_at ?? dataUpdatedAt,
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
  const manifest = shown?.manifest
  const focus = focusOf(manifest, clicked, lastBuild?.values)
  // The folder the report sits in, as the library names it, in its hue.
  const library = useLibrary()
  const folder = folderOf(name)
  const inFolder = folder ? library.byPath[folder] : null

  return (
    <div ref={rootRef} className={['rp', pointOn && 'rp--build', wide && 'rp--wide'].filter(Boolean).join(' ')}>
      <header className="rp__head">
        <nav aria-label="Where this report is" className="rp__crumb">
          {navMenu && (
            <button type="button" className="cmd rp__menu-btn" aria-label="Menu" onClick={navMenu.open}><Icon name="menu" size={18} /></button>
          )}
          <Link to="/">Library</Link>
          {folder && (
            <>
              <span aria-hidden="true">›</span>
              <Link to={folderPath(folder)} className="rp__crumb-folder"
                    style={inFolder ? hueStyle(inFolder.hue) : undefined}>
                {inFolder?.label || (model && folder === model ? labelOf(model) : folder.split('/').join(' / '))}
              </Link>
            </>
          )}
          <span aria-hidden="true">›</span>
          <span aria-current="page" className="rp__crumb-here" title={label}>{label}</span>
        </nav>
        <div className="rp__bar-r">
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
            {manifest && <span className="rp__hide-sm">{count((manifest.figures || []).length, 'figure')}</span>}
            {manifest && <span className="rp__hide-sm">{count((manifest.embedded_data || []).length, 'query', 'queries')}</span>}
            {refreshed && <span className="rp__hide-sm rp__hide-md">Data refreshed <Time iso={refreshed} /></span>}
            {words && <span className="rp__hide-sm"><Icon name="calendar" size={13} /> {words.short}</span>}
          </div>
        </div>

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
              <Cmd icon="rebuild" onClick={rebuild} disabled={running} className="cmd--outline"
                   title="Re-run every query and build the report again">
                {running ? <><Spinner size={12} /> Rebuilding…</> : 'Rebuild'}
              </Cmd>
            )}
            <EditAsDraft kind="reports" path={name} bare className="cmd cmd--primary" />
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
        {message && (
          <p role="status" className={`rp__why${message.state === 'does-not-reproduce' ? ' rp__why--bad' : ''}`}>
            {message.detail}
          </p>
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
            <iframe key={buildKey || 'frame'} name={`report-${buildKey || 'frame'}`} ref={frameRef} srcDoc={frameHtml} sandbox={FRAME_SANDBOX} title={name} className="rp__frame" />
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
                         beside={wide} report={report} shown={shown} lastBuild={lastBuild} focus={focus}
                         selection={selection} checkedAt={lastBuild?.computed_at ?? dataUpdatedAt}
                         verdict={verdict} onCheck={checkAgain} checking={checking} />
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

// How a report is made, from the reports API's `form` field and, for a
// package, `made_from`: the file it draws its page from.
const FORMS = {
  spec: { label: 'JSON spec', title: 'A reports/<name>.json spec: sections in the default style' },
  'app.jsx': { label: 'Dashboard (app.jsx)', title: 'A reports/<name>/ package drawn by its app.jsx' },
  'template.html': { label: 'Page (template.html)', title: 'A reports/<name>/ package drawn by its template.html' },
  code: { label: 'Code', title: 'Registered from Python code' },
}

// The files that define the report, read-only. A spec is one JSON file; a
// package is report.json + template.html + style.css + script.js (+ assets).
function ReportSource({ name }) {
  const { data, isLoading, error } = useReportSource(name, true)
  if (isLoading) return <div style={{ color: 'var(--muted)', fontSize: 'var(--text-caption)' }}><Spinner /> Loading code…</div>
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
  const rank = f => (f === mine ? 0 : f === '' ? -1 : 3)
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([folder, items]) => ({ folder, items }))
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

// The showcase: the report that shows everything a report can do, by its name.
const isShowcase = r => /(^|\/|_)showcase$/.test(r.name)

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

const WELCOMED = 'tracebi-welcomed'
const VIEW_KEY = 'tracebi-library-view'
const VIEWS = [['grid', 'Grid'], ['list', 'List']]

// Grid (the directory) or list, kept per person in this browser; until they
// pick, the directory, on a phone too: its rows scroll sideways.
function useLibraryView() {
  const [picked, setPicked] = useState(() => {
    try { return localStorage.getItem(VIEW_KEY) } catch { return null }
  })
  const pick = v => {
    try { localStorage.setItem(VIEW_KEY, v) } catch { /* private window: kept for this visit */ }
    setPicked(v)
  }
  const view = VIEWS.some(([v]) => v === picked) ? picked : 'grid'
  return [view, pick]
}

/**
 * One quiet row under the library's folder tiles the first time a person
 * opens the app in this browser: Get started, a report that shows everything
 * a report can do when the project has one, and the jump key. Dismissed, it
 * never comes back (a flag in this browser's storage; with no storage it is
 * not shown, since it could not stay dismissed).
 */
function Welcome({ role, showcase }) {
  const [shown, setShown] = useState(() => {
    try { return !localStorage.getItem(WELCOMED) } catch { return false }
  })
  if (!shown || role === null) return null
  const dismiss = () => {
    try { localStorage.setItem(WELCOMED, '1') } catch { /* private window: gone for this visit */ }
    setShown(false)
  }
  return (
    <section className="welcome" aria-label="Welcome to TraceBi">
      <p className="welcome__line">
        New here? <Link to="/docs/get-started" className="welcome__go">Get started</Link>
        {showcase && <><span aria-hidden="true"> · </span>
          <Link to={reportPagePath(showcase.name)}>Open {showcase.display_name || 'the showcase'}</Link></>}
        <span aria-hidden="true"> · </span>
        <span className="welcome__kbd"><kbd>⌘K</kbd> jumps to any report, folder or table</span>
      </p>
      <button type="button" className="welcome__x" onClick={dismiss} aria-label="Dismiss the welcome">×</button>
    </section>
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
  const { data: folderData } = useFolders()
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState('')
  const [closed, setClosed] = useState(() => new Set())
  const [view, setView] = useLibraryView()
  const role = useRole()
  const library = useLibrary()
  const { desk, builds, verdictFor } = useBuilds()
  const opened = params.get('folder')
  useDocumentTitle(opened === null ? 'Reports' : '')
  if (moved) return <Navigate to={moved} replace />
  if (opened !== null) return <FolderPage path={opened} />

  const models = modelList || []
  const asked = params.get('model') || ''
  const model = models.some(m => m.name === asked) ? asked : ''
  const labelOf = name => models.find(m => m.name === name)?.label || name
  const all = data || []
  const reports = all.filter(r => reportBelongsToModel(r, model))
  const needle = query.trim().toLowerCase()
  const matches = r => !needle || [r.display_name, r.name, r.description]
    .some(t => (t || '').toLowerCase().includes(needle))
  const listed = reports.filter(matches)
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
  const newest = newestBuild(all, builds)
  // The model chips, the search and the view: under the folder tiles in the
  // directory (they narrow its rows), above the list.
  const find = (
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
      <div className="library__search">
        <SearchInput value={query} onChange={setQuery} placeholder="Search reports…" label="Search reports"
                     style={{ padding: 0, borderBottom: 0 }} />
        <Segmented options={VIEWS} value={view} onChange={setView} label="View" className="library__view" />
      </div>
    </div>
  )

  const welcome = <Welcome role={role} showcase={all.find(isShowcase)} />

  return (
    <div className="library">
      <header className="dir-head">
        <div className="dir-head__row">
          <div className="dir-head__text">
            <nav aria-label="Breadcrumb" className="crumbs"><span aria-current="page">Library</span></nav>
            <h1 className="display-title">Reports</h1>
            {all.length > 0 && (
              <p className="dir-head__lede">
                {count(library.folders.filter(f => f.items.length).length, 'folder')}, {count(all.length, 'report')},
                {' '}every cover its page as it was last built.
                {newest && <> Last built <Time iso={newest.built_at} />.</>}
              </p>
            )}
          </div>
          <LibraryActions models={models} />
        </div>
      </header>
      {isLoading ? <SkeletonList /> : !all.length && !(canPublish && folderData?.personal) ? (
        canPublish ? (
          <Empty title="No reports yet"
                 body="A report is a page where every number is a live query against a model. Scaffold one, build it, and it is listed here."
                 command={'tracebi new-report "My report"'}
                 action={<BtnLink to="/docs/get-started" size="sm">Get started</BtnLink>} />
        ) : (
          <Empty title="No reports yet"
                 body="Reports appear here once an analyst publishes one into a folder you can see." />
        )
      ) : (
        <>
          <Health reports={reports} verdictFor={verdictFor} builds={builds} known={!!desk} />
          {!listed.length && !mine
            ? <>{welcome}{find}<p className="lfolder__none">No report matches. Clear the search or pick All models.</p></>
            : view === 'grid' ? (
              <DirectoryView library={library} listed={listed} mine={mine} builds={builds} verdictFor={verdictFor}
                             find={find} welcome={welcome} />
            ) : (
              <>{welcome}{find}<div className="library__list">
                {groupByFolder(listed, mine).map(({ folder, items }) => (
                  <LibraryFolder key={folder || '(top)'} folder={folder} label={folderLabel(folder, folderInfo[folder])}
                                 items={items} info={folderInfo[folder]} usual={usual}
                                 // A search always shows its matches, even in a closed folder.
                                 open={!folder || !!needle || !closed.has(folder)} onToggle={() => toggle(folder)}
                                 verdictFor={verdictFor} builds={builds} searching={!!needle} />
                ))}
              </div></>
            )}
        </>
      )}
    </div>
  )
}

/**
 * The library's two actions, right of its h1, as a folder's page has them:
 * New report (the command that scaffolds one; an analyst's or admin's) and
 * Refresh data (an admin's: it writes the warehouse). Refresh runs each
 * model's own pipeline once, the one its Transform tab calls Refresh data;
 * with no pipeline for any model there is nothing to refresh, so no button.
 */
function LibraryActions({ models }) {
  const role = useRole()
  const { data: me } = useMe()
  const { data: pipelines } = usePipelines()
  const { mutateAsync: start } = useStartPipelineRun()
  const [making, setMaking] = useState(false)
  const [starting, setStarting] = useState(false)
  const navigate = useNavigate()
  const toast = useToast()
  // With no sign-in everyone is admin: the same gate as the folder page's.
  const admin = !!me && (!me.role || me.role === 'admin')
  const canAuthor = role === 'analyst' || role === 'admin'
  const own = admin ? [...new Set(models.map(m => (
    (pipelines || []).find(p => p.model === m.name) || (pipelines || []).find(p => pipelineBelongsToModel(p, m.name))
  )?.pipeline).filter(Boolean))] : []
  const refresh = async () => {
    setStarting(true)
    const failed = []
    for (const pipeline of own) {
      try { await start({ pipeline }) } catch (err) { failed.push(`${pipeline}: ${err.message}`) }
    }
    setStarting(false)
    if (failed.length) toast(`Could not start ${failed.join('; ')}`, 'error')
    if (failed.length < own.length) navigate('/runs')
  }
  if (!canAuthor && !own.length) return null
  return (
    <div className="dir-head__acts">
      <div className="fhero__acts">
        {canAuthor && (
          <Btn aria-expanded={making} onClick={() => setMaking(m => !m)}>New report</Btn>
        )}
        {own.length > 0 && (
          <Btn variant="outline" onClick={refresh} disabled={starting}
               title={`Runs ${count(own.length, 'pipeline')}: ${own.join(', ')}`}>
            {starting ? <><Spinner size={12} /> Starting…</> : 'Refresh data'}
          </Btn>
        )}
      </div>
      {making && (
        <div className="fhero__new">
          <CopyCommand>{'tracebi new-dashboard "New dashboard"'}</CopyCommand>
        </div>
      )}
    </div>
  )
}

// Grid: the library as a directory. Its folders as tiles (the first visit's
// welcome under them), then a row of covers for the newest builds, then a row
// per folder; a search or a model narrows every row and drops the empty ones
// (their own My published stays, to say how it fills).
function DirectoryView({ library, listed, mine, builds, verdictFor, find, welcome }) {
  const shown = new Set(listed.map(r => r.name))
  const rows = library.folders
    .map(f => ({ ...f, items: f.items.filter(r => shown.has(r.name)) }))
    .filter(f => f.items.length || f.path === mine)
  const hueOf = name => library.folders.find(f => f.path === folderOf(name))?.hue
  const recent = (Object.values(builds))
    .filter(b => shown.has(b.report) && b.built_at)
    .sort((a, b) => b.built_at.localeCompare(a.built_at))
    .slice(0, 6)
    .map(b => listed.find(r => r.name === b.report))
  const top = listed.filter(r => !folderOf(r.name))
  const tile = (r, i, wide = false) => (
    <li key={r.name}>
      <CoverTile report={r} verdict={verdictFor(r)} built={builds[r.name]} hue={hueOf(r.name)}
                 tag={tagOf(r)} wide={wide && i === 0} />
    </li>
  )
  return (
    <div className="dir">
      <ul className="ftiles" aria-label="Folders">
        {rows.map(f => <li key={f.path}><FolderTile folder={f} builds={builds} /></li>)}
      </ul>
      {welcome}
      {find}
      {recent.length > 0 && (
        <CoverRow title="Recently built" row="recent" meta={builtLine(recent, builds)}>
          {recent.map((r, i) => tile(r, i, true))}
        </CoverRow>
      )}
      {rows.map(f => (
        <CoverRow key={f.path} title={f.label} hue={f.hue} row="folder" open={folderPath(f.path)}
                  meta={`${count(f.items.length, 'report')}${f.models.length === 1 && f.models[0] !== f.path ? ` · ${f.models[0]}` : ''}`}
                  empty={f.mine ? 'Nothing here yet. Publish a draft to My published from Review to put a report here.' : null}>
          {[...f.items].sort((a, b) => isShowcase(b) - isShowcase(a)).map((r, i) => tile(r, i))}
        </CoverRow>
      ))}
      {top.length > 0 && (
        <CoverRow title="Not in a folder" row="folder" meta={count(top.length, 'report')}>
          {top.map((r, i) => tile(r, i))}
        </CoverRow>
      )}
    </div>
  )
}

/** /reports/<name>: that report as a page of its own; /reports alone is the library. */
export function ReportRoute() {
  const open = useOpenReport()
  return open ? <ReportPage name={open.name} /> : <Moved />
}
