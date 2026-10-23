import { Fragment, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useDesk, useModels, usePipelines, useReports, useRuns } from '../api'
import { ago, day, isoTitle } from '../when'
import { checkedVerdict, verdictOf } from '../verdict'
import { useModelLabel, useReportModels } from '../components/Scope'
import { dataPath, historyPath, pipelineModels, reportPagePath } from '../nav'
import {
  Btn, Chip, Spinner, Empty, ErrorDetail, Segmented, Verdict, useNarrow,
} from '../components/Shared'

// What a reader can tell apart: four kinds, each the store's kinds it covers
// (a build from the app's background queue is a report build like any other).
// ?kind= names one of these, or a store kind (an older link), which picks its group.
const KIND_GROUPS = [
  ['build', 'Report builds', ['report_build', 'background_run']],
  ['refresh', 'Data refreshes', ['pipeline_run', 'pipeline_layer']],
  ['schedule', 'Schedules', ['schedule']],
  ['publish', 'Publishes', ['publish']],
  ['credential', 'Credential changes', ['credential']],
]
// Each row's kind, in the same words.
const KIND_LABEL = {
  report_build: 'Report build', background_run: 'Report build', schedule: 'Schedule',
  pipeline_run: 'Data refresh', pipeline_layer: 'Data refresh step', publish: 'Publish',
}
// A credential row's status is what happened to it (set or unset), so its kind
// says that and the row shows no outcome besides. Never the value: the store
// records none.
const kindOf = run => (run.kind === 'credential'
  ? (run.status === 'unset' ? 'Credential removed' : 'Credential set')
  : KIND_LABEL[run.kind] || run.kind)
const REPORT_KINDS = new Set(['report_build', 'background_run', 'schedule'])
// Kinds that write a report's page. Those rows record a build, not a check.
const BUILD_KINDS = new Set(['report_build', 'background_run'])

const STATUS = {
  success: 'green', succeeded: 'green', delivered: 'green', built: 'green',
  failed: 'red', error: 'red', refused: 'red',
  running: 'amber', empty: 'amber',
}

// The chip the library shows, from the same rule (verdict.js), and only
// `reproduces` is green. A build row stores no verdict (a build is not a
// check). Only the newest successful build of a report is still the page on
// disk, and the desk re-checks that one: its row shows that verdict. Any other
// build was never checked, and says so. Null while the check is coming.
function runVerdict(run, latestBuild, checks) {
  if (run.verdict) return checkedVerdict(run.verdict)
  const latest = BUILD_KINDS.has(run.kind) && latestBuild[run.target] === run.id
  if (latest && checks.loading) return null
  if (latest && checks.builds[run.target]) {
    return verdictOf({ report: checks.reports[run.target], build: checks.builds[run.target] })
  }
  return {
    state: 'not-checked',
    detail: BUILD_KINDS.has(run.kind) ? 'Only the latest build of a report is re-checked; the library shows it.' : undefined,
  }
}

function duration(start, end) {
  if (!start || !end) return null
  const ms = new Date(end) - new Date(start)
  if (!Number.isFinite(ms) || ms < 0) return null
  if (ms < 1000) return `${Math.round(ms)} ms`
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  if (m < 60) return rem ? `${m}m ${rem}s` : `${m}m`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

// Where a row leads: a report's page, or the Transform tab of the model a
// pipeline run refreshes.
function rowLink(run, pipelineModelsOf) {
  if (!run.target) return null
  if (REPORT_KINDS.has(run.kind)) return reportPagePath(run.target)
  if (run.kind === 'publish' && run.target.startsWith('reports/')) return reportPagePath(run.target.slice(8))
  if (run.kind === 'pipeline_run' || run.kind === 'pipeline_layer') {
    const model = pipelineModelsOf(run.target)[0]
    return model ? dataPath(model, 'transform') : null
  }
  return null
}

// The day a run started, as the sticky header above it says it.
function dayOf(iso) {
  const d = new Date(iso)
  if (!iso || Number.isNaN(d.getTime())) return 'Unknown date'
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.getFullYear() === today.getFullYear() ? day(d) : `${day(d)} ${d.getFullYear()}`
}

// Entries (newest first) in runs of the same day: an entry's day is its newest run's.
function byDay(entries) {
  const days = []
  for (const entry of entries) {
    const day = dayOf(entry.row.run.started)
    if (days.length && days[days.length - 1].day === day) days[days.length - 1].entries.push(entry)
    else days.push({ day, entries: [entry] })
  }
  return days
}

// One entry per report or pipeline: its newest run, then the older ones
// (folded by default). A report's builds and scheduled runs are one entry; a
// run with no target stands alone.
function byTarget(rows) {
  const groups = []
  const index = new Map()
  for (const row of rows) {
    const { kind, target } = row.run
    const key = target && `${REPORT_KINDS.has(kind) ? 'report' : kind}:${target}`
    if (key && index.has(key)) index.get(key).older.push(row)
    else {
      const group = { key: key || `#${row.run.id}`, row, older: [] }
      if (key) index.set(key, group)
      groups.push(group)
    }
  }
  return groups
}

// "3 older runs", and how many of them failed: a failure is never folded away unsaid.
function olderWords(older, noun) {
  const failed = older.filter(r => failedRun(r.run)).length
  return `${older.length} older ${older.length === 1 ? noun : `${noun}s`}${failed ? ` · ${failed} failed` : ''}`
}

/** The disclosure under a report's or pipeline's newest run. */
export function Older({ older, open, onToggle, noun = 'run' }) {
  if (!older.length) return null
  return (
    <button type="button" className="runs-older" aria-expanded={open} onClick={onToggle}>
      <span aria-hidden="true" className="runs-older__caret">{open ? '▾' : '▸'}</span>
      {olderWords(older, noun)}
    </button>
  )
}

// An empty cell: a dash quieter than any text in the row.
const Dash = () => <span className="runs__dash" aria-label="none">—</span>

function actorOf(run) {
  if (!run.actor && !run.actor_role) return null
  return [run.actor, run.actor_role].filter(Boolean).join(' · ')
}

// A run that failed or is still going says so in a chip; a build that
// succeeded is its verdict; any other kind that finished says so quietly.
const STATUS_WORD = {
  success: 'Succeeded', succeeded: 'Succeeded', ok: 'Done', delivered: 'Delivered', built: 'Built',
  failed: 'Failed', error: 'Error', refused: 'Refused', running: 'Running', empty: 'Empty',
}
const LOUD = new Set(['failed', 'error', 'refused', 'running', 'empty'])
const STATUS_TONE = { red: 'bad', amber: 'warn' }
const failedRun = run => STATUS[run.status] === 'red'

function Outcome({ run, verdict }) {
  const word = run.kind === 'credential' ? null : STATUS_WORD[run.status] || run.status
  const loud = LOUD.has(run.status)
  const showVerdict = REPORT_KINDS.has(run.kind) && !['failed', 'error', 'running'].includes(run.status)
  return (
    <span className="runs__outcome">
      {loud && <Chip tone={STATUS_TONE[STATUS[run.status]]}>{word}</Chip>}
      {showVerdict && (verdict
        ? <Verdict state={verdict.state} detail={verdict.detail} size="sm" />
        : <span className="runs__quiet">Checking…</span>)}
      {!loud && !showVerdict && word && <span className="runs__quiet">{word}</span>}
    </span>
  )
}

// A report run belongs to the models its report reads; a refresh (a pipeline
// run, or one of its steps) to the models its pipeline names.
function runModels(run, modelsOf, pipelineModelsOf) {
  if (REPORT_KINDS.has(run.kind)) return modelsOf(run.target)
  if (run.kind === 'pipeline_run' || run.kind === 'pipeline_layer') return pipelineModelsOf(run.target)
  return []
}

/**
 * History: what ran. On its own page (/runs) a model is a filter; given
 * *model* it is that model's Runs tab on Data, with no heading of its own.
 */
export default function Runs({ model: only }) {
  // The owner alert links here as /runs?kind=schedule&target=<report>, and a
  // model's page as /runs?model=<model>. The filters are that query string, so
  // the link arrives already selected and a change stays in the URL.
  const [searchParams, setSearchParams] = useSearchParams()
  const model = only || searchParams.get('model') || ''
  const asked = searchParams.get('kind') || ''
  const group = KIND_GROUPS.find(([key, , kinds]) => key === asked || kinds.includes(asked))
  const kind = group ? group[0] : ''
  const target = searchParams.get('target') || ''
  // By default one row per report or pipeline (its newest run, older ones
  // folded); ?all=1 lists every run. A single target's runs are listed whole.
  const every = searchParams.get('all') === '1'
  const grouped = !every && !target.trim()
  const [unfolded, setUnfolded] = useState(() => new Set())
  const toggle = key => setUnfolded(prev => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })
  const setFilter = (key, value) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      if (value) next.set(key, value)
      else next.delete(key)
      return next
    }, { replace: true })
  }
  const { data, isLoading, error } = useRuns(group ? group[2] : '', target.trim())
  const { data: everything } = useRuns('', '')   // the same request when nothing is filtered
  const modelsOf = useReportModels()
  const labelOf = useModelLabel()
  const { data: modelList } = useModels()
  // On a phone each run is a card, not a row of columns.
  const narrow = useNarrow('(max-width: 640px)')
  const { data: pipelines } = usePipelines()
  // A run's `target` is its pipeline's name, or a step's (layer's) name.
  const pipelineModelsOf = useMemo(() => {
    const index = new Map()
    for (const p of pipelines || []) {
      for (const name of [p.pipeline, ...(p.layers || []).map(l => l.name)]) {
        index.set(name, [...new Set([...(index.get(name) || []), ...pipelineModels(p)])])
      }
    }
    return name => index.get(name) || []
  }, [pipelines])
  const { data: desk, isLoading: deskLoading } = useDesk()
  const { data: reports, isLoading: reportsLoading } = useReports()
  const checks = {
    loading: deskLoading || reportsLoading,
    builds: Object.fromEntries((desk?.builds || []).map(b => [b.report, b])),
    reports: Object.fromEntries((reports || []).map(r => [r.name, r])),
  }
  // The newest successful build of each report, whatever the filters hide.
  const latestBuild = {}
  for (const r of [...(Array.isArray(everything) ? everything : []), ...(Array.isArray(data) ? data : [])]) {
    if (BUILD_KINDS.has(r.kind) && r.status === 'succeeded' && r.target && r.id > (latestBuild[r.target] || 0)) {
      latestBuild[r.target] = r.id
    }
  }
  const runs = (Array.isArray(data) ? data : [])
    .filter(r => !model || runModels(r, modelsOf, pipelineModelsOf).includes(model))
  const nameOf = run => run.display_name || run.target || '—'
  // A link may narrow the list to one report or pipeline (?target=): say which, by its name.
  const targetName = (Array.isArray(everything) ? everything : []).find(r => r.target === target.trim())
  const filtered = !!(kind || target.trim())
  const recorded = Array.isArray(everything) && everything.length > 0
  // A column every row leaves empty is not drawn.
  const rows = runs.map(run => ({
    run,
    models: runModels(run, modelsOf, pipelineModelsOf),
    verdict: runVerdict(run, latestBuild, checks),
    link: rowLink(run, pipelineModelsOf),
    took: duration(run.started, run.finished),
    who: actorOf(run),
  }))
  const show = {
    model: !model && rows.some(r => r.models.length),
    took: rows.some(r => r.took),
    who: rows.some(r => r.who),
  }
  const entries = grouped ? byTarget(rows) : rows.map(row => ({ key: `#${row.run.id}`, row, older: [] }))
  const openOf = e => unfolded.has(e.key)

  const fold = e => e.older.length > 0 && <Older older={e.older} open={openOf(e)} onToggle={() => toggle(e.key)} />

  const tableRow = (r, older, folded) => {
    const { run } = r
    return (
      <tr key={run.id} data-target={run.target || undefined}
          className={[failedRun(run) && 'runs__row--failed', older && 'runs__row--older'].filter(Boolean).join(' ') || undefined}>
        <td>
          <span className="runs__kind">{kindOf(run)}</span>
          {' · '}
          {r.link
            ? <Link to={r.link} title={run.target}>{nameOf(run)}</Link>
            : <span title={run.target || undefined}>{nameOf(run)}</span>}
          {folded}
        </td>
        {show.model && <td className="runs__muted">{r.models.map(labelOf).join(', ') || <Dash />}</td>}
        <td className="runs__verdict"><Outcome run={run} verdict={r.verdict} /></td>
        <td className="runs__muted runs__nowrap" title={isoTitle(run.started)}>{ago(run.started) || <Dash />}</td>
        {show.took && <td className="runs__muted runs__nowrap">{r.took || <Dash />}</td>}
        {show.who && <td className="runs__muted">{r.who || <Dash />}</td>}
      </tr>
    )
  }

  const card = (r, older, folded) => {
    const { run } = r
    const body = (
      <>
        <span className="runs-card__top">
          <span className="runs-card__name" title={run.target || undefined}>{nameOf(run)}</span>
          <Outcome run={run} verdict={r.verdict} />
        </span>
        <span className="runs-card__meta">
          {[kindOf(run), ago(run.started), r.took, r.who].filter(Boolean).join(' · ')}
        </span>
      </>
    )
    return (
      <li key={run.id} data-target={run.target || undefined}
          className={['runs-card', failedRun(run) && 'runs-card--failed', older && 'runs-card--older'].filter(Boolean).join(' ')}>
        {r.link ? <Link to={r.link} className="runs-card__body">{body}</Link>
          : <div className="runs-card__body">{body}</div>}
        {folded && <div className="runs-card__fold">{folded}</div>}
      </li>
    )
  }

  return (
    <>
      {only ? (
        <div className="dtab__head">
          <p>Every build of {labelOf(model)}&rsquo;s reports and every refresh of its data: when, how long, by whom,
            and whether it reproduced. <Link to={historyPath(model)}>Open in History</Link></p>
        </div>
      ) : (
        // History is a tab of Review (its frame holds the page's heading).
        <div className="review__lead">
          <h2>History</h2>
          <p>{model
            ? `Every build of ${labelOf(model)}'s reports and every refresh of its data: when, how long, by whom, and whether it reproduced.`
            : 'What ran, when, how long it took, by whom, and whether it reproduced. Only a build that re-runs to the same numbers reads green.'}</p>
        </div>
      )}

      {/* Before anything has run there is nothing to filter. */}
      {(recorded || filtered || model) && <div className="runs__find">
        {!only && (modelList || []).length > 1 && (
          <div className="library__chips" role="group" aria-label="Model">
            <button type="button" className="rsplit__chip" aria-pressed={!model} onClick={() => setFilter('model', '')}>
              All models
            </button>
            {modelList.map(m => (
              <button key={m.name} type="button" className="rsplit__chip" aria-pressed={model === m.name}
                      onClick={() => setFilter('model', m.name)} title={m.name}>
                {m.label || m.name}
              </button>
            ))}
          </div>
        )}
        <div className="runs__selects">
          <label className="runs__select">
            Kind
            <select value={kind} onChange={e => setFilter('kind', e.target.value)}>
              <option value="">All kinds</option>
              {KIND_GROUPS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          {target.trim() ? (
            <p className="runs__only">
              Only <strong>{targetName ? nameOf(targetName) : target}</strong>{' '}
              <Btn size="sm" variant="outline" onClick={() => setFilter('target', '')}>Show everything</Btn>
            </p>
          ) : (
            <Segmented className="runs__show" label="Show" value={every ? '1' : ''}
                       onChange={v => setFilter('all', v)}
                       options={[['', 'Latest of each'], ['1', 'Every run']]} />
          )}
        </div>
      </div>}

      {isLoading ? (
        <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', fontSize: 13 }}>
          <Spinner size={14} /> Loading runs…
        </div>
      ) : error ? (
        <ErrorDetail error={error} />
      ) : runs.length === 0 ? (
        <Empty message={filtered || model
          ? 'Nothing that ran matches these filters.'
          : <>Nothing has run yet. A build from the app, <code>tracebi report build</code>, or a schedule appears here.</>} />
      ) : narrow ? (
        <div className="runs-cards fade-in">
          {byDay(entries).map(({ day, entries: dayEntries }) => (
            <section key={day} aria-label={day}>
              <h2 className="runs__day">{day}</h2>
              <ol className="runs-cards__list">
                {dayEntries.map(e => (
                  <Fragment key={e.key}>
                    {card(e.row, false, fold(e))}
                    {openOf(e) && e.older.map(r => card(r, true))}
                  </Fragment>
                ))}
              </ol>
            </section>
          ))}
        </div>
      ) : (
        <table className="tb-list runs-table fade-in">
          <thead>
            <tr>
              <th>What</th>
              {show.model && <th>Model</th>}
              <th>Verdict</th>
              <th>Started</th>
              {show.took && <th>Took</th>}
              {show.who && <th>Who</th>}
            </tr>
          </thead>
          {byDay(entries).map(({ day, entries: dayEntries }) => (
            <tbody key={day}>
              <tr className="runs__dayrow"><th colSpan={6} scope="colgroup" className="runs__day">{day}</th></tr>
              {dayEntries.map(e => (
                <Fragment key={e.key}>
                  {tableRow(e.row, false, fold(e))}
                  {openOf(e) && e.older.map(r => tableRow(r, true))}
                </Fragment>
              ))}
            </tbody>
          ))}
        </table>
      )}
    </>
  )
}
