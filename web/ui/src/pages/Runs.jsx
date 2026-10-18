import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { useDesk, useModels, usePipelines, useReports, useRuns } from '../api'
import { ago } from '../components/map/states'
import { checkedVerdict, verdictOf } from '../verdict'
import { PageHeader, useModelLabel, useReportModels } from '../components/Scope'
import { dataPath, pipelineModels, reportPagePath } from '../nav'
import {
  Badge, Spinner, Empty, ErrorDetail, Verdict, useNarrow,
} from '../components/Shared'

// Kinds the store records. The values are the API's filters; the labels
// are what the table shows.
const KINDS = [
  ['report_build', 'Report build'],
  ['background_run', 'Background run'],
  ['schedule', 'Schedule'],
  ['pipeline_layer', 'Pipeline'],
  ['pipeline_run', 'Pipeline run'],
  ['publish', 'Publish'],
]
const KIND_LABEL = Object.fromEntries(KINDS)
const REPORT_KINDS = new Set(['report_build', 'background_run', 'schedule'])
// Kinds that write a report's page. Those rows record a build, not a check.
const BUILD_KINDS = new Set(['report_build', 'background_run'])

const STATUS = {
  success: 'green', succeeded: 'green', delivered: 'green', built: 'green',
  failed: 'red', error: 'red', refused: 'red',
  running: 'amber', empty: 'amber',
}

// The chip the Reports page shows, from the same rule (verdict.js), and only
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
    detail: BUILD_KINDS.has(run.kind) ? 'Only the latest build of a report is re-checked; the Reports page shows it.' : undefined,
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

// Where a row leads: a report's page, or the Transform stage of the model a
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

function absolute(iso) {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
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
  return d.toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
    ...(d.getFullYear() === today.getFullYear() ? {} : { year: 'numeric' }),
  })
}

// Rows (newest first) in runs of the same day.
function byDay(rows) {
  const days = []
  for (const row of rows) {
    const day = dayOf(row.run.started)
    if (days.length && days[days.length - 1].day === day) days[days.length - 1].rows.push(row)
    else days.push({ day, rows: [row] })
  }
  return days
}

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
const failedRun = run => STATUS[run.status] === 'red'

function Outcome({ run, verdict }) {
  const word = STATUS_WORD[run.status] || run.status
  const loud = LOUD.has(run.status)
  const showVerdict = REPORT_KINDS.has(run.kind) && !['failed', 'error', 'running'].includes(run.status)
  return (
    <span className="runs__outcome">
      {loud && (
        <Badge variant={STATUS[run.status] || 'gray'} style={{ textTransform: 'none' }}>{word}</Badge>
      )}
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

export default function Runs() {
  // The owner alert links here as /runs?kind=schedule&target=<report>, and a
  // model's line as /runs?model=<model>. The filters are that query string, so
  // the link arrives already selected and a change stays in the URL.
  const [searchParams, setSearchParams] = useSearchParams()
  const model = searchParams.get('model') || ''
  const kind = searchParams.get('kind') || ''
  const target = searchParams.get('target') || ''
  const setFilter = (key, value) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev)
      if (value) next.set(key, value)
      else next.delete(key)
      return next
    }, { replace: true })
  }
  const { data, isLoading, error } = useRuns(kind, target.trim())
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
  // Targets to pick from: what the store has recorded, and the one asked for.
  const targets = new Map()
  for (const r of Array.isArray(everything) ? everything : []) {
    if (r.target && !targets.has(r.target)) targets.set(r.target, nameOf(r))
  }
  if (target && !targets.has(target)) targets.set(target, target)
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

  return (
    <>
      <PageHeader pageKey="runs" model={model}
        sub={model
          ? `Every build of ${labelOf(model)}'s reports and every refresh of its data: when, how long, by whom, and whether it reproduced.`
          : 'What ran, when, how long it took, by whom, and whether it reproduced. Only a receipt that reproduces reads green.'} />

      {/* Before anything has run there is nothing to filter. */}
      {(recorded || filtered || model) && <div className="runs__find">
        {(modelList || []).length > 1 && (
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
              {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label className="runs__select">
            Report or pipeline
            <select value={target} onChange={e => setFilter('target', e.target.value)}>
              <option value="">All</option>
              {[...targets].sort((a, b) => a[1].localeCompare(b[1])).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
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
          {byDay(rows).map(({ day, rows: dayRows }) => (
            <section key={day} aria-label={day}>
              <h2 className="runs__day">{day}</h2>
              <ol className="runs-cards__list">
                {dayRows.map(r => {
                  const { run } = r
                  const body = (
                    <>
                      <span className="runs-card__top">
                        <span className="runs-card__name" title={run.target || undefined}>{nameOf(run)}</span>
                        <Outcome run={run} verdict={r.verdict} />
                      </span>
                      <span className="runs-card__meta">
                        {[KIND_LABEL[run.kind] || run.kind, ago(run.started), r.took, r.who].filter(Boolean).join(' · ')}
                      </span>
                    </>
                  )
                  return (
                    <li key={run.id} data-target={run.target || undefined}
                        className={`runs-card${failedRun(run) ? ' runs-card--failed' : ''}`}>
                      {r.link ? <Link to={r.link} className="runs-card__body">{body}</Link>
                        : <div className="runs-card__body">{body}</div>}
                    </li>
                  )
                })}
              </ol>
            </section>
          ))}
        </div>
      ) : (
        <table className="runs-table fade-in">
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
          {byDay(rows).map(({ day, rows: dayRows }) => (
            <tbody key={day}>
              <tr className="runs__dayrow"><th colSpan={6} scope="colgroup" className="runs__day">{day}</th></tr>
              {dayRows.map(r => {
                const { run } = r
                return (
                  <tr key={run.id} data-target={run.target || undefined}
                      className={failedRun(run) ? 'runs__row--failed' : undefined}>
                    <td>
                      <span className="runs__kind">{KIND_LABEL[run.kind] || run.kind}</span>
                      {' · '}
                      {r.link
                        ? <Link to={r.link} title={run.target}>{nameOf(run)}</Link>
                        : <span title={run.target || undefined}>{nameOf(run)}</span>}
                    </td>
                    {show.model && <td className="runs__muted">{r.models.map(labelOf).join(', ') || '—'}</td>}
                    <td className="runs__verdict"><Outcome run={run} verdict={r.verdict} /></td>
                    <td className="runs__muted runs__nowrap" title={absolute(run.started)}>{ago(run.started) || '—'}</td>
                    {show.took && <td className="runs__muted runs__nowrap">{r.took || '—'}</td>}
                    {show.who && <td className="runs__muted">{r.who || '—'}</td>}
                  </tr>
                )
              })}
            </tbody>
          ))}
        </table>
      )}
    </>
  )
}
