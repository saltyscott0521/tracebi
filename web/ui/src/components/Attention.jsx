import { Link } from 'react-router-dom'
import { Badge, Verdict } from './Shared'
import { VERDICT_LABEL, needsAction, verdictOf } from '../verdict'
import { pipelineModels, pagePath, reportPagePath } from '../nav'

// What needs a person, from GET /api/desk plus the pipelines list: review
// notes, receipts that don't reproduce, failed refreshes, and sink checks
// that are stale or missing. Shown on the Reports page only when non-empty.

const SINK = {
  stale:       'Data changed since its checks last passed',
  no_contract: 'No data checks declared',
}

export function when(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const sameDay = d.toDateString() === new Date().toDateString()
  return sameDay
    ? d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function reportHref(name, models) {
  return name && name !== '_discovery' ? reportPagePath(name, models) : null
}

const NOTE = 'Review note'

/** The review notes among *items*: the one thing the Overview's line and a report's row do not already say. */
export const reviewNotes = items => items.filter(it => it.kind === NOTE)

// Each item carries `models`: the models it is about (none = the project).
// *modelsOf* maps a report name to the models it reads; *reports* is GET
// /api/reports, so a build whose files changed since needs a look here too.
export function attentionItems(desk, pipelines, modelsOf = () => [], reports = []) {
  const items = []
  for (const pin of desk?.pins || []) {
    items.push({
      key: `pin-${pin.report}-${pin.id}`, kind: NOTE, variant: 'blue',
      models: modelsOf(pin.report),
      title: pin.report === '_discovery' ? 'Project workbench' : pin.report,
      detail: pin.note || `Pin ${pin.id}`, href: reportHref(pin.report, modelsOf(pin.report)),
    })
  }
  // Every build the desk re-checked, and every receipt it could not pair with
  // a page (`verdicts` lists those too, with what the check said).
  const builds = new Map((desk?.builds || []).map(b => [b.report, b]))
  for (const row of desk?.verdicts || []) builds.set(row.report, { ...builds.get(row.report), ...row })
  for (const [name, build] of [...builds].sort(([a], [b]) => a.localeCompare(b))) {
    const v = verdictOf({ report: reports.find(r => r.name === name), build })
    if (!needsAction(v)) continue
    items.push({
      key: `verdict-${name}`, kind: VERDICT_LABEL[v.state], verdict: v.state,
      models: modelsOf(name),
      title: name, detail: v.detail,
      href: reportHref(name, modelsOf(name)),
    })
  }
  for (const p of pipelines || []) {
    for (const l of p.layers || []) {
      if (l.last_status !== 'failed') continue
      items.push({
        key: `run-${p.pipeline}-${l.name}`, kind: 'Refresh failed', variant: 'red',
        models: pipelineModels(p),
        title: `${p.pipeline} / ${l.name}`,
        detail: `Last run ${when(l.last_run) || 'recently'}`,
        href: pagePath('transform', pipelineModels(p)[0] || ''),
      })
    }
  }
  for (const s of desk?.sinks || []) {
    items.push({
      key: `sink-${s.table}`, kind: s.status === 'stale' ? 'Checks stale' : 'No checks',
      variant: s.status === 'stale' ? 'amber' : 'gray',
      models: [], title: s.table, detail: SINK[s.status] || s.status, href: '/models',
    })
  }
  return items
}

export function AttentionStrip({ items }) {
  if (!items.length) return null
  return (
    <section aria-label="Needs attention" style={{
      background: 'var(--card)', border: '1px solid var(--amber-br)',
      borderRadius: 'var(--radius)', overflow: 'hidden', marginBottom: 20,
    }}>
      <div style={{
        padding: '9px 16px', fontSize: 12.5, fontWeight: 700, color: 'var(--text)',
        background: 'var(--amber-lt)', borderBottom: '1px solid var(--amber-br)',
      }}>
        Needs attention · {items.length}
      </div>
      {items.map((it, i) => {
        const style = {
          display: 'flex', alignItems: 'center', gap: '6px 12px', flexWrap: 'wrap',
          padding: '10px 16px', textDecoration: 'none', color: 'inherit',
          borderBottom: i === items.length - 1 ? 'none' : '1px solid var(--border)',
        }
        const body = (
          <>
            {it.verdict
              ? <span style={{ flexShrink: 0, minWidth: 104 }}><Verdict state={it.verdict} /></span>
              : (
                <Badge variant={it.variant} style={{ textTransform: 'none', flexShrink: 0, minWidth: 104, textAlign: 'center' }}>
                  {it.kind}
                </Badge>
              )}
            <span style={{ flex: '1 1 14rem', minWidth: 0 }}>
              <span style={{ display: 'block', fontSize: 12.5, fontWeight: 600, color: 'var(--text)' }}>{it.title}</span>
              <span style={{ display: 'block', fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{it.detail}</span>
            </span>
          </>
        )
        return it.href
          ? <Link key={it.key} to={it.href} className="list-item-hover" style={style}>{body}</Link>
          : <div key={it.key} style={style}>{body}</div>
      })}
    </section>
  )
}
