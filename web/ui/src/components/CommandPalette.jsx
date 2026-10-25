import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useModels, usePipelines, useRole, useGuides, useWarehouses } from '../api'
import {
  PAGES, placesFor, askPath, dataPath, dataTabPath, docPath, flowPath, GET_STARTED, reportPagePath, pipelineModels,
  sourcesPath, tablePath, transformsPath, warehousePath,
} from '../nav'
import { count } from '../format'
import { encodeQuery } from '../ask'
import { folderPath, hueStyle, reportLabel, useBuilds, useLibrary } from '../folders'
import { VERDICT_LABEL } from '../verdict'
import { ReportCover } from './Cover'

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
      { label: 'Flow', path: flowPath(), kind: 'page', sub: 'The board: sources, transforms, warehouse, models and reports, as the data moves.' },
      { label: 'Sources', path: sourcesPath(), kind: 'page', sub: 'Every connection and input file, and what reads each.' },
      { label: 'Transforms', path: transformsPath(), kind: 'page', sub: 'Every file in transforms/: its form, what it feeds, its checks.' },
      { label: 'Warehouse', path: warehousePath(), kind: 'page', sub: 'Every table: who wrote it, who reads it, its checks.' },
      { label: 'Models', path: dataTabPath('models'), kind: 'page', sub: 'Every model as a chain: sources, transform, tables, measures, reports.' },
    ] : []),
    { label: 'Get started', path: docPath(GET_STARTED), kind: 'doc', sub: 'Install, scaffold a project, and build one verified report.' },
  ]
}

// Each kind's word (a query that starts it lists that kind) and its group.
// The groups, in order: what a person most often jumps to first.
const KIND_META = {
  folder:   { tag: 'Folder',   group: 'folder' },
  report:   { tag: 'Report',   group: 'report' },
  table:    { tag: 'Table',    group: 'table' },
  model:    { tag: 'Model',    group: 'model', glyph: '◇' },
  measure:  { tag: 'Measure',  group: 'model', glyph: 'ƒ' },
  pipeline: { tag: 'Pipeline', group: 'model', glyph: '▸' },
  page:     { tag: 'Page',     group: 'place', glyph: '→' },
  doc:      { tag: 'Doc',      group: 'place', glyph: '¶' },
}
const GROUPS = [
  ['recent', 'Recent'], ['folder', 'Folders'], ['report', 'Reports'], ['table', 'Tables'],
  ['model', 'Models'], ['place', 'Places'],
]
// A table's glyph is what it is in the model that reads it.
const TABLE_GLYPH = { fact: ['Σ', 'Fact'], dimension: ['⚷', 'Dimension'], table: ['▦', 'Table'] }
const PER_GROUP = 6

// The last six things picked, newest first, kept in this browser (a
// convenience: without storage the palette simply starts with no Recent).
const RECENT_KEY = 'tracebi-palette-recent'
const RECENT_MAX = 6
const keyOf = it => `${it.kind}:${it.path}`
function readRecent() {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    return Array.isArray(v) ? v.filter(k => typeof k === 'string').slice(0, RECENT_MAX) : []
  } catch { return [] }
}
function remember(item) {
  const next = [keyOf(item), ...readRecent().filter(k => k !== keyOf(item))].slice(0, RECENT_MAX)
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(next)) } catch { /* private window */ }
}

// What leads a row: a folder's hue, a report's cover (its picture, else the
// drawn one), a table's kind, else the kind's glyph.
function Lead({ it }) {
  if (it.kind === 'folder') return <span className="cp__hue" style={hueStyle(it.hue)} aria-hidden="true" />
  if (it.kind === 'report') {
    return (
      <span className="cp__thumb" aria-hidden="true">
        <ReportCover report={it.report} name={it.label} build={it.build} />
      </span>
    )
  }
  const [glyph, word] = it.kind === 'table' ? TABLE_GLYPH[it.tableKind] : [KIND_META[it.kind].glyph, KIND_META[it.kind].tag]
  return <span className={`cp__glyph cp__glyph--${it.tableKind || it.kind}`} title={word} aria-hidden="true">{glyph}</span>
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const [recent, setRecent] = useState(readRecent)
  const inputRef = useRef(null)
  const listRef = useRef(null)
  const navigate = useNavigate()

  const { data: models }     = useModels()
  const { data: pipelines }  = usePipelines()
  const { data: guides }     = useGuides()
  const library = useLibrary()
  const { builds, verdictFor } = useBuilds()
  const role = useRole()

  // A model opens its Data page for those who see Data, else Ask of it; a
  // pipeline lives only on Data.
  const seesData = placesFor(role).some(p => p.key === 'data')
  // Tables live on Data: the warehouses' are asked for once the palette opens.
  const { data: warehouses } = useWarehouses(open && seesData)
  const items = useMemo(() => {
    // What each table is, and which models read it, from the models' own lists.
    const readers = {}
    ;(models || []).forEach(m => (m.tables || []).forEach(t => {
      const r = readers[t] || (readers[t] = { kind: 'table', models: [] })
      if ((m.facts || []).includes(t)) r.kind = 'fact'
      else if ((m.dimensions || []).includes(t) && r.kind !== 'fact') r.kind = 'dimension'
      r.models.push(m.label || m.name)
    }))
    return [
      // A folder is found by its name or its path, not by its count ("6 reports").
      ...library.folders.map(f => ({
        label: f.label, path: folderPath(f.path), kind: 'folder', hue: f.hue, sub: count(f.items.length, 'report'),
        find: `${f.label} ${f.path}`,
      })),
      ...library.all.map(r => ({
        label: reportLabel(r), path: reportPagePath(r.name), kind: 'report', sub: r.description,
        report: r, build: builds[r.name], verdict: verdictFor(r),
      })),
      // Every warehouse table (its own page), with what it is and who reads it.
      ...(seesData ? warehouses?.warehouses || [] : []).flatMap(w => (w.tables || []).map(t => ({
        label: t.name, path: tablePath(w.name, t.name), kind: 'table', tableKind: readers[t.name]?.kind || 'table',
        sub: [readers[t.name]?.models.join(', ') || w.name, t.rows != null && count(t.rows, 'row')].filter(Boolean).join(' · '),
      }))),
      ...(models     || []).map(m => ({
        label: m.label || m.name,
        path: seesData ? dataPath(m.name) : askPath(m.name),
        kind: 'model',
        sub: `${m.tables.length} tables`,
      })),
      // Every measure: its model's Measures view on Data, else Ask with the measure asked.
      ...(models || []).flatMap(m => (m.measures || []).map(name => ({
        label: name,
        path: seesData
          ? `${dataPath(m.name)}?view=measures&measure=${encodeURIComponent(name)}`
          : `${askPath(m.name)}&q=${encodeURIComponent(encodeQuery({ measures: [name], dimensions: [], filters: {} }))}`,
        kind: 'measure',
        sub: m.label || m.name,
      }))),
      ...(seesData ? pipelines || [] : []).map(p => ({
        label: p.pipeline,
        path: pipelineModels(p)[0] ? dataPath(pipelineModels(p)[0], 'transform') : '/data',
        kind: 'pipeline',
        sub: `${(p.layers || []).length} steps${pipelineModels(p).length ? ` · ${pipelineModels(p).join(', ')}` : ''}`,
      })),
      ...pagesFor(role),
      // The handbook, page by page, by title (everyone sees Docs); Get started
      // is listed above.
      ...(guides?.sections || []).flatMap(s => s.pages)
        .filter(g => g.name !== GET_STARTED).map(g => ({
          label: (g.title || g.name).replace(/`/g, ''), path: docPath(g.name), kind: 'doc',
        })),
    ]
  }, [models, pipelines, guides, role, seesData, warehouses, library, builds, verdictFor])

  // The results as groups. With no query: the recent picks, the folders and
  // the places. With one: what matches, a few per group, recent picks first.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    const rank = it => { const i = recent.indexOf(keyOf(it)); return i < 0 ? RECENT_MAX : i }
    if (!q) {
      const byKey = Object.fromEntries(items.map(it => [keyOf(it), it]))
      const picked = recent.map(k => byKey[k]).filter(Boolean)
      const seen = new Set(picked.map(keyOf))
      return [
        ['recent', picked],
        ['folder', items.filter(it => it.kind === 'folder' && !seen.has(keyOf(it)))],
        ['place', items.filter(it => it.kind === 'page' && !seen.has(keyOf(it))).slice(0, PER_GROUP)],
      ].filter(([, list]) => list.length)
    }
    const hits = items.filter(it =>
      (it.find ?? `${it.label} ${it.sub || ''}`).toLowerCase().includes(q) ||
      KIND_META[it.kind].tag.toLowerCase().startsWith(q))
    return GROUPS.filter(([g]) => g !== 'recent')
      .map(([g]) => [g, hits.filter(it => KIND_META[it.kind].group === g)
        .sort((a, b) => rank(a) - rank(b)).slice(0, PER_GROUP)])
      .filter(([, list]) => list.length)
  }, [items, query, recent])
  const results = useMemo(() => groups.flatMap(([, list]) => list), [groups])

  const close = useCallback(() => {
    setOpen(false)
    setQuery('')
    setCursor(0)
  }, [])

  const go = useCallback(item => {
    if (item) {
      remember(item)
      setRecent(readRecent())
      navigate(item.path)
    }
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

  // The row under the cursor stays in view as the arrows move it.
  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  if (!open) return null

  const onInputKey = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); go(results[cursor]) }
  }

  const title = Object.fromEntries(GROUPS)
  let index = -1
  return (
    <div className="cp" onClick={close}>
      <div className="cp__box fade-in" onClick={e => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Jump to anything">
        <div className="cp__field">
          <svg width="15" height="15" viewBox="0 0 20 20" fill="var(--muted)" aria-hidden="true">
            <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Jump to a page, model, report, pipeline…"
            aria-label="Jump to anything"
            role="combobox" aria-expanded="true" aria-controls="cp-list"
            aria-activedescendant={results[cursor] ? `cp-${cursor}` : undefined}
          />
          <kbd className="cp__kbd">esc</kbd>
        </div>

        <div className="cp__list" id="cp-list" role="listbox" aria-label="Results" ref={listRef}>
          {results.length === 0 && (
            <div className="cp__none">{query.trim() ? `No matches for “${query}”.` : 'Type to find a report, a folder, a table or a page.'}</div>
          )}
          {groups.map(([g, list]) => (
            <div key={g} role="group" aria-label={title[g]}>
              <div className="cp__group" aria-hidden="true">{title[g]}</div>
              {list.map(it => {
                index += 1
                const i = index
                return (
                  <div key={`${g}-${keyOf(it)}`} id={`cp-${i}`} role="option" aria-selected={i === cursor}
                       className="cp__row" onClick={() => go(it)} onMouseEnter={() => setCursor(i)}>
                    <Lead it={it} />
                    <span className="cp__label">{it.label}</span>
                    {it.sub && <span className="cp__sub" title={it.sub}>{it.sub}</span>}
                    {it.verdict && VERDICT_LABEL[it.verdict.state] && (
                      <span className={`cp__dot verdict--${it.verdict.state}`} title={VERDICT_LABEL[it.verdict.state]}>
                        <span className="sr-only">{VERDICT_LABEL[it.verdict.state]}</span>
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          ))}
        </div>

        <div className="cp__foot">
          <span><kbd>↑↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  )
}
