import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

// Where the API lives. Defaults to a same-origin /api, which is what the
// bundled dev server and the container image serve. Set VITE_API_BASE at
// build time to point the UI at an API on another origin, such as an
// external host:
//
//   VITE_API_BASE=https://tracebi-api.example.com/api  npm run build
//
// Trailing slashes are trimmed so both forms work.
const BASE = (import.meta.env?.VITE_API_BASE || '/api').replace(/\/+$/, '')

// A report in a folder is named by its path ("finance/weekly"). Encode each
// part but keep the slashes: an encoded slash (%2F) is refused by some
// proxies, and the API's routes take the path as-is.
export const reportPath = (name) => name.split('/').map(encodeURIComponent).join('/')

// API errors carry a structured `detail` ({ message, exception_type, traceback })
// for 500s from report/pipeline runs; fall back to plain text otherwise.
async function toError(r) {
  const text = await r.text()
  let message = text || r.statusText
  let detail = null
  try {
    const body = JSON.parse(text)
    detail = body.detail ?? null
    if (typeof detail === 'string') message = detail
    else if (detail?.message) message = detail.message
  } catch { /* non-JSON body — keep raw text */ }
  const err = new Error(message)
  err.detail = typeof detail === 'object' ? detail : null
  err.status = r.status
  // The server signs people in itself (OIDC) and says where: a 401 that names
  // a login address sends the browser there, and back to this page after.
  if (r.status === 401 && typeof detail?.login === 'string' && detail.login.startsWith('/')) {
    const next = window.location.pathname + window.location.search
    window.location.assign(`${detail.login}?next=${encodeURIComponent(next)}`)
  }
  return err
}

async function get(path) {
  // no-store: live data — never let the browser HTTP cache answer for the API
  const r = await fetch(BASE + path, { cache: 'no-store' })
  if (!r.ok) throw await toError(r)
  return r.json()
}

async function getOrNull(path) {
  const r = await fetch(BASE + path, { cache: 'no-store' })
  if (r.status === 404) return null
  if (!r.ok) throw await toError(r)
  return r.json()
}

async function post(path) {
  const r = await fetch(BASE + path, { method: 'POST' })
  if (!r.ok) throw await toError(r)
  return r.json()
}

async function postJson(path, body) {
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw await toError(r)
  return r.json()
}

export const reportDownloadUrl = (name, format) =>
  `${BASE}/reports/${reportPath(name)}/download?format=${format}`

// The share link: the last build as a full page at /r/<name>, outside /api.
// Under the UI's base path, so it resolves where the UI is mounted under a
// prefix (tracebi.com serves the app at /app/ and strips it before the server).
export const reportShareUrl = (name) =>
  `${window.location.origin}${import.meta.env.BASE_URL.replace(/\/+$/, '')}/r/${reportPath(name)}`

// Offline file check: rehash a report .html's embedded data against its
// manifest receipt (no model needed). The verdict lives in the response body.
export const useVerifyFile = () =>
  useMutation({
    mutationFn: ({ html, manifest }) => postJson('/verify/file', { html, manifest }),
  })

export const tableCsvUrl = (model, table) =>
  `${BASE}/models/${encodeURIComponent(model)}/tables/${encodeURIComponent(table)}/export.csv`

export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: () => get('/health') })

// Install status, including whether a newer TraceBi is published. The server
// answers from a cached check (refreshed in the background), so poll gently
// until it has an answer, then rarely.
export const useAppStatus = () =>
  useQuery({
    queryKey: ['status'],
    queryFn: () => get('/status'),
    refetchInterval: (q) => (q.state.data?.update?.latest ? 30 * 60 * 1000 : 60 * 1000),
  })

// Who is signed in, and how. Only an OIDC sign-in shows a person and a way out.
export const useMe = () =>
  useQuery({ queryKey: ['me'], queryFn: () => get('/me'), staleTime: 5 * 60 * 1000, retry: false })

export const signOut = () =>
  fetch('/logout', { method: 'POST' }).finally(() => window.location.assign('/'))

export const useConnectors = () =>
  useQuery({ queryKey: ['connectors'], queryFn: () => get('/connectors') })

// Markdown guides from docs/ — static content, cache for the session.
export const useGuides = () =>
  useQuery({ queryKey: ['guides'], queryFn: () => get('/docs'), staleTime: Infinity })

export const useGuide = (name) =>
  useQuery({
    queryKey: ['guide', name],
    queryFn: () => get(`/docs/${encodeURIComponent(name)}`),
    enabled: !!name,
    staleTime: Infinity,
  })

export const useModels = () =>
  useQuery({ queryKey: ['models'], queryFn: () => get('/models') })

export const useModel = (name) =>
  useQuery({ queryKey: ['model', name], queryFn: () => get(`/models/${name}`), enabled: !!name })

export const useTablePreview = (model, table) =>
  useQuery({
    queryKey: ['preview', model, table],
    queryFn: () => get(`/models/${model}/tables/${table}/preview`),
    enabled: !!(model && table),
  })

export const useReports = () =>
  useQuery({ queryKey: ['reports'], queryFn: () => get('/reports') })

export const useDesk = () =>
  useQuery({ queryKey: ['desk'], queryFn: () => get('/desk') })

export const fetchBuiltReport = (name) =>
  getOrNull(`/reports/${reportPath(name)}/built`)

export const useBuiltReport = (name) =>
  useQuery({
    queryKey: ['built-report', name],
    queryFn: () => fetchBuiltReport(name),
    enabled: !!name,
    retry: false,
  })

// Background report runs: start returns a run_id; the status query polls
// every 1.2s while the run is in flight, then stops on its own.
export const useStartReportRun = () =>
  useMutation({ mutationFn: (name) => post(`/reports/${reportPath(name)}/runs`) })

export const useReportRun = (name, runId) =>
  useQuery({
    queryKey: ['report-run', name, runId],
    queryFn: () => get(`/reports/${reportPath(name)}/runs/${runId}`),
    enabled: !!(name && runId),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 1200 : false),
    // Keep polling even when the tab is backgrounded — the run is on the
    // server, and the copy promises "you can keep browsing".
    refetchIntervalInBackground: true,
  })

export const useReportRunHistory = (name) =>
  useQuery({
    queryKey: ['report-runs', name],
    queryFn: () => get(`/reports/${reportPath(name)}/runs?limit=5`),
    enabled: !!name,
  })

// The files that define a report (its spec, or its package's files).
export const useReportSource = (name, enabled) =>
  useQuery({
    queryKey: ['report-source', name],
    queryFn: () => get(`/reports/${reportPath(name)}/source`),
    enabled: !!(name && enabled),
  })

// The code behind a model, pipeline or connector (read-only): the files
// discovery found for it. `kind` is the route family.
export const useSource = (kind, name) =>
  useQuery({
    queryKey: ['source', kind, name],
    queryFn: () => get(`/${kind}/${encodeURIComponent(name)}/source`),
    enabled: !!name,
  })

// What a file-backed warehouse holds: tables, row counts, profiles, contract status.
export const useConnectorWarehouse = (name) =>
  useQuery({
    queryKey: ['warehouse', name],
    queryFn: () => get(`/connectors/${encodeURIComponent(name)}/warehouse`),
    enabled: !!name,
  })

export const useReportLineage =() =>
  useMutation({ mutationFn: (name) => get(`/reports/${reportPath(name)}/lineage`) })

// Ask is a client of the selection endpoint: a cut, not a private query path.
export const useReportSelection = () =>
  useMutation({
    mutationFn: ({ name, filters, question }) =>
      postJson(`/reports/${reportPath(name)}/selection`,
        question ? { question } : { filters: filters || {} }),
  })

// Build mode (local only): what the builder is pointing at, so the agent can
// resolve "this". `pointing: null` stops pointing. Not the Ask cut above.
// One scope runs these one at a time, in the order sent: a click and then
// leaving Build mode must reach the server in that order, or the clear can
// land first and the agent keeps acting on a figure nobody is looking at.
export const usePointing = () =>
  useMutation({
    scope: { id: 'workbench-pointing' },
    mutationFn: ({ name, pointing }) => {
      const path = `/reports/${reportPath(name)}/workbench/pointing`
      return pointing
        ? postJson(path, pointing)
        : fetch(BASE + path, { method: 'DELETE' }).then(r => (r.ok ? r.json() : toError(r)))
    },
  })

// The workbench in the app. `version` is a cheap fingerprint polled every
// 1.5s; the state and the preview are fetched again only when it moves.
const wb = (name) => `/reports/${reportPath(name)}/workbench`

export const useWorkbenchVersion = (name, enabled) =>
  useQuery({
    queryKey: ['wb-version', name],
    queryFn: () => get(`${wb(name)}/version`).then(d => d.version),
    enabled: !!name && enabled,
    refetchInterval: 1500,
    retry: false,
  })

export const useWorkbenchState = (name, version, enabled) =>
  useQuery({
    queryKey: ['wb-state', name, version],
    queryFn: () => get(`${wb(name)}/state`),
    enabled: !!name && !!version && enabled,
    retry: false,
    placeholderData: (previous) => previous,
  })

export const useWorkbenchPreview = (name, version, enabled) =>
  useQuery({
    queryKey: ['wb-preview', name, version],
    queryFn: async () => {
      const r = await fetch(BASE + `${wb(name)}/preview`, { cache: 'no-store' })
      if (!r.ok) throw await toError(r)
      return r.text()
    },
    enabled: !!name && !!version && enabled,
    retry: false,
    placeholderData: (previous) => previous,
  })

// A note for the agent, left from the workbench: it reads it as an open pin.
// `name` is the report whose workbench this is, or null for the project feed.
export const useLeaveNote = (name) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (note) => postJson(name ? `${wb(name)}/note` : '/workbench/project/note', { note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [name ? 'wb-state' : 'wb-project'] }),
  })
}

// The project feed (dev mode only): what the agent shows you, and your notes to
// it, before a report is open. The server rebuilds it only when it changed.
export const useProjectFeed = (enabled) =>
  useQuery({
    queryKey: ['wb-project'],
    queryFn: () => get('/workbench/project'),
    enabled,
    refetchInterval: 2000,
    retry: false,
    placeholderData: (previous) => previous,
  })

export const useKeepSelection = () =>
  useMutation({
    mutationFn: ({ name, filters }) =>
      postJson(`/reports/${reportPath(name)}/selection/keep`, { filters }),
  })

export const usePipelines = () =>
  useQuery({ queryKey: ['pipelines'], queryFn: () => get('/pipelines'), refetchInterval: 10000 })

// A run in the background, with its log read as it grows. `layer` runs just
// that step (`refresh` adds what it depends on); without it, the whole pipeline.
export const useStartPipelineRun = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ pipeline, layer, refresh }) => {
      const q = new URLSearchParams()
      if (layer) q.set('layer', layer)
      if (refresh != null) q.set('refresh', String(refresh))
      const qs = q.toString()
      return post(`/pipelines/${encodeURIComponent(pipeline)}/runs${qs ? `?${qs}` : ''}`)
    },
    onSuccess: (_, { pipeline }) => qc.invalidateQueries({ queryKey: ['pipeline-runs', pipeline] }),
  })
}

export const usePipelineRuns = pipeline =>
  useQuery({
    queryKey: ['pipeline-runs', pipeline],
    queryFn: () => get(`/pipelines/${encodeURIComponent(pipeline)}/runs?limit=30`),
    enabled: !!pipeline,
    refetchInterval: q => (q.state.data || []).some(r => r.status === 'running') ? 2000 : 15000,
  })

const NO_LOG = { text: '', status: null, done: false, expired: false, error: null }

/**
 * What a run has printed so far, following it until it is done. Asks from
 * where the last answer ended, so each poll carries only the new lines.
 */
export function useRunLog(pipeline, runId) {
  const [log, setLog] = useState(NO_LOG)
  useEffect(() => {
    setLog(NO_LOG)
    if (!pipeline || !runId) return undefined
    let stopped = false
    let after = 0
    let timer
    const poll = async () => {
      try {
        const got = await get(`/pipelines/${encodeURIComponent(pipeline)}/runs/${runId}/log?after=${after}`)
        if (stopped) return
        after = got.next
        setLog(prev => ({ text: prev.text + got.text, status: got.status, done: got.done, expired: got.expired, error: null }))
        if (!got.done) timer = setTimeout(poll, 1000)
      } catch (error) {
        if (stopped) return
        setLog(prev => ({ ...prev, error }))
        if (error.status !== 403 && error.status !== 404) timer = setTimeout(poll, 3000)
      }
    }
    poll()
    return () => { stopped = true; clearTimeout(timer) }
  }, [pipeline, runId])
  return log
}

export const useLayerHistory = (pipeline, layer) =>
  useQuery({
    queryKey: ['history', pipeline, layer],
    queryFn: () => get(`/pipelines/${pipeline}/layers/${layer}/history`),
    enabled: !!(pipeline && layer),
  })

export const useRunQuery = () =>
  useMutation({ mutationFn: ({ model, body }) => postJson(`/models/${encodeURIComponent(model)}/query`, body) })

// Shared run store. kind and target are the API's own filters (exact match).
export const useRuns = (kind, target) =>
  useQuery({
    queryKey: ['runs', kind || '', target || ''],
    queryFn: () => {
      const params = new URLSearchParams()
      if (kind) params.set('kind', kind)
      if (target) params.set('target', target)
      const q = params.toString()
      return get('/runs' + (q ? `?${q}` : ''))
    },
  })

// Drafts: what an agent (or a person) is writing before it is published. A
// draft's path may hold slashes, so each part is encoded like a report's.
const draftUrl = (d) => `/drafts/${encodeURIComponent(d.owner)}/${d.kind}/${reportPath(d.path)}`

export const useDrafts = () =>
  useQuery({ queryKey: ['drafts'], queryFn: () => get('/drafts'), refetchInterval: 10000 })

export const useDraftVersion = (d) =>
  useQuery({
    queryKey: ['draft-version', d.owner, d.kind, d.path],
    queryFn: () => get(`${draftUrl(d)}/version`).then(x => x.version),
    refetchInterval: 1500,
    retry: false,
  })

export const useDraftFiles = (d, version) =>
  useQuery({
    queryKey: ['draft-files', d.owner, d.kind, d.path, version],
    queryFn: () => get(`${draftUrl(d)}/files`),
    enabled: !!version,
    retry: false,
    placeholderData: (previous) => previous,
  })

export const useDraftPreview = (d, version, enabled) =>
  useQuery({
    queryKey: ['draft-preview', d.owner, d.kind, d.path, version],
    queryFn: async () => {
      const r = await fetch(BASE + `${draftUrl(d)}/preview`, { cache: 'no-store' })
      if (!r.ok) throw await toError(r)
      return r.text()
    },
    enabled: !!version && enabled,
    retry: false,
    placeholderData: (previous) => previous,
  })

export const usePublishDraft = (d) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (note) => postJson(`${draftUrl(d)}/publish`, { note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['drafts'] }),
  })
}

export const useDeleteDraft = (d) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => fetch(BASE + draftUrl(d), { method: 'DELETE' })
      .then(async r => { if (!r.ok) throw await toError(r); return r.json() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['drafts'] }),
  })
}
