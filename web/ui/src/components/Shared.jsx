export function Card({ children, style }) {
  return (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--border)',
      borderRadius: 10, padding: '20px 24px', marginBottom: 20,
      transition: 'border-color .2s',
      ...style,
    }}>
      {children}
    </div>
  )
}

export function CardTitle({ children }) {
  return (
    <div style={{
      fontSize: 13, fontWeight: 600, color: 'var(--text)',
      marginBottom: 14, paddingBottom: 10,
      borderBottom: '1px solid var(--border)',
    }}>{children}</div>
  )
}

export function PageTitle({ children }) {
  return <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>{children}</div>
}

export function PageSub({ children }) {
  return <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 28 }}>{children}</p>
}

const BADGE_STYLES = {
  blue:  { background: 'var(--blue-lt)',              color: '#93c5fd', border: '1px solid var(--blue-br)' },
  green: { background: 'rgba(34,197,94,.12)',          color: '#86efac', border: '1px solid rgba(34,197,94,.25)' },
  amber: { background: 'rgba(245,158,11,.12)',         color: '#fcd34d', border: '1px solid rgba(245,158,11,.25)' },
  red:   { background: 'rgba(239,68,68,.12)',          color: '#fca5a5', border: '1px solid rgba(239,68,68,.25)' },
  gray:  { background: 'rgba(255,255,255,.06)',        color: '#94a3b8', border: '1px solid var(--border)' },
  gold:  { background: 'rgba(234,179,8,.1)',           color: '#fde68a', border: '1px solid rgba(234,179,8,.25)' },
  silver:{ background: 'rgba(148,163,184,.1)',         color: '#cbd5e1', border: '1px solid rgba(148,163,184,.25)' },
  bronze:{ background: 'rgba(180,120,40,.15)',         color: '#fbbf24', border: '1px solid rgba(180,120,40,.3)' },
  purple:{ background: 'rgba(167,139,250,.12)',        color: '#c4b5fd', border: '1px solid rgba(167,139,250,.25)' },
}

export function Badge({ variant = 'gray', children, style }) {
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 10,
      fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
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
      borderRadius: '50%', animation: 'spin .7s linear infinite',
    }} />
  )
}

export function Empty({ icon = '○', message }) {
  return (
    <div style={{ textAlign: 'center', padding: '56px 24px', color: 'var(--muted)' }}>
      <div style={{ fontSize: 40, marginBottom: 14, opacity: .5 }}>{icon}</div>
      <p style={{ fontSize: 13 }}>{message}</p>
    </div>
  )
}

export function Alert({ variant = 'info', children }) {
  const s = variant === 'err'
    ? { background: 'rgba(239,68,68,.1)', color: '#fca5a5', borderLeft: '3px solid var(--red)' }
    : { background: 'var(--blue-lt)',     color: '#93c5fd', borderLeft: '3px solid var(--blue)' }
  return (
    <div style={{ borderRadius: 8, padding: '12px 16px', fontSize: 13, marginBottom: 16, ...s }}>
      {children}
    </div>
  )
}

export function Btn({ children, onClick, disabled, variant = 'primary', size, style }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: size === 'sm' ? '5px 11px' : '8px 16px',
    borderRadius: 6, border: 'none', fontSize: size === 'sm' ? 12 : 13,
    fontWeight: 600, cursor: disabled ? 'not-allowed' : 'pointer',
    textDecoration: 'none', opacity: disabled ? .35 : 1,
    transition: 'opacity .15s, transform .1s',
    ...style,
  }
  const variants = {
    primary: { background: 'linear-gradient(135deg,var(--blue),var(--blue-md))', color: '#fff', boxShadow: '0 2px 12px rgba(59,130,246,.3)' },
    outline: { background: 'transparent', color: 'var(--blue)', border: '1px solid var(--blue-br)' },
    red:     { background: 'rgba(239,68,68,.15)', color: '#fca5a5', border: '1px solid rgba(239,68,68,.3)' },
  }
  return <button onClick={onClick} disabled={disabled} style={{ ...base, ...variants[variant] }}>{children}</button>
}

export function StatTile({ value, label }) {
  return (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 10,
      padding: '18px 24px', minWidth: 140,
    }}>
      <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--blue)' }}>{value ?? '—'}</div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>{label}</div>
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
          marginBottom: -1, transition: 'color .15s, border-color .15s',
        }}>{t}</button>
      ))}
    </div>
  )
}

export function SplitLayout({ left, right }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 20, alignItems: 'start' }}>
      <div style={{ background: 'var(--card)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        {left}
      </div>
      <div>{right}</div>
    </div>
  )
}

export function ListItem({ selected, onClick, name, sub }) {
  return (
    <div onClick={onClick} style={{
      padding: '12px 16px', borderBottom: '1px solid var(--border)',
      cursor: 'pointer', transition: 'background .12s',
      background: selected ? 'var(--blue-lt)' : 'transparent',
      borderLeft: `3px solid ${selected ? 'var(--blue)' : 'transparent'}`,
    }}>
      <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text)' }}>{name}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

export function CodeBlock({ children }) {
  return <pre className="code-block">{children}</pre>
}

// inject keyframe once
if (typeof document !== 'undefined' && !document.getElementById('tb-spin')) {
  const s = document.createElement('style')
  s.id = 'tb-spin'
  s.textContent = '@keyframes spin { to { transform: rotate(360deg); } }'
  document.head.appendChild(s)
}
