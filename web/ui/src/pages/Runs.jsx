import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { reportShareUrl, useDesk, usePipelines, useRuns } from '../api'
import { verdictOf, when } from '../components/Attention'
import { PageHeader, useReportModels } from '../components/Scope'
import { pipelineModels, reportPagePath } from '../nav'
import {
  Badge, Spinner, Empty, ErrorDetail,
} from '../components/Shared'

// Kinds the store records. The values are the API's filters; the labels
// are what the table shows.
const KINDS = [
  ['report_build', 'Report build'],
  ['background_run', 'Background run'],
  ['schedule', 'Schedule'],
  ['pipeline_layer', 'Pipeline'],
  ['pipeline_run', 'Pipeline run'],
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

const field = {
  font: 'inherit', fontSize: 13, color: 'var(--text)',
  background: 'var(--surface)', border: '1px solid var(--border)',
  borderRadius: 6, padding: '6px 10px',
}

// The words and chips the Reports page uses, and only `reproduces` is green.
// A build row stores no verdict (a build is not a check). Only the newest
// successful build of a report is still the page on disk, and the Reports page
// re-checks that one: its row shows that verdict. Any other build was never
// checked, and says so in grey.
function runVerdict(run, latestBuild, checks) {
  if (run.verdict) return verdictOf(run.verdict)
  const latest = BUILD_KINDS.has(run.kind) && latestBuild[run.target] === run.id
  if (latest && checks.loading) return { label: 'Checking…', variant: 'gray' }
  if (latest && checks.byReport[run.target]) return verdictOf(checks.byReport[run.target])
  return {
    label: 'Not checked', variant: 'gray',
    title: BUILD_KINDS.has(run.kind) ? 'Only the latest build of a report is re-checked; the Reports page shows it.' : undefined,
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

function reportPage(run, models) {
  if (!run.target || !REPORT_KINDS.has(run.kind)) return null
  return reportPagePath(run.target, models)
}

// A filesystem path is not a URL the app serves. A report run's file is
// the share page; an http(s) or /r/ or /api/ path is already one.
function outputHref(run) {
  const path = typeof run.output_path === 'string' ? run.output_path.trim() : ''
  if (!path) return null
  if (/^https?:\/\//i.test(path)) return path
  if (path.startsWith('/r/') || path.startsWith('/api/')) return path
  if (REPORT_KINDS.has(run.kind) && run.target) return reportShareUrl(run.target)
  return null
}

function Actor({ run }) {
  if (!run.actor && !run.actor_role) return '—'
  return (
    <>
      {run.actor || '—'}
      {run.actor_role
        ? <span style={{ color: 'var(--muted)' }}> · {run.actor_role}</span>
        : null}
    </>
  )
}

// A report run belongs to the models its report reads; a refresh (a pipeline
// run, or one of its steps) to the models its pipeline names.
function runModels(run, modelsOf, pipelineModelsOf) {
  if (REPORT_KINDS.has(run.kind)) return modelsOf(run.target)
  if (run.kind === 'pipeline_run' || run.kind === 'pipeline_layer') return pipelineModelsOf(run.target)
  return []
}

export default function Runs({ model = '' }) {
  // The owner alert links here as /runs?kind=schedule&target=<report>.
  // The filters are that query string, so the link arrives already selected
  // and a change stays in the URL.
  const [searchParams, setSearchParams] = useSearchParams()
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
  const checks = {
    loading: deskLoading,
    byReport: Object.fromEntries((desk?.builds || []).map(b => [b.report, b.verdict])),
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

  return (
    <>
      <PageHeader pageKey="runs" model={model}
        sub={model
          ? `Every build of ${model}'s reports and every refresh of its data: when, for whom, and whether it reproduced.`
          : 'What ran, when, for whom, and whether it reproduced. Only a receipt that reproduces reads green.'} />

      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16, alignItems: 'flex-end' }}>
        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 4 }}>
          Kind
          <select value={kind} onChange={e => setFilter('kind', e.target.value)} style={field}>
            <option value="">All</option>
            {KINDS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 4 }}>
          Target
          <input
            value={target}
            onChange={e => setFilter('target', e.target.value)}
            placeholder="Exact name"
            style={{ ...field, minWidth: 220 }}
          />
        </label>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', fontSize: 13 }}>
          <Spinner size={14} /> Loading runs…
        </div>
      ) : error ? (
        <ErrorDetail error={error} />
      ) : runs.length === 0 ? (
        <Empty message={kind || target.trim() ? 'No runs match these filters.' : 'No runs yet.'} />
      ) : (
        <div style={{ overflowX: 'auto' }} className="fade-in">
          <table>
            <thead>
              <tr>
                <th>Kind</th>
                <th>Target</th>
                {!model && <th>Model</th>}
                <th>Status</th>
                <th>Started</th>
                <th>Finished</th>
                <th>Actor</th>
                <th>Verdict</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(run => {
                const models = runModels(run, modelsOf, pipelineModelsOf)
                const verdict = runVerdict(run, latestBuild, checks)
                const page = reportPage(run, models)
                const output = outputHref(run)
                const dur = duration(run.started, run.finished)
                return (
                  <tr key={run.id}>
                    <td>{KIND_LABEL[run.kind] || run.kind || '—'}</td>
                    <td>
                      {page
                        ? <Link to={page}>{run.target}</Link>
                        : (run.target || '—')}
                      {output && (
                        <>
                          {' '}
                          <a href={output}>Open</a>
                        </>
                      )}
                    </td>
                    {!model && <td style={{ fontSize: 12, color: 'var(--muted)' }}>{models.join(', ') || '—'}</td>}
                    <td>
                      <Badge variant={STATUS[run.status] || 'gray'} style={{ textTransform: 'none' }}>
                        {run.status || '—'}
                      </Badge>
                    </td>
                    <td style={{ color: 'var(--muted)', fontSize: 12, whiteSpace: 'nowrap' }}>
                      {when(run.started) || '—'}
                    </td>
                    <td style={{ color: 'var(--muted)', fontSize: 12, whiteSpace: 'nowrap' }}>
                      {when(run.finished) || '—'}
                      {dur && <div style={{ fontSize: 11 }}>{dur}</div>}
                    </td>
                    <td style={{ fontSize: 12 }}><Actor run={run} /></td>
                    <td>
                      <Badge variant={verdict.variant} style={{ textTransform: 'none' }} title={verdict.title}>
                        {verdict.label}
                      </Badge>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
