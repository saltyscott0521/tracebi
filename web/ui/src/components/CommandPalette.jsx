import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useModels, useReports, usePipelines, useRole, useGuides, useWarehouses } from '../api'
import {
  PAGES, placesFor, askPath, dataPath, docPath, mapPath, reportPagePath, pipelineModels,
  sourcesPath, tablePath, warehousePath,
} from '../nav'
import { count } from '../format'
import { encodeQuery } from '../ask'

// Static page destinations — always available, even before data loads. The
// places the role sees (the sidebar's), the pages inside them, then the
// handbook's first page.
function pagesFor(role) {
  const places = placesFor(role)
  const inside = key => PAGES.filter(p => p.parent === key)
    .map(p => ({ label: p.key === 'verify' ? 'Verify a file' : p.label, path: p.path, kind: 'page', sub: p.sub }))
  return [
    ...places.map(p => ({ label: p.label, path: p.path, kind: 'page', sub: p.sub })),
    ...places.flatMap(p => inside(p.key)),
    ...(places.some(p => p.key === 'data') ? [
      { label: 'Sources', path: sourcesPath(), kind: 'page', sub: 'Every connection and input file, and what reads each.' },
      { label: 'Warehouse', path: warehousePath(), kind: 'page', sub: 'Every table: who wrote it, who reads it, its checks.' },
      { label: 'Map', path: mapPath(), kind: 'page', sub: 'Every model as one picture: what feeds what.' },
    ] : []),
    { label: 'Get started', path: docPath('get-started'), kind: 'doc', sub: 'How TraceBi fits together, in five steps.' },
  ]
}

// Handbook pages that are not listed in Docs (internal, retired, or the
// design notes under docs/architecture/).
const UNLISTED = /^architecture--|(^|--)(north-star|ROADMAP|receipts)$/

const KIND_META = {
  page:      { tag: 'Page',      color: 'var(--role-table)' },
  doc:       { tag: 'Doc',       color: 'var(--muted)' },
  model:     { tag: 'Model',     color: 'var(--phase-model)' },
  report:    { tag: 'Report',    color: 'var(--phase-report)' },
  pipeline:  { tag: 'Pipeline',  color: 'var(--phase-transform)' },
  table:     { tag: 'Table',     color: 'var(--role-table)' },
  measure:   { tag: 'Measure',   color: 'var(--phase-model)' },
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  const { data: models }     = useModels()
  const { data: reports }    = useReports()
  const { data: pipelines }  = usePipelines()
  const { data: guides }     = useGuides()
  const role = useRole()

  // A model opens its Data page for those who see Data, else Ask of it; a
  // pipeline lives only on Data.
  const seesData = placesFor(role).some(p => p.key === 'data')
  // Tables live on Data: the warehouses' are asked for once the palette opens.
  const { data: warehouses } = useWarehouses(open && seesData)
  const items = useMemo(() => [
    ...pagesFor(role),
    ...(models     || []).map(m => ({
      label: m.label || m.name,
      path: seesData ? dataPath(m.name) : askPath(m.name),
      kind: 'model',
      sub: `${m.tables.length} tables`,
    })),
    ...(reports    || []).map(r => ({ label: r.display_name || r.name, path: reportPagePath(r.name), kind: 'report', sub: r.description })),
    ...(seesData ? pipelines || [] : []).map(p => ({
      label: p.pipeline,
      path: pipelineModels(p)[0] ? dataPath(pipelineModels(p)[0], 'transform') : '/data',
      kind: 'pipeline',
      sub: `${(p.layers || []).length} steps${pipelineModels(p).length ? ` · ${pipelineModels(p).join(', ')}` : ''}`,
    })),
    // Every warehouse table (its own page), and every measure: its model's
    // Measures view on Data, else Ask with the measure asked.
    ...(seesData ? warehouses?.warehouses || [] : []).flatMap(w => (w.tables || []).map(t => ({
      label: t.name, path: tablePath(w.name, t.name), kind: 'table',
      sub: [w.name, t.rows != null && count(t.rows, 'row')].filter(Boolean).join(' · '),
    }))),
    ...(models || []).flatMap(m => (m.measures || []).map(name => ({
      label: name,
      path: seesData
        ? `${dataPath(m.name)}?view=measures&measure=${encodeURIComponent(name)}`
        : `${askPath(m.name)}&q=${encodeURIComponent(encodeQuery({ measures: [name], dimensions: [], filters: {} }))}`,
      kind: 'measure',
      sub: m.label || m.name,
    }))),
    // The handbook, page by page, by title (everyone sees Docs).
    ...(guides || []).filter(g => !UNLISTED.test(g.name) && g.name !== 'index').map(g => ({
      label: (g.title || g.name).replace(/`/g, ''), path: docPath(g.name), kind: 'doc',
    })),
  ], [models, reports, pipelines, guides, role, seesData, warehouses])

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
                key={`${it.kind}-${it.path}`}
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
                  fontSize: 10, fontWeight: 600,
                  color: meta.color, background: `color-mix(in srgb, ${meta.color} 8%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${meta.color} 19%, transparent)`, borderRadius: 4,
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
