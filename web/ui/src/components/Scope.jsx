import { createContext, useContext, useEffect, useMemo } from 'react'
import { Link, Navigate, useLocation, useParams } from 'react-router-dom'

import { useModels, useReports, useRole } from '../api'
import { page, whereAmI, rememberModel, reportModels, openedReport, movedTo } from '../nav'
import { PageTitle, PageSub, SkeletonCard, Empty, BtnLink } from './Shared'

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

/** An older address: it lands where that page lives now, its #section kept. */
export function Moved() {
  const { pathname, search, hash } = useLocation()
  const to = movedTo(pathname, search)
  return to ? <Navigate to={to + hash} replace /> : <NotFound />
}

// What each role can do, in the words of the places it sees (nav.js placesFor).
const CAN = {
  viewer: 'You can read reports, ask a model questions and read the docs.',
  analyst: 'You can read and build reports, ask questions, look at the data, and work in Review: drafts, history and checks.',
}

/**
 * An address above the person's role (a viewer at /data): a plain page in the
 * app's frame. The API refuses the work anyway; this says so in words, and
 * says what this person can do instead.
 */
export function NotForYou({ role }) {
  const mine = useRole()
  return (
    <>
      <PageTitle>This part of the app is for {role === 'admin' ? 'admins' : 'analysts'}.</PageTitle>
      <PageSub>{CAN[mine] || CAN.viewer}</PageSub>
      <BtnLink to="/" variant="primary">Go to the reports</BtnLink>
    </>
  )
}

export function NotFound() {
  return (
    <>
      <PageTitle>Page not found</PageTitle>
      <PageSub>There is nothing at this address. It may be an old link.</PageSub>
      <Empty message="Start from the reports, or search with ⌘K."
             action={<BtnLink to="/" variant="primary">Go to the reports</BtnLink>} />
    </>
  )
}
