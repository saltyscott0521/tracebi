import { Link } from 'react-router-dom'
import { Badge } from './Shared'

// What needs a person, from GET /api/desk plus the pipelines list: review
// notes, receipts that don't reproduce, failed refreshes, and sink checks
// that are stale or missing. Shown on the Reports page only when non-empty.

// Receipt-level verdicts from tracebi/verify.py (plus the desk's own
// "error"). Only `reproduces` is good; only `unverifiable` (honestly
// python-derived) is quiet. Anything else, including a verdict this page
// doesn't know, needs attention: the bias is toward loud.
const VERDICT = {
  reproduces:           { label: 'Reproduces',        variant: 'green' },
  unverifiable:         { label: 'Not re-runnable',   variant: 'gray',
                          detail: 'Its numbers come from report.py, so they cannot be re-run.' },
  source_drift:         { label: 'Source changed',    variant: 'amber',
                          detail: 'The data changed since it was built. Rebuild to refresh it.' },
  not_reproduced:       { label: "Doesn't reproduce", variant: 'red',
                          detail: 'Re-running its queries gave different numbers, for a reason not yet known.' },
  nothing_to_verify:    { label: 'Nothing to check',  variant: 'amber',
                          detail: 'Its last build recorded no numbers to check.' },
  refused_newer_schema: { label: 'Newer build',       variant: 'amber',
                          detail: 'Built by a newer TraceBi than this server runs.' },
  error:                { label: 'Check failed',      variant: 'red' },
}

const SINK = {
  stale:       'Data changed since its checks last passed',
  no_contract: 'No data checks declared',
}

export function verdictOf(v) {
  return VERDICT[v] || { label: v || 'Unknown', variant: 'amber' }
}

const isQuiet = v => ['green', 'gray'].includes(verdictOf(v).variant)

export function when(iso) {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const sameDay = d.toDateString() === new Date().toDateString()
  return sameDay
    ? d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function reportHref(name) {
  return name && name !== '_discovery' ? `/reports?r=${encodeURIComponent(name)}` : null
}

export function attentionItems(desk, pipelines) {
  const items = []
  for (const pin of desk?.pins || []) {
    items.push({
      key: `pin-${pin.report}-${pin.id}`, kind: 'Review note', variant: 'blue',
      title: pin.report === '_discovery' ? 'Project workbench' : pin.report,
      detail: pin.note || `Pin ${pin.id}`, href: reportHref(pin.report),
    })
  }
  for (const row of desk?.verdicts || []) {
    if (isQuiet(row.verdict)) continue
    const v = verdictOf(row.verdict)
    items.push({
      key: `verdict-${row.report}`, kind: v.label, variant: v.variant,
      title: row.report, detail: v.detail || row.detail || 'Its last build needs a look.',
      href: reportHref(row.report),
    })
  }
  for (const p of pipelines || []) {
    for (const l of p.layers || []) {
      if (l.last_status !== 'failed') continue
      items.push({
        key: `run-${p.pipeline}-${l.name}`, kind: 'Refresh failed', variant: 'red',
        title: `${p.pipeline} / ${l.name}`,
        detail: `Last run ${when(l.last_run) || 'recently'}`, href: '/pipelines',
      })
    }
  }
  for (const s of desk?.sinks || []) {
    items.push({
      key: `sink-${s.table}`, kind: s.status === 'stale' ? 'Checks stale' : 'No checks',
      variant: s.status === 'stale' ? 'amber' : 'gray',
      title: s.table, detail: SINK[s.status] || s.status, href: '/models',
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
            <Badge variant={it.variant} style={{ textTransform: 'none', flexShrink: 0, minWidth: 104, textAlign: 'center' }}>
              {it.kind}
            </Badge>
            <span style={{ flex: '1 1 14rem', minWidth: 0 }}>
              <span style={{ display: 'block', fontFamily: "'IBM Plex Mono', monospace", fontSize: 12.5, color: 'var(--text)' }}>{it.title}</span>
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
