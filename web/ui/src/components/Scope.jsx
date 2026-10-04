import { useEffect } from 'react'
import { Link, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'

import { useModels } from '../api'
import {
  PAGES, page, pagePath, whereAmI, rememberModel, lastModel,
} from '../nav'
import { PageTitle, PageSub, SkeletonCard, Empty } from './Shared'

/** The page and model the URL names. */
export function useScope() {
  const { pathname } = useLocation()
  return whereAmI(pathname) || { model: '', page: null }
}

/**
 * Top of the sidebar: which model every page below is about. Hidden with one
 * model (there is nothing to switch), and with none.
 */
export function ModelSwitcher({ model, onNavigate }) {
  const { data } = useModels()
  const { page: current } = useScope()
  const navigate = useNavigate()
  const names = (data || []).map(m => m.name).sort()
  if (names.length < 2) return null

  const go = next => {
    rememberModel(next)
    navigate(pagePath(current || 'model', next))
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

/** `/`: the model you were last in, the only model, or the list of models. */
export function Home() {
  const { data, isLoading } = useModels()
  if (isLoading) return <SkeletonCard />
  const names = (data || []).map(m => m.name)
  const last = lastModel()
  if (names.includes(last)) return <Navigate to={pagePath('model', last)} replace />
  if (names.length === 1) return <Navigate to={pagePath('model', names[0])} replace />
  return <Navigate to="/models" replace />
}

/** Old URLs keep working: they land on the page that replaced them. */
export function Legacy() {
  const { pathname, search } = useLocation()
  const { name } = useParams()
  const params = new URLSearchParams(search)
  const tab = params.get('tab')
  let to = '/'
  if (pathname.startsWith('/models/')) {
    const key = { refresh: 'refresh', explore: 'explore', reports: 'reports' }[tab] || 'model'
    to = pagePath(key, name)
  } else if (pathname === '/connectors') {
    to = '/sources'
  } else if (pathname === '/pipelines') {
    to = pagePath('refresh', params.get('model') || '')
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
