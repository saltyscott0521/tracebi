import { useState } from 'react'
import { NavLink } from 'react-router-dom'

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
  dashboards: (
    <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
      <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
    </svg>
  ),
}

const NAV = [
  { path: '/',           label: 'Home',       icon: 'home',       color: '#2563eb' },
  { path: '/connectors', label: 'Connectors', icon: 'connectors', color: '#059669' },
  { path: '/models',     label: 'Models',     icon: 'models',     color: '#7c3aed' },
  { path: '/explore',    label: 'Explore',    icon: 'explore',    color: '#0284c7' },
  { path: '/reports',    label: 'Reports',    icon: 'reports',    color: '#db2777' },
  { path: '/pipelines',  label: 'Pipelines',  icon: 'pipelines',  color: '#d97706' },
  { path: '/dashboards', label: 'Dashboards', icon: 'dashboards', color: '#0891b2' },
]

export default function Layout({ children }) {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Background orbs */}
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />

      {/* Mobile top bar */}
      <div className="mobile-header" style={{
        display: 'none', position: 'fixed', top: 0, left: 0, right: 0,
        height: 52,
        background: 'rgba(255,255,255,0.92)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
        borderBottom: '1px solid var(--border)',
        alignItems: 'center', justifyContent: 'space-between', padding: '0 16px',
        zIndex: 200,
      }}>
        <span className="gradient-text" style={{ fontSize: 16, fontWeight: 800 }}>TraceBi</span>
        <button onClick={() => setOpen(true)} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          display: 'flex', flexDirection: 'column', gap: 5, padding: 4,
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
        background: 'var(--surface)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        position: 'fixed', top: 0, left: 0, zIndex: 300,
      }} className={open ? 'nav-open' : ''}>

        {/* Brand */}
        <div style={{ padding: '24px 20px 20px', borderBottom: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11, marginBottom: 5 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 9,
              background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 16px rgba(124,58,237,0.35)',
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
                  color: isActive ? 'var(--text)' : 'var(--muted)',
                  textDecoration: 'none',
                  fontSize: 13,
                  fontWeight: isActive ? 600 : 400,
                  borderLeft: `2px solid ${isActive ? color : 'transparent'}`,
                  background: isActive ? `${color}1a` : 'transparent',
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
          borderTop: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <span className="pulse-glow" style={{
            display: 'inline-block', width: 7, height: 7,
            borderRadius: '50%', background: '#22c55e', flexShrink: 0,
          }} />
          <span style={{ fontSize: 11, color: 'var(--muted)' }}>TraceBi v0.5.2</span>
          <span style={{
            marginLeft: 'auto', fontSize: 10, color: 'var(--accent-text)',
            background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
            padding: '1px 6px', borderRadius: 4,
          }}>BETA</span>
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
