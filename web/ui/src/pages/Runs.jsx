import { Link, useSearchParams } from 'react-router-dom'

import { reportShareUrl, useRuns } from '../api'
import { verdictOf, when } from '../components/Attention'
import { PageHeader, useReportModels } from '../components/Scope'
import { reportPagePath } from '../nav'
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

// Only `reproduces` is green — the same words the Reports page uses.
// An unset verdict has not been checked, so it never reads green.
function runVerdict(v) {
  if (v == null || v === '') return { label: 'Not verified', variant: 'gray' }
  return verdictOf(v)
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

// A report run belongs to the models its report reads. A pipeline's own steps
// keep their history with the pipeline (Refresh shows it), so a model's Runs
// are its reports'.
function runModels(run, modelsOf) {
  return REPORT_KINDS.has(run.kind) ? modelsOf(run.target) : []
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
  const modelsOf = useReportModels()
  const runs = (Array.isArray(data) ? data : []).filter(r => !model || runModels(r, modelsOf).includes(model))

  return (
    <>
      <PageHeader pageKey="runs" model={model}
        sub={model
          ? `Every build of ${model}'s reports: when, for whom, and whether it reproduced. Its refreshes are on Refresh.`
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
                const verdict = runVerdict(run.verdict)
                const page = reportPage(run, runModels(run, modelsOf))
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
                    {!model && <td style={{ fontSize: 12, color: 'var(--muted)' }}>{runModels(run, modelsOf).join(', ') || '—'}</td>}
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
                      <Badge variant={verdict.variant} style={{ textTransform: 'none' }}>
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
