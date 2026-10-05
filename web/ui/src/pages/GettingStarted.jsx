import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useGuides } from '../api'
import { PageTitle, PageSub, CodeBlock } from '../components/Shared'
import { PAGES } from '../nav'
import { ThreePhases } from '../components/ThreePhases'

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
    title: 'Declare the data model',
    desc: 'Phase ② is a DataModel in models/: grain, keys, measures. A reviewer reads it without opening the pandas above it.',
    code: `tracebi new-model "Portfolio"`,
  },
  {
    n: 4,
    title: 'Build the report and verify it',
    desc: 'Phase ③ is a package in reports/. tracebi dev opens it in this app with Build mode on. The build fills every figure from a query. verify re-runs those queries.',
    code: `tracebi new-report "portfolio"
tracebi dev portfolio
tracebi report build portfolio
tracebi verify output/portfolio.html.manifest.json`,
  },
  {
    n: 5,
    title: 'Open the desk',
    desc: 'The published file is the thing a person approves. Open a model for its reports; the Reports page can also open them from the library.',
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
      <h2 className="section-title">Docs</h2>
      <p style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 14 }}>
        The full handbook — concepts, guides and reference, versioned in <code>docs/</code>.
      </p>
      <Link to="/handbook" style={{ ...LINK_STYLE, fontSize: 12.5 }}>
        ☰ Browse the docs ({guides.length} pages)
      </Link>
    </div>
  )
}

// Where each page's content comes from, in the project.
const FOLDER = {
  model: 'models/<model>.py',
  explore: 'a question, not a file',
  refresh: 'pipelines/<model>.py → transforms/',
  reports: 'reports/<model>/',
  sources: 'the connector a model declares',
  runs: 'the run history',
}

// How the pieces fit: pick a model, and every page is about it.
function HowItFits() {
  return (
    <div style={{ marginBottom: 36 }}>
      <h2 className="section-title">How the app fits together</h2>
      <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, margin: '0 0 14px', maxWidth: '74ch' }}>
        Everything belongs to a <strong>model</strong>. Pick one at the top of the sidebar and
        every page below it is about that model: its data model, its questions, its refresh,
        its reports, where its data is kept, and what ran. Pick “All models” to see everything,
        with each row naming its model.
      </p>
      <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
        {PAGES.map(p => (
          <Link key={p.key} to={p.all} style={{
            textDecoration: 'none', background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '14px 16px', display: 'block',
          }}>
            <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', margin: '0 0 4px' }}>{p.label}</div>
            <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>{p.sub}</div>
            <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 8, fontFamily: 'var(--font-mono)' }}>{FOLDER[p.key]}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}

export default function GettingStarted() {
  // /workflow (now a section here) and other links land on a section by hash.
  const { hash } = useLocation()
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [hash])
  return (
    <div>
      <PageTitle>Get started</PageTitle>
      <PageSub>How TraceBi fits together, then five steps from install to your first report with a receipt.</PageSub>

      <HowItFits />

      <section id="phases" style={{ marginBottom: 40 }}>
        <h2 className="section-title">The three phases</h2>
        <p className="section-sub">
          From a messy source to a served report. Each phase has its own folder and its own pace,
          and hands the next a frozen artifact, so slow analysis and fast reporting never block
          each other.
        </p>
        <ThreePhases />
      </section>

      <h2 className="section-title" id="steps">Five steps</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 40 }}>
        {STEPS.map(s => (
          <div key={s.n} style={{
            display: 'flex', gap: 18, alignItems: 'flex-start',
            background: 'var(--card)', border: '1px solid var(--border)',
            borderRadius: 12, padding: '20px 24px',
          }}>
            <div style={{
              width: 34, height: 34, borderRadius: 8, flexShrink: 0, marginTop: 1,
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 14, fontWeight: 600, color: 'var(--text)',
            }}>{s.n}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', marginBottom: 5 }}>{s.title}</div>
              <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, marginBottom: 12 }}>{s.desc}</p>
              <CodeBlock>{s.code}</CodeBlock>
            </div>
          </div>
        ))}
      </div>

      <Guides />

      <div style={{
        background: 'var(--blue-lt)', border: '1px solid var(--blue-br)',
        borderRadius: 12, padding: '20px 24px',
      }}>
        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', marginBottom: 12 }}>Go deeper</div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <Link to="/models" style={LINK_STYLE}>Models</Link>
          <Link to="/reports" style={LINK_STYLE}>Reports</Link>
        </div>
      </div>
    </div>
  )
}
