import { Link } from 'react-router-dom'
import { useConnectors, useModels, useReports, usePipelines } from '../api'
import { Skeleton } from '../components/Shared'

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

function StatCard({ label, value, icon, color, href, loading }) {
  const inner = (
    <div style={{
      background: 'var(--card)', border: '1px solid var(--border)',
      borderRadius: 14, padding: '20px 22px',
      display: 'flex', alignItems: 'flex-start', gap: 14,
    }} className="card-hover card-accent">
      <div style={{
        width: 40, height: 40, borderRadius: 10, flexShrink: 0,
        background: `${color}18`, border: `1px solid ${color}30`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color,
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 26, fontWeight: 800, color: 'var(--text)', lineHeight: 1.1 }}>
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

// ── Nav card ──────────────────────────────────────────────────────────────────

function NavCard({ href, title, desc, icon, color, badge }) {
  return (
    <Link to={href} style={{ textDecoration: 'none' }}>
      <div style={{
        background: 'var(--card)', border: '1px solid var(--border)',
        borderRadius: 14, padding: '18px 20px', height: '100%',
      }} className="card-hover">
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, flexShrink: 0,
            background: `${color}18`, border: `1px solid ${color}28`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color,
          }}>
            {icon}
          </div>
          <span style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)' }}>{title}</span>
          {badge != null && (
            <span style={{
              marginLeft: 'auto', fontSize: 11, fontWeight: 700,
              background: `${color}18`, color, border: `1px solid ${color}28`,
              padding: '1px 8px', borderRadius: 20,
            }}>{badge}</span>
          )}
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55, margin: 0 }}>{desc}</p>
      </div>
    </Link>
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
            <span style={{ flex: 1, fontFamily: 'Cascadia Code, Fira Code, monospace', fontSize: 12 }}>
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
  compass: <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-11.707a1 1 0 00-1.111-.206l-4 1.714a1 1 0 00-.525.525l-1.714 4a1 1 0 001.317 1.317l4-1.714a1 1 0 00.525-.525l1.714-4a1 1 0 00-.206-1.111zM10 11a1 1 0 110-2 1 1 0 010 2z" clipRule="evenodd" /></svg>,
  code: <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M12.316 3.051a1 1 0 01.633 1.265l-4 12a1 1 0 11-1.898-.632l4-12a1 1 0 011.265-.633zM5.707 6.293a1 1 0 010 1.414L3.414 10l2.293 2.293a1 1 0 11-1.414 1.414l-3-3a1 1 0 010-1.414l3-3a1 1 0 011.414 0zm8.586 0a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 11-1.414-1.414L16.586 10l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" /></svg>,
}

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

  return (
    <div className="fade-in">
      {/* Header */}
      <div style={{ marginBottom: 36 }}>
        <h1 style={{ fontSize: 26, fontWeight: 800, color: 'var(--text)', marginBottom: 4 }}>
          {greeting()}
        </h1>
        <p style={{ fontSize: 14, color: 'var(--muted)' }}>{formatDate()}</p>
      </div>

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 40 }}>
        <StatCard label="Connectors" value={nConn} icon={I.db}      color="#2563eb" href="/connectors" loading={lc} />
        <StatCard label="Models"     value={nMod}  icon={I.cube}    color="#7c3aed" href="/models"     loading={lm} />
        <StatCard label="Reports"    value={nRep}  icon={I.doc}     color="#db2777" href="/reports"    loading={lr} />
        <StatCard label="Pipelines"  value={nPipe} icon={I.bolt}    color="#d97706" href="/pipelines"  loading={lp} />
      </div>

      {/* Two-column layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 32, alignItems: 'start' }}>

        {/* Left */}
        <div>
          <SH title="Navigate" />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 32 }}>
            <NavCard href="/explore"  title="Explore"   icon={I.compass} color="#0891b2" badge={nMod || undefined}
              desc="Run star-schema queries across your models. Pick measures, dimensions, and filters." />
            <NavCard href="/models"   title="Models"    icon={I.cube}    color="#7c3aed" badge={nMod || undefined}
              desc="Browse DataModel tables, preview rows, inspect relationships, and view the ER diagram." />
            <NavCard href="/reports"  title="Reports"   icon={I.doc}     color="#db2777" badge={nRep || undefined}
              desc="Run registered reports and download HTML or Excel outputs with lineage manifests." />
            <NavCard href="/requests" title="Requests"  icon={I.code}    color="#6d28d9"
              desc="Execute ad-hoc Python scripts with custom parameters and live lineage graphs." />
          </div>

          <SH title="Recent pipeline activity" action={{ href: '/pipelines', label: 'View all' }} />
          <div style={{
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 14, padding: '8px 4px',
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
          <SH title="Quick start" />
          <div style={{
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 14, padding: '20px 22px', marginBottom: 20,
          }}>
            <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.65, marginBottom: 16 }}>
              TraceBi is a code-first analytics framework. Every transform is immutable and lineage-tracked automatically.
            </p>
            {[
              'Define a connector + DataModel in your app module',
              'Load, filter, transform — each step appends a LineageNode',
              'Run queries via .query() or the Explore page',
              'Build reports and render to HTML or Excel',
            ].map((text, n) => (
              <div key={n} style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 10 }}>
                <span style={{
                  width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                  background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
                  color: 'var(--accent-text)', fontSize: 11, fontWeight: 800,
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
                borderRadius: 14, overflow: 'hidden',
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
                    <span style={{ flex: 1, fontFamily: 'Cascadia Code, Fira Code, monospace', fontSize: 12, color: 'var(--text)' }}>
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
