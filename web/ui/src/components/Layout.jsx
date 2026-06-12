import { useState, useEffect } from 'react'
import { NavLink } from 'react-router-dom'

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
  requests: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" />
    </svg>
  ),
  pipelines: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
    </svg>
  ),
  dashboards: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
    </svg>
  ),
  guide: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
    </svg>
  ),
}

const NAV = [
  { path: '/',                 label: 'Home',          icon: 'home',       color: '#93c5fd' },
  { path: '/getting-started',  label: 'Get Started',   icon: 'guide',      color: '#86efac' },
  { path: '/connectors',       label: 'Connectors',    icon: 'connectors', color: '#6ee7b7' },
  { path: '/models',     label: 'Models',     icon: 'models',     color: '#93c5fd' },
  { path: '/explore',    label: 'Explore',    icon: 'explore',    color: '#7dd3fc' },
  { path: '/reports',    label: 'Reports',    icon: 'reports',    color: '#f9a8d4' },
  { path: '/requests',   label: 'Requests',   icon: 'requests',   color: '#c4b5fd' },
  { path: '/pipelines',  label: 'Pipelines',  icon: 'pipelines',  color: '#fde68a' },
  { path: '/dashboards', label: 'Dashboards', icon: 'dashboards', color: '#a5f3fc' },
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

export default function Layout({ children }) {
  const [open, setOpen] = useState(false)
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('tracebi-theme') === 'dark' } catch { return false }
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    try { localStorage.setItem('tracebi-theme', dark ? 'dark' : 'light') } catch { /* ignore */ }
  }, [dark])

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <CommandPalette />

      {/* Background orbs */}
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />

      {/* Mobile top bar */}
      <div className="mobile-header" style={{
        display: 'none', position: 'fixed', top: 0, left: 0, right: 0,
        height: 52,
        background: 'rgba(240,243,248,0.95)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border)',
        alignItems: 'center', justifyContent: 'space-between', padding: '0 16px',
        zIndex: 200,
      }}>
        <span className="gradient-text" style={{ fontSize: 16, fontWeight: 800 }}>TraceBi</span>
        <button onClick={() => setOpen(true)} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          display: 'flex', flexDirection: 'column', gap: 5,
          padding: 0, width: 44, height: 44,
          alignItems: 'center', justifyContent: 'center',
        }}>
          {[0,1,2].map(i => (
            <span key={i} style={{ display: 'block', width: 20, height: 2, background: 'var(--text-2)', borderRadius: 2 }} />
          ))}
        </button>
      </div>

      {/* Overlay */}
      {open && (
        <div onClick={() => setOpen(false)} style={{
          position: 'fixed', inset: 0,
          background: 'rgba(22,35,60,.4)',
          backdropFilter: 'blur(4px)',
          zIndex: 250,
        }} />
      )}

      {/* Sidebar */}
      <nav style={{
        width: 'var(--nav-w)', minHeight: '100vh',
        background: 'var(--sidebar-bg)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderRight: '1px solid var(--sidebar-border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        position: 'fixed', top: 0, left: 0, zIndex: 300,
      }} className={open ? 'nav-open' : ''}>

        {/* Close button — mobile only, positioned top-right of sidebar */}
        <button
          className="nav-close-btn"
          onClick={() => setOpen(false)}
          style={{
            display: 'none',
            position: 'absolute', top: 10, right: 10,
            background: 'rgba(255,255,255,0.1)',
            border: '1px solid rgba(255,255,255,0.18)',
            borderRadius: 6, width: 32, height: 32,
            alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
            color: 'rgba(200,220,255,0.85)', fontSize: 17, lineHeight: 1,
            zIndex: 1,
          }}
        >×</button>

        {/* Brand */}
        <div style={{ padding: '24px 20px 20px', borderBottom: '1px solid var(--sidebar-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginBottom: 5 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 9,
              background: 'linear-gradient(135deg, #091a55, #0369a1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 16px rgba(9,26,85,0.45)',
              flexShrink: 0,
            }}>
              <svg width="15" height="15" viewBox="0 0 20 20" fill="white">
                <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" />
              </svg>
            </div>
            <h1 className="gradient-text" style={{ fontSize: 18, fontWeight: 800, letterSpacing: .2 }}>
              TraceBi
            </h1>
          </div>
          <p style={{ fontSize: 11, color: 'var(--muted)', paddingLeft: 43, letterSpacing: .2 }}>
            Code-first traceable BI
          </p>
          <button
            onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))}
            style={{
              marginTop: 14, width: '100%',
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 8, padding: '7px 10px', cursor: 'pointer',
              color: 'rgba(200,220,255,0.55)', fontSize: 12, fontFamily: 'inherit',
              transition: 'background .15s',
            }}
          >
            <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
            </svg>
            Search…
            <kbd style={{
              marginLeft: 'auto', fontSize: 10, padding: '1px 5px',
              background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.14)',
              borderRadius: 4, color: 'rgba(200,220,255,0.6)',
            }}>⌘K</kbd>
          </button>
        </div>

        {/* Nav items */}
        <ul style={{ listStyle: 'none', padding: '10px 0', flex: 1 }}>
          {NAV.map(({ path, label, icon, color }) => (
            <li key={path}>
              <NavLink
                to={path}
                end={path === '/'}
                onClick={() => setOpen(false)}
                className="nav-link"
                style={({ isActive }) => ({
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '9px 20px',
                  color: isActive ? 'var(--sidebar-text-active)' : 'var(--sidebar-text)',
                  textDecoration: 'none',
                  fontSize: 13,
                  fontWeight: isActive ? 600 : 400,
                  borderLeft: `2px solid ${isActive ? color : 'transparent'}`,
                  background: isActive ? 'rgba(255,255,255,0.13)' : 'transparent',
                })}
              >
                <span style={{
                  width: 15, height: 15,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                  color: 'inherit',
                }}>
                  {ICONS[icon]}
                </span>
                {label}
              </NavLink>
            </li>
          ))}
        </ul>

        {/* Footer */}
        <div style={{
          padding: '14px 20px',
          borderTop: '1px solid var(--sidebar-border)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span className="pulse-glow" style={{
            display: 'inline-block', width: 7, height: 7,
            borderRadius: '50%', background: '#22c55e', flexShrink: 0,
          }} />
          <span style={{ fontSize: 11, color: 'var(--sidebar-text)' }}>TraceBi v0.5.2</span>
          <span style={{
            fontSize: 10, color: 'rgba(200,220,255,0.8)',
            background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.15)',
            padding: '1px 6px', borderRadius: 4,
          }}>BETA</span>
          <button
            onClick={() => setDark(d => !d)}
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            style={{
              marginLeft: 'auto', background: 'rgba(255,255,255,0.09)',
              border: '1px solid rgba(255,255,255,0.14)', borderRadius: 6,
              color: 'rgba(200,220,255,0.75)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              width: 26, height: 26, flexShrink: 0, transition: 'background .15s',
            }}
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main style={{
        marginLeft: 'var(--nav-w)', flex: 1,
        padding: '40px 44px', maxWidth: 1340,
      }} className="layout-main">
        {children}
      </main>

      <style>{`
        @media (max-width: 768px) {
          .mobile-header { display: flex !important; }
          nav { transform: translateX(-100%); transition: transform .25s ease; }
          nav.nav-open { transform: translateX(0); }
          main { margin-left: 0 !important; margin-top: 52px; padding: 20px 16px !important; max-width: 100% !important; }
        }
      `}</style>
    </div>
  )
}
