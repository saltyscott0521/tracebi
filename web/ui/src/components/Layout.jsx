import { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { useHealth, useAppStatus, useModels, useMe, signOut } from '../api'
import { pagePath, lastModel } from '../nav'
import { ModelSwitcher, useScope, useOpenReport } from './Scope'
import CommandPalette from './CommandPalette'
import { BrandMark } from './Art'

const ICONS = {
  overview: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="4" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="20" cy="12" r="2" /><path d="M6 12h4M14 12h4" />
    </svg>
  ),
  map: (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5" cy="6" r="2.5" /><circle cx="19" cy="6" r="2.5" /><circle cx="12" cy="18" r="2.5" /><path d="M7.5 6h9M6.5 8l4 8M17.5 8l-4 8" />
    </svg>
  ),
  explore: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-11.707a1 1 0 00-1.111-.206l-4 1.714a1 1 0 00-.525.525l-1.714 4a1 1 0 001.317 1.317l4-1.714a1 1 0 00.525-.525l1.714-4a1 1 0 00-.206-1.111zM10 11a1 1 0 110-2 1 1 0 010 2z" clipRule="evenodd" />
    </svg>
  ),
  workflow: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M3 4.5A1.5 1.5 0 014.5 3h2A1.5 1.5 0 018 4.5v2A1.5 1.5 0 016.5 8h-2A1.5 1.5 0 013 6.5v-2zM12 13.5a1.5 1.5 0 011.5-1.5h2a1.5 1.5 0 011.5 1.5v2a1.5 1.5 0 01-1.5 1.5h-2a1.5 1.5 0 01-1.5-1.5v-2z" />
      <path fillRule="evenodd" d="M6 8.5a.5.5 0 01.5.5v2a2 2 0 002 2h3a.5.5 0 010 1h-3a3 3 0 01-3-3V9a.5.5 0 01.5-.5z" clipRule="evenodd" />
    </svg>
  ),
  drafts: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
    </svg>
  ),
  verify: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
    </svg>
  ),
  docs: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
    </svg>
  ),
}

// Help is not a place you work in, so it sits in the footer. Get started and
// the Docs it links to are one entry, marked current on either (a plain link
// would only mark its own path).
const HELP_PATHS = ['/getting-started', '/handbook']

/**
 * The model the sidebar's links are about: the one in the URL; on a page
 * outside the frame, the only model or the one you were last in.
 */
function useSidebarModel() {
  const { model, page } = useScope()
  const { data } = useModels()
  const names = (data || []).map(m => m.name)
  if (page) return model
  if (names.length === 1) return names[0]
  return names.includes(lastModel()) ? lastModel() : ''
}

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
      <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
    </svg>
  )
}

function NavItem({ path, label, icon, active, onNavigate }) {
  return (
    <li>
      <Link
        to={path}
        onClick={onNavigate}
        aria-current={active ? 'page' : undefined}
        className="nav-link"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '8px 12px',
          margin: '0 8px',
          borderRadius: 6,
          color: active ? 'var(--sidebar-text-active)' : 'var(--sidebar-text)',
          textDecoration: 'none',
          fontSize: 13,
          fontWeight: active ? 500 : 400,
          background: active ? 'var(--sidebar-active)' : 'transparent',
        }}
      >
        <span style={{
          width: 15, height: 15,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          opacity: active ? 1 : 0.85,
          color: active ? 'var(--sidebar-accent)' : 'inherit',
        }}>
          {ICONS[icon]}
        </span>
        {label}
      </Link>
    </li>
  )
}

export default function Layout({ children }) {
  const [open, setOpen] = useState(false)
  const { data: health, isSuccess: healthOk } = useHealth()
  const version = healthOk && typeof health?.version === 'string' ? health.version : ''
  const { data: appStatus } = useAppStatus()
  const update = appStatus?.update?.available ? appStatus.update : null
  const { data: me } = useMe()
  const person = me?.sign_in === 'oidc' && me.actor ? me : null
  // Follow the OS until the viewer picks one; their pick is remembered, the OS
  // default is not (so it keeps following the OS).
  const [dark, setDark] = useState(() => {
    try {
      const saved = localStorage.getItem('tracebi-theme')
      if (saved) return saved === 'dark'
    } catch { /* private window */ }
    return !!window.matchMedia?.('(prefers-color-scheme: dark)').matches
  })
  const [chose, setChose] = useState(() => {
    try { return !!localStorage.getItem('tracebi-theme') } catch { return false }
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    if (chose) { try { localStorage.setItem('tracebi-theme', dark ? 'dark' : 'light') } catch { /* ignore */ } }
  }, [dark, chose])

  const close = () => setOpen(false)
  const { pathname } = useLocation()
  const inHelp = HELP_PATHS.some(p => pathname.startsWith(p))
  const model = useSidebarModel()
  const scope = useScope()
  const openReport = useOpenReport()
  const { data: modelList } = useModels()
  const multi = (modelList || []).length > 1

  // While the mobile menu is open, the page behind it stays put.
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  // An open report is a page of its own, with a light bar of its own: no sidebar.
  if (openReport) return children

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <CommandPalette />

      {/* Mobile top bar */}
      <header className="mobile-header" style={{
        display: 'none', position: 'fixed', top: 0, left: 0, right: 0,
        height: 52,
        background: 'var(--header-bg)',
        borderBottom: '1px solid var(--border)',
        alignItems: 'center', justifyContent: 'space-between', padding: '0 16px',
        zIndex: 200,
      }}>
        {/* On a phone the switcher is in the drawer, so the header says which
            model every page is about. */}
        <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text)', letterSpacing: '-0.02em', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          TraceBi
          {multi && (
            <button type="button" className="mobile-header__model" onClick={() => setOpen(true)}>
              {model || 'All models'}
            </button>
          )}
        </span>
        <button onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          display: 'flex', flexDirection: 'column', gap: 5,
          padding: 0, width: 44, height: 44,
          alignItems: 'center', justifyContent: 'center',
        }}>
          {[0,1,2].map(i => (
            <span key={i} style={{ display: 'block', width: 20, height: 2, background: 'var(--text-2)', borderRadius: 1 }} />
          ))}
        </button>
      </header>

      {/* Overlay */}
      {open && (
        <div onClick={close} style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,.4)',
          zIndex: 250,
        }} />
      )}

      {/* Sidebar */}
      {/* Pinned top AND bottom, not min-height: 100vh — on a phone, 100vh is
          not the visible screen (browser bars, zoom), and the drawer stopped
          short. It scrolls itself if the links outgrow a short screen. */}
      <nav aria-label="Main" style={{
        width: 'var(--nav-w)',
        background: 'var(--sidebar-bg)',
        borderRight: '1px solid var(--sidebar-border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        position: 'fixed', top: 0, bottom: 0, left: 0, zIndex: 300,
        overflowY: 'auto', overscrollBehavior: 'contain',
      }} className={`app-nav${open ? ' nav-open' : ''}`}>

        <button
          className="nav-close-btn"
          onClick={close}
          style={{
            display: 'none',
            position: 'absolute', top: 10, right: 10,
            background: 'var(--sidebar-field)',
            border: '1px solid var(--sidebar-field-border)',
            borderRadius: 6, width: 32, height: 32,
            alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
            color: 'var(--sidebar-text)', fontSize: 17, lineHeight: 1,
            zIndex: 1,
          }}
          aria-label="Close menu"
        >×</button>

        {/* Brand */}
        <div style={{ padding: '22px 20px 16px', borderBottom: '1px solid var(--sidebar-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <BrandMark />
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--sidebar-text-active)', letterSpacing: '-0.02em', lineHeight: 1.2 }}>
                TraceBi
              </div>
              <div style={{ fontSize: 11, color: 'var(--sidebar-text)', marginTop: 1 }}>
                Analytics trust layer
              </div>
            </div>
          </div>
          <button
            onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
            style={{
              width: '100%',
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--sidebar-field)', border: '1px solid var(--sidebar-field-border)',
              borderRadius: 6, padding: '7px 10px', cursor: 'pointer',
              color: 'var(--sidebar-text)', fontSize: 12, fontFamily: 'inherit',
              transition: 'background .15s',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
            </svg>
            Search…
            <kbd style={{
              marginLeft: 'auto', fontSize: 10, padding: '1px 5px',
              background: 'var(--sidebar-field)', border: '1px solid var(--sidebar-field-border)',
              borderRadius: 3, color: 'var(--sidebar-text)',
            }}>⌘K</kbd>
          </button>
          <ModelSwitcher model={model} onNavigate={close} />
        </div>

        {/* Overview and Explore are about the picked model (all models: the
            Overview lists them); the Map is every model, the picked one's band
            tinted; Drafts and Verify a file are about no one model: a file can
            come from anywhere. */}
        <ul style={{ flex: 1, overflowY: 'auto', listStyle: 'none', padding: '12px 0 4px' }}>
          {[
            { path: pagePath('overview', model), label: 'Overview', icon: 'overview', active: scope.page === 'overview' },
            { path: '/map', label: 'Map', icon: 'map', active: pathname.startsWith('/map') },
            { path: pagePath('explore', model), label: 'Explore', icon: 'explore', active: scope.page === 'explore' },
            { path: '/drafts', label: 'Drafts', icon: 'drafts', active: pathname.startsWith('/drafts') },
            { path: '/verify', label: 'Verify a file', icon: 'verify', active: pathname.startsWith('/verify') },
          ].map(item => <NavItem key={item.path} {...item} onNavigate={close} />)}
        </ul>

        <div style={{
          padding: '12px 16px 14px',
          borderTop: '1px solid var(--sidebar-border)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              display: 'inline-block', width: 6, height: 6,
              borderRadius: '50%', background: 'var(--muted)', flexShrink: 0,
            }} />
            <Link to="/getting-started" onClick={close}
              aria-current={inHelp ? 'page' : undefined}
              className="nav-link"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                fontSize: 12, textDecoration: 'none', borderRadius: 5, padding: '3px 6px',
                color: inHelp ? 'var(--sidebar-text-active)' : 'var(--sidebar-text)',
                background: inHelp ? 'var(--sidebar-active)' : 'transparent',
              }}>
              {ICONS.docs}Help
            </Link>
            {version ? (
              <span style={{ fontSize: 11, color: 'var(--sidebar-text)' }}>v{version}</span>
            ) : null}
            {update && (
              <a href={update.url || '#'} target="_blank" rel="noreferrer"
                 title={`TraceBi ${update.latest} is available. To update this ${update.kind} install:\n${update.command}\n\n(or run: tracebi update)`}
                 style={{
                   fontSize: 10.5, fontWeight: 600, color: 'var(--sidebar-accent)', textDecoration: 'none',
                   border: '1px solid var(--sidebar-field-border)', borderRadius: 999,
                   padding: '1px 7px', whiteSpace: 'nowrap',
                 }}>
                v{update.latest} available
              </a>
            )}
            <button
              onClick={() => { setChose(true); setDark(d => !d) }}
              title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              style={{
                marginLeft: 'auto', background: 'var(--sidebar-field)',
                border: '1px solid var(--sidebar-field-border)', borderRadius: 5,
                color: 'var(--sidebar-text)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 26, height: 26, flexShrink: 0, transition: 'background .15s',
              }}
            >
              {dark ? <SunIcon /> : <MoonIcon />}
            </button>
          </div>
          {person && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, fontSize: 11.5, color: 'var(--sidebar-text)' }}>
              <span title={`${person.actor} (${person.role})`}
                    style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {person.actor}
              </span>
              <button onClick={signOut} style={{
                marginLeft: 'auto', flexShrink: 0, background: 'none', cursor: 'pointer',
                border: '1px solid var(--sidebar-field-border)', borderRadius: 5,
                color: 'var(--sidebar-text)', fontSize: 11, padding: '2px 8px', fontFamily: 'inherit',
              }}>Sign out</button>
            </div>
          )}
        </div>
      </nav>

      {/* Main content */}
      <main style={{
        marginLeft: 'var(--nav-w)', flex: 1, minWidth: 0,
        padding: '36px 44px', maxWidth: 1340,
      }} className="layout-main">
        {children}
      </main>

      <style>{`
        @media (max-width: 860px) {
          .mobile-header { display: flex !important; }
          .nav-close-btn { display: flex !important; }
          .app-nav { transform: translateX(-100%); transition: transform .25s ease; }
          .app-nav.nav-open { transform: translateX(0); }
          main { margin-left: 0 !important; margin-top: 52px; padding: 20px 16px !important; max-width: 100% !important; }
        }
      `}</style>
    </div>
  )
}
