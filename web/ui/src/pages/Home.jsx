import { Link } from 'react-router-dom'
import { useModels, useReports, usePipelines, useDesk } from '../api'
import { Skeleton, Badge } from '../components/Shared'

// The Desk answers two questions, in order: does anything need me, and what
// state is each report in? Teaching material lives on its own pages
// (Workflow, Get Started, Docs); an empty project gets one pointer there.

// ── Plain-word labels for what the API reports ─────────────────────────────

// Receipt-level verdicts from tracebi/verify.py (plus the desk's own
// "error"). Only `reproduces` is good; only `unverifiable` (honestly
// python-derived) is quiet. Anything else, including a verdict this page
// doesn't know, is shown as needing attention: the bias is toward loud.
const VERDICT = {
  reproduces:           { label: 'Reproduces',        variant: 'green' },
  unverifiable:         { label: 'Not re-runnable',   variant: 'gray',
                          detail: 'Its numbers come from report.py, so they cannot be re-run.' },
  source_drift:         { label: 'Source changed',    variant: 'amber',
                          detail: 'The data changed since it was built. Rebuild to refresh it.' },
  not_reproduced:       { label: "Doesn't reproduce", variant: 'red',
                          detail: 'Re-running its queries gave different numbers, for a reason not yet known.' },
  nothing_to_verify:    { label: 'Empty receipt',     variant: 'amber',
                          detail: 'The receipt records no numbers to check.' },
  refused_newer_schema: { label: 'Newer receipt',     variant: 'amber',
                          detail: 'Built by a newer TraceBi than this server runs.' },
  error:                { label: 'Check failed',      variant: 'red' },
}

const SINK = {
  stale:       'Data changed since its checks last passed',
  no_contract: 'No data checks declared',
}

function verdictOf(v) {
  return VERDICT[v] || { label: v || 'Unknown', variant: 'amber' }
}

const isQuiet = v => ['green', 'gray'].includes(verdictOf(v).variant)

function when(iso) {
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

// ── Building blocks ────────────────────────────────────────────────────────

function Panel({ children }) {
  return (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', overflow: 'hidden',
    }}>{children}</div>
  )
}

function SectionHead({ title, count, action }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', margin: 0 }}>{title}</h2>
      {count != null && (
        <span style={{ fontSize: 12, color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>{count}</span>
      )}
      {action && (
        <Link to={action.href} style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--accent-text)', textDecoration: 'none' }}>
          {action.label} →
        </Link>
      )}
    </div>
  )
}

function Row({ href, children, last }) {
  const style = {
    display: 'flex', alignItems: 'center', gap: '6px 12px', flexWrap: 'wrap',
    padding: '11px 16px', textDecoration: 'none', color: 'inherit',
    borderBottom: last ? 'none' : '1px solid var(--border)',
  }
  return href
    ? <Link to={href} className="list-item-hover" style={style}>{children}</Link>
    : <div style={style}>{children}</div>
}

function Name({ children, sub }) {
  return (
    <span style={{ flex: '1 1 14rem', minWidth: 0 }}>
      <span style={{
        display: 'block', fontFamily: "'IBM Plex Mono', monospace", fontSize: 12.5,
        color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>{children}</span>
      {sub && (
        <span style={{
          display: 'block', fontSize: 12, color: 'var(--muted)', marginTop: 2,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{sub}</span>
      )}
    </span>
  )
}

function Loading() {
  return (
    <div style={{ padding: '14px 16px' }}>
      <Skeleton height={13} style={{ marginBottom: 10 }} />
      <Skeleton width="70%" height={13} />
    </div>
  )
}

// ── Needs attention ────────────────────────────────────────────────────────

function attentionItems(desk, pipelines) {
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
      title: row.report, detail: v.detail || row.detail || 'Its receipt needs a look.',
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

function NeedsAttention({ items, loading }) {
  if (loading) return <Panel><Loading /></Panel>
  if (!items.length) {
    return (
      <Panel>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 16px', fontSize: 13, color: 'var(--text-2)' }}>
          <span aria-hidden="true" style={{ color: 'var(--green-text)', fontWeight: 700 }}>✓</span>
          Nothing needs you right now.
        </div>
      </Panel>
    )
  }
  return (
    <Panel>
      {items.map((it, i) => (
        <Row key={it.key} href={it.href} last={i === items.length - 1}>
          <Badge variant={it.variant} style={{ textTransform: 'none', flexShrink: 0, minWidth: 104, textAlign: 'center' }}>
            {it.kind}
          </Badge>
          <Name sub={it.detail}>{it.title}</Name>
        </Row>
      ))}
    </Panel>
  )
}

// ── Reports ────────────────────────────────────────────────────────────────

function ReportsList({ reports, desk, loading }) {
  if (loading) return <Panel><Loading /></Panel>
  if (!reports?.length) {
    return (
      <Panel>
        <div style={{ padding: '14px 16px', fontSize: 13, color: 'var(--muted)', lineHeight: 1.6 }}>
          No reports yet. Scaffold one with <code>tracebi new-report</code>.
        </div>
      </Panel>
    )
  }
  const builds = Object.fromEntries((desk?.builds || []).map(b => [b.report, b]))
  const notes = new Set((desk?.drafts || []).map(d => d.report))
  const rank = r => {
    const b = builds[r.name]
    if (!b) return [2, '']
    return [isQuiet(b.verdict) ? 1 : 0, b.built_at || '']
  }
  const sorted = [...reports].sort((a, b) => {
    const [ra, ta] = rank(a), [rb, tb] = rank(b)
    if (ra !== rb) return ra - rb
    if (ta !== tb) return ta < tb ? 1 : -1
    return a.name.localeCompare(b.name)
  })
  return (
    <Panel>
      {sorted.map((r, i) => {
        const b = builds[r.name]
        const v = b ? verdictOf(b.verdict) : null
        return (
          <Row key={r.name} href={reportHref(r.name)} last={i === sorted.length - 1}>
            <Name sub={r.description}>{r.name}</Name>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
              {notes.has(r.name) && (
                <span title="The template has working-notes blocks. They show in tracebi dev and are removed from the built report."
                      style={{ fontSize: 11.5, color: 'var(--muted)' }}>
                  working notes
                </span>
              )}
              {b && (
                <span style={{ fontSize: 11.5, color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>
                  built {when(b.built_at) || '—'}
                </span>
              )}
              {v && <Badge variant={v.variant} style={{ textTransform: 'none' }}>{v.label}</Badge>}
            </span>
          </Row>
        )
      })}
    </Panel>
  )
}

// ── Recent data refreshes ──────────────────────────────────────────────────

function Refreshes({ pipelines, loading }) {
  if (loading) return <Panel><Loading /></Panel>
  const runs = (pipelines || [])
    .flatMap(p => (p.layers || []).map(l => ({ ...l, pipeline: p.pipeline })))
    .filter(l => l.last_run)
    .sort((a, b) => new Date(b.last_run) - new Date(a.last_run))
    .slice(0, 5)
  if (!runs.length) {
    return (
      <Panel>
        <div style={{ padding: '14px 16px', fontSize: 13, color: 'var(--muted)' }}>
          No refreshes have run yet.
        </div>
      </Panel>
    )
  }
  return (
    <Panel>
      {runs.map((l, i) => {
        const failed = l.last_status === 'failed'
        return (
          <Row key={`${l.pipeline}-${l.name}`} href="/pipelines" last={i === runs.length - 1}>
            <Name sub={l.last_rows_out != null ? `${l.last_rows_out.toLocaleString()} rows` : null}>
              {l.pipeline} / {l.name}
            </Name>
            <span style={{ fontSize: 11.5, color: 'var(--muted)', flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
              {when(l.last_run)}
            </span>
            <Badge variant={failed ? 'red' : l.last_status === 'running' ? 'amber' : 'green'}
                   style={{ textTransform: 'none', flexShrink: 0 }}>
              {failed ? 'Failed' : l.last_status === 'running' ? 'Running' : 'OK'}
            </Badge>
          </Row>
        )
      })}
    </Panel>
  )
}

// ── Empty project ──────────────────────────────────────────────────────────

function StartHere() {
  return (
    <Panel>
      <div style={{ padding: '18px 20px', fontSize: 13.5, color: 'var(--text-2)', lineHeight: 1.6 }}>
        <div style={{ fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>This project is empty</div>
        Write a transform that lands clean tables, declare a model over them, then
        point a report at the model.{' '}
        <Link to="/getting-started" style={{ color: 'var(--accent-text)', textDecoration: 'none' }}>Get started →</Link>
        {' · '}
        <Link to="/workflow" style={{ color: 'var(--accent-text)', textDecoration: 'none' }}>How the three phases fit →</Link>
      </div>
    </Panel>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function Home() {
  const { data: models,    isLoading: lm } = useModels()
  const { data: reports,   isLoading: lr } = useReports()
  const { data: pipelines, isLoading: lp } = usePipelines()
  const { data: desk,      isLoading: ld } = useDesk()

  const items = attentionItems(desk, pipelines)
  const nRep = (reports || []).length
  const empty = !lm && !lr && nRep === 0 && (models || []).length === 0
  const hasRefreshes = (pipelines || []).some(p => (p.layers || []).length)

  const openName = desk?.open?.report
  const summary = ld || lp
    ? null
    : items.length
      ? `${items.length} ${items.length === 1 ? 'thing needs' : 'things need'} you.`
      : 'Nothing needs you.'

  return (
    <div className="fade-in" style={{ maxWidth: 880 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 16, flexWrap: 'wrap', marginBottom: 28 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 6 }}>
            {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
          </div>
          <h1 className="home-thesis" style={{ fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.15, margin: '0 0 6px', color: 'var(--text)' }}>
            Desk
          </h1>
          <div style={{ fontSize: 14, color: 'var(--text-2)', minHeight: 20 }}>
            {summary ?? <Skeleton width={200} height={14} />}
            {!lr && nRep > 0 && (
              <span style={{ color: 'var(--muted)' }}> {nRep} {nRep === 1 ? 'report' : 'reports'}.</span>
            )}
          </div>
        </div>
        {openName && (
          <Link to={reportHref(openName)} style={{
            padding: '9px 16px', borderRadius: 'var(--radius-sm)',
            background: 'var(--blue)', color: '#fff', fontWeight: 600, fontSize: 13,
            textDecoration: 'none', whiteSpace: 'nowrap',
          }}>
            Open latest report
          </Link>
        )}
      </div>

      {empty ? (
        <StartHere />
      ) : (
        <>
          <section style={{ marginBottom: 28 }}>
            <SectionHead title="Needs attention" count={items.length || null} />
            <NeedsAttention items={items} loading={ld || lp} />
          </section>

          <section style={{ marginBottom: 28 }}>
            <SectionHead title="Reports" action={{ href: '/reports', label: 'All reports' }} />
            <ReportsList reports={reports} desk={desk} loading={lr || ld} />
          </section>

          {hasRefreshes && (
            <section>
              <SectionHead title="Recent data refreshes" action={{ href: '/pipelines', label: 'All refreshes' }} />
              <Refreshes pipelines={pipelines} loading={lp} />
            </section>
          )}
        </>
      )}
    </div>
  )
}
