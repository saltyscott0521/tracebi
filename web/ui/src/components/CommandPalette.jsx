import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useModels, useReports, useRequests, usePipelines, useDashboards } from '../api'

// Static page destinations — always available, even before data loads.
const PAGES = [
  { label: 'Home',            path: '/',                kind: 'page' },
  { label: 'Getting Started', path: '/getting-started', kind: 'page' },
  { label: 'Connectors',      path: '/connectors',      kind: 'page' },
  { label: 'Models',          path: '/models',          kind: 'page' },
  { label: 'Explore',         path: '/explore',         kind: 'page' },
  { label: 'Reports',         path: '/reports',         kind: 'page' },
  { label: 'Requests',        path: '/requests',        kind: 'page' },
  { label: 'Pipelines',       path: '/pipelines',       kind: 'page' },
  { label: 'Dashboards',      path: '/dashboards',      kind: 'page' },
]

const KIND_META = {
  page:      { tag: 'Page',      color: '#64748b' },
  model:     { tag: 'Model',     color: '#7c3aed' },
  report:    { tag: 'Report',    color: '#db2777' },
  request:   { tag: 'Request',   color: '#6d28d9' },
  pipeline:  { tag: 'Pipeline',  color: '#d97706' },
  dashboard: { tag: 'Dashboard', color: '#0891b2' },
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  const { data: models }     = useModels()
  const { data: reports }    = useReports()
  const { data: requests }   = useRequests()
  const { data: pipelines }  = usePipelines()
  const { data: dashboards } = useDashboards()

  const items = useMemo(() => [
    ...PAGES,
    ...(models     || []).map(m => ({ label: m.name,     path: '/models',     kind: 'model',     sub: `${m.tables.length} tables` })),
    ...(reports    || []).map(r => ({ label: r.name,     path: '/reports',    kind: 'report',    sub: r.description })),
    ...(requests   || []).map(r => ({ label: r.name,     path: '/requests',   kind: 'request',   sub: r.type })),
    ...(pipelines  || []).map(p => ({ label: p.pipeline, path: '/pipelines',  kind: 'pipeline',  sub: `${(p.layers || []).length} layers` })),
    ...(dashboards || []).map(d => ({ label: d.name,     path: '/dashboards', kind: 'dashboard', sub: d.description })),
  ], [models, reports, requests, pipelines, dashboards])

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items.slice(0, 9)
    return items
      .filter(it =>
        it.label.toLowerCase().includes(q) ||
        (it.sub || '').toLowerCase().includes(q) ||
        KIND_META[it.kind].tag.toLowerCase().startsWith(q))
      .slice(0, 9)
  }, [items, query])

  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
    setCursor(0)
  }, [])

  const go = useCallback(item => {
    if (item) navigate(item.path)
    close()
  }, [navigate, close])

  // Global hotkey: Cmd+K / Ctrl+K toggles; Esc closes.
  useEffect(() => {
    const onKey = e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(o => !o)
      } else if (e.key === 'Escape' && open) {
        close()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, close])

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => { setCursor(0) }, [query])

  if (!open) return null

  const onInputKey = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); go(results[cursor]) }
  }

  return (
    <div
      onClick={close}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(10,18,40,.45)',
        backdropFilter: 'blur(3px)', WebkitBackdropFilter: 'blur(3px)',
        display: 'flex', justifyContent: 'center', paddingTop: '14vh',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="fade-in"
        style={{
          width: 560, maxWidth: 'calc(100vw - 32px)', height: 'fit-content',
          background: 'var(--card-solid)', border: '1px solid var(--border)',
          borderRadius: 14, boxShadow: 'var(--shadow), var(--shadow-glow)',
          overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 18px', borderBottom: '1px solid var(--border)' }}>
          <svg width="15" height="15" viewBox="0 0 20 20" fill="var(--muted)">
            <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Jump to a page, model, report, pipeline…"
            style={{
              flex: 1, border: 'none', outline: 'none', background: 'transparent',
              color: 'var(--text)', fontSize: 14, fontFamily: 'inherit',
            }}
          />
          <kbd style={{
            fontSize: 10, color: 'var(--muted)', border: '1px solid var(--border)',
            borderRadius: 4, padding: '2px 6px', background: 'var(--surface)',
          }}>esc</kbd>
        </div>

        <div style={{ maxHeight: 380, overflowY: 'auto', padding: '6px 0' }}>
          {results.length === 0 && (
            <div style={{ padding: '18px 18px', color: 'var(--muted)', fontSize: 13 }}>
              No matches for “{query}”.
            </div>
          )}
          {results.map((it, i) => {
            const meta = KIND_META[it.kind]
            return (
              <div
                key={`${it.kind}-${it.label}`}
                onClick={() => go(it)}
                onMouseEnter={() => setCursor(i)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '9px 18px', cursor: 'pointer', fontSize: 13.5,
                  background: i === cursor ? 'var(--blue-lt)' : 'transparent',
                  borderLeft: `2px solid ${i === cursor ? meta.color : 'transparent'}`,
                }}
              >
                <span style={{
                  fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .5,
                  color: meta.color, background: `${meta.color}14`,
                  border: `1px solid ${meta.color}30`, borderRadius: 4,
                  padding: '1px 7px', width: 76, textAlign: 'center', flexShrink: 0,
                }}>{meta.tag}</span>
                <span style={{ color: 'var(--text)', fontWeight: i === cursor ? 600 : 400 }}>
                  {it.label}
                </span>
                {it.sub && (
                  <span style={{
                    marginLeft: 'auto', fontSize: 11.5, color: 'var(--muted)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 200,
                  }}>{it.sub}</span>
                )}
              </div>
            )
          })}
        </div>

        <div style={{
          padding: '8px 18px', borderTop: '1px solid var(--border)',
          display: 'flex', gap: 16, fontSize: 10.5, color: 'var(--muted)',
        }}>
          <span><kbd>↑↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  )
}
