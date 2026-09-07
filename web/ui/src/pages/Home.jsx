import { Link } from 'react-router-dom'
import { useConnectors, useModels, useReports, usePipelines } from '../api'
import { Skeleton, Badge } from '../components/Shared'
import WorkflowDiagram from '../components/WorkflowDiagram'

// ── Greeting ─────────────────────────────────────────────────────────────────

function greeting() {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function formatDate() {
  return new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, icon, href, loading }) {
  const inner = (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: '18px 20px',
      display: 'flex', alignItems: 'flex-start', gap: 14,
    }} className="card-hover">
      <div style={{
        width: 36, height: 36, borderRadius: 8, flexShrink: 0,
        background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: 'var(--accent-text)',
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 24, fontWeight: 700, color: 'var(--text)', lineHeight: 1.1, fontVariantNumeric: 'tabular-nums' }}>
          {loading ? <Skeleton width={36} height={24} /> : value}
        </div>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>{label}</div>
      </div>
    </div>
  )
  return href
    ? <Link to={href} style={{ textDecoration: 'none', display: 'block' }}>{inner}</Link>
    : inner
}

// ── Trust ledger ────────────────────────────────────────────────────────────
// Each registered report and whether it renders a verifiable artifact — the
// receipt state of the whole deployment, at rest, with no run. The `kind`
// field comes straight from the reports API (see registry.list_reports).

function LedgerRow({ report, last }) {
  const verifiable = report.kind === 'artifact'
  return (
    <Link
      to={`/reports?r=${encodeURIComponent(report.name)}`}
      className="list-item-hover"
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '11px 16px', textDecoration: 'none',
        borderBottom: last ? 'none' : '1px solid var(--border)',
      }}
    >
      <span style={{
        width: 30, height: 30, borderRadius: 8, flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: verifiable ? 'var(--green-lt)' : 'var(--surface-2)',
        border: `1px solid ${verifiable ? 'var(--green-br)' : 'var(--border)'}`,
        color: verifiable ? 'var(--green-text)' : 'var(--muted)',
      }}>
        {I.receipt}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{
          display: 'block', fontFamily: "'IBM Plex Mono', monospace", fontSize: 12.5,
          color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>{report.name}</span>
        {report.description && (
          <span style={{
            display: 'block', fontSize: 11.5, color: 'var(--muted)', marginTop: 1,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{report.description}</span>
        )}
      </span>
      <Badge
        variant={verifiable ? 'green' : 'gray'}
        style={{ textTransform: 'none', flexShrink: 0 }}
        title={verifiable
          ? 'Renders a self-contained artifact whose figures are fingerprinted — re-checkable with verify --file'
          : 'A code-factory report — rendered, but not a byte-verifiable artifact'}
      >
        {verifiable ? 'verifiable' : 'python-derived'}
      </Badge>
    </Link>
  )
}

function TrustLedger({ reports, loading }) {
  if (loading) {
    return (
      <div style={{ padding: '12px 16px' }}>
        <Skeleton height={13} style={{ marginBottom: 10 }} />
        <Skeleton width="72%" height={13} />
      </div>
    )
  }
  if (!reports?.length) {
    return (
      <div style={{ color: 'var(--muted)', fontSize: 13, padding: '16px 16px', lineHeight: 1.6 }}>
        No reports registered yet. Point a spec in <code>reports/</code> at a model,
        or scaffold one with <code>tracebi new-report</code> — each renders a
        verifiable artifact you can re-check offline.
      </div>
    )
  }
  return (
    <div>
      {reports.map((r, i) => (
        <LedgerRow key={r.name} report={r} last={i === reports.length - 1} />
      ))}
    </div>
  )
}

// ── Recent pipeline runs ───────────────────────────────────────────────────────

const STATUS_COLOR = { success: '#16a34a', failed: '#dc2626', running: '#d97706', never: '#94a3b8' }
const STATUS_LABEL = { success: 'OK', failed: 'ERR', running: '…', never: '—' }

function PipelineActivity({ pipelines }) {
  const layers = (pipelines || []).flatMap(p =>
    (p.layers || []).map(l => ({ ...l, pipeline: p.pipeline }))
  )

  const active = layers
    .filter(l => l.last_run)
    .sort((a, b) => new Date(b.last_run) - new Date(a.last_run))
    .slice(0, 6)

  if (!active.length) {
    return (
      <div style={{ color: 'var(--muted)', fontSize: 13, padding: '16px 12px' }}>
        No runs yet.{' '}
        <Link to="/pipelines" style={{ color: 'var(--accent-text)' }}>Run a pipeline</Link>{' '}
        to see activity here.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      {active.map((l, i) => {
        const status = l.last_status || 'never'
        const color = STATUS_COLOR[status] ?? STATUS_COLOR.never
        const when = l.last_run
          ? new Date(l.last_run).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
          : '—'
        return (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '9px 12px', borderRadius: 8, fontSize: 13,
            background: i % 2 === 0 ? 'var(--surface)' : 'transparent',
          }}>
            <span style={{
              width: 28, textAlign: 'center', fontSize: 10, fontWeight: 700,
              color, background: `${color}18`, border: `1px solid ${color}30`,
              borderRadius: 5, padding: '2px 0', flexShrink: 0,
            }}>{STATUS_LABEL[status]}</span>
            <span style={{ flex: 1, fontFamily: 'IBM Plex Mono, Cascadia Code, monospace', fontSize: 12 }}>
              <span style={{ color: 'var(--text)' }}>{l.pipeline}</span>
              <span style={{ color: 'var(--muted)' }}> / {l.name}</span>
            </span>
            {l.last_rows_out != null && (
              <span style={{ color: 'var(--muted)', fontSize: 11 }}>
                {l.last_rows_out.toLocaleString()} rows
              </span>
            )}
            <span style={{ color: 'var(--muted)', fontSize: 11, flexShrink: 0 }}>{when}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Section header ────────────────────────────────────────────────────────────

function SH({ title, action }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14 }}>
      <h2 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', margin: 0 }}>{title}</h2>
      {action && (
        <Link to={action.href} style={{ fontSize: 12, color: 'var(--accent-text)', textDecoration: 'none' }}>
          {action.label} →
        </Link>
      )}
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────

const I = {
  db: <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path d="M5 4a1 1 0 00-2 0v7.268a2 2 0 000 3.464V16a1 1 0 102 0v-1.268a2 2 0 000-3.464V4zM11 4a1 1 0 10-2 0v1.268a2 2 0 000 3.464V16a1 1 0 102 0V8.732a2 2 0 000-3.464V4zM16 3a1 1 0 011 1v7.268a2 2 0 010 3.464V16a1 1 0 11-2 0v-1.268a2 2 0 010-3.464V4a1 1 0 011-1z" /></svg>,
  cube: <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path d="M3 12v3c0 1.657 3.134 3 7 3s7-1.343 7-3v-3c0 1.657-3.134 3-7 3s-7-1.343-7-3z" /><path d="M3 7v3c0 1.657 3.134 3 7 3s7-1.343 7-3V7c0 1.657-3.134 3-7 3S3 8.657 3 7z" /><path d="M17 5c0 1.657-3.134 3-7 3S3 6.657 3 5s3.134-3 7-3 7 1.343 7 3z" /></svg>,
  doc: <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" /></svg>,
  bolt: <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd" /></svg>,
  receipt: <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M5 2a1 1 0 00-1 1v14l2-1 2 1 2-1 2 1 2-1 2 1V3a1 1 0 00-1-1H5zm2.5 4a.75.75 0 000 1.5h5a.75.75 0 000-1.5h-5zm0 3a.75.75 0 000 1.5h5a.75.75 0 000-1.5h-5zm0 3a.75.75 0 000 1.5h3a.75.75 0 000-1.5h-3z" clipRule="evenodd" /></svg>,
}

// ── Trust "how it works" bullets ──────────────────────────────────────────────

const RECEIPT_BULLETS = [
  ['Stamped queries', 'Every figure is a live query against the model — the result carries the resolved query, its full lineage chain, and a SHA-256 fingerprint of the bytes.'],
  ['Validation before execution', 'Report specs are checked against the model contract first — an invalid spec is refused, never rendered.'],
  ['The verify loop', 'tracebi verify re-runs every query a manifest recorded and classifies the outcome — reproduces, source drift, model changed, or unexplained; verify --file re-checks a shared report offline, no model needed.'],
  ['Agent gateway', 'Eleven MCP tools let agents discover, query, author, render, fetch, and verify against the semantic contract — read-and-compute only, never the warehouse.'],
]

const QUICK_START = [
  'Transform: pull queries and run Python in transforms/ — sink the result to the warehouse',
  'Model: declare a star schema over the warehouse in models/ — grain, keys, measures',
  'Dashboard: point a spec in reports/ at the model — KPI cards, charts, tables',
  'Serve: every figure is a live query; edit the spec and re-render in milliseconds',
  'Re-run any output later: tracebi verify re-runs the recorded queries and classifies the result',
]

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const { data: connectors, isLoading: lc } = useConnectors()
  const { data: models,     isLoading: lm } = useModels()
  const { data: reports,    isLoading: lr } = useReports()
  const { data: pipelines,  isLoading: lp } = usePipelines()

  const nConn  = (connectors || []).length
  const nMod   = (models     || []).length
  const nRep   = (reports    || []).length
  const nPipe  = (pipelines  || []).length

  const verifiable = (reports || []).filter(r => r.kind === 'artifact').length
  const trustLine =
    nRep === 0
      ? 'Register a report and every figure drawn through the model arrives with a receipt.'
      : verifiable === 0
        ? 'None of the registered reports render a verifiable artifact yet.'
        : verifiable === nRep
          ? 'Every registered report renders a verifiable artifact.'
          : `${verifiable} of ${nRep} reports render${verifiable === 1 ? 's' : ''} a verifiable artifact.`

  return (
    <div className="fade-in">
      {/* Workspace header — product first, verify available but not the lead CTA */}
      <div className="home-hero" style={{ marginBottom: 32 }}>
        <div className="home-hero-grid">
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 8, fontWeight: 500 }}>
              {greeting()} · {formatDate()}
            </div>
            <h1 className="home-thesis" style={{
              fontWeight: 700, letterSpacing: '-0.03em', lineHeight: 1.15, marginBottom: 10,
              color: 'var(--text)',
            }}>
              Workspace
            </h1>
            <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.55, maxWidth: '56ch', margin: 0 }}>
              Models, reports, and pipelines registered in this deployment.
              Figures drawn through the model carry a fingerprint you can re-check later.
            </p>
            <div style={{ marginTop: 14, minHeight: 18 }}>
              {lr
                ? <Skeleton width={240} height={13} />
                : (
                  <span style={{ fontSize: 13, color: 'var(--muted)' }}>
                    {trustLine}
                  </span>
                )}
            </div>
          </div>

          <div className="home-hero-cta">
            <Link to="/reports" style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              padding: '9px 16px', borderRadius: 'var(--radius-sm)',
              background: 'var(--blue)', color: '#fff', fontWeight: 600, fontSize: 13,
              textDecoration: 'none', whiteSpace: 'nowrap',
            }}>
              Browse reports
            </Link>
            <Link to="/getting-started" style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              padding: '9px 16px', borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)', background: 'var(--card)',
              color: 'var(--text-2)', fontWeight: 500, fontSize: 13,
              textDecoration: 'none', whiteSpace: 'nowrap',
            }}>
              Get started
            </Link>
          </div>
        </div>
      </div>

      {/* Workflow — the framework, as a flowchart */}
      <div style={{ marginBottom: 40 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
          <h2 style={{ fontSize: 15, fontWeight: 800, color: 'var(--text)', margin: 0 }}>
            From messy analysis to a reportable model
          </h2>
          <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>
            three phases, three folders, frozen between each
          </span>
          <Link to="/workflow" style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--accent-text)', textDecoration: 'none' }}>
            Walk through it →
          </Link>
        </div>
        <WorkflowDiagram />
      </div>

      {/* Stats row */}
      <div className="grid-4" style={{ marginBottom: 36 }}>
        <StatCard label="Connectors" value={nConn} icon={I.db}   href="/connectors" loading={lc} />
        <StatCard label="Models"     value={nMod}  icon={I.cube} href="/models"     loading={lm} />
        <StatCard label="Reports"    value={nRep}  icon={I.doc}  href="/reports"    loading={lr} />
        <StatCard label="Pipelines"  value={nPipe} icon={I.bolt} href="/pipelines"  loading={lp} />
      </div>

      {/* Two-column layout */}
      <div className="home-main-grid">

        {/* Left */}
        <div>
          <SH title="Reports & their receipts" action={{ href: '/reports', label: 'Open reports' }} />
          <div style={{
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', overflow: 'hidden', marginBottom: 32,
          }}>
            <TrustLedger reports={reports} loading={lr} />
          </div>

          <SH title="Recent pipeline activity" action={{ href: '/pipelines', label: 'View all' }} />
          <div style={{
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '8px 4px',
          }}>
            {lp
              ? <div style={{ padding: '12px 12px' }}>
                  <Skeleton height={13} style={{ marginBottom: 10 }} />
                  <Skeleton width="70%" height={13} />
                </div>
              : <PipelineActivity pipelines={pipelines} />
            }
          </div>
        </div>

        {/* Right */}
        <div>
          <SH title="How the receipt works" />
          <div style={{
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '20px 22px', marginBottom: 20,
          }}>
            {RECEIPT_BULLETS.map(([title, desc], i) => (
              <div key={title} style={{ marginBottom: i < RECEIPT_BULLETS.length - 1 ? 14 : 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>{title}</div>
                <div style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55 }}>{desc}</div>
              </div>
            ))}
          </div>

          <SH title="Quick start" />
          <div style={{
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', padding: '20px 22px', marginBottom: 20,
          }}>
            <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.65, marginBottom: 16 }}>
              Take data from messy to reportable in three phases — write the analysis, freeze it into a model, dashboard the model. Every figure on the page stays a live query.
            </p>
            {QUICK_START.map((text, n) => (
              <div key={n} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 10 }}>
                <span style={{
                  width: 22, height: 22, borderRadius: 6, flexShrink: 0,
                  background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
                  color: 'var(--accent-text)', fontSize: 11, fontWeight: 700,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>{n + 1}</span>
                <span style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5, paddingTop: 2 }}>{text}</span>
              </div>
            ))}
            <Link to="/getting-started" style={{
              display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 8,
              fontSize: 13, fontWeight: 600, color: 'var(--accent-text)', textDecoration: 'none',
            }}>
              Full walkthrough →
            </Link>
          </div>

          {!lc && connectors?.length > 0 && (
            <>
              <SH title="Connectors" action={{ href: '/connectors', label: 'Details' }} />
              <div style={{
                background: 'var(--card)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius)', overflow: 'hidden',
              }}>
                {connectors.slice(0, 6).map((c, i) => (
                  <div key={c.name} style={{
                    display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
                    borderBottom: i < connectors.length - 1 && i < 5 ? '1px solid var(--border)' : 'none',
                    fontSize: 13,
                  }}>
                    <span style={{
                      width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                      background: c.connected === false ? '#dc2626' : '#22c55e',
                    }} />
                    <span style={{ flex: 1, fontFamily: 'IBM Plex Mono, Cascadia Code, monospace', fontSize: 12, color: 'var(--text)' }}>
                      {c.name}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>{c.type}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
