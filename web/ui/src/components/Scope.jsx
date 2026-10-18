import { createContext, useContext, useEffect, useMemo } from 'react'
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'

import { useModels, useReports } from '../api'
import { PAGES, page, whereAmI, rememberModel, reportModels, openedReport, movedTo } from '../nav'
import { PageTitle, PageSub, SkeletonCard, Empty } from './Shared'

/** The place, and on Data the model and tab, the URL names. */
export function useScope() {
  const { pathname } = useLocation()
  return whereAmI(pathname) || { model: '', page: null, tab: null }
}

/**
 * The full menu, for a page that shows only the rail (a report) or, on a phone,
 * nothing: `{open}` there, null where the sidebar is always on screen.
 */
export const NavMenuContext = createContext(null)
export const useNavMenu = () => useContext(NavMenuContext)

/** The report this address opens as a page of its own ({name}), or null. */
export function useOpenReport() {
  const { pathname } = useLocation()
  return openedReport(pathname)
}

/** report name → the models it reads, from the (cached) report list. */
export function useReportModels() {
  const { data } = useReports()
  return useMemo(() => {
    const index = new Map((data || []).map(r => [r.name, reportModels(r)]))
    return name => index.get(name) || []
  }, [data])
}

/** model name → what people read it as (its `label`), from the model list. */
export function useModelLabel() {
  const { data } = useModels()
  return useMemo(() => {
    const index = new Map((data || []).map(m => [m.name, m.label || m.name]))
    return name => index.get(name) || name
  }, [data])
}

/** Every page's heading: the model it is about, the page, what it is for. */
export function PageHeader({ pageKey, model, sub, children }) {
  const p = page(pageKey)
  const labelOf = useModelLabel()
  return (
    <header className="page-header">
      {model !== undefined && <div className="page-header__scope">{model ? labelOf(model) : 'All models'}</div>}
      <PageTitle>{p.label}</PageTitle>
      <PageSub>{sub ?? p.sub}</PageSub>
      {children}
    </header>
  )
}

/** A /data/<model>/… page: the model must exist; it becomes the remembered one. */
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
        <Link to="/data">See all models →</Link>
      </>
    )
  }
  return children(model)
}

/** An address from before the four places: it lands where that page lives now. */
export function Moved() {
  const { pathname, search } = useLocation()
  const to = movedTo(pathname, search)
  return to ? <Navigate to={to} replace /> : <NotFound />
}

export function NotFound() {
  return (
    <>
      <PageTitle>Page not found</PageTitle>
      <PageSub>There is nothing at this address. It may be an old link.</PageSub>
      <Empty message="Start from the reports, or search with ⌘K."
             action={<Link to="/" className="btn">Go to the reports</Link>} />
    </>
  )
}

export { PAGES }
