import { useState, useEffect } from 'react'
import { NavLink, Link } from 'react-router-dom'

import CommandPalette from './CommandPalette'

const ICONS = {
  home: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" />
    </svg>
  ),
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
  guide: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
    </svg>
  ),
  workflow: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M3 4.5A1.5 1.5 0 014.5 3h2A1.5 1.5 0 018 4.5v2A1.5 1.5 0 016.5 8h-2A1.5 1.5 0 013 6.5v-2zM12 13.5a1.5 1.5 0 011.5-1.5h2a1.5 1.5 0 011.5 1.5v2a1.5 1.5 0 01-1.5 1.5h-2a1.5 1.5 0 01-1.5-1.5v-2z" />
      <path fillRule="evenodd" d="M6 8.5a.5.5 0 01.5.5v2a2 2 0 002 2h3a.5.5 0 010 1h-3a3 3 0 01-3-3V9a.5.5 0 01.5-.5z" clipRule="evenodd" />
    </svg>
  ),
  docs: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
    </svg>
  ),
}

// Workspace first; learn/docs below. Verify is intentionally not a primary
// nav peer — it lives as a quiet footer action so the chrome reads as product
// surfaces, not a trust marketing strip.
const NAV_PRIMARY = [
  { path: '/',          label: 'Home',       icon: 'home' },
  { path: '/connectors', label: 'Connectors', icon: 'connectors' },
  { path: '/models',    label: 'Models',     icon: 'models' },
  { path: '/explore',   label: 'Explore',    icon: 'explore' },
  { path: '/reports',   label: 'Reports',    icon: 'reports' },
  { path: '/pipelines', label: 'Pipelines',  icon: 'pipelines' },
]

const NAV_SECONDARY = [
  { path: '/workflow',        label: 'Workflow',    icon: 'workflow' },
  { path: '/getting-started', label: 'Get Started', icon: 'guide' },
  { path: '/handbook',        label: 'Docs',        icon: 'docs' },
]

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

function NavItem({ path, label, icon, onNavigate }) {
  return (
    <li>
      <NavLink
        to={path}
        end={path === '/'}
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
          fontWeight: isActive ? 600 : 400,
          background: isActive ? 'rgba(255,255,255,0.1)' : 'transparent',
        })}
      >
        <span style={{
          width: 15, height: 15,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          opacity: 0.9,
        }}>
          {ICONS[icon]}
        </span>
        {label}
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
          color: 'rgba(200,220,255,0.38)',
        }}>
          {label}
        </div>
      )}
      <ul style={{ listStyle: 'none', padding: label ? '0 0 4px' : '8px 0 4px' }}>
        {items.map(item => (
          <NavItem key={item.path} {...item} onNavigate={onNavigate} />
        ))}
      </ul>
    </div>
  )
}

export default function Layout({ children }) {
  const [open, setOpen] = useState(false)
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('tracebi-theme') === 'dark' } catch { return false }
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    try { localStorage.setItem('tracebi-theme', dark ? 'dark' : 'light') } catch { /* ignore */ }
  }, [dark])

  const close = () => setOpen(false)

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <CommandPalette />

      {/* Mobile top bar */}
      <div className="mobile-header" style={{
        display: 'none', position: 'fixed', top: 0, left: 0, right: 0,
        height: 52,
        background: 'var(--header-bg)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border)',
        alignItems: 'center', justifyContent: 'space-between', padding: '0 16px',
        zIndex: 200,
      }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>
          TraceBi
        </span>
        <button onClick={() => setOpen(true)} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          display: 'flex', flexDirection: 'column', gap: 5,
          padding: 0, width: 44, height: 44,
          alignItems: 'center', justifyContent: 'center',
        }}>
          {[0,1,2].map(i => (
            <span key={i} style={{ display: 'block', width: 20, height: 2, background: 'var(--text-2)', borderRadius: 1 }} />
          ))}
        </button>
      </div>

      {/* Overlay */}
      {open && (
        <div onClick={close} style={{
          position: 'fixed', inset: 0,
          background: 'rgba(10,18,40,.45)',
          backdropFilter: 'blur(2px)',
          zIndex: 250,
        }} />
      )}

      {/* Sidebar */}
      <nav style={{
        width: 'var(--nav-w)', minHeight: '100vh',
        background: 'var(--sidebar-bg)',
        borderRight: '1px solid var(--sidebar-border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        position: 'fixed', top: 0, left: 0, zIndex: 300,
      }} className={`app-nav${open ? ' nav-open' : ''}`}>

        <button
          className="nav-close-btn"
          onClick={close}
          style={{
            display: 'none',
            position: 'absolute', top: 10, right: 10,
            background: 'rgba(255,255,255,0.08)',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 6, width: 32, height: 32,
            alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
            color: 'rgba(200,220,255,0.85)', fontSize: 17, lineHeight: 1,
            zIndex: 1,
          }}
        >×</button>

        {/* Brand */}
        <div style={{ padding: '22px 20px 16px', borderBottom: '1px solid var(--sidebar-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <div style={{
              width: 28, height: 28, borderRadius: 6,
              background: '#091a55',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
                <path d="M6.6 4.5 H4.6 V15.5 H6.6 M13.4 4.5 H15.4 V15.5 H13.4" stroke="white" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                <rect x="8.1" y="9.6" width="1.7" height="4.4" rx=".4" fill="white" />
                <rect x="11" y="7.2" width="1.7" height="6.8" rx=".4" fill="white" />
              </svg>
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#fff', letterSpacing: '-0.02em', lineHeight: 1.2 }}>
                TraceBi
              </div>
              <div style={{ fontSize: 11, color: 'rgba(200,220,255,0.45)', marginTop: 1 }}>
                Analytics trust layer
              </div>
            </div>
          </div>
          <button
            onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
            style={{
              width: '100%',
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 6, padding: '7px 10px', cursor: 'pointer',
              color: 'rgba(200,220,255,0.5)', fontSize: 12, fontFamily: 'inherit',
              transition: 'background .15s',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
            </svg>
            Search…
            <kbd style={{
              marginLeft: 'auto', fontSize: 10, padding: '1px 5px',
              background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 3, color: 'rgba(200,220,255,0.5)',
            }}>⌘K</kbd>
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', paddingTop: 4 }}>
          <NavSection items={NAV_PRIMARY} onNavigate={close} />
          <NavSection label="Learn" items={NAV_SECONDARY} onNavigate={close} />
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 16px 14px',
          borderTop: '1px solid var(--sidebar-border)',
          display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <Link
            to="/verify"
            onClick={close}
            style={{
              fontSize: 12,
              color: 'rgba(200,220,255,0.48)',
              textDecoration: 'none',
              padding: '2px 4px',
            }}
            className="nav-footer-link"
          >
            Verify a report file
          </Link>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              display: 'inline-block', width: 6, height: 6,
              borderRadius: '50%', background: '#22c55e', flexShrink: 0,
            }} />
            <span style={{ fontSize: 11, color: 'var(--sidebar-text)' }}>v0.5.2</span>
            <button
              onClick={() => setDark(d => !d)}
              title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              style={{
                marginLeft: 'auto', background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.1)', borderRadius: 5,
                color: 'rgba(200,220,255,0.7)', cursor: 'pointer',
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
        .nav-footer-link:hover { color: rgba(200,220,255,0.85) !important; }
      `}</style>
    </div>
  )
}
