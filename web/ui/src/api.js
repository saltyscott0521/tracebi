import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const BASE = '/api'

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
  return err
}

async function get(path) {
  // no-store: live data — never let the browser HTTP cache answer for the API
  const r = await fetch(BASE + path, { cache: 'no-store' })
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
  `${BASE}/reports/${encodeURIComponent(name)}/download?format=${format}`

export const tableCsvUrl = (model, table) =>
  `${BASE}/models/${encodeURIComponent(model)}/tables/${encodeURIComponent(table)}/export.csv`

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

export const useRunReport = () =>
  useMutation({ mutationFn: (name) => post(`/reports/${name}/run`) })

// Background report runs: start returns a run_id; the status query polls
// every 1.2s while the run is in flight, then stops on its own.
export const useStartReportRun = () =>
  useMutation({ mutationFn: (name) => post(`/reports/${encodeURIComponent(name)}/runs`) })

export const useReportRun = (name, runId) =>
  useQuery({
    queryKey: ['report-run', name, runId],
    queryFn: () => get(`/reports/${encodeURIComponent(name)}/runs/${runId}`),
    enabled: !!(name && runId),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 1200 : false),
  })

export const useReportRunHistory = (name) =>
  useQuery({
    queryKey: ['report-runs', name],
    queryFn: () => get(`/reports/${encodeURIComponent(name)}/runs?limit=5`),
    enabled: !!name,
  })

export const useReportLineage = () =>
  useMutation({ mutationFn: (name) => get(`/reports/${name}/lineage`) })

export const useRequests = () =>
  useQuery({ queryKey: ['requests'], queryFn: () => get('/requests') })

// Declared request_params() defaults — statically discovered, no execution.
export const useRequestParams = (name) =>
  useQuery({
    queryKey: ['request-params', name],
    queryFn: () => get(`/requests/${encodeURIComponent(name)}/params`),
    enabled: !!name,
  })

export const useRunRequest = () =>
  useMutation({
    mutationFn: ({ name, params }) =>
      postJson(`/requests/${encodeURIComponent(name)}/run`, { params: params || {} }),
  })

export const useRequestLineage = () =>
  useMutation({
    mutationFn: ({ name, params }) => {
      const qs = params && Object.keys(params).length
        ? `?params_json=${encodeURIComponent(JSON.stringify(params))}`
        : ''
      return get(`/requests/${encodeURIComponent(name)}/lineage${qs}`)
    },
  })

export const usePipelines = () =>
  useQuery({ queryKey: ['pipelines'], queryFn: () => get('/pipelines'), refetchInterval: 10000 })

export const useRunLayer = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ pipeline, layer, refresh }) =>
      post(`/pipelines/${pipeline}/layers/${layer}/run${refresh ? '?refresh=true' : ''}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipelines'] }),
  })
}

export const useRunPipeline = () => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ pipeline }) => post(`/pipelines/${pipeline}/run`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pipelines'] }),
  })
}

export const useDashboardLineage = () =>
  useMutation({ mutationFn: (name) => get(`/dashboards/${name}/lineage`) })

export const useLayerHistory = (pipeline, layer) =>
  useQuery({
    queryKey: ['history', pipeline, layer],
    queryFn: () => get(`/pipelines/${pipeline}/layers/${layer}/history`),
    enabled: !!(pipeline && layer),
  })

export const useDashboards = () =>
  useQuery({ queryKey: ['dashboards'], queryFn: () => get('/dashboards') })

export const useRunQuery = () =>
  useMutation({ mutationFn: ({ model, body }) => postJson(`/models/${encodeURIComponent(model)}/query`, body) })
