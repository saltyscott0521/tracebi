import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

const BASE = '/api'

async function get(path) {
  const r = await fetch(BASE + path)
  if (!r.ok) throw new Error((await r.text()) || r.statusText)
  return r.json()
}

async function post(path) {
  const r = await fetch(BASE + path, { method: 'POST' })
  if (!r.ok) throw new Error((await r.text()) || r.statusText)
  return r.json()
}

export const useConnectors = () =>
  useQuery({ queryKey: ['connectors'], queryFn: () => get('/connectors') })

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

export const useReportLineage = () =>
  useMutation({ mutationFn: (name) => get(`/reports/${name}/lineage`) })

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

export const useLayerHistory = (pipeline, layer) =>
  useQuery({
    queryKey: ['history', pipeline, layer],
    queryFn: () => get(`/pipelines/${pipeline}/layers/${layer}/history`),
    enabled: !!(pipeline && layer),
  })

export const useDashboards = () =>
  useQuery({ queryKey: ['dashboards'], queryFn: () => get('/dashboards') })
