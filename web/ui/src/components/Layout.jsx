import { useState, useEffect } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'

import { useHealth, useAppStatus, useModels } from '../api'
import { PAGES, pagePath, lastModel } from '../nav'
import { ModelSwitcher, useScope } from './Scope'
import CommandPalette from './CommandPalette'
import { BrandMark } from './Art'

const ICONS = {
  connectors: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M5 4a1 1 0 00-2 0v7.268a2 2 0 000 3.464V16a1 1 0 102 0v-1.268a2 2 0 000-3.464V4zM11 4a1 1 0 10-2 0v1.268a2 2 0 000 3.464V16a1 1 0 102 0V8.732a2 2 0 000-3.464V4zM16 3a1 1 0 011 1v7.268a2 2 0 010 3.464V16a1 1 0 11-2 0v-1.268a2 2 0 010-3.464V4a1 1 0 011-1z" />
    </svg>
  ),
  models: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z" />
      <path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z" />
      <path d="M17 5c0 1.657-3.134 3-7 3S3 6.657 3 5s3.134-3 7-3 7 1.343 7 3z" />
    </svg>
  ),
  explore: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-11.707a1 1 0 00-1.111-.206l-4 1.714a1 1 0 00-.525.525l-1.714 4a1 1 0 001.317 1.317l4-1.714a1 1 0 00.525-.525l1.714-4a1 1 0 00-.206-1.111zM10 11a1 1 0 110-2 1 1 0 010 2z" clipRule="evenodd" />
    </svg>
  ),
  reports: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
    </svg>
  ),
  pipelines: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
    </svg>
  ),
  workflow: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M3 4.5A1.5 1.5 0 014.5 3h2A1.5 1.5 0 018 4.5v2A1.5 1.5 0 016.5 8h-2A1.5 1.5 0 013 6.5v-2zM12 13.5a1.5 1.5 0 011.5-1.5h2a1.5 1.5 0 011.5 1.5v2a1.5 1.5 0 01-1.5 1.5h-2a1.5 1.5 0 01-1.5-1.5v-2z" />
      <path fillRule="evenodd" d="M6 8.5a.5.5 0 01.5.5v2a2 2 0 002 2h3a.5.5 0 010 1h-3a3 3 0 01-3-3V9a.5.5 0 01.5-.5z" clipRule="evenodd" />
    </svg>
  ),
  runs: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
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

// Beneath the switcher: the same pages for every model (nav.js). Below them,
// the one page about no model: a file can come from anywhere.
const NAV_UNSCOPED = [
  { path: '/verify', label: 'Verify a file', icon: 'verify' },
]

// Help is not a place you work in, so it sits in the footer. Get started and
// the Docs it links to are one entry, marked current on either (a NavLink
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

function NavItem({ path, label, icon, onNavigate, end }) {
  return (
    <li>
      <NavLink
        to={path}
        end={end}
        onClick={onNavigate}
        className="nav-link"
        style={({ isActive }) => ({
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '8px 12px',
          margin: '0 8px',
          borderRadius: 6,
          color: isActive ? 'var(--sidebar-text-active)' : 'var(--sidebar-text)',
          textDecoration: 'none',
          fontSize: 13,
          fontWeight: isActive ? 500 : 400,
          background: isActive ? 'var(--sidebar-active)' : 'transparent',
        })}
      >
        {({ isActive }) => (
          <>
            {icon && ICONS[icon] && (
              <span style={{
                width: 15, height: 15,
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
                opacity: isActive ? 1 : 0.85,
                color: isActive ? 'var(--sidebar-accent)' : 'inherit',
              }}>
                {ICONS[icon]}
              </span>
            )}
            {label}
          </>
        )}
      </NavLink>
    </li>
  )
}

function NavSection({ label, items, onNavigate }) {
  return (
    <div style={{ marginBottom: 6 }}>
      {label && (
        <div style={{
          padding: '14px 20px 6px',
          fontSize: 10.5,
          fontWeight: 600,
          letterSpacing: '0.06em',
          textTransform: 'uppercase',
          color: 'var(--sidebar-text)',
        }}>
          {label}
        </div>
      )}
      <ul style={{ listStyle: 'none', padding: label ? '0 0 4px' : '8px 0 4px' }}>
        {items.map(item => (
          <NavItem key={item.path} {...item} onNavigate={onNavigate} end={item.end} />
        ))}
      </ul>
    </div>
  )
}

export default function Layout({ children }) {
  const [open, setOpen] = useState(false)
  const { data: health, isSuccess: healthOk } = useHealth()
  const version = healthOk && typeof health?.version === 'string' ? health.version : ''
  const { data: appStatus } = useAppStatus()
  const update = appStatus?.update?.available ? appStatus.update : null
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
  const { data: modelList } = useModels()
  const multi = (modelList || []).length > 1

  // While the mobile menu is open, the page behind it stays put.
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

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

        <div style={{ flex: 1, overflowY: 'auto', paddingTop: 4 }}>
          <NavSection onNavigate={close}
            items={PAGES.map(p => ({
              path: pagePath(p.key, model), label: p.label, icon: p.icon, end: p.key === 'model',
            }))} />
          <div style={{ borderTop: '1px solid var(--sidebar-border)', margin: '0 16px' }} />
          <NavSection items={NAV_UNSCOPED} onNavigate={close} />
        </div>

        <div style={{
          padding: '12px 16px 14px',
          borderTop: '1px solid var(--sidebar-border)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              display: 'inline-block', width: 6, height: 6,
              borderRadius: '50%', background: 'var(--green)', flexShrink: 0,
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
        @media (max-width: 768px) {
          .mobile-header { display: flex !important; }
          .app-nav { transform: translateX(-100%); transition: transform .25s ease; }
          .app-nav.nav-open { transform: translateX(0); }
          main { margin-left: 0 !important; margin-top: 52px; padding: 20px 16px !important; max-width: 100% !important; }
        }
      `}</style>
    </div>
  )
}
