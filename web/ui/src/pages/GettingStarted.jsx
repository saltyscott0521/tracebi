import { Link } from 'react-router-dom'
import { useGuides } from '../api'
import { PageTitle, PageSub, CodeBlock } from '../components/Shared'

const STEPS = [
  {
    n: 1,
    title: 'Install and scaffold',
    desc: 'One install, then a project with the three folders the workflow uses.',
    code: `pip install "tracebi[analyst]"
tracebi init`,
  },
  {
    n: 2,
    title: 'Sink the warehouse',
    desc: 'Phase ① is ordinary pandas in transforms/. It ends by writing named tables. The sink contract checks what landed.',
    code: `tracebi new-transform "holdings"
tracebi run-transform holdings`,
  },
  {
    n: 3,
    title: 'Declare the contract',
    desc: 'Phase ② is a DataModel in models/: grain, keys, measures. A reviewer reads it without opening the pandas above it.',
    code: `tracebi new-model "Portfolio"`,
  },
  {
    n: 4,
    title: 'Build the report and verify it',
    desc: 'Phase ③ is a package in reports/. The build fills every figure from a query. verify re-runs those queries.',
    code: `tracebi new-report "portfolio"
tracebi dev portfolio
tracebi report build portfolio
tracebi verify output/portfolio.html.manifest.json`,
  },
  {
    n: 5,
    title: 'Open the desk',
    desc: 'The published file is the thing a person approves. The Reports page opens it; the Contract page reads the model.',
    code: `python -m tracebi.web.run
# → http://localhost:8000`,
  },
]

const LINK_STYLE = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '7px 14px', borderRadius: 7, fontSize: 12, fontWeight: 600,
  background: 'var(--blue-lt)', color: 'var(--accent-text)',
  border: '1px solid var(--blue-br)', textDecoration: 'none',
}

// ── Guides (markdown from docs/, served by /api/docs) ─────────────────────────

function Guides() {
  // The docs live on their own page now — the vault outgrew a flat row of
  // buttons the moment docs/ became a tree. This is the pointer to it.
  const { data: guides, isLoading } = useGuides()
  if (isLoading || !guides?.length) return null
  return (
    <div style={{ marginBottom: 40 }}>
      <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)', marginBottom: 4 }}>Docs</div>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 14 }}>
        The full handbook — concepts, guides and reference, versioned in <code>docs/</code>.
      </p>
      <Link to="/handbook" style={{ ...LINK_STYLE, fontSize: 12.5 }}>
        ☰ Browse the docs ({guides.length} pages)
      </Link>
    </div>
  )
}

export default function GettingStarted() {
  return (
    <div>
      <PageTitle>Getting started</PageTitle>
      <PageSub>Five steps from install to your first lineage-tracked report.</PageSub>

      <Guides />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 40 }}>
        {STEPS.map(s => (
          <div key={s.n} style={{
            display: 'flex', gap: 18, alignItems: 'flex-start',
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '20px 24px',
          }}>
            <div style={{
              width: 34, height: 34, borderRadius: 8, flexShrink: 0, marginTop: 1,
              background: 'linear-gradient(135deg, rgba(37,99,235,.12), rgba(124,58,237,.12))',
              border: '1px solid rgba(124,58,237,.22)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 800, color: '#6d28d9',
            }}>{s.n}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 5 }}>{s.title}</div>
              <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 12 }}>{s.desc}</p>
              <CodeBlock>{s.code}</CodeBlock>
            </div>
          </div>
        ))}
      </div>

      <div style={{
        background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
        borderRadius: 12, padding: '20px 24px',
      }}>
        <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text)', marginBottom: 12 }}>Go deeper</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Link to="/reports" style={LINK_STYLE}>▤ Report</Link>
          <Link to="/models" style={LINK_STYLE}>⬡ Contract</Link>
          <Link to="/workflow" style={LINK_STYLE}>↝ Workflow</Link>
          <Link to="/connectors" style={LINK_STYLE}>⇌ Connectors</Link>
          <Link to="/pipelines" style={LINK_STYLE}>↻ Refresh</Link>
        </div>
      </div>
    </div>
  )
}
