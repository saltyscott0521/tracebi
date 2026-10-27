import { Fragment } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { DataFrame } from '../pages/Data'
import { LineageTab } from '../pages/Map'
import { lineagePath } from '../nav'
import { StatusPill, TypeChip } from './ResourceTable'
import { BtnLink, Empty, Time } from './Shared'

// One page shape for every resource under Data (design/control-tower.md, the
// console): the breadcrumb; the name with its type and status; one line of
// its facts; its actions top right, View lineage last on every one; then tabs
// at ?tab=, in one order: Overview (a grid of its facts, the passport's rows
// among them), the resource's own (Tables, Columns and Data, Steps and Code,
// Schema and Measures), Lineage (the map focused on it), Activity, Agents,
// Settings. A tab the resource has nothing for is left out, never shown empty.

const AFTER_LINEAGE = new Set(['activity', 'agents', 'settings'])

/**
 * The Overview grid: *items* `[term, value]`, three to a row on a wide
 * screen; a value that is null or empty reads "—". The passport's rows (From,
 * Read by, Last moved, Trust, Agents) are among them, in those words.
 */
export function Details({ items }) {
  return (
    <div className="rdetails">
      {items.filter(Boolean).map(([dt, dd]) => (
        <dl key={dt} data-row={dt}>
          <dt>{dt}</dt>
          <dd>{dd === null || dd === undefined || dd === '' ? <span className="pass__none">—</span> : dd}</dd>
        </dl>
      ))}
    </div>
  )
}

/** Names, each a link, comma-separated: *items* `[{key, to, label, code}]`. */
export function Links({ items, none = null }) {
  if (!items.length) return none
  return items.map((it, i) => (
    <Fragment key={it.key}>
      {i > 0 && ', '}
      {it.to ? <Link to={it.to}>{it.code ? <code>{it.label}</code> : it.label}</Link>
        : it.code ? <code>{it.label}</code> : it.label}
    </Fragment>
  ))
}

/**
 * What happened, newest first, one line each: a pill (*status*, statusWords'
 * shape), what (*what*, a link when *to*), a few words more (*sub*), and when
 * (*at*, or *when* in words). The Data home's Recent activity and Schedules,
 * and every page's Activity tab.
 */
export function ActivityList({ items, empty }) {
  if (!items.length) return <Empty message={empty} />
  return (
    <ul className="ract">
      {items.map(it => (
        <li key={it.key} className="ract__row">
          <StatusPill status={it.status} />
          <span className="ract__what">
            {it.to ? <Link to={it.to}>{it.what}</Link> : <b>{it.what}</b>}
            {it.sub && <span className="ract__sub"> · {it.sub}</span>}
          </span>
          <span className="ract__at">{it.when ?? <Time iso={it.at} fallback="—" />}</span>
        </li>
      ))}
    </ul>
  )
}

/**
 * A resource's page. *trail* / *here* / *code*: the breadcrumb (DataFrame);
 * *title* its name for people and *id* its identifier beside it; *type* the
 * mechanism chip; *status* the pill (statusWords); *sub* one line of facts;
 * *actions* its buttons, top right; *node* its graph id, which adds View
 * lineage and the Lineage tab; *tabs* `{key, label, count?, render()}` in
 * order, Overview first (falsy ones are left out); *tab* the one open when
 * the address names none (an older address's query picks it); *keep* the
 * query keys a tab change keeps (the rest are the tab's own).
 */
export default function ResourcePage({
  trail, here, code, title, id, type, typeTitle, status, sub, actions, node, tabs, tab: fallback, keep = [],
}) {
  const [params, setParams] = useSearchParams()
  const shown = tabs.filter(Boolean)
  if (node) {
    const at = shown.findIndex(t => AFTER_LINEAGE.has(t.key))
    shown.splice(at === -1 ? shown.length : at, 0, { key: 'lineage', label: 'Lineage', render: () => <LineageTab node={node} /> })
  }
  const asked = params.get('tab') || fallback
  const current = shown.find(t => t.key === asked) || shown[0]
  const pick = key => setParams(p => {
    const next = new URLSearchParams()
    keep.forEach(k => { if (p.get(k)) next.set(k, p.get(k)) })
    if (key !== shown[0].key) next.set('tab', key)
    return next
  })
  return (
    <DataFrame trail={trail} here={here} code={code}>
      <div className="rpage fade-in">
        <header className="rpage__head">
          <div className="rpage__titles">
            <div className="rpage__title">
              <h1 className={`rpage__name${code ? ' rpage__name--code' : ''}`}>{title}</h1>
              {id && id !== title && <code className="rname__id">{id}</code>}
              <TypeChip title={typeTitle}>{type}</TypeChip>
              <StatusPill status={status} />
            </div>
            {sub && <p className="rpage__sub">{sub}</p>}
          </div>
          <div className="rpage__acts">
            {actions}
            {node && <BtnLink size="sm" to={lineagePath(node)}>View lineage</BtnLink>}
          </div>
        </header>
        <div className="rtabs" role="tablist" aria-label="What to show">
          {shown.map(t => (
            <button key={t.key} type="button" role="tab" id={`rtab-${t.key}`} aria-controls="rpanel"
                    aria-selected={t === current} onClick={() => pick(t.key)}>
              {t.label}{t.count != null && <span className="rtabs__n">{t.count}</span>}
            </button>
          ))}
        </div>
        <div id="rpanel" role="tabpanel" aria-labelledby={`rtab-${current.key}`} className="rtabpanel">
          {current.render()}
        </div>
      </div>
    </DataFrame>
  )
}
