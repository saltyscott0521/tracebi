import { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { FRAME_SANDBOX, listenToFrame } from '../frameBridge'
import { VERDICT_LABEL } from '../verdict'
import { ago, isoTitle, stamp } from '../when'

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
            border: `1px solid ${isErr ? 'var(--red-br)' : 'var(--border-strong)'}`,
            borderRadius: 'var(--radius-lg)', padding: '12px 14px',
            fontSize: 'var(--text-caption)', lineHeight: 1.5,
            color: isErr ? 'var(--red-text)' : 'var(--text)',
            boxShadow: 'var(--shadow-pop)',
            display: 'flex', alignItems: 'center', gap: 10,
            minWidth: 260, maxWidth: 380,
          }}>
            <span style={{
              fontSize: 'var(--text-base)', flexShrink: 0,
              color: isErr ? 'var(--red)' : isOk ? 'var(--text-2)' : 'var(--blue)',
            }}>
              {isErr ? '✕' : isOk ? '✓' : 'ℹ'}
            </span>
            <span style={{ flex: 1 }}>{t.message}</span>
            <button onClick={() => remove(t.id)} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--muted)', fontSize: 'var(--text-lg)', lineHeight: 1, padding: '0 2px', flexShrink: 0,
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
      borderRadius: 'var(--radius-lg)', padding: '20px 24px', marginBottom: 20,
    }}>
      <Skeleton width="45%" height={17} radius={5} style={{ marginBottom: 18 }} />
      <Skeleton height={13} style={{ marginBottom: 9 }} />
      <Skeleton width="80%" height={13} style={{ marginBottom: 9 }} />
      <Skeleton width="55%" height={13} />
    </div>
  )
}

// ── Search ────────────────────────────────────────────────────────────────────

export function SearchInput({ value, onChange, placeholder = 'Search…', label, style }) {
  return (
    <div className="search-wrap" style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', ...style }}>
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
        aria-label={label}
      />
    </div>
  )
}

// ── Layout components ─────────────────────────────────────────────────────────

export function Card({ children, style, hover, accent, className }) {
  return (
    <div
      className={['surface', hover ? 'card-hover' : '', accent ? 'card-accent' : '', className].filter(Boolean).join(' ')}
      style={{
        background: 'var(--card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
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
    // A page's h1 is the display: the sans, tight, at its one weight.
    <h1 style={{
      fontFamily: 'var(--font-display)',
      fontSize: 'var(--text-2xl)', fontWeight: 'var(--weight-display)',
      marginBottom: 'var(--space-1)', lineHeight: 1.2,
      letterSpacing: 'var(--tracking-display)',
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
  // A fine state is a plain fact: the app colours only exceptions, so the
  // "good" variant reads neutral (the verdict logic still calls it green).
  green:        { background: 'var(--surface-2)',        color: 'var(--text-2)',      border: '1px solid var(--border)' },
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

/**
 * A label that is not a state: a layer's type, a file's size, a kind of
 * source. A state (succeeded, failed, checks passed) is a `Chip`. Sentence
 * case, as written: an upper-case pill reads as a second chip style.
 */
export function Badge({ variant = 'gray', children, style, title }) {
  return (
    <span title={title} style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: 'var(--radius-sm)',
      fontSize: 'var(--text-xs)', fontWeight: 600,
      ...BADGE_STYLES[variant],
      ...style,
    }}>{children}</span>
  )
}

/**
 * The verdict chip: the app's copy of the artifact's .tb-verdict, the same
 * words and colour rule. *state* is one of verdict.js's states (derive it with
 * verdictOf, never by hand); *detail* says why, as the chip's title. With
 * *onClick* it is a button. `size="sm"` for a dense row. *children* replace the
 * state's words with a count of it ("6 reproduce"), in the same chip.
 */
export function Verdict({ state, detail, size, onClick, children }) {
  if (!VERDICT_LABEL[state]) return null
  const label = children ?? VERDICT_LABEL[state]
  const cls = `verdict verdict--${state}${size === 'sm' ? ' verdict--sm' : ''}`
  return onClick
    ? <button type="button" className={cls} title={detail} onClick={onClick}>{label}</button>
    : <span className={cls} title={detail}>{label}</span>
}

/**
 * A state that is not a verdict (a table's checks, a run's outcome) in the
 * verdict chip's shape, so the app keeps one chip: *tone* `bad` is red, `warn`
 * amber, `none` a hollow dot, anything else neutral. Words in sentence case;
 * *title* says why.
 */
export function Chip({ tone, title, children }) {
  return <span className={`verdict verdict--sm${tone ? ` chip--${tone}` : ''}`} title={title}>{children}</span>
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

/**
 * A command to run, in a block with a Copy button: the one way the app hands a
 * person a command line. The text is selectable either way; Copy says Copied.
 */
export function CopyCommand({ children }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(String(children))
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch { /* no clipboard (an insecure origin): the text is still selectable */ }
  }
  return (
    <div className="copycmd">
      <code className="copycmd__text">{children}</code>
      <button type="button" className="copycmd__btn" onClick={copy} aria-label={`Copy: ${children}`}>
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

/**
 * The one empty state. *title* names what is empty; *body* says what the
 * thing is and why it is empty (*message* is the older name for it); then the
 * one thing that fills it: an *action* (a button or link), or a *command* to
 * run, shown with Copy. No glyph: the words are the state. Inside a surface it
 * is plain text (global.css).
 */
export function Empty({ title, body, message, command, action }) {
  return (
    <div className="empty">
      {title && <p className="empty__title">{title}</p>}
      {(body ?? message) && <p className="empty__body">{body ?? message}</p>}
      {command && <CopyCommand>{command}</CopyCommand>}
      {action && <div className="empty__action">{action}</div>}
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
 * scroll. The frame is sandboxed (see frameBridge.js), so the app cannot
 * measure it: the report's own runtime says how tall it is, and again whenever
 * that changes (late fonts, images, a chart settling).
 */
export function ReportFrame({ html, title, frameRef }) {
  const ref = useRef(null)
  const [height, setHeight] = useState(480)

  useEffect(() => {
    const frame = ref.current
    if (!frame) return undefined
    return listenToFrame(frame, m => {
      if (m.type !== 'size') return
      if (m.height) setHeight(m.height)
      // A frame holding nothing to operate is not a keyboard stop: Tab would
      // land on a page-sized box that shows no focus.
      frame.tabIndex = m.focusable ? 0 : -1
    })
  }, [html])

  return (
    <iframe
      ref={(node) => {
        ref.current = node
        if (frameRef) frameRef.current = node
      }}
      srcDoc={html}
      sandbox={FRAME_SANDBOX}
      title={title}
      scrolling="no"
      style={{
        width: '100%', height, display: 'block',
        border: 'none', borderRadius: 'var(--radius)', background: '#fff',
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
    <div style={{ borderRadius: 'var(--radius-lg)', padding: '11px 16px', fontSize: 'var(--text-caption)', marginBottom: 16, lineHeight: 1.5, ...s }}>
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
          <summary style={{ cursor: 'pointer', fontSize: 'var(--text-sm)', opacity: .8 }}>
            Show Python traceback
          </summary>
          <pre style={{
            marginTop: 8, padding: 12, borderRadius: 'var(--radius)', overflowX: 'auto',
            background: 'var(--code-bg)', color: 'var(--red-text)',
            fontSize: 'var(--text-xs)', lineHeight: 1.55,
            fontFamily: 'var(--font-mono)',
            whiteSpace: 'pre-wrap',
          }}>{tb}</pre>
        </details>
      )}
    </Alert>
  )
}

function btnStyle(variant, size, disabled, style) {
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
  // The caller's style comes last: a colour it sets is the colour it gets.
  return { ...base, ...variants[variant], ...style }
}

/** A button. `variant="outline"` is the one secondary look; `BtnLink` draws a link the same way. */
export function Btn({ children, onClick, disabled, variant = 'primary', size, style, type = 'button', ...rest }) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} {...rest}
      className={`btn-${variant}`}
      style={btnStyle(variant, size, disabled, style)}
    >
      {children}
    </button>
  )
}

/**
 * A link that looks like `Btn` (outline by default): an in-app route with
 * *to*, a file or another page with *href* (and `download`, say). Use it where
 * an action navigates, so a secondary action has one look beside a button.
 */
export function BtnLink({ to, href, variant = 'outline', size, style, children, ...rest }) {
  const props = { ...rest, className: `btn-${variant}`, style: btnStyle(variant, size, false, style) }
  return to ? <Link to={to} {...props}>{children}</Link> : <a href={href} {...props}>{children}</a>
}

/**
 * The one CSV control: "Export CSV", the secondary button. *href* downloads a
 * file the server writes; *onClick* writes one in the page. *title* says which
 * rows it holds when that is not what is shown (all of them, say).
 */
export function ExportCsv({ href, onClick, title }) {
  return href
    ? <BtnLink href={href} download size="sm" title={title}>Export CSV</BtnLink>
    : <Btn size="sm" variant="outline" onClick={onClick} title={title}>Export CSV</Btn>
}

/**
 * Views of one thing, inside a card or a panel: the one switch for them.
 * (Page tabs, `.dtabs`, are for addresses.) *options* are values or `[value,
 * label]` pairs; *label* names the group. With *panel* (the id of the element
 * it switches) it is an ARIA tablist and each option's id is
 * `${panel}-${value}`, for the panel's aria-labelledby; otherwise a group of
 * pressed buttons.
 */
export function Segmented({ options, value, onChange, label, panel, className }) {
  const pairs = options.map(o => (Array.isArray(o) ? o : [o, o]))
  return (
    <div className={['seg', className].filter(Boolean).join(' ')} role={panel ? 'tablist' : 'group'} aria-label={label}>
      {pairs.map(([v, text]) => (
        <button key={v} type="button" onClick={() => onChange(v)}
          {...(panel
            ? { role: 'tab', id: `${panel}-${v}`, 'aria-selected': value === v, 'aria-controls': panel }
            : { 'aria-pressed': value === v })}>
          {text}
        </button>
      ))}
    </div>
  )
}

/**
 * A moment as the app writes it (when.js): its stamp, or with *relative* how
 * long ago, and the full ISO time in the title. Renders *fallback* (default
 * nothing) when *iso* is missing or unreadable.
 */
export function Time({ iso, relative, fallback = null }) {
  const text = relative ? ago(iso) : stamp(iso)
  if (!text) return fallback
  return <time dateTime={isoTitle(iso)} title={isoTitle(iso)}>{text}</time>
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
        borderRadius: 'var(--radius-lg)', overflow: 'hidden',
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
          <div className="list-item__name" style={{ fontWeight: selected ? 600 : 500, fontSize: 'var(--text-caption)', color: selected ? 'var(--text)' : 'var(--text-2)', overflowWrap: 'anywhere' }}>{name}</div>
          {sub && (
            <div title={typeof sub === 'string' ? sub : undefined} style={{
              fontSize: 'var(--text-xs)', color: 'var(--muted)', marginTop: 2,
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
