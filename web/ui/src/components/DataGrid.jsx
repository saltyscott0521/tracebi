import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { tableExportUrl, useTableRows } from '../api'
import { count } from '../format'
import { Btn, ErrorDetail, ExportCsv, Skeleton, useToast } from './Shared'

// The one grid for rows of data: a table's page, a model's table inline, and
// later Ask's answer. Rows are read a page at a time from the table API
// (`/api/tables/{source}/{table}/rows`), sorted, searched and filtered by the
// engine, never in the browser. What is shown is a presentation of each value,
// never another number: separators and a date's shape only, with the raw value
// in the cell's title and on copy.
//
// It is a `<table role="grid">`, not a `.tb-list`: a list of things is the app's
// words, a grid holds the data's (scripts/ui_audit.py reads no date shapes in it).

export const PAGE_SIZE = 100

/** A column's kind, from its engine type: number, time, bool or text. */
export function kindOf(type) {
  const t = String(type || '').toUpperCase()
  if (/INT|DOUBLE|FLOAT|DECIMAL|NUMERIC|REAL/.test(t)) return 'number'
  if (/DATE|TIME/.test(t)) return 'time'
  if (/BOOL/.test(t)) return 'bool'
  return 'text'
}

// The closed operators of the API's `where`, in words, and those each kind takes.
export const OPS = {
  eq: '=', ne: '≠', lt: '<', le: '≤', gt: '>', ge: '≥',
  contains: 'contains', is_null: 'is empty', not_null: 'is not empty',
}
const OPS_FOR = {
  number: ['eq', 'ne', 'lt', 'le', 'gt', 'ge', 'is_null', 'not_null'],
  time: ['eq', 'ne', 'lt', 'le', 'gt', 'ge', 'is_null', 'not_null'],
  text: ['eq', 'ne', 'contains', 'is_null', 'not_null'],
  bool: ['eq', 'ne', 'is_null', 'not_null'],
}
const NO_VALUE = new Set(['is_null', 'not_null'])

// An identifier, a year or a code reads wrong with separators (2024 is not
// "2,024"): the same rule the report renderer's derived formats follow.
const UNGROUPED = /(^|_)(id|key|year|code)$/i

// Thousands separators on the number's own digits: the shortest form that
// reads back as the same double, so nothing is rounded away.
function grouped(v) {
  const s = String(v)
  if (!Number.isFinite(v) || /e/i.test(s)) return s
  const [whole, frac] = s.split('.')
  const neg = whole.startsWith('-')
  const digits = (neg ? whole.slice(1) : whole).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${neg ? '-' : ''}${digits}${frac ? `.${frac}` : ''}`
}

/** The raw value as text: what the title shows and a copy takes. */
export function rawText(v) {
  if (v === null || v === undefined) return ''
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

/**
 * How a cell shows *value* of a column (`{name, type}`): `{text, num, none}`.
 * Numbers with separators, a timestamp as `2031-10-20 14:03` (seconds when
 * there are any), a date as it is, null as `null`.
 */
export function cellText(value, column) {
  if (value === null || value === undefined) return { text: 'null', none: true }
  const kind = kindOf(column.type)
  if (kind === 'number' && typeof value === 'number') {
    return { text: UNGROUPED.test(column.name) ? String(value) : grouped(value), num: true }
  }
  if (kind === 'time' && typeof value === 'string') {
    const m = value.match(/^(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d)(:\d\d)?(\.\d+)?(.*)$/)
    if (m) return { text: `${m[1]} ${m[2]}${m[3] && m[3] !== ':00' ? m[3] : ''}${m[5] || ''}` }
  }
  return { text: rawText(value) }
}

// ── The cut: sort, search, filters and page ──────────────────────────────────

const NONE = { sort: '', desc: false, q: '', where: [], offset: 0 }

function readCut(params) {
  let where = []
  try {
    const got = JSON.parse(params.get('where') || '[]')
    if (Array.isArray(got)) where = got.filter(w => w && typeof w.column === 'string' && OPS[w.op])
  } catch { /* a hand-edited address: no filters */ }
  return {
    sort: params.get('sort') || '',
    desc: params.get('desc') === '1',
    q: params.get('q') || '',
    where,
    offset: Math.max(0, parseInt(params.get('offset') || '0', 10) || 0),
  }
}

function writeCut(params, cut) {
  const set = (k, v) => (v ? params.set(k, v) : params.delete(k))
  set('sort', cut.sort)
  set('desc', cut.sort && cut.desc ? '1' : '')
  set('q', cut.q)
  set('where', cut.where.length ? JSON.stringify(cut.where) : '')
  set('offset', cut.offset ? String(cut.offset) : '')
}

/**
 * The grid's cut and a way to change it. In the address (`sort`, `desc`, `q`,
 * `where`, `offset` in the query) when *inAddress*, so a cut can be linked and
 * Back steps back through sorts, filters and pages; otherwise local state.
 * `update(patch, {push})` pushes a history entry only when asked.
 */
export function useGridCut(inAddress) {
  const [params, setParams] = useSearchParams()
  const [local, setLocal] = useState(NONE)
  const key = params.toString()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const fromAddress = useMemo(() => readCut(params), [key])
  const update = useCallback((patch, { push = false } = {}) => {
    if (!inAddress) { setLocal(c => ({ ...c, ...patch })); return }
    setParams(p => {
      const next = new URLSearchParams(p)
      writeCut(next, { ...readCut(p), ...patch })
      return next
    }, { replace: !push })
  }, [inAddress, setParams])
  return [inAddress ? fromAddress : local, update]
}

// ── Copy ──────────────────────────────────────────────────────────────────────

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // An insecure origin has no clipboard API: the old way still works there.
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    ta.remove()
    return ok
  }
}

const ident = n => `"${String(n).replace(/"/g, '""')}"`
const literal = (v, kind) => (kind === 'number' || kind === 'bool' ? String(v) : `'${String(v).replace(/'/g, "''")}'`)
const SQL_OP = { eq: '=', ne: '<>', lt: '<', le: '<=', gt: '>', ge: '>=' }

/**
 * The cut as a DuckDB statement, for whoever takes it to a notebook:
 * `SELECT … FROM fact_holdings WHERE … ORDER BY … LIMIT 100`. Text to copy,
 * never run here.
 */
export function cutSql(source, table, columns, cut) {
  const ext = String(table).split('.').pop().toLowerCase()
  const from = source !== 'inputs' ? ident(table)
    : ext === 'parquet' ? `read_parquet('inputs/${table}')`
    : ext === 'json' ? `read_json_auto('inputs/${table}')`
    : `read_csv_auto('inputs/${table}')`
  const kinds = Object.fromEntries(columns.map(c => [c.name, kindOf(c.type)]))
  const conds = cut.where.map(w => {
    if (w.op === 'is_null') return `${ident(w.column)} IS NULL`
    if (w.op === 'not_null') return `${ident(w.column)} IS NOT NULL`
    if (w.op === 'contains') return `${ident(w.column)} ILIKE ${literal(`%${w.value}%`)}`
    return `${ident(w.column)} ${SQL_OP[w.op]} ${literal(w.value, kinds[w.column])}`
  })
  const text = columns.filter(c => kinds[c.name] === 'text')
  if (cut.q && text.length) {
    conds.push(`(${text.map(c => `${ident(c.name)} ILIKE ${literal(`%${cut.q}%`)}`).join(' OR ')})`)
  }
  return [
    `SELECT ${columns.map(c => ident(c.name)).join(', ') || '*'}`,
    `FROM ${from}`,
    conds.length ? `WHERE ${conds.join('\n  AND ')}` : null,
    cut.sort ? `ORDER BY ${ident(cut.sort)}${cut.desc ? ' DESC' : ''}` : null,
    `LIMIT ${PAGE_SIZE}`,
  ].filter(Boolean).join('\n')
}

// ── Filters ───────────────────────────────────────────────────────────────────

/** A filter in words: "fund_id = 2", "sector is empty". */
export const filterText = w => `${w.column} ${OPS[w.op]}${NO_VALUE.has(w.op) ? '' : ` ${w.value}`}`

// One filter, built from the closed ops for the column's kind. A number must
// read as one before it is applied.
function FilterForm({ columns, column: first, onApply, onCancel }) {
  const [column, setColumn] = useState(first || columns[0]?.name || '')
  const kind = kindOf(columns.find(c => c.name === column)?.type)
  const ops = OPS_FOR[kind]
  const [op, setOp] = useState(ops[0])
  const [value, setValue] = useState(kind === 'bool' ? 'true' : '')
  const valid = ops.includes(op) ? op : ops[0]
  const needs = !NO_VALUE.has(valid)
  const parsed = !needs ? null
    : kind === 'number' ? (value.trim() === '' ? NaN : Number(value))
    : kind === 'bool' ? value === 'true'
    : value
  const bad = needs && (kind === 'number' ? !Number.isFinite(parsed) : kind !== 'bool' && value === '')
  const submit = e => {
    e.preventDefault()
    if (bad) return
    onApply(needs ? { column, op: valid, value: parsed } : { column, op: valid })
  }
  return (
    <form className="grid__filter" onSubmit={submit} aria-label="Add a filter">
      <label>
        <span>Column</span>
        <select aria-label="Column" value={column} onChange={e => {
          setColumn(e.target.value)
          setValue(kindOf(columns.find(c => c.name === e.target.value)?.type) === 'bool' ? 'true' : '')
        }}>
          {columns.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
        </select>
      </label>
      <label>
        <span>Condition</span>
        <select aria-label="Condition" value={valid} onChange={e => setOp(e.target.value)}>
          {ops.map(o => <option key={o} value={o}>{OPS[o]}</option>)}
        </select>
      </label>
      {needs && (
        <label>
          <span>Value</span>
          {kind === 'bool' ? (
            <select aria-label="Value" value={value} onChange={e => setValue(e.target.value)}>
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : (
            <input aria-label="Value" value={value} onChange={e => setValue(e.target.value)} autoFocus
              inputMode={kind === 'number' ? 'decimal' : undefined}
              placeholder={kind === 'time' ? '2031-10-20' : kind === 'number' ? '0' : ''} />
          )}
        </label>
      )}
      <span className="grid__filter-act">
        <Btn size="sm" type="submit" disabled={bad}>Apply</Btn>
        <Btn size="sm" variant="outline" onClick={onCancel}>Cancel</Btn>
      </span>
    </form>
  )
}

// ── A column's menu ───────────────────────────────────────────────────────────

// Drawn outside the scrolling table (which would clip it), under the header's
// button. Arrow keys move through it; Escape closes it and returns focus.
function ColumnMenu({ column, at, sorted, onClose, onPick }) {
  const ref = useRef(null)
  useEffect(() => {
    ref.current?.querySelector('[role=menuitem]')?.focus()
    const away = e => { if (!ref.current?.contains(e.target)) onClose(false) }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [onClose])
  const keys = e => {
    const items = [...ref.current.querySelectorAll('[role=menuitem]')]
    const i = items.indexOf(document.activeElement)
    if (e.key === 'Escape') { e.preventDefault(); onClose(true) }
    else if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length]?.focus() }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length]?.focus() }
    else if (e.key === 'Tab') onClose(false)
  }
  const item = (key, text) => (
    <button key={key} type="button" role="menuitem" tabIndex={-1} onClick={() => onPick(key)}>{text}</button>
  )
  return (
    <div ref={ref} className="grid__menu" role="menu" aria-label={`Column ${column}`}
         style={{ left: at.left, top: at.top }} onKeyDown={keys}>
      {item('copy', 'Copy name')}
      {item('asc', 'Sort ascending')}
      {item('desc', 'Sort descending')}
      {sorted && item('unsort', 'Clear sort')}
      {item('filter', 'Filter…')}
    </div>
  )
}

// ── The grid ──────────────────────────────────────────────────────────────────

function Loading({ columns }) {
  const n = Math.max(columns?.length || 0, 4)
  return (
    <div className="grid__scroll" aria-busy="true">
      <table className="grid" role="grid" aria-label="Reading rows">
        <tbody>
          {Array.from({ length: 10 }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: n }).map((__, c) => (
                <td key={c}><Skeleton width={c % 3 === 0 ? 90 : 60} height={12} /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * The one grid for rows of one table, read through `/api/tables`.
 *
 * - *source*, *table*: the table's address (a connector's name or `inputs`;
 *   the table, or a path under inputs/).
 * - *columns* (optional): `[{name, type}]` already known (the table's detail),
 *   so the loading state has the right width.
 * - *inAddress*: keep the cut (sort, search, filters, page) in the address;
 *   off, it is the grid's own state (a grid mounted inside another page).
 * - *label*: the grid's accessible name (default "Rows of <table>").
 * - *dense*: a sample of the first *limit* rows (default 20), small, with no
 *   search, filters or pages (the data browser's inspector; its table's page
 *   has the rest).
 */
export default function DataGrid({ source, table, columns: known, inAddress = false, label, dense = false, limit = 20 }) {
  const toast = useToast()
  const [cut, update] = useGridCut(inAddress)
  const { data, isLoading, isFetching, error } = useTableRows(source, table, { ...cut, limit: dense ? limit : PAGE_SIZE })
  const columns = data?.columns || known || []
  const rows = data?.rows || []

  // The search box answers as you type, a moment after the last key. A new
  // search is a step Back undoes; refining it is not another one.
  const [typed, setTyped] = useState(cut.q)
  useEffect(() => { setTyped(cut.q) }, [cut.q])
  useEffect(() => {
    if (typed === cut.q) return undefined
    const t = setTimeout(() => update({ q: typed, offset: 0 }, { push: !cut.q && !!typed }), 300)
    return () => clearTimeout(t)
  }, [typed]) // eslint-disable-line react-hooks/exhaustive-deps

  const [filtering, setFiltering] = useState(null)      // null, or the column to start from ('' for any)
  const [menu, setMenu] = useState(null)                // {column, at, button}
  const [cell, setCell] = useState(null)                // {r, c}: the selected cell
  const rootRef = useRef(null)
  const scrollRef = useRef(null)
  const [more, setMore] = useState(false)

  // A grid wider than its card says so at its right edge while there is more.
  const measure = useCallback(() => {
    const el = scrollRef.current
    setMore(!!el && el.scrollWidth - el.clientWidth - el.scrollLeft > 1)
  }, [])
  useLayoutEffect(() => {
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [measure, data])

  // A new cut is a new set of rows: the selection does not carry over.
  useEffect(() => { setCell(null) }, [cut.sort, cut.desc, cut.q, cut.where, cut.offset])

  const say = useCallback(async (text, what) => {
    const ok = await copyText(text)
    toast?.(ok ? `Copied ${what}` : 'Could not copy', ok ? 'success' : 'error')
  }, [toast])

  const sortBy = (column, direction) => update({
    sort: direction ? column : '', desc: direction === 'desc', offset: 0,
  }, { push: true })
  // A header click goes ascending, then descending, then back to no sort.
  const cycle = column => {
    if (cut.sort !== column) sortBy(column, 'asc')
    else if (!cut.desc) sortBy(column, 'desc')
    else sortBy(column, null)
  }
  const addFilter = w => {
    setFiltering(null)
    update({ where: [...cut.where, w], offset: 0 }, { push: true })
  }
  const dropFilter = i => update({ where: cut.where.filter((_, j) => j !== i), offset: 0 }, { push: true })
  const clearAll = () => { setTyped(''); update({ where: [], q: '', offset: 0 }, { push: true }) }

  const openMenu = (column, button) => {
    const root = rootRef.current.getBoundingClientRect()
    const b = button.getBoundingClientRect()
    const left = Math.max(0, Math.min(b.right - root.left - 180, root.width - 184))
    setMenu({ column, button, at: { left, top: b.bottom - root.top + 4 } })
  }
  const menuRef = useRef(null)
  menuRef.current = menu
  const closeMenu = useCallback(refocus => {
    if (refocus) menuRef.current?.button?.focus()
    setMenu(null)
  }, [])
  const pick = key => {
    const column = menu.column
    closeMenu(key === 'copy')
    if (key === 'copy') say(column, `“${column}”`)
    else if (key === 'asc' || key === 'desc') sortBy(column, key)
    else if (key === 'unsort') sortBy(column, null)
    else if (key === 'filter') setFiltering(column)
  }

  // Arrow keys move the selected cell; ⌘C / Ctrl+C copies its raw value.
  const focusCell = (r, c) => {
    setCell({ r, c })
    rootRef.current?.querySelector(`[data-cell="${r}:${c}"]`)?.focus()
  }
  const onCellKey = (e, r, c) => {
    const last = { r: rows.length - 1, c: columns.length - 1 }
    const step = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] }[e.key]
    if (step) {
      e.preventDefault()
      focusCell(Math.min(last.r, Math.max(0, r + step[0])), Math.min(last.c, Math.max(0, c + step[1])))
    } else if (e.key === 'Home') {
      e.preventDefault(); focusCell(r, 0)
    } else if (e.key === 'End') {
      e.preventDefault(); focusCell(r, last.c)
    } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'c' && !window.getSelection()?.toString()) {
      e.preventDefault()
      say(rawText(rows[r][c]), 'the value')
    }
  }

  if (error) {
    return (
      <div className="grid-wrap">
        <ErrorDetail error={error} />
        {(cut.where.length > 0 || cut.q) && <Btn size="sm" variant="outline" onClick={clearAll}>Clear filters</Btn>}
      </div>
    )
  }
  if (data && data.connected === false) {
    return (
      <p className="src-quiet" data-connected="false">
        Not connected here · {data.variable ? <>set <code>{data.variable}</code></> : data.reason}
      </p>
    )
  }

  const total = data?.total ?? 0
  const approx = data && !data.total_exact ? '~' : ''
  const filtered = cut.where.length > 0 || !!cut.q
  const selected = cell && rows[cell.r] ? rows[cell.r][cell.c] : undefined
  const first = rows.length ? cut.offset + 1 : 0
  const lastRow = cut.offset + rows.length

  return (
    <div className={`grid-wrap${dense ? ' grid-wrap--dense' : ''}`} ref={rootRef}>
      {!dense && <div className="grid__bar">
        <div className="search-wrap grid__search">
          <span className="search-icon" aria-hidden="true">
            <svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <circle cx="9" cy="9" r="5.5" /><line x1="15" y1="15" x2="19" y2="19" />
            </svg>
          </span>
          <input type="search" className="search-input" value={typed} onChange={e => setTyped(e.target.value)}
                 placeholder="Search text columns…" aria-label={`Search ${table}`} />
        </div>
        <Btn size="sm" variant="outline" onClick={() => setFiltering(filtering === null ? '' : null)}
             aria-expanded={filtering !== null} disabled={!columns.length}>Add filter</Btn>
        <span className="grid__bar-end">
          <Btn size="sm" variant="outline" disabled={selected === undefined}
               title={selected === undefined ? 'Select a cell first' : rawText(selected)}
               onClick={() => say(rawText(selected), 'the value')}>Copy value</Btn>
          <Btn size="sm" variant="outline" disabled={!columns.length}
               title="This cut as a DuckDB SELECT, for a notebook"
               onClick={() => say(cutSql(source, table, columns, cut), 'the SQL')}>Copy SQL</Btn>
          <ExportCsv href={tableExportUrl(source, table, cut)}
                     title={filtered ? 'Every row that matches, not only this page' : 'Every row, not only this page'} />
        </span>
      </div>}

      {filtering !== null && (
        <FilterForm key={filtering} columns={columns} column={filtering} onApply={addFilter} onCancel={() => setFiltering(null)} />
      )}
      {cut.where.length > 0 && (
        <ul className="grid__chips" aria-label="Filters">
          {cut.where.map((w, i) => (
            <li key={`${i}-${filterText(w)}`}>
              <button type="button" className="grid__chip" onClick={() => dropFilter(i)}
                      aria-label={`Remove filter ${filterText(w)}`}>
                {filterText(w)} <span aria-hidden="true">×</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {isLoading && !data ? <Loading columns={known} /> : rows.length === 0 ? (
        <div className="grid__empty">
          {filtered
            ? <><p>No rows match.</p><Btn size="sm" variant="outline" onClick={clearAll}>Clear filters</Btn></>
            : <p>This table has no rows.</p>}
        </div>
      ) : (
        <div ref={scrollRef} onScroll={measure}
             className={`grid__scroll${more ? ' grid__scroll--more' : ''}${isFetching ? ' grid__scroll--busy' : ''}`}
             aria-busy={isFetching || undefined}>
          <table className="grid" role="grid" aria-label={label || `Rows of ${table}`}
                 aria-rowcount={total + 1} aria-colcount={columns.length}>
            <thead>
              <tr aria-rowindex={1}>
                {columns.map((col, c) => {
                  const on = cut.sort === col.name
                  const num = kindOf(col.type) === 'number'
                  return (
                    <th key={col.name} scope="col" aria-colindex={c + 1} className={num ? 'grid__num' : undefined}
                        aria-sort={on ? (cut.desc ? 'descending' : 'ascending') : 'none'}>
                      <span className="grid__th">
                        <button type="button" className="grid__sort" onClick={() => cycle(col.name)}
                                title={`Sort by ${col.name}`}>
                          <span className="grid__colname">{col.name}</span>
                          <span className="grid__type">{col.type}{on && <span aria-hidden="true">{cut.desc ? ' ↓' : ' ↑'}</span>}</span>
                        </button>
                        <button type="button" className="grid__menu-btn" aria-haspopup="menu"
                                aria-expanded={menu?.column === col.name}
                                aria-label={`${col.name}: copy, sort or filter`}
                                onClick={e => (menu?.column === col.name ? closeMenu(false) : openMenu(col.name, e.currentTarget))}>
                          <span aria-hidden="true">⋯</span>
                        </button>
                      </span>
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={cut.offset + r} aria-rowindex={cut.offset + r + 2}>
                  {row.map((v, c) => {
                    const shown = cellText(v, columns[c] || { name: '', type: '' })
                    const at = cell?.r === r && cell?.c === c
                    const roving = cell ? at : r === 0 && c === 0
                    return (
                      <td key={c} role="gridcell" data-cell={`${r}:${c}`} tabIndex={roving ? 0 : -1}
                          aria-selected={at || undefined} title={rawText(v) || 'null'}
                          className={[shown.num && 'grid__num', shown.none && 'grid__null', at && 'grid__cell--on'].filter(Boolean).join(' ') || undefined}
                          onClick={() => setCell({ r, c })} onFocus={() => !at && setCell({ r, c })}
                          onKeyDown={e => onCellKey(e, r, c)}>
                        {shown.text}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {rows.length > 0 && !dense && (
        <div className="grid__pager">
          <span className="grid__count" aria-live="polite">
            {first.toLocaleString('en-US')}–{lastRow.toLocaleString('en-US')} of {approx}{count(total, 'row')}
          </span>
          <Btn size="sm" variant="outline" aria-label="Previous rows" disabled={cut.offset === 0}
               onClick={() => update({ offset: Math.max(0, cut.offset - PAGE_SIZE) }, { push: true })}>‹</Btn>
          <Btn size="sm" variant="outline" aria-label="Next rows" disabled={lastRow >= total}
               onClick={() => update({ offset: cut.offset + PAGE_SIZE }, { push: true })}>›</Btn>
        </div>
      )}

      {menu && (
        <ColumnMenu column={menu.column} at={menu.at} sorted={cut.sort === menu.column}
                    onClose={closeMenu} onPick={pick} />
      )}
    </div>
  )
}
