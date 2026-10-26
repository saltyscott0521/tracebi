import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { useReportRun, useStartReportRun } from '../api'
import { useToast } from './Shared'
import { VERDICT_LABEL, needsAction, verdictOf } from '../verdict'
import { count } from '../format'
import { pipelineModels, dataPath, folderOf, historyPath, reportPagePath, transformPath, warehouseTablePath } from '../nav'

// What needs a person, from GET /api/desk, the pipelines list, the run store
// (GET /api/runs) and the publish and code requests: review notes, builds
// that need a look or do not reproduce, failed runs and refreshes, sink checks
// that are stale or missing, and requests waiting on a decision. Review lists
// them first, newest first.

const SINK = {
  stale:       'Data changed since its checks last passed',
  no_contract: 'No data checks declared',
}

function reportHref(name) {
  return name && name !== '_discovery' ? reportPagePath(name) : null
}

const NOTE = 'Review note'

// Each item carries `models`: the models it is about (none = the project).
// *modelsOf* maps a report name to the models it reads; *reports* is GET
// /api/reports, so a build whose files changed since needs a look here too.
// *more* holds the run store's rows (`runs`), the publish requests
// (`requests`) and the code requests (`codeRequests`), each optional. Every
// item says what (`title`), why (`detail`), when (`at`, ISO) and what to do:
// `href` with its `action` words, or `decide` (a publish request), `review`
// (a code request) or `buildAll` (the reports never built) for the page to
// act on in place.
export function attentionItems(desk, pipelines, modelsOf = () => [], reports = [], more = {}) {
  const items = []
  const nameOf = name => reports.find(r => r.name === name)?.display_name || name
  for (const pin of desk?.pins || []) {
    items.push({
      key: `pin-${pin.report}-${pin.id}`, kind: NOTE, variant: 'blue',
      models: modelsOf(pin.report),
      title: pin.report === '_discovery' ? 'Project workbench' : (pin.display_name || nameOf(pin.report)),
      detail: pin.note || `Pin ${pin.id}`, href: reportHref(pin.report), action: 'Open report',
    })
  }
  // Every build the desk re-checked, and every receipt it could not pair with
  // a page (`verdicts` lists those too, with what the check said).
  const builds = new Map((desk?.builds || []).map(b => [b.report, b]))
  for (const row of desk?.verdicts || []) builds.set(row.report, { ...builds.get(row.report), ...row })
  for (const [name, build] of [...builds].sort(([a], [b]) => a.localeCompare(b))) {
    const report = reports.find(r => r.name === name)
    const v = verdictOf({ report, build })
    if (!needsAction(v)) continue
    const changed = Date.parse(report?.last_change) > Date.parse(build.built_at) ? report.last_change : null
    items.push({
      key: `verdict-${name}`, kind: VERDICT_LABEL[v.state], verdict: v.state,
      models: modelsOf(name),
      title: build.display_name || nameOf(name), detail: v.detail, at: changed || build.built_at,
      href: reportHref(name), action: 'Open report',
    })
  }
  // Reports with no build at all: on a fresh project, the first thing to do.
  // One item for all of them, not one each, so it does not bury the rest.
  // Before the desk has answered nothing is known to be unbuilt.
  const unbuilt = desk ? reports.filter(r => !builds.has(r.name)) : []
  if (unbuilt.length) {
    const names = unbuilt.map(r => r.display_name || r.name)
    const n = unbuilt.length
    items.push({
      key: 'never-built', kind: VERDICT_LABEL['never-built'], verdict: 'never-built', models: [],
      title: `${count(n, 'report')} ${n === 1 ? 'has' : 'have'} never been built`,
      detail: n > 3 ? `${names.slice(0, 3).join(', ')} and ${n - 3} more.` : `${names.join(', ')}.`,
      buildAll: unbuilt.map(r => r.name),
    })
  }
  // The newest run of each target in the run store (it lists newest first).
  const runs = Array.isArray(more.runs) ? more.runs : []
  const newest = new Map()
  for (const run of runs) if (run.target && !newest.has(run.target)) newest.set(run.target, run)
  // A refresh with failed steps is one item, saying why when the run store
  // recorded it; its steps and its run are not listed again below.
  const failedLayers = new Set()
  const failedPipelines = new Set()
  for (const p of pipelines || []) {
    const failed = (p.layers || []).filter(l => l.last_status === 'failed')
    if (!failed.length) continue
    failed.forEach(l => failedLayers.add(l.name))
    failedPipelines.add(p.pipeline)
    const run = newest.get(p.pipeline)
    const said = run?.kind === 'pipeline_run' && RUN_FAILED[run.status] && errorOf(run)
    const last = failed.map(l => l.last_run).sort().pop()
    items.push({
      key: `run-${p.pipeline}`, kind: 'Refresh failed', variant: 'red',
      models: pipelineModels(p),
      title: p.pipeline,
      detail: said
        ? `Refresh failed: ${said}`
        : `Refresh failed at ${failed.map(l => l.name).join(', ')}.`,
      at: last,
      href: pipelineModels(p)[0] ? dataPath(pipelineModels(p)[0], 'transform') : '/data',
      action: 'Open run',
    })
  }
  for (const s of desk?.sinks || []) {
    items.push({
      key: `sink-${s.table}`, kind: s.status === 'stale' ? 'Checks stale' : 'No checks',
      variant: s.status === 'stale' ? 'amber' : 'gray',
      // A stale table names the transform whose checks it no longer matches;
      // a table with none is opened itself.
      models: [], title: s.table, detail: SINK[s.status] || s.status,
      href: s.transform ? transformPath(s.transform) : warehouseTablePath(s.table),
      action: s.transform ? 'Open transform' : 'Open table',
    })
  }
  // The newest run of each other target, when it did not succeed. A step or
  // pipeline already listed as a failed refresh is not listed twice.
  for (const run of newest.values()) {
    if (!RUN_FAILED[run.status]) continue
    if (run.kind === 'pipeline_layer' && failedLayers.has(run.target)) continue
    if (run.kind === 'pipeline_run' && failedPipelines.has(run.target)) continue
    const said = errorOf(run)
    const what = `${RUN_KIND[run.kind] || 'Run'} ${RUN_SAID[run.status]}`
    const pipeline = (pipelines || []).find(
      p => p.pipeline === run.target || (p.layers || []).some(l => l.name === run.target))
    const model = pipeline && pipelineModels(pipeline)[0]
    const isReport = REPORT_RUNS.has(run.kind)
    items.push({
      key: `runs-${run.id}`, kind: RUN_FAILED[run.status], variant: run.status === 'empty' ? 'amber' : 'red',
      models: isReport ? modelsOf(run.target) : pipeline ? pipelineModels(pipeline) : [],
      title: run.display_name || run.target,
      detail: said ? `${what}: ${said}` : `${what}.`, at: run.started,
      href: isReport ? reportHref(run.target)
        : model ? dataPath(model, 'transform')
          : `${historyPath()}?${new URLSearchParams({ kind: run.kind || '', target: run.target })}`,
      action: isReport ? 'Open report' : 'Open run',
    })
  }
  // Publish requests still pending: ones the person may decide, and their own,
  // which wait on the folder's approvers. Pending code requests an admin may
  // decide.
  for (const r of Array.isArray(more.requests) ? more.requests : []) {
    if (r.status !== 'pending') continue
    const asked = `Asked by ${r.requested_by || 'unknown'}${r.note ? `: \u201c${r.note}\u201d` : ''}`
    items.push(r.can_decide ? {
      key: `request-${r.id}`, kind: 'Publish request', variant: 'amber', models: modelsOf(r.destination),
      title: `Publish ${nameOf(r.destination)}`, detail: asked, at: r.requested_at, decide: r,
    } : {
      key: `request-${r.id}`, kind: 'Waiting', variant: 'gray', models: modelsOf(r.destination),
      title: `Publish ${nameOf(r.destination)}`,
      detail: `Waiting on ${folderOf(r.destination) || 'the library'}\u2019s approvers.`, at: r.requested_at,
    })
  }
  for (const r of Array.isArray(more.codeRequests) ? more.codeRequests : []) {
    if (r.status !== 'pending') continue
    const files = r.files.length === 1 ? r.files[0] : `${r.files.length} files`
    if (!r.can_decide) {
      items.push({
        key: `code-${r.id}`, kind: 'Waiting', variant: 'gray', models: [],
        title: files, detail: 'Waiting on an admin to review the code.', at: r.requested_at,
      })
      continue
    }
    items.push({
      key: `code-${r.id}`, kind: 'Code request', variant: 'amber', models: [],
      title: files,
      detail: `Asked by ${r.requested_by || 'unknown'}: \u201c${r.note}\u201d`, at: r.requested_at, review: r,
    })
  }
  // Newest first; what has no time keeps its place after.
  const t = it => Date.parse(it.at) || 0
  return items.map((it, i) => [it, i]).sort(([a, i], [b, j]) => (t(b) - t(a)) || (i - j)).map(([it]) => it)
}

// A run that did not succeed, in the words History uses.
const RUN_FAILED = { failed: 'Failed', error: 'Error', refused: 'Refused', empty: 'Empty' }
const RUN_SAID = {
  failed: 'failed', error: 'stopped with an error', refused: 'was refused',
  empty: 'sent nothing: a figure had no rows',
}
const RUN_KIND = {
  report_build: 'Build', background_run: 'Build', schedule: 'Scheduled run',
  pipeline_layer: 'Refresh step', pipeline_run: 'Refresh', publish: 'Publish',
}
const REPORT_RUNS = new Set(['report_build', 'background_run', 'schedule'])

// What a run's row says went wrong: its error (a string, or the structured
// payload's message), else its note.
function errorOf(run) {
  const e = run.detail?.error ?? run.detail?.note
  const text = typeof e === 'string' ? e : e?.message
  return typeof text === 'string' ? text.replace(/^Run failed: /, '') : ''
}

// Follows one background build until it settles, then says how it ended.
function Follow({ name, runId, onSettled }) {
  const { data } = useReportRun(name, runId)
  const status = data?.status
  useEffect(() => {
    if (status && status !== 'running') onSettled(name, status)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])
  return null
}

/**
 * Build every report in *names*: each a background run on the server (POST
 * /api/reports/{name}/runs, what a report page's "Build it now" starts),
 * followed until it settles. When all have, the builds are read again, so the
 * item goes and the library shows them.
 */
export function BuildAll({ names }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { mutateAsync: start } = useStartReportRun()
  const [runs, setRuns] = useState(null)      // [{name, runId}] once started
  const [ended, setEnded] = useState({})      // name -> how its run settled
  const done = Object.keys(ended).length

  useEffect(() => {
    if (!runs?.length || done < runs.length) return
    const failed = Object.values(ended).filter(s => s !== 'succeeded').length
    toast(failed ? `${count(runs.length - failed, 'report')} built, ${failed} failed. History says why.`
      : `${count(runs.length, 'report')} built.`, failed ? 'error' : 'info')
    qc.invalidateQueries({ queryKey: ['desk'] })
    qc.invalidateQueries({ queryKey: ['runs'] })
    setRuns(null)
    setEnded({})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done, runs])

  // A run that could not start has settled already: it failed.
  const begin = async () => {
    setRuns([])
    const started = await Promise.all(names.map(name => start(name)
      .then(res => ({ name, runId: res.run_id }))
      .catch(() => { setEnded(e => ({ ...e, [name]: 'failed' })); return { name, runId: null } })))
    setRuns(started)
  }

  const busy = runs !== null
  return (
    <>
      <button type="button" className="review__open review__btn" onClick={begin} disabled={busy}>
        {busy ? `Building ${count(names.length - done, 'report')}…` : 'Build all'}
      </button>
      {(runs || []).filter(r => r.runId).map(r => (
        <Follow key={r.runId} name={r.name} runId={r.runId}
                onSettled={(name, status) => setEnded(e => ({ ...e, [name]: status }))} />
      ))}
    </>
  )
}
