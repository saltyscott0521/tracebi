import { useEffect, useMemo } from 'react'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'

import { useModels, useReports } from '../api'
import {
  PAGES, page, pagePath, whereAmI, rememberModel, lastModel, reportModels,
} from '../nav'
import { PageTitle, PageSub, SkeletonCard, Empty } from './Shared'

/** The page, model and (on the Overview) stage the URL names. */
export function useScope() {
  const { pathname } = useLocation()
  return whereAmI(pathname) || { model: '', page: null, stage: null }
}

/**
 * Top of the sidebar: which model every page below is about. Hidden with one
 * model (there is nothing to switch), and with none.
 */
export function ModelSwitcher({ model, onNavigate }) {
  const { data } = useModels()
  const { page: current, stage } = useScope()
  const navigate = useNavigate()
  const names = (data || []).map(m => m.name).sort()
  if (names.length < 2) return null

  // Switching keeps you on the same page, and the same stage of the Overview.
  const go = next => {
    rememberModel(next)
    navigate(pagePath(stage || current || 'overview', next))
    onNavigate?.()
  }
  return (
    <label className="model-switcher">
      <span className="model-switcher__label">Model</span>
      <select value={model} onChange={e => go(e.target.value)} aria-label="Model">
        <option value="">All models</option>
        {names.map(n => <option key={n} value={n}>{n}</option>)}
      </select>
    </label>
  )
}

/** report name → the models it reads, from the (cached) report list. */
export function useReportModels() {
  const { data } = useReports()
  return useMemo(() => {
    const index = new Map((data || []).map(r => [r.name, reportModels(r)]))
    return name => index.get(name) || []
  }, [data])
}

/** Every page's heading: the model it is about, the page, what it is for. */
export function PageHeader({ pageKey, model, sub, children }) {
  const p = page(pageKey)
  return (
    <header className="page-header">
      <div className="page-header__scope">{model || 'All models'}</div>
      <PageTitle>{p.label}</PageTitle>
      <PageSub>{sub ?? p.sub}</PageSub>
      {children}
    </header>
  )
}

/**
 * An all-models page. With exactly one model there is no "all", so it opens
 * that model's page instead, keeping the query (a deep link to a report).
 */
export function AllModels({ pageKey, children }) {
  const { data, isLoading } = useModels()
  const { search } = useLocation()
  if (isLoading) return <SkeletonCard />
  if ((data || []).length === 1) {
    return <Navigate to={pagePath(pageKey, data[0].name) + search} replace />
  }
  return children
}

/** A /m/<model>/… page: the model must exist; it becomes the remembered one. */
export function OneModel({ children }) {
  const { model } = useParams()
  const { data, isLoading } = useModels()
  const known = (data || []).some(m => m.name === model)
  useEffect(() => { if (known) rememberModel(model) }, [known, model])
  if (isLoading) return <SkeletonCard />
  if (!known) {
    return (
      <>
        <PageTitle>No model named “{model}”</PageTitle>
        <PageSub>It may have been renamed or removed.</PageSub>
        <Link to="/models">See all models →</Link>
      </>
    )
  }
  return children(model)
}

/** `/`: the Overview of the model you were last in, or of the only model; else the models. */
export function Home() {
  const { data, isLoading } = useModels()
  if (isLoading) return <SkeletonCard />
  const names = (data || []).map(m => m.name)
  const last = lastModel()
  if (names.includes(last)) return <Navigate to={pagePath('overview', last)} replace />
  if (names.length === 1) return <Navigate to={pagePath('overview', names[0])} replace />
  return <Navigate to="/models" replace />
}

/** A /m/<model>/<page> address that moved: it opens *stage* of the same model. */
export function ToStage({ stage }) {
  const { model } = useParams()
  return <Navigate to={pagePath(stage, model)} replace />
}

/** Old URLs keep working: they land on the page that replaced them. */
export function Legacy() {
  const { pathname, search } = useLocation()
  const { name } = useParams()
  const params = new URLSearchParams(search)
  const tab = params.get('tab')
  let to = '/'
  if (pathname.startsWith('/models/')) {
    const key = { refresh: 'transform', explore: 'explore', reports: 'reports' }[tab] || 'overview'
    to = pagePath(key, name)
  } else if (pathname === '/connectors') {
    to = '/sources'
  } else if (pathname === '/pipelines') {
    to = pagePath('transform', params.get('model') || '')
  }
  return <Navigate to={to} replace />
}

export function NotFound() {
  return (
    <>
      <PageTitle>Page not found</PageTitle>
      <PageSub>There is nothing at this address. It may be an old link.</PageSub>
      <Empty message="Start from the models, or search with ⌘K."
             action={<Link to="/" className="btn">Go to the start</Link>} />
    </>
  )
}

export { PAGES }
