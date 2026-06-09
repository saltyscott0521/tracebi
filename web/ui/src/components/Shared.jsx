import { createContext, useContext, useState, useCallback } from 'react'

// ── Toast ─────────────────────────────────────────────────────────────────────

export const ToastContext = createContext(null)

function ToastContainer({ toasts, remove }) {
  if (!toasts.length) return null
  return (
    <div style={{
      position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
      display: 'flex', flexDirection: 'column', gap: 8, pointerEvents: 'none',
    }}>
      {toasts.map(t => {
        const isErr = t.type === 'error', isOk = t.type === 'success'
        return (
          <div key={t.id} className="toast-enter" style={{
            pointerEvents: 'all',
            background: isErr ? 'rgba(239,68,68,.14)' : isOk ? 'rgba(34,197,94,.14)' : 'var(--card)',
            border: `1px solid ${isErr ? 'rgba(239,68,68,.4)' : isOk ? 'rgba(34,197,94,.4)' : 'var(--border-hl)'}`,
            borderRadius: 10, padding: '11px 14px',
            fontSize: 13, lineHeight: 1.5,
            color: isErr ? '#fca5a5' : isOk ? '#86efac' : 'var(--text)',
            boxShadow: 'var(--shadow)',
            display: 'flex', alignItems: 'center', gap: 10,
            minWidth: 260, maxWidth: 380,
          }}>
            <span style={{ fontSize: 14, flexShrink: 0, opacity: .8 }}>
              {isErr ? '✕' : isOk ? '✓' : 'ℹ'}
            </span>
            <span style={{ flex: 1 }}>{t.message}</span>
            <button onClick={() => remove(t.id)} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--muted)', fontSize: 17, lineHeight: 1,
              padding: '0 2px', flexShrink: 0,
            }}>×</button>
          </div>
        )
      })}
    </div>
  )
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const add = useCallback((message, type = 'info') => {
    const id = Date.now()
    setToasts(t => [...t, { id, message, type }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4200)
  }, [])
  const remove = useCallback(id => setToasts(t => t.filter(x => x.id !== id)), [])
  return (
    <ToastContext.Provider value={add}>
      {children}
      <ToastContainer toasts={toasts} remove={remove} />
    </ToastContext.Provider>
  )
}

export function useToast() { return useContext(ToastContext) }

// ── Skeleton ──────────────────────────────────────────────────────────────────

export function Skeleton({ width = '100%', height = 14, radius = 4, style }) {
  return <span className="skeleton" style={{ width, height, borderRadius: radius, ...style }} />
}

export function SkeletonList({ rows = 4 }) {
  return (
    <div>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
          <Skeleton width="65%" height={13} style={{ marginBottom: 7 }} />
          <Skeleton width="38%" height={11} />
        </div>
      ))}
    </div>
  )
}

export function SkeletonCard() {
  return (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '20px 24px', marginBottom: 20,
    }}>
      <Skeleton width="45%" height={17} radius={5} style={{ marginBottom: 18 }} />
      <Skeleton height={13} style={{ marginBottom: 9 }} />
      <Skeleton width="80%" height={13} style={{ marginBottom: 9 }} />
      <Skeleton width="55%" height={13} />
    </div>
  )
}

// ── Search ────────────────────────────────────────────────────────────────────

export function SearchInput({ value, onChange, placeholder = 'Search…' }) {
  return (
    <div className="search-wrap" style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
      <span className="search-icon">
        <svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <circle cx="9" cy="9" r="5.5" /><line x1="15" y1="15" x2="19" y2="19" />
        </svg>
      </span>
      <input
        type="search"
        className="search-input"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}

// ── Layout components ─────────────────────────────────────────────────────────

export function Card({ children, style, hover }) {
  return (
    <div className={hover ? 'card-hover' : ''} style={{
      background: 'var(--card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '20px 24px',
      marginBottom: 20,
      ...style,
    }}>
      {children}
    </div>
  )
}

export function CardTitle({ children, action }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center',
      justifyContent: action ? 'space-between' : 'flex-start',
      marginBottom: 16, paddingBottom: 12,
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', lineHeight: 1.3 }}>{children}</div>
      {action && <div>{action}</div>}
    </div>
  )
}

export function PageTitle({ children }) {
  return (
    <h1 style={{
      fontSize: 22, fontWeight: 700, color: 'var(--text)',
      marginBottom: 6, lineHeight: 1.3,
    }}>{children}</h1>
  )
}

export function PageSub({ children }) {
  return (
    <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 28, lineHeight: 1.6 }}>
      {children}
    </p>
  )
}

const BADGE_STYLES = {
  blue:         { background: 'var(--blue-lt)',              color: '#93c5fd', border: '1px solid var(--blue-br)' },
  green:        { background: 'rgba(34,197,94,.12)',          color: '#86efac', border: '1px solid rgba(34,197,94,.28)' },
  amber:        { background: 'rgba(245,158,11,.12)',         color: '#fcd34d', border: '1px solid rgba(245,158,11,.28)' },
  red:          { background: 'rgba(239,68,68,.12)',          color: '#fca5a5', border: '1px solid rgba(239,68,68,.28)' },
  gray:         { background: 'rgba(255,255,255,.06)',        color: '#94a3b8', border: '1px solid var(--border)' },
  gold:         { background: 'rgba(234,179,8,.1)',           color: '#fde68a', border: '1px solid rgba(234,179,8,.28)' },
  silver:       { background: 'rgba(148,163,184,.1)',         color: '#cbd5e1', border: '1px solid rgba(148,163,184,.28)' },
  bronze:       { background: 'rgba(180,120,40,.15)',         color: '#fbbf24', border: '1px solid rgba(180,120,40,.32)' },
  landing:      { background: 'rgba(74,144,226,.12)',         color: '#93c5fd', border: '1px solid rgba(74,144,226,.3)' },
  manipulation: { background: 'rgba(123,104,238,.12)',        color: '#c4b5fd', border: '1px solid rgba(123,104,238,.3)' },
  final:        { background: 'rgba(16,185,129,.12)',         color: '#6ee7b7', border: '1px solid rgba(16,185,129,.3)' },
  purple:       { background: 'rgba(167,139,250,.12)',        color: '#c4b5fd', border: '1px solid rgba(167,139,250,.28)' },
}

export function Badge({ variant = 'gray', children, style }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 10,
      fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: .3,
      ...BADGE_STYLES[variant],
      ...style,
    }}>{children}</span>
  )
}

export function Spinner({ size = 18 }) {
  return (
    <span style={{
      display: 'inline-block', width: size, height: size,
      border: '2px solid var(--border)', borderTopColor: 'var(--blue)',
      borderRadius: '50%', animation: 'spin .7s linear infinite', flexShrink: 0,
    }} />
  )
}

export function Empty({ icon, message, action }) {
  return (
    <div style={{ textAlign: 'center', padding: '60px 24px', color: 'var(--muted)' }}>
      {icon && <div style={{ fontSize: 32, marginBottom: 14, opacity: .35 }}>{icon}</div>}
      <p style={{ fontSize: 13, lineHeight: 1.65, maxWidth: 300, margin: '0 auto' }}>{message}</p>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  )
}

export function Alert({ variant = 'info', children }) {
  const s = variant === 'err'
    ? { background: 'rgba(239,68,68,.1)', color: '#fca5a5', borderLeft: '3px solid var(--red)' }
    : { background: 'var(--blue-lt)', color: '#93c5fd', borderLeft: '3px solid var(--blue)' }
  return (
    <div style={{ borderRadius: 8, padding: '11px 16px', fontSize: 13, marginBottom: 16, lineHeight: 1.5, ...s }}>
      {children}
    </div>
  )
}

export function Btn({ children, onClick, disabled, variant = 'primary', size, style, type = 'button' }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: size === 'sm' ? '5px 11px' : '8px 16px',
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    fontSize: size === 'sm' ? 12 : 13,
    fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    textDecoration: 'none',
    opacity: disabled ? .4 : 1,
    transition: 'filter var(--t), box-shadow var(--t), background var(--t), opacity var(--t)',
    lineHeight: 1,
    ...style,
  }
  const variants = {
    primary: {
      background: 'linear-gradient(135deg,var(--blue),var(--blue-md))',
      color: '#fff',
      boxShadow: '0 2px 10px rgba(59,130,246,.25)',
    },
    outline: {
      background: 'transparent',
      color: 'var(--blue)',
      border: '1px solid var(--blue-br)',
    },
    red: {
      background: 'rgba(239,68,68,.12)',
      color: '#fca5a5',
      border: '1px solid rgba(239,68,68,.3)',
    },
  }
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`btn-${variant}`}
      style={{ ...base, ...variants[variant] }}
    >
      {children}
    </button>
  )
}

export function StatTile({ value, label, color }) {
  return (
    <div className="card-hover" style={{
      background: 'var(--card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '18px 22px',
      minWidth: 130,
      flex: 1,
    }}>
      <div style={{
        fontSize: 30, fontWeight: 800,
        color: color || 'var(--blue)',
        lineHeight: 1,
        fontVariantNumeric: 'tabular-nums',
      }}>{value ?? '—'}</div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 6, fontWeight: 500 }}>{label}</div>
    </div>
  )
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 16, flexWrap: 'wrap' }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          padding: '9px 18px', border: 'none', background: 'none',
          fontSize: 13, fontWeight: 600, cursor: 'pointer',
          color: active === t ? 'var(--blue)' : 'var(--muted)',
          borderBottom: `2px solid ${active === t ? 'var(--blue)' : 'transparent'}`,
          marginBottom: -1,
          transition: 'color var(--t), border-color var(--t)',
        }}>{t}</button>
      ))}
    </div>
  )
}

export function SplitLayout({ left, right }) {
  return (
    <div className="split-layout">
      <div style={{
        background: 'var(--card)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden',
      }}>
        {left}
      </div>
      <div>{right}</div>
    </div>
  )
}

export function ListItem({ selected, onClick, name, sub, right }) {
  return (
    <div
      onClick={onClick}
      className={selected ? '' : 'list-item-hover'}
      style={{
        padding: '11px 16px',
        borderBottom: '1px solid rgba(30,45,74,.6)',
        cursor: 'pointer',
        background: selected ? 'rgba(59,130,246,.1)' : 'transparent',
        borderLeft: `2px solid ${selected ? 'var(--blue)' : 'transparent'}`,
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        transition: 'background var(--t)',
      }}
    >
      <div>
        <div style={{ fontWeight: 600, fontSize: 13, color: selected ? 'var(--text)' : '#cbd5e1' }}>{name}</div>
        {sub && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{sub}</div>}
      </div>
      {right && <div style={{ marginLeft: 8, flexShrink: 0 }}>{right}</div>}
    </div>
  )
}

export function CodeBlock({ children }) {
  return <pre className="code-block">{children}</pre>
}
