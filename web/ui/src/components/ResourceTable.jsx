import { useEffect, useId, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { Chip, Empty, SearchInput } from './Shared'

// One list shape for every kind of resource under Data (design/control-tower.md,
// the console): a search box, filter chips, a count at the right, then a dense
// table whose headers sort it. Sources, Transforms, Warehouse and Models all
// draw theirs with it, so the same column means the same thing on each: Name
// (its identifier muted beside it), Type, Status (a pill, words.js
// statusWords), one count, who reads it or what it writes, Agents, Last
// activity, and a row menu (⋯) holding the row's actions. The search, the
// filter and the sort are the address's (?q=, ?filter=, ?sort=, "-name" for
// descending), so a cut of a list can be linked and Back undoes it.

/**
 * A state as a pill with a dot: *status* `{text, tone, title}` (statusWords).
 * Only Reproduces is green, as everywhere in the app (*tone* `good` is a
 * count of them, "11 reproduce"): Checks passed and Connected are said in the
 * neutral pill, a warning in amber, a failure in red.
 */
export function StatusPill({ status }) {
  if (!status?.text) return null
  if (status.text === 'Reproduces' || status.tone === 'good') {
    return <span className="verdict verdict--sm verdict--reproduces" title={status.title}>{status.text}</span>
  }
  const tone = { warn: 'warn', bad: 'bad', none: 'none' }[status.tone] || ''
  return <Chip tone={tone} title={status.title}>{status.text}</Chip>
}

/** The mechanism word (SQLite, SQL, fact, view), as a small mono chip. */
export function TypeChip({ children, title }) {
  if (!children) return null
  return <span className="rtype" title={title}>{children}</span>
}

/**
 * A menu of actions behind one button: the row menu (⋯) and a page's ▾
 * menus. *items*: `{label, to}` (a link), `{label, onClick}` or `{label,
 * href}`; a falsy item is left out, and with none left there is no button.
 * Escape or a click outside closes it.
 */
export function DropMenu({ items, label, children, variant = 'dots', align = 'right' }) {
  // Where the open menu sits (fixed, under its button), or null when shut.
  const [open, setOpen] = useState(null)
  const box = useRef(null)
  const placeOf = el => {
    const r = el.getBoundingClientRect()
    return align === 'left' ? { top: r.bottom + 4, left: r.left } : { top: r.bottom + 4, right: window.innerWidth - r.right }
  }
  const id = useId()
  const shown = (items || []).filter(Boolean)
  useEffect(() => {
    if (!open) return undefined
    const away = e => { if (!box.current?.contains(e.target)) setOpen(null) }
    const key = e => { if (e.key === 'Escape') { setOpen(null); box.current?.querySelector('button')?.focus() } }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', key)
    // Drawn fixed (a page's actions row scrolls on a phone, and would clip
    // it): a scroll moves it with its button.
    const off = () => setOpen(o => (o ? placeOf(box.current?.querySelector('button')) : o))
    window.addEventListener('scroll', off, true)
    return () => {
      document.removeEventListener('mousedown', away); document.removeEventListener('keydown', key)
      window.removeEventListener('scroll', off, true)
    }
  }, [!!open]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (open) box.current?.querySelector('[role="menuitem"]')?.focus({ preventScroll: true })
  }, [!!open]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!shown.length) return null
  const close = () => setOpen(null)
  return (
    <span className={`rmenu rmenu--${align}`} ref={box}>
      <button type="button" className={variant === 'dots' ? 'rmenu__dots' : 'btn-outline rmenu__btn'}
              aria-haspopup="menu" aria-expanded={!!open} aria-controls={open ? id : undefined} aria-label={label}
              onClick={e => { const el = e.currentTarget; setOpen(o => (o ? null : placeOf(el))) }}>
        {children || <span aria-hidden="true">⋯</span>}
      </button>
      {open && (
        <ul className="rmenu__list" role="menu" id={id} aria-label={label} style={open}>
          {shown.map(it => (
            <li key={it.label} role="none">
              {it.to
                ? <Link role="menuitem" to={it.to} onClick={close}>{it.label}</Link>
                : it.href
                  ? <a role="menuitem" href={it.href} onClick={close}>{it.label}</a>
                  : <button type="button" role="menuitem" disabled={it.disabled} title={it.title}
                            onClick={() => { close(); it.onClick() }}>{it.label}</button>}
            </li>
          ))}
        </ul>
      )}
    </span>
  )
}

/**
 * A resource's name in its list: what people call it, a link to its page,
 * its identifier muted beside it when that differs.
 */
export function NameCell({ to, label, id, code = false }) {
  const name = code ? <code>{label}</code> : label
  return (
    <span className="rname">
      {to ? <Link to={to} className="rname__link">{name}</Link> : <span className="rname__link">{name}</span>}
      {id && id !== label && <span className="rname__id">{id}</span>}
    </span>
  )
}

const compare = (a, b) => {
  if (a == null && b == null) return 0
  if (a == null) return 1
  if (b == null) return -1
  return typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b))
}

/**
 * The list. *columns*: `{key, label, render(row), sort(row)?, num?, wrap?}`
 * (a column with *sort* has a header that sorts by it; *wrap* lets a list of
 * names break across lines, every other cell stays on one); *rows* each carry a
 * `key`; *search(row)* the text the box matches; *filters*: `{key, label,
 * test(row)}` (the first is All, no test); *count(shown, total)* the words at
 * the right; *menu(row)* the row's actions (DropMenu items); *rowProps(row)*
 * attributes for its `<tr>` (a data-* the tests find it by); *label* names the
 * table; *empty* what an empty list says.
 */
export default function ResourceTable({
  columns, rows, search, filters = [], count, menu, rowProps, label, placeholder = 'Find…',
  defaultSort, empty, before,
}) {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') || ''
  const filter = filters.find(f => f.key === params.get('filter')) || filters[0]
  const sortParam = params.get('sort') || defaultSort || ''
  const desc = sortParam.startsWith('-')
  const sortKey = desc ? sortParam.slice(1) : sortParam
  const sortCol = columns.find(c => c.key === sortKey && c.sort)

  const set = patch => setParams(p => {
    const next = new URLSearchParams(p)
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)))
    return next
  }, { replace: true })

  const needle = q.trim().toLowerCase()
  let shown = rows.filter(r => (!filter?.test || filter.test(r)) && (!needle || (search?.(r) || '').toLowerCase().includes(needle)))
  if (sortCol) {
    shown = [...shown].sort((a, b) => compare(sortCol.sort(a), sortCol.sort(b)) * (desc ? -1 : 1))
  }
  const sortBy = col => {
    const next = sortKey === col.key && !desc ? `-${col.key}` : col.key
    set({ sort: next === defaultSort ? '' : next })
  }

  return (
    <div className="rlist">
      <div className="rlist__tools">
        <SearchInput value={q} onChange={v => set({ q: v })} placeholder={placeholder} label={placeholder}
                     style={{ padding: 0, borderBottom: 0, flex: '1 1 220px', maxWidth: 360 }} />
        {filters.length > 1 && (
          <div className="rlist__filters" role="group" aria-label="Show">
            {filters.map((f, i) => (
              <button key={f.key} type="button" className="rfilt" aria-pressed={f === filter}
                      onClick={() => set({ filter: i === 0 ? '' : f.key })}>{f.label}</button>
            ))}
          </div>
        )}
        <span className="rlist__count" aria-live="polite">{count ? count(shown.length, rows.length) : `${shown.length} of ${rows.length}`}</span>
      </div>
      {before}
      {shown.length === 0
        ? <Empty message={rows.length ? 'Nothing matches.' : empty} />
        : (
          <div className="rlist__scroll">
            <table className="rtable" aria-label={label}>
              <thead>
                <tr>
                  {columns.map(c => (
                    <th key={c.key} scope="col" className={c.num ? 'num' : undefined}
                        aria-sort={sortCol === c ? (desc ? 'descending' : 'ascending') : undefined}>
                      {c.sort
                        ? <button type="button" className="rtable__sort" onClick={() => sortBy(c)}>
                            {c.label}<span className="rtable__arrow" aria-hidden="true">{sortCol === c ? (desc ? '↓' : '↑') : ''}</span>
                          </button>
                        : c.label}
                    </th>
                  ))}
                  {menu && <th scope="col" className="rtable__menu"><span className="sr-only">Actions</span></th>}
                </tr>
              </thead>
              <tbody>
                {shown.map(r => (
                  <tr key={r.key} {...(rowProps ? rowProps(r) : {})}>
                    {columns.map(c => <td key={c.key} className={c.num ? 'num' : c.wrap ? 'wrap' : undefined}>{c.render(r)}</td>)}
                    {menu && <td className="rtable__menu"><DropMenu items={menu(r)} label={`Actions for ${r.label || r.key}`} /></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}
