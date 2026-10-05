import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'

/** Track a media query, so an inline-styled layout can still be responsive. */
export function useNarrow(query = '(max-width: 768px)') {
  const [narrow, setNarrow] = useState(
    () => typeof matchMedia !== 'undefined' && matchMedia(query).matches)
  useEffect(() => {
    const mq = matchMedia(query)
    const on = e => setNarrow(e.matches)
    mq.addEventListener('change', on)
    setNarrow(mq.matches)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return narrow
}

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
            background: 'var(--surface)',
            border: `1px solid ${isErr ? 'var(--red-br)' : isOk ? 'var(--green-br)' : 'var(--border-strong)'}`,
            borderRadius: 'var(--radius-lg)', padding: '12px 14px',
            fontSize: 13, lineHeight: 1.5,
            color: isErr ? 'var(--red-text)' : isOk ? 'var(--green-text)' : 'var(--text)',
            boxShadow: 'var(--shadow-pop)',
            display: 'flex', alignItems: 'center', gap: 10,
            minWidth: 260, maxWidth: 380,
          }}>
            <span style={{
              fontSize: 15, flexShrink: 0,
              color: isErr ? 'var(--red)' : isOk ? 'var(--green)' : 'var(--blue)',
            }}>
              {isErr ? '✕' : isOk ? '✓' : 'ℹ'}
            </span>
            <span style={{ flex: 1 }}>{t.message}</span>
            <button onClick={() => remove(t.id)} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--muted)', fontSize: 17, lineHeight: 1, padding: '0 2px', flexShrink: 0,
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

export function Card({ children, style, hover, accent }) {
  return (
    <div
      className={['surface', hover ? 'card-hover' : '', accent ? 'card-accent' : ''].filter(Boolean).join(' ')}
      style={{
        background: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)',
        padding: '20px 24px',
        marginBottom: 20,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function CardTitle({ children, action }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center',
      justifyContent: action ? 'space-between' : 'flex-start',
      marginBottom: 'var(--space-4)', paddingBottom: 'var(--space-3)',
      borderBottom: '1px solid var(--border)',
    }}>
      <div style={{
        fontSize: 'var(--text-base)', fontWeight: 600,
        color: 'var(--text)', lineHeight: 1.3,
      }}>{children}</div>
      {action && <div>{action}</div>}
    </div>
  )
}

export function PageTitle({ children }) {
  return (
    <h1 style={{
      fontSize: 'var(--text-2xl)', fontWeight: 600,
      marginBottom: 'var(--space-1)', lineHeight: 1.2,
      letterSpacing: 'var(--tracking-tight)',
      color: 'var(--text)',
    }}>{children}</h1>
  )
}

export function PageSub({ children }) {
  return (
    <p style={{
      fontSize: 'var(--text-caption)', color: 'var(--muted)',
      // The gap under the subtitle is the page's first rhythm cue — it sets
      // how far the content sits from the heading block on every page.
      marginBottom: 'var(--space-7)', lineHeight: 1.6,
      maxWidth: '68ch',
    }}>
      {children}
    </p>
  )
}

const BADGE_STYLES = {
  blue:         { background: 'var(--blue-lt)',          color: 'var(--accent-text)', border: '1px solid var(--blue-br)' },
  green:        { background: 'var(--green-lt)',         color: 'var(--green-text)',  border: '1px solid var(--green-br)' },
  amber:        { background: 'var(--amber-lt)',         color: 'var(--amber-text)',  border: '1px solid var(--amber-br)' },
  red:          { background: 'var(--red-lt)',           color: 'var(--red-text)',    border: '1px solid var(--red-br)' },
  gray:         { background: 'var(--surface-2)',        color: 'var(--muted)',       border: '1px solid var(--border)' },
  // A layer's type is a meaning (landing, manipulation, final), so it keeps a
  // colour: the same operation palette the diagrams use, with a dark value.
  gold:         { background: 'var(--op-gold-bg)',         color: 'var(--op-gold-tx)',         border: '1px solid var(--op-gold-br)' },
  silver:       { background: 'var(--op-silver-bg)',       color: 'var(--op-silver-tx)',       border: '1px solid var(--op-silver-br)' },
  bronze:       { background: 'var(--op-bronze-bg)',       color: 'var(--op-bronze-tx)',       border: '1px solid var(--op-bronze-br)' },
  landing:      { background: 'var(--op-landing-bg)',      color: 'var(--op-landing-tx)',      border: '1px solid var(--op-landing-br)' },
  manipulation: { background: 'var(--op-manipulation-bg)', color: 'var(--op-manipulation-tx)', border: '1px solid var(--op-manipulation-br)' },
  final:        { background: 'var(--op-final-bg)',        color: 'var(--op-final-tx)',        border: '1px solid var(--op-final-br)' },
  purple:       { background: 'var(--blue-lt)',          color: 'var(--accent-text)', border: '1px solid var(--blue-br)' },
}

export function Badge({ variant = 'gray', children, style, title }) {
  return (
    <span title={title} style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 4,
      fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: .4,
      ...BADGE_STYLES[variant],
      ...style,
    }}>{children}</span>
  )
}

export function Spinner({ size = 18 }) {
  return (
    <span style={{
      display: 'inline-block', width: size, height: size,
      border: `${size > 16 ? 2 : 1.5}px solid var(--blue-br)`,
      borderTopColor: 'var(--blue)',
      borderRadius: '50%', animation: 'spin .7s linear infinite', flexShrink: 0,
    }} />
  )
}

export function Empty({ icon, message, action }) {
  return (
    <div className="empty" style={{ textAlign: 'center', padding: '60px 24px', color: 'var(--muted)' }}>
      {icon && <div style={{ fontSize: 30, marginBottom: 14, opacity: .3 }}>{icon}</div>}
      <p style={{ fontSize: 13, lineHeight: 1.65, maxWidth: 300, margin: '0 auto' }}>{message}</p>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  )
}

/**
 * Renders a rendered-report HTML document at its natural height.
 *
 * Both callers previously used a fixed-height iframe — 640px, against demo
 * output that is 1872px tall. Two thirds of every report sat behind the
 * iframe's own scrollbar, including charts and tables, and because the frame
 * ends on a clean white edge a truncated report looks like a finished one.
 * Nobody scrolls a region they cannot tell is scrollable.
 *
 * A report is a document, so it should lay out at full height and let the page
 * scroll. srcDoc inherits this origin, so the content is measurable; the
 * ResizeObserver covers content that settles after load (late fonts, images)
 * rather than trusting a single measurement at the load event.
 */
export function ReportFrame({ html, title, frameRef }) {
  const ref = useRef(null)
  const [height, setHeight] = useState(480)

  useEffect(() => {
    const frame = ref.current
    if (!frame) return
    let observer

    const measure = () => {
      const doc = frame.contentDocument
      if (!doc?.body) return
      const h = Math.max(doc.documentElement?.scrollHeight || 0, doc.body.scrollHeight || 0)
      if (h) setHeight(h)
    }

    const onLoad = () => {
      measure()
      const doc = frame.contentDocument
      if (doc?.body && typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(measure)
        observer.observe(doc.body)
      }
    }

    frame.addEventListener('load', onLoad)
    if (frame.contentDocument?.readyState === 'complete') onLoad()
    return () => {
      frame.removeEventListener('load', onLoad)
      observer?.disconnect()
    }
  }, [html])

  return (
    <iframe
      ref={(node) => {
        ref.current = node
        if (frameRef) frameRef.current = node
      }}
      srcDoc={html}
      title={title}
      scrolling="no"
      style={{
        width: '100%', height, display: 'block',
        border: 'none', borderRadius: 6, background: '#fff',
      }}
    />
  )
}

export function Alert({ variant = 'info', children }) {
  const s = variant === 'err'
    ? { background: 'var(--red-lt)', color: 'var(--red-text)', borderLeft: '3px solid var(--red)' }
    : variant === 'warn'
    ? { background: 'var(--amber-lt)', color: 'var(--amber-text)', borderLeft: '3px solid var(--amber)' }
    : { background: 'var(--blue-lt)', color: 'var(--accent-text)', borderLeft: '3px solid var(--blue)' }
  return (
    <div style={{ borderRadius: 8, padding: '11px 16px', fontSize: 13, marginBottom: 16, lineHeight: 1.5, ...s }}>
      {children}
    </div>
  )
}

// Renders an API error with an expandable Python traceback when the
// backend supplied one (err.detail.traceback — see api.js toError()).
export function ErrorDetail({ error }) {
  if (!error) return null
  const tb = error.detail?.traceback
  return (
    <Alert variant="err">
      <div>{error.message}</div>
      {tb && (
        <details style={{ marginTop: 8 }}>
          <summary style={{ cursor: 'pointer', fontSize: 12, opacity: .8 }}>
            Show Python traceback
          </summary>
          <pre style={{
            marginTop: 8, padding: 12, borderRadius: 6, overflowX: 'auto',
            background: 'var(--code-bg)', color: 'var(--red-text)',
            fontSize: 11, lineHeight: 1.55,
            fontFamily: 'var(--font-mono)',
            whiteSpace: 'pre-wrap',
          }}>{tb}</pre>
        </details>
      )}
    </Alert>
  )
}

export function Btn({ children, onClick, disabled, variant = 'primary', size, style, type = 'button', ...rest }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    // 6px keeps a small button at 24px tall: the smallest a thumb can hit.
    padding: size === 'sm' ? '6px 12px' : '9px 18px',
    borderRadius: 'var(--radius-sm)', border: 'none',
    fontSize: size === 'sm' ? 12 : 13,
    fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    textDecoration: 'none',
    opacity: disabled ? .4 : 1,
    transition: 'filter var(--t), box-shadow var(--t), background var(--t), opacity var(--t), transform var(--t)',
    lineHeight: 1,
    ...style,
  }
  const variants = {
    primary: {
      background: 'var(--ink)',
      color: 'var(--on-ink)',
    },
    outline: {
      background: 'transparent',
      color: 'var(--text)',
      border: '1px solid var(--border-strong)',
    },
    red: {
      background: 'var(--red-lt)',
      color: 'var(--red-text)',
      border: '1px solid var(--red-br)',
    },
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} {...rest}
      className={`btn-${variant}`}
      style={{ ...base, ...variants[variant] }}
    >
      {children}
    </button>
  )
}

export function StatTile({ value, label, icon }) {
  return (
    <div className="card-hover" style={{
      background: 'var(--card)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '20px 22px',
      minWidth: 130, flex: 1,
      position: 'relative', overflow: 'hidden',
    }}>
      {icon && <div style={{ fontSize: 18, marginBottom: 10, opacity: .7 }}>{icon}</div>}
      <div style={{
        fontSize: 30, fontWeight: 600, color: 'var(--text)',
        letterSpacing: '-0.02em',
        lineHeight: 1, fontVariantNumeric: 'tabular-nums',
      }}>{value ?? '—'}</div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 7, fontWeight: 500 }}>{label}</div>
    </div>
  )
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 18, flexWrap: 'wrap' }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          padding: '9px 18px', border: 'none', background: 'none',
          fontSize: 13, fontWeight: 600, cursor: 'pointer',
          color: active === t ? 'var(--accent-text)' : 'var(--muted)',
          borderBottom: `2px solid ${active === t ? 'var(--blue)' : 'transparent'}`,
          marginBottom: -1,
          transition: 'color var(--t), border-color var(--t)',
        }}>{t}</button>
      ))}
    </div>
  )
}

// Pass `detail` (true/false) to make the panes two screens on a phone: the
// list, or the right pane sliding in. Without it they stack. Side by side
// above phone width either way.
export function SplitLayout({ left, right, detail }) {
  const cls = detail === undefined ? 'split-layout'
    : `split-layout split-layout--screens${detail ? ' split-layout--detail' : ''}`
  return (
    <div className={cls}>
      <div className="surface" style={{
        background: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius)', overflow: 'hidden',
      }}>
        {left}
      </div>
      <div className="split-detail">{right}</div>
    </div>
  )
}

/**
 * Props that make a non-button element act like one: reachable with Tab,
 * activated with Enter or Space. For things that must stay a block (a list
 * row holding badges, a drop zone), where a real <button> can't.
 */
export function pressable(onActivate) {
  return {
    role: 'button',
    tabIndex: 0,
    onClick: onActivate,
    onKeyDown: e => {
      if (e.target !== e.currentTarget) return
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onActivate(e) }
    },
  }
}

export function ListItem({ selected, onClick, name, sub, right, meta }) {
  return (
    <div {...pressable(onClick)} aria-current={selected ? 'true' : undefined}
      className={selected ? 'list-item' : 'list-item list-item-hover'}
      style={{
        padding: '11px 16px',
        borderBottom: '1px solid var(--border)',
        cursor: 'pointer',
        background: selected ? 'var(--blue-lt)' : 'transparent',
        borderLeft: `2px solid ${selected ? 'var(--blue)' : 'transparent'}`,
        display: 'flex', flexDirection: 'column', gap: meta ? 4 : 0,
        transition: 'background var(--t)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="list-item__name" style={{ fontWeight: selected ? 600 : 500, fontSize: 13, color: selected ? 'var(--text)' : 'var(--text-2)', overflowWrap: 'anywhere' }}>{name}</div>
          {sub && (
            <div title={typeof sub === 'string' ? sub : undefined} style={{
              fontSize: 11, color: 'var(--muted)', marginTop: 2,
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
            }}>{sub}</div>
          )}
        </div>
        {right && <div style={{ marginLeft: 8, flexShrink: 0 }}>{right}</div>}
      </div>
      {meta && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 12px', maxWidth: '100%' }}>{meta}</div>
      )}
    </div>
  )
}

export function CodeBlock({ children }) {
  // Focusable: a long command scrolls sideways, and a keyboard must reach it.
  return <pre className="code-block" tabIndex={0}>{children}</pre>
}
