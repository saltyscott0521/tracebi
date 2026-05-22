import { useState } from 'react'
import { NavLink } from 'react-router-dom'

const NAV = [
  { path: '/', label: 'Home', icon: '⌂' },
  { path: '/connectors', label: 'Connectors', icon: '⇌' },
  { path: '/models', label: 'Models', icon: '⊞' },
  { path: '/reports', label: 'Reports', icon: '▤' },
  { path: '/pipelines', label: 'Pipelines', icon: '⧖' },
  { path: '/dashboards', label: 'Dashboards', icon: '◫' },
]

const linkStyle = (isActive) => ({
  display: 'flex', alignItems: 'center', gap: 10,
  padding: '10px 20px',
  color: isActive ? 'var(--blue)' : '#94a3b8',
  textDecoration: 'none',
  fontSize: 13, fontWeight: 500,
  borderLeft: `3px solid ${isActive ? 'var(--blue)' : 'transparent'}`,
  background: isActive ? 'var(--blue-lt)' : 'transparent',
  transition: 'background .15s, color .15s',
})

export default function Layout({ children }) {
  const [open, setOpen] = useState(false)

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>

      {/* Mobile top bar */}
      <div style={{
        display: 'none', position: 'fixed', top: 0, left: 0, right: 0,
        height: 52, background: 'var(--navy)', borderBottom: '1px solid var(--border)',
        alignItems: 'center', justifyContent: 'space-between', padding: '0 16px',
        zIndex: 200,
        ['@media (max-width: 768px)']: { display: 'flex' },
      }} className="mobile-header">
        <span style={{
          fontSize: 16, fontWeight: 800,
          background: 'linear-gradient(90deg,#60a5fa,#a78bfa)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
        }}>TraceBi</span>
        <button onClick={() => setOpen(true)} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          display: 'flex', flexDirection: 'column', gap: 5, padding: 4,
        }}>
          {[0,1,2].map(i => <span key={i} style={{ display:'block', width:22, height:2, background:'#94a3b8', borderRadius:2 }} />)}
        </button>
      </div>

      {/* Overlay */}
      {open && (
        <div onClick={() => setOpen(false)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,.6)', zIndex: 250,
        }} />
      )}

      {/* Sidebar */}
      <nav style={{
        width: 'var(--nav-w)', minHeight: '100vh',
        background: 'var(--navy)', borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
        position: 'fixed', top: 0, left: 0, zIndex: 300,
      }} className={open ? 'nav-open' : ''}>
        <div style={{
          padding: '24px 20px 18px',
          borderBottom: '1px solid var(--border)',
          background: 'linear-gradient(135deg,#0d1835 0%,#0f2040 100%)',
        }}>
          <h1 style={{
            fontSize: 19, fontWeight: 800, letterSpacing: .5,
            background: 'linear-gradient(90deg,#60a5fa,#a78bfa)',
            WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}>TraceBi</h1>
          <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>Code-first traceable BI</p>
        </div>

        <ul style={{ listStyle: 'none', padding: '10px 0', flex: 1 }}>
          {NAV.map(({ path, label, icon }) => (
            <li key={path}>
              <NavLink
                to={path}
                end={path === '/'}
                onClick={() => setOpen(false)}
                style={({ isActive }) => linkStyle(isActive)}
              >
                <span style={{ fontSize: 15, width: 18, textAlign: 'center' }}>{icon}</span>
                {label}
              </NavLink>
            </li>
          ))}
        </ul>

        <div style={{ padding: '14px 20px', borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--muted)' }}>
          TraceBi v0.5.0
        </div>
      </nav>

      {/* Main */}
      <main style={{ marginLeft: 'var(--nav-w)', flex: 1, padding: '36px 40px', maxWidth: 1300 }}>
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
